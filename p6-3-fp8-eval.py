# SPDX-License-Identifier: Apache-2.0
"""P6-3 GPU evaluation driver (not for upstream): FP8 backbone weights and FP8 KV.

Run mode (from the repo root), one pipeline start per variant:

    PYTHONPATH=. python p6-3-fp8-eval.py run --out-dir R/bf16
    PYTHONPATH=. python p6-3-fp8-eval.py run --out-dir R/fp8-w \
        --stage-args '--lm.engine.quantization fp8'
    PYTHONPATH=. python p6-3-fp8-eval.py run --out-dir R/bf16-cap \
        --phases capacity --capacity-requests N

Phases, all against one running pipeline, every request streamed:
  quality   each SeedTTS-EN clip x seed once with one voice, at most
            --quality-concurrency requests in flight; every reply is saved
  greedy    each reference recording once at temperature 0, one at a time
  long      one recording of at least --long-seconds, once per --long-seeds,
            all in flight together; it runs past the attention window
  speed-N   N unseeded requests together, --speed-repeats times per N
  capacity  --capacity-requests unseeded long requests submitted together

Score mode, after all runs, with an SGLang-Omni ASR server on --asr-port:

    PYTHONPATH=. python p6-3-fp8-eval.py score R/bf16 R/fp8-w --asr-port 8100

Compare mode, the first directory is the baseline:

    PYTHONPATH=. python p6-3-fp8-eval.py compare R/bf16 R/bf16-again R/fp8-w

Greedy parity does not hold under FP8, so quality is a distribution
comparison. Replies are paired by clip, voice and seed, and compare prints
a bootstrap 95% interval for each paired difference that resamples whole
clips. A second bf16 run (bf16-again) gives the noise floor: batched kernels
round differently, and one changed token changes the rest of a sampled reply.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import itertools
import json
import os
import shlex
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict, get_args

import numpy as np
import soundfile
import torch
import torchaudio
from huggingface_hub import HfApi
from numpy.typing import NDArray

from benchmarks.dataset.prepare import SEEDTTS_DATASET_ID, SEEDTTS_DATASET_REVISION
from benchmarks.dataset.seedtts import load_seedtts_samples
from benchmarks.metrics.utmos import UTMOSScorer
from benchmarks.metrics.wer import SampleOutput
from benchmarks.tasks.asr import (
    QWEN3_ASR_MODEL_PATH,
    apply_wer,
    load_router_asr,
    transcribe,
)
from sglang_omni.client.client import Client
from sglang_omni.client.types import GenerateRequest, SamplingParams
from sglang_omni.config.manager import ConfigManager
from sglang_omni.models.personaplex.architecture import SAMPLE_RATE, SAMPLES_PER_FRAME
from sglang_omni.models.personaplex.config import PersonaPlexPipelineConfig
from sglang_omni.pipeline.mp_runner import MultiProcessPipelineRunner
from sglang_omni.utils.checkpoint import resolve_checkpoint

Phase = Literal["quality", "greedy", "long", "speed", "capacity"]
REFERENCE_RECORDINGS = (
    "tests/data/query_to_cars.wav",
    "tests/data/query_to_draw.wav",
)
REPLY_VOICE = "NATF2"
SPEED_VOICE = "NATF0"
WARMUP_VOICE = "VARM4"
# Note (Jinjie Guo): Silence after each clip of the long recording lets the agent
# answer it.
SILENCE_AFTER_CLIP_S = 4.0
WINDOW_S = 60.0
FRAME_MS = 1000 * SAMPLES_PER_FRAME / SAMPLE_RATE
# Note (Jinjie Guo): benchmarks.metrics.utmos downloads utmos.jit from this repo.
UTMOS_REPO_ID = "balacoon/utmos"
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 0


@dataclass(frozen=True, kw_only=True)
class Job:
    request_id: str
    recording: Path
    voice: str
    seed: int | None
    greedy: bool


class ReplyRecord(TypedDict):
    request_id: str
    recording: str
    voice: str
    seed: int | None
    text: str
    ttfa_s: float
    latency_s: float
    audio_s: float
    chunk_gaps_s: list[float]
    pause_count: int
    pause_s: float


class SavedReply(ReplyRecord):
    wav: str


class SpeedRepeat(TypedDict):
    requests: int
    wall_s: float
    audio_s_per_s: float
    ttfa_mean_s: float
    ttfa_p95_s: float
    ttfa_max_s: float
    rtf_mean: float
    chunk_gap_p95_s: float
    replies_with_pauses: int
    pause_s_total: float


class RunSummary(TypedDict):
    head_sha: str
    stage_args: list[str]
    checkpoint: str
    seedtts: str
    torch: str
    cuda: str | None
    gpu: str
    startup_s: float
    quality: list[SavedReply]
    greedy: list[SavedReply]
    long: list[SavedReply]
    speed: dict[str, list[SpeedRepeat]]
    capacity: list[SpeedRepeat]


class ReplyScore(TypedDict):
    utmos: float
    asr_text: str
    has_no_text: bool
    wer: float
    reference_words: int
    word_errors: int


class WindowScore(TypedDict):
    utmos: float
    asr_words: int


class LongScore(TypedDict):
    windows: list[WindowScore]
    asr_text: str
    reference_words: int
    word_errors: int


class ScoreSources(TypedDict):
    asr_model: str
    utmos: str


class RunScores(TypedDict):
    sources: ScoreSources
    quality: dict[str, ReplyScore]
    long: dict[str, LongScore]


@dataclass(frozen=True, kw_only=True)
class LoadedRun:
    name: str
    summary: RunSummary
    scores: RunScores


def mono_at_model_rate(path: str | Path) -> NDArray[np.float32]:
    audio, sample_rate = soundfile.read(str(path), dtype="float32", always_2d=True)
    return torchaudio.functional.resample(
        torch.from_numpy(audio[:, 0]), sample_rate, SAMPLE_RATE
    ).numpy()


def write_padded(audio: NDArray[np.float32], min_seconds: float, path: Path) -> Path:
    """Append silence so the agent answers after the caller stops."""
    missing_samples = max(0, int(np.ceil(min_seconds * SAMPLE_RATE)) - len(audio))
    soundfile.write(
        str(path),
        np.concatenate([audio, np.zeros(missing_samples, np.float32)]),
        SAMPLE_RATE,
    )
    return path


def write_long_recording(
    clips: list[NDArray[np.float32]], min_seconds: float, path: Path
) -> Path:
    """Chain clips, each followed by silence, until min_seconds is reached."""
    silence = np.zeros(int(SILENCE_AFTER_CLIP_S * SAMPLE_RATE), np.float32)
    parts: list[NDArray[np.float32]] = []
    total_samples = 0
    clip_cycle = itertools.cycle(clips)
    while total_samples < min_seconds * SAMPLE_RATE:
        clip = next(clip_cycle)
        parts.extend([clip, silence])
        total_samples += len(clip) + len(silence)
    soundfile.write(str(path), np.concatenate(parts), SAMPLE_RATE)
    return path


def speed_repeat(reply_records: list[ReplyRecord], wall_s: float) -> SpeedRepeat:
    ttfa_s = [reply_record["ttfa_s"] for reply_record in reply_records]
    chunk_gaps_s = [
        gap_s
        for reply_record in reply_records
        for gap_s in reply_record["chunk_gaps_s"]
    ]
    return SpeedRepeat(
        requests=len(reply_records),
        wall_s=wall_s,
        audio_s_per_s=sum(reply_record["audio_s"] for reply_record in reply_records)
        / wall_s,
        ttfa_mean_s=float(np.mean(ttfa_s)),
        ttfa_p95_s=float(np.percentile(ttfa_s, 95)),
        ttfa_max_s=float(np.max(ttfa_s)),
        rtf_mean=float(
            np.mean(
                [
                    reply_record["latency_s"] / reply_record["audio_s"]
                    for reply_record in reply_records
                ]
            )
        ),
        chunk_gap_p95_s=float(np.percentile(chunk_gaps_s, 95)),
        replies_with_pauses=sum(
            reply_record["pause_count"] > 0 for reply_record in reply_records
        ),
        pause_s_total=sum(reply_record["pause_s"] for reply_record in reply_records),
    )


async def run_suite(arguments: argparse.Namespace) -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("needs CUDA")
    else:
        pass
    out_dir = Path(arguments.out_dir).expanduser().resolve()
    replies_dir = out_dir / "replies"
    inputs_dir = out_dir / "inputs"
    replies_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir.mkdir(parents=True, exist_ok=True)
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    print(f"code under test: HEAD={head_sha} stage_args={arguments.stage_args!r}")

    seedtts_samples = load_seedtts_samples(
        SEEDTTS_DATASET_ID, max_samples=arguments.clips
    )
    clip_audio = [mono_at_model_rate(sample.ref_audio) for sample in seedtts_samples]
    clip_paths = [
        write_padded(
            audio,
            arguments.min_seconds,
            inputs_dir / f"clip{index:02d}_{arguments.min_seconds:g}s.wav",
        )
        for index, audio in enumerate(clip_audio)
    ]
    reference_paths = [
        write_padded(
            mono_at_model_rate(source),
            arguments.min_seconds,
            inputs_dir / f"{Path(source).stem}_{arguments.min_seconds:g}s.wav",
        )
        for source in REFERENCE_RECORDINGS
    ]
    long_path = write_long_recording(
        clip_audio,
        arguments.long_seconds,
        inputs_dir / f"long_{arguments.long_seconds:g}s.wav",
    )

    checkpoint = Path(resolve_checkpoint(arguments.checkpoint))
    config = PersonaPlexPipelineConfig(model_path=str(checkpoint))
    overrides = [
        "--lm.engine.max_running_requests",
        str(
            max(
                [
                    *arguments.concurrency_levels,
                    arguments.quality_concurrency,
                    len(arguments.long_seeds),
                    arguments.capacity_requests,
                ]
            )
        ),
        "--lm.engine.mem_fraction_static",
        str(arguments.mem_fraction),
        *shlex.split(arguments.stage_args),
    ]
    manager = ConfigManager(config)
    config = manager.merge_config(manager.parse_extra_args(overrides))
    runner = MultiProcessPipelineRunner(config)
    startup_start_s = time.perf_counter()
    await runner.start(
        timeout=float(os.environ.get("SGLANG_OMNI_STARTUP_TIMEOUT", "900"))
    )
    startup_s = time.perf_counter() - startup_start_s
    print(f"startup: {startup_s:.1f} s")
    try:
        client = Client(runner.coordinator)

        async def reply(job: Job) -> tuple[ReplyRecord, NDArray[np.int16]]:
            extra_params: dict[str, str | int | float] = {"voice": job.voice}
            if job.seed is not None:
                extra_params["seed"] = job.seed
            else:
                pass
            if job.greedy:
                extra_params["audio_temperature"] = 0.0
            else:
                pass
            request = GenerateRequest(
                model=config.name,
                prompt={"audio_path": str(job.recording)},
                sampling=(
                    SamplingParams(temperature=0.0) if job.greedy else SamplingParams()
                ),
                extra_params=extra_params,
                output_modalities=["text", "audio"],
                stream=True,
            )
            start_s = time.perf_counter()
            audio_arrivals: list[tuple[float, int]] = []
            text_parts: list[str] = []
            pcm_parts: list[bytes] = []
            async for chunk in client.completion_stream(
                request, request_id=job.request_id, audio_format="pcm"
            ):
                if chunk.audio_b64:
                    pcm = base64.b64decode(chunk.audio_b64)
                    audio_arrivals.append(
                        (time.perf_counter() - start_s, len(pcm) // 2)
                    )
                    pcm_parts.append(pcm)
                elif chunk.modality == "text" and chunk.text:
                    text_parts.append(chunk.text)
                else:
                    pass
            latency_s = time.perf_counter() - start_s
            if not audio_arrivals:
                raise RuntimeError(f"{job.request_id}: no audio")
            else:
                pass
            # Note (Jinjie Guo): Playback starts with the first chunk, as in the
            # #2554 pause table.
            playback_end_s = audio_arrivals[0][0]
            pause_count = 0
            pause_s = 0.0
            for arrival_s, chunk_samples in audio_arrivals:
                if arrival_s > playback_end_s:
                    pause_count += 1
                    pause_s += arrival_s - playback_end_s
                    playback_end_s = arrival_s
                else:
                    pass
                playback_end_s += chunk_samples / SAMPLE_RATE
            audio = np.frombuffer(b"".join(pcm_parts), dtype="<i2").copy()
            reply_record = ReplyRecord(
                request_id=job.request_id,
                recording=job.recording.name,
                voice=job.voice,
                seed=job.seed,
                text="".join(text_parts),
                ttfa_s=audio_arrivals[0][0],
                latency_s=latency_s,
                audio_s=len(audio) / SAMPLE_RATE,
                chunk_gaps_s=np.diff(
                    [arrival_s for arrival_s, _ in audio_arrivals]
                ).tolist(),
                pause_count=pause_count,
                pause_s=pause_s,
            )
            return reply_record, audio

        async def saved_reply(job: Job) -> SavedReply:
            reply_record, audio = await reply(job)
            wav_path = replies_dir / f"{job.request_id}.wav"
            soundfile.write(str(wav_path), audio, SAMPLE_RATE, subtype="PCM_16")
            return SavedReply(**reply_record, wav=str(wav_path))

        await reply(
            Job(
                request_id="warmup",
                recording=clip_paths[0],
                voice=WARMUP_VOICE,
                seed=None,
                greedy=False,
            )
        )

        quality_jobs = [
            Job(
                request_id=f"quality-{index}",
                recording=recording,
                voice=REPLY_VOICE,
                seed=seed,
                greedy=False,
            )
            for index, (recording, seed) in enumerate(
                itertools.product(clip_paths, arguments.seeds)
            )
            if "quality" in arguments.phases
        ]
        in_flight = asyncio.Semaphore(arguments.quality_concurrency)

        async def quality_reply(job: Job) -> SavedReply:
            async with in_flight:
                return await saved_reply(job)

        start_s = time.perf_counter()
        quality_replies = await asyncio.gather(
            *(quality_reply(job) for job in quality_jobs)
        )
        print(
            f"quality: {len(quality_jobs)} replies in "
            f"{time.perf_counter() - start_s:.1f} s"
        )

        greedy_replies = [
            await saved_reply(
                Job(
                    request_id=f"greedy-{recording.stem}",
                    recording=recording,
                    voice=REPLY_VOICE,
                    seed=None,
                    greedy=True,
                )
            )
            for recording in reference_paths
            if "greedy" in arguments.phases
        ]
        print(f"greedy: {len(greedy_replies)} replies")

        long_jobs = [
            Job(
                request_id=f"long-{seed}",
                recording=long_path,
                voice=REPLY_VOICE,
                seed=seed,
                greedy=False,
            )
            for seed in arguments.long_seeds
            if "long" in arguments.phases
        ]
        start_s = time.perf_counter()
        long_replies = await asyncio.gather(*(saved_reply(job) for job in long_jobs))
        print(
            f"long: {len(long_jobs)} replies in {time.perf_counter() - start_s:.1f} s"
        )

        speed: dict[str, list[SpeedRepeat]] = {}
        speed_levels = (
            arguments.concurrency_levels if "speed" in arguments.phases else []
        )
        for level in speed_levels:
            repeats: list[SpeedRepeat] = []
            for repeat in range(arguments.speed_repeats):
                jobs = [
                    Job(
                        request_id=f"speed-{level}-{repeat}-{index}",
                        recording=clip_paths[index % len(clip_paths)],
                        voice=SPEED_VOICE,
                        seed=None,
                        greedy=False,
                    )
                    for index in range(level)
                ]
                start_s = time.perf_counter()
                speed_records = [
                    reply_record
                    for reply_record, _ in await asyncio.gather(
                        *(reply(job) for job in jobs)
                    )
                ]
                repeats.append(
                    speed_repeat(speed_records, time.perf_counter() - start_s)
                )
                print(
                    f"speed-{level} #{repeat}: "
                    f"{repeats[-1]['audio_s_per_s']:.2f} audio-s/s, "
                    f"TTFA mean {repeats[-1]['ttfa_mean_s'] * 1000:.1f} ms"
                )
            speed[str(level)] = repeats

        capacity: list[SpeedRepeat] = []
        capacity_repeats = (
            arguments.capacity_repeats if "capacity" in arguments.phases else 0
        )
        for repeat in range(capacity_repeats):
            jobs = [
                Job(
                    request_id=f"capacity-{repeat}-{index}",
                    recording=long_path,
                    voice=SPEED_VOICE,
                    seed=None,
                    greedy=False,
                )
                for index in range(arguments.capacity_requests)
            ]
            start_s = time.perf_counter()
            capacity_records = [
                reply_record
                for reply_record, _ in await asyncio.gather(
                    *(reply(job) for job in jobs)
                )
            ]
            capacity.append(
                speed_repeat(capacity_records, time.perf_counter() - start_s)
            )
            print(
                f"capacity #{repeat}: {capacity[-1]['audio_s_per_s']:.2f} audio-s/s, "
                f"TTFA p95 {capacity[-1]['ttfa_p95_s']:.1f} s"
            )

        summary = RunSummary(
            head_sha=head_sha,
            stage_args=overrides,
            checkpoint=str(checkpoint),
            seedtts=f"{SEEDTTS_DATASET_ID}@{SEEDTTS_DATASET_REVISION}",
            torch=torch.__version__,
            cuda=torch.version.cuda,
            gpu=torch.cuda.get_device_name(0),
            startup_s=startup_s,
            quality=quality_replies,
            greedy=greedy_replies,
            long=long_replies,
            speed=speed,
            capacity=capacity,
        )
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        print(f"wrote {out_dir}")
    finally:
        await runner.stop()


def word_errors(wer_output: SampleOutput) -> int:
    return wer_output.substitutions + wer_output.deletions + wer_output.insertions


def score(arguments: argparse.Namespace) -> None:
    utmos = UTMOSScorer(device="cuda:0")
    asr = load_router_asr(arguments.asr_port, model_path=arguments.asr_model)
    sources = ScoreSources(
        asr_model=str(resolve_checkpoint(arguments.asr_model)),
        utmos=f"{UTMOS_REPO_ID}@{HfApi().model_info(UTMOS_REPO_ID).sha}",
    )
    window_samples = int(WINDOW_S * SAMPLE_RATE)
    for run_dir in arguments.run_dirs:
        run_root = Path(run_dir)
        summary: RunSummary = json.loads((run_root / "summary.json").read_text())

        quality_utmos = utmos.score_batch(
            [saved_reply["wav"] for saved_reply in summary["quality"]]
        )
        quality_scores: dict[str, ReplyScore] = {}
        for saved_reply, utmos_score in zip(
            summary["quality"], quality_utmos, strict=True
        ):
            asr_text = transcribe(asr, saved_reply["wav"], "en", "cuda")
            wer_output = apply_wer(
                SampleOutput(
                    sample_id=saved_reply["request_id"],
                    target_text=saved_reply["text"],
                ),
                asr_text,
                "en",
            )
            pair_key = (
                f"{saved_reply['recording']}|{saved_reply['voice']}|"
                f"{saved_reply['seed']}"
            )
            quality_scores[pair_key] = ReplyScore(
                utmos=utmos_score,
                asr_text=asr_text,
                has_no_text=not wer_output.ref_norm,
                wer=wer_output.wer,
                reference_words=len(wer_output.ref_norm.split()),
                word_errors=word_errors(wer_output),
            )

        # Note (Jinjie Guo): The decode stage sends the reply text once, at the end,
        # so WER covers the whole long reply.
        windows_dir = run_root / "windows"
        windows_dir.mkdir(exist_ok=True)
        long_scores: dict[str, LongScore] = {}
        for saved_reply in summary["long"]:
            audio, _ = soundfile.read(saved_reply["wav"], dtype="int16")
            window_wavs: list[str] = []
            for window_index, start in enumerate(range(0, len(audio), window_samples)):
                window_wav = (
                    windows_dir / f"{saved_reply['request_id']}-{window_index}.wav"
                )
                soundfile.write(
                    str(window_wav),
                    audio[start : start + window_samples],
                    SAMPLE_RATE,
                    subtype="PCM_16",
                )
                window_wavs.append(str(window_wav))
            window_utmos = utmos.score_batch(window_wavs)
            window_texts = [
                transcribe(asr, window_wav, "en", "cuda") for window_wav in window_wavs
            ]
            asr_text = " ".join(window_texts)
            wer_output = apply_wer(
                SampleOutput(
                    sample_id=saved_reply["request_id"],
                    target_text=saved_reply["text"],
                ),
                asr_text,
                "en",
            )
            long_scores[saved_reply["request_id"]] = LongScore(
                windows=[
                    WindowScore(utmos=utmos_score, asr_words=len(window_text.split()))
                    for utmos_score, window_text in zip(
                        window_utmos, window_texts, strict=True
                    )
                ],
                asr_text=asr_text,
                reference_words=len(wer_output.ref_norm.split()),
                word_errors=word_errors(wer_output),
            )

        (run_root / "scores.json").write_text(
            json.dumps(
                RunScores(sources=sources, quality=quality_scores, long=long_scores),
                indent=2,
            )
        )
        print(
            f"scored {len(quality_scores)} quality and {len(long_scores)} long "
            f"replies in {run_root}"
        )


def load_run(run_dir: str) -> LoadedRun:
    run_root = Path(run_dir)
    summary: RunSummary = json.loads((run_root / "summary.json").read_text())
    scored = bool(summary["quality"] or summary["long"])
    scores: RunScores = (
        json.loads((run_root / "scores.json").read_text())
        if scored
        else RunScores(
            sources=ScoreSources(asr_model="", utmos=""), quality={}, long={}
        )
    )
    return LoadedRun(name=run_root.name, summary=summary, scores=scores)


def clip_interval(
    differences_by_clip: dict[str, list[float]], generator: np.random.Generator
) -> tuple[float, float]:
    """Bootstrap 95% interval of the mean difference, resampling whole clips."""
    clip_sums = np.array([sum(values) for values in differences_by_clip.values()])
    clip_counts = np.array([len(values) for values in differences_by_clip.values()])
    picks = generator.integers(0, len(clip_sums), (BOOTSTRAP_SAMPLES, len(clip_sums)))
    resampled_means = clip_sums[picks].sum(axis=1) / clip_counts[picks].sum(axis=1)
    low, high = np.percentile(resampled_means, [2.5, 97.5])
    return float(low), float(high)


def first_differing_frame(
    baseline: NDArray[np.int16], candidate: NDArray[np.int16]
) -> int | None:
    """None when equal; else the first 80 ms frame where the samples differ."""
    if len(baseline) == len(candidate) and np.array_equal(baseline, candidate):
        return None
    else:
        pass
    common = min(len(baseline), len(candidate))
    differing = np.nonzero(baseline[:common] != candidate[:common])[0]
    sample = int(differing[0]) if len(differing) else common
    return sample // SAMPLES_PER_FRAME


def compare_quality(runs: list[LoadedRun]) -> None:
    baseline = runs[0]
    for run in runs[1:]:
        assert (
            run.scores["quality"].keys() == baseline.scores["quality"].keys()
        ), f"{run.name} has other replies than {baseline.name}"

    print("quality (UTMOS: higher is better; WER: ASR of the reply audio vs its text)")
    print("  run          n   UTMOS   corpus-WER  no-text  words/reply")
    for run in runs:
        reply_scores = list(run.scores["quality"].values())
        with_text = [
            reply_score
            for reply_score in reply_scores
            if not reply_score["has_no_text"]
        ]
        corpus_wer = sum(reply_score["word_errors"] for reply_score in with_text) / sum(
            reply_score["reference_words"] for reply_score in with_text
        )
        utmos_mean = np.mean([reply_score["utmos"] for reply_score in reply_scores])
        words_per_reply = np.mean(
            [reply_score["reference_words"] for reply_score in reply_scores]
        )
        print(
            f"  {run.name:<12} {len(reply_scores):<3} {utmos_mean:.3f}   "
            f"{corpus_wer:.3f}       "
            f"{len(reply_scores) - len(with_text)}/{len(reply_scores)}    "
            f"{words_per_reply:.1f}"
        )

    print(
        f"paired difference vs {baseline.name}, mean [95% interval, whole clips "
        "resampled] (pairs):"
    )
    generator = np.random.default_rng(BOOTSTRAP_SEED)
    baseline_scores = baseline.scores["quality"]
    pair_keys = sorted(baseline_scores)
    for run in runs[1:]:
        reply_scores = run.scores["quality"]
        both_with_text = [
            key
            for key in pair_keys
            if not baseline_scores[key]["has_no_text"]
            and not reply_scores[key]["has_no_text"]
        ]
        metrics: tuple[tuple[Literal["utmos", "wer"], list[str]], ...] = (
            ("utmos", pair_keys),
            ("wer", both_with_text),
        )
        for metric, keys in metrics:
            differences_by_clip: dict[str, list[float]] = {}
            for key in keys:
                clip_name = key.split("|", 1)[0]
                differences_by_clip.setdefault(clip_name, []).append(
                    reply_scores[key][metric] - baseline_scores[key][metric]
                )
            mean_difference = np.mean(
                [value for values in differences_by_clip.values() for value in values]
            )
            low, high = clip_interval(differences_by_clip, generator)
            print(
                f"  {run.name:<12} {metric:<5} {mean_difference:+.3f} "
                f"[{low:+.3f}, {high:+.3f}] ({len(keys)})"
            )


def compare_greedy(runs: list[LoadedRun]) -> None:
    baseline = runs[0]
    print(
        f"greedy, one request at a time: first differing 80 ms frame vs "
        f"{baseline.name}"
    )
    for run in runs[1:]:
        for baseline_reply, candidate_reply in zip(
            baseline.summary["greedy"], run.summary["greedy"], strict=True
        ):
            baseline_audio, _ = soundfile.read(baseline_reply["wav"], dtype="int16")
            candidate_audio, _ = soundfile.read(candidate_reply["wav"], dtype="int16")
            frame = first_differing_frame(baseline_audio, candidate_audio)
            frames = len(baseline_audio) // SAMPLES_PER_FRAME
            audio_result = (
                "identical audio" if frame is None else f"frame {frame}/{frames}"
            )
            print(
                f"  {run.name:<12} {baseline_reply['recording']:<24} {audio_result}, "
                f"text equal {baseline_reply['text'] == candidate_reply['text']}"
            )


def compare_long(runs: list[LoadedRun]) -> None:
    print(
        f"long input, mean over seeds per {WINDOW_S:g} s window "
        "(UTMOS / ASR words); WER over whole replies"
    )
    for run in runs:
        long_scores = list(run.scores["long"].values())
        window_columns = zip(
            *(long_score["windows"] for long_score in long_scores), strict=True
        )
        window_cells = [
            f"{np.mean([window['utmos'] for window in windows]):.2f}/"
            f"{np.mean([window['asr_words'] for window in windows]):.0f}"
            for windows in window_columns
        ]
        corpus_wer = sum(long_score["word_errors"] for long_score in long_scores) / sum(
            long_score["reference_words"] for long_score in long_scores
        )
        print(f"  {run.name:<12} {'  '.join(window_cells)}  WER {corpus_wer:.3f}")


def compare_speed(runs: list[LoadedRun]) -> None:
    print("speed, mean over repeats (min-max)")
    for run in runs:
        print(f"  {run.name:<12} startup {run.summary['startup_s']:.1f} s")
        for level, repeats in run.summary["speed"].items():
            throughput = [repeat["audio_s_per_s"] for repeat in repeats]
            ttfa_ms = [repeat["ttfa_mean_s"] * 1000 for repeat in repeats]
            ms_per_frame = (
                np.mean([repeat["rtf_mean"] for repeat in repeats]) * FRAME_MS
            )
            gap_p95_ms = (
                np.mean([repeat["chunk_gap_p95_s"] for repeat in repeats]) * 1000
            )
            paused = sum(repeat["replies_with_pauses"] for repeat in repeats)
            pause_ms = sum(repeat["pause_s_total"] for repeat in repeats) * 1000
            print(
                f"  {run.name:<12} c{level:<3} {np.mean(throughput):.2f} audio-s/s "
                f"({min(throughput):.2f}-{max(throughput):.2f})  "
                f"TTFA {np.mean(ttfa_ms):.0f} ms "
                f"({min(ttfa_ms):.0f}-{max(ttfa_ms):.0f})  "
                f"{ms_per_frame:.1f} ms/frame  gap p95 {gap_p95_ms:.0f} ms  "
                f"paused {paused}/{int(level) * len(repeats)} "
                f"({pause_ms:.0f} ms total)"
            )


def compare_capacity(runs: list[LoadedRun]) -> None:
    """A queued request's wait counts in its TTFA and ms/frame but not in its
    pauses, which start at the first chunk."""
    print("capacity, long requests submitted together, mean over repeats")
    for run in runs:
        repeats = run.summary["capacity"]
        requests = repeats[0]["requests"]
        paused = sum(repeat["replies_with_pauses"] for repeat in repeats)
        print(
            f"  {run.name:<14} N {requests}  "
            f"{np.mean([repeat['audio_s_per_s'] for repeat in repeats]):.2f} "
            f"audio-s/s  TTFA mean "
            f"{np.mean([repeat['ttfa_mean_s'] for repeat in repeats]):.1f} s  "
            f"p95 {np.mean([repeat['ttfa_p95_s'] for repeat in repeats]):.1f} s  "
            f"max {np.mean([repeat['ttfa_max_s'] for repeat in repeats]):.1f} s  "
            f"{np.mean([repeat['rtf_mean'] for repeat in repeats]) * FRAME_MS:.1f} "
            f"ms/frame  gap p95 "
            f"{np.mean([repeat['chunk_gap_p95_s'] for repeat in repeats]) * 1000:.0f} ms  "
            f"paused {paused}/{requests * len(repeats)}"
        )


def compare(arguments: argparse.Namespace) -> None:
    runs = [load_run(run_dir) for run_dir in arguments.run_dirs]
    sections: tuple[tuple[Callable[[list[LoadedRun]], None], Phase], ...] = (
        (compare_quality, "quality"),
        (compare_greedy, "greedy"),
        (compare_long, "long"),
        (compare_speed, "speed"),
        (compare_capacity, "capacity"),
    )
    for compare_section, phase in sections:
        phase_runs = [run for run in runs if run.summary[phase]]
        if phase_runs:
            compare_section(phase_runs)
        else:
            pass


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--out-dir", required=True)
    run_parser.add_argument("--checkpoint", default="nvidia/personaplex-7b-v1")
    run_parser.add_argument(
        "--phases",
        nargs="+",
        choices=get_args(Phase),
        default=["quality", "greedy", "long", "speed"],
    )
    run_parser.add_argument("--clips", type=int, default=64)
    run_parser.add_argument("--min-seconds", type=float, default=15.0)
    run_parser.add_argument("--seeds", nargs="+", type=int, default=[1])
    run_parser.add_argument("--quality-concurrency", type=int, default=8)
    run_parser.add_argument("--long-seconds", type=float, default=300.0)
    run_parser.add_argument("--long-seeds", nargs="+", type=int, default=[1, 2])
    run_parser.add_argument(
        "--concurrency",
        dest="concurrency_levels",
        nargs="+",
        type=int,
        default=[1, 8, 16],
    )
    run_parser.add_argument("--speed-repeats", type=int, default=3)
    run_parser.add_argument("--capacity-requests", type=int, default=12)
    run_parser.add_argument("--capacity-repeats", type=int, default=1)
    # Note (Jinjie Guo): P2-1 ran at 0.5 on an H100 NVL; the default 0.3 was tuned
    # on H200.
    run_parser.add_argument("--mem-fraction", type=float, default=0.5)
    run_parser.add_argument("--stage-args", default="")
    score_parser = commands.add_parser("score")
    score_parser.add_argument("run_dirs", nargs="+")
    score_parser.add_argument("--asr-port", type=int, required=True)
    score_parser.add_argument("--asr-model", default=QWEN3_ASR_MODEL_PATH)
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("run_dirs", nargs="+")
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    if arguments.command == "run":
        asyncio.run(run_suite(arguments))
    elif arguments.command == "score":
        score(arguments)
    else:
        compare(arguments)


if __name__ == "__main__":
    main()
