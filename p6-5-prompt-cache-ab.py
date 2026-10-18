# SPDX-License-Identifier: Apache-2.0
"""P6-5 GPU validation driver (not committed): one pipeline start per run.

Run mode (from the repo root):

    PYTHONPATH=. python -u p6-5-prompt-cache-ab.py run --out-dir R/off --phases ttfa
    PYTHONPATH=. python -u p6-5-prompt-cache-ab.py run --out-dir R/on --phases ttfa \
        --stage-args '--lm.engine.disable_radix_cache false'

--phases ttfa (the Q3 gate runs, in the order off, on, on, off):
  same-voice-prime  one request that caches the voice's prompt
  same-voice-N      N requests with that voice together
  mixed-voice-N     N requests together, each with a voice no other phase uses

--phases correctness (the full runs):
  probe-baseline    a short request; its decode lines give the pool baseline
  seeded-miss       each recording once with its own voice, seed 7, one in flight
  seeded-hit        the same requests again; with radix on, each prompt is cached
  layout-i          seeded-miss-i again, prefilled together with three 1-frame
                    requests that finish at prefill: the batch-layout noise
  overlap-abort     A starts, B (same voice) starts while A decodes, A is
                    aborted; then B alone
  retract           a cached request is retracted while it decodes, then resumed;
                    then the same request alone
  partial-hit       the voice of a primed request with another role prompt
  long              two requests longer than the 3000-position window, one voice
  probe-after-*     a short probe after each phase above: the pool must return
                    to the baseline

--phases all runs both lists.

Other modes:

    python p6-5-prompt-cache-ab.py compare R/off R/on   # outputs, pair by pair
    python p6-5-prompt-cache-ab.py gate --off R/off R/off2 --on R/on R/on2
    python p6-5-prompt-cache-ab.py logs R/on.log R/on/summary.json

Requests in one prefill batch do not share a prompt: the radix match runs
before the batch is built. So same-voice-N primes the voice first.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile
import torch

from sglang_omni.client.client import Client
from sglang_omni.client.types import GenerateRequest, SamplingParams
from sglang_omni.config.manager import ConfigManager
from sglang_omni.models.personaplex import prompts, request_builders
from sglang_omni.models.personaplex.architecture import (
    PROMPT_SILENCE_FRAMES,
    SAMPLE_RATE,
    SAMPLES_PER_FRAME,
)
from sglang_omni.models.personaplex.config import LM_STAGE, PersonaPlexPipelineConfig
from sglang_omni.pipeline.mp_runner import MultiProcessPipelineRunner
from sglang_omni.utils.checkpoint import resolve_checkpoint

DEFAULT_RECORDINGS = (
    "tests/data/query_to_cars.wav",
    "tests/data/query_to_draw.wav",
    "tests/data/cough.wav",
)
# Each phase owns its voices, so one phase's cached prompt never turns another
# phase's miss into a hit.
WARMUP_VOICE = "VARM4"
SEEDED_VOICES = ("NATF2", "NATM1", "NATF0")
SAME_VOICE = "NATM0"
LONG_VOICE = "NATF1"
PROBE_VOICE = "NATF3"
OVERLAP_VOICE = "NATM2"
RETRACT_VOICE = "VARM3"
PARTIAL_VOICE = "NATM3"
MIXED_VOICES = ("VARF0", "VARF1", "VARF2", "VARF3", "VARF4", "VARM0", "VARM1", "VARM2")
ALT_TEXT_PROMPT = "You enjoy having a good conversation."
SEED = 7
LAYOUT_FILLERS = 3
DECODING_SECONDS = 30.0
PHASE_MARK = "P65-PHASE"
GATE_LEVELS = (4, 8)
GATE_FACTOR = 2.0


@dataclass(frozen=True)
class Job:
    recording: Path
    voice: str
    seeded: bool
    text_prompt: str | None = None


def say(message: str) -> None:
    """Driver lines start with P65, so `logs` can skip them."""
    print(f"P65 {message}", flush=True)


def marker(name: str, edge: str) -> None:
    print(f"{PHASE_MARK} {name} {edge}", flush=True)


def tiled(path: str, min_seconds: float, out_dir: Path) -> Path:
    """Repeat a recording until it lasts at least min_seconds."""
    out_dir.mkdir(parents=True, exist_ok=True)
    audio, rate = soundfile.read(path, dtype="float32", always_2d=True)
    mono = audio[:, 0]
    repeats = max(1, int(np.ceil(min_seconds * rate / len(mono))))
    target = out_dir / f"{Path(path).stem}_{min_seconds:g}s.wav"
    soundfile.write(str(target), np.tile(mono, repeats), rate)
    return target


def one_frame(path: str, out_dir: Path) -> Path:
    """The first 80 ms of a recording: a request that finishes at prefill."""
    out_dir.mkdir(parents=True, exist_ok=True)
    audio, rate = soundfile.read(path, dtype="float32", always_2d=True)
    samples = int(round(rate * SAMPLES_PER_FRAME / SAMPLE_RATE))
    target = out_dir / f"{Path(path).stem}_1frame.wav"
    soundfile.write(str(target), audio[:samples, 0], rate)
    return target


def git_head() -> str:
    output = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return output.stdout.strip()


def expected_rows(checkpoint: Path) -> dict[str, object]:
    """Prompt rows per voice with the default role prompt, and the rows the
    partial-hit request shares with its primed prompt."""
    tokenizer = prompts.load_text_tokenizer(checkpoint)
    default_ids = prompts.tokenize_text_prompt(tokenizer, prompts.DEFAULT_TEXT_PROMPT)
    alt_ids = prompts.tokenize_text_prompt(tokenizer, ALT_TEXT_PROMPT)
    common_tokens = 0
    for default_id, alt_id in zip(default_ids, alt_ids, strict=False):
        if default_id != alt_id:
            break
        else:
            common_tokens += 1
    folder = prompts.voices_dir(checkpoint)
    voice_rows = {
        path.stem: prompts.load_voice_prompt(path, load_audio=None).frames
        for path in sorted(folder.glob("*.pt"))
    }
    prompt_rows = {
        voice: rows + 2 * PROMPT_SILENCE_FRAMES + len(default_ids)
        for voice, rows in voice_rows.items()
    }
    return {
        "text_prompt_rows": len(default_ids),
        "prompt_rows": prompt_rows,
        "partial_hit_cached": voice_rows[PARTIAL_VOICE]
        + PROMPT_SILENCE_FRAMES
        + common_tokens,
    }


async def run_suite(args: argparse.Namespace) -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("needs CUDA")
    else:
        pass
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    head = git_head()
    keyed_prompt = hasattr(request_builders, "PROMPT_CACHE_KEY")
    say(
        f"code under test: HEAD={head} keyed_prompt={keyed_prompt} "
        f"phases={args.phases} stage_args={args.stage_args!r}"
    )

    inputs = out_dir / "inputs"
    recordings = [tiled(path, args.min_seconds, inputs) for path in args.recordings]
    decoding = tiled(args.recordings[0], DECODING_SECONDS, inputs)
    long_recording = tiled(args.recordings[0], args.long_seconds, inputs)
    filler = one_frame(args.recordings[2], inputs)
    levels = [int(level) for level in args.concurrency.split(",")]
    if max(levels) > len(MIXED_VOICES):
        raise ValueError(
            f"mixed-voice needs one voice per request; max {len(MIXED_VOICES)}"
        )
    else:
        pass
    checkpoint = Path(resolve_checkpoint(args.checkpoint))
    expected = expected_rows(checkpoint)
    say(f"expected rows: {json.dumps(expected)}")
    config = PersonaPlexPipelineConfig(model_path=str(checkpoint))
    overrides = [
        "--lm.engine.max_running_requests",
        str(max(*levels, LAYOUT_FILLERS + 1)),
        "--lm.engine.mem_fraction_static",
        str(args.mem_fraction),
        *shlex.split(args.stage_args),
    ]
    manager = ConfigManager(config)
    config = manager.merge_config(manager.parse_extra_args(overrides))
    runner = MultiProcessPipelineRunner(config)
    await runner.start(
        timeout=float(os.environ.get("SGLANG_OMNI_STARTUP_TIMEOUT", "900"))
    )
    summary: dict[str, object] = {
        "head": head,
        "keyed_prompt": keyed_prompt,
        "phases_run": args.phases,
        "stage_args": overrides,
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "expected": expected,
        "phases": {},
        "events": {},
    }
    audio_blobs: dict[str, np.ndarray] = {}
    try:
        client = Client(runner.coordinator)

        async def reply(
            request_id: str, job: Job, first_audio: asyncio.Event | None = None
        ) -> dict[str, object]:
            extra: dict[str, object] = {"voice": job.voice}
            if job.seeded:
                extra["seed"] = SEED
            else:
                pass
            if job.text_prompt is not None:
                extra["text_prompt"] = job.text_prompt
            else:
                pass
            request = GenerateRequest(
                model=config.name,
                prompt={"audio_path": str(job.recording)},
                sampling=SamplingParams(),
                extra_params=extra,
                output_modalities=["text", "audio"],
                stream=True,
            )
            start = time.perf_counter()
            first_audio_s = None
            text_parts: list[str] = []
            pcm_parts: list[bytes] = []
            async for chunk in client.completion_stream(
                request, request_id=request_id, audio_format="pcm"
            ):
                if chunk.audio_b64:
                    if first_audio_s is None:
                        first_audio_s = time.perf_counter() - start
                        if first_audio is not None:
                            first_audio.set()
                        else:
                            pass
                    else:
                        pass
                    pcm_parts.append(base64.b64decode(chunk.audio_b64))
                elif chunk.modality == "text" and chunk.text:
                    text_parts.append(chunk.text)
                else:
                    pass
            latency = time.perf_counter() - start
            if first_audio_s is None:
                raise RuntimeError(f"{request_id}: no audio")
            else:
                pass
            audio = np.frombuffer(b"".join(pcm_parts), dtype="<i2").copy()
            return {
                "request_id": request_id,
                "recording": job.recording.name,
                "voice": job.voice,
                "text_prompt": job.text_prompt,
                "text": "".join(text_parts),
                "audio": audio,
                "ttfa_s": first_audio_s,
                "latency_s": latency,
                "audio_s": len(audio) / SAMPLE_RATE,
            }

        def record(name: str, replies: list[dict[str, object]], wall: float) -> None:
            for r in replies:
                audio_blobs[f"{name}/{r['request_id']}"] = r.pop("audio")
            ttfa = [r["ttfa_s"] for r in replies]
            audio_s = sum(r["audio_s"] for r in replies)
            summary["phases"][name] = {
                "requests": len(replies),
                "wall_s": wall,
                "audio_s_per_s": audio_s / wall,
                "ttfa_mean_s": float(np.mean(ttfa)),
                "ttfa_p95_s": float(np.percentile(ttfa, 95)),
                "ttfa_max_s": float(np.max(ttfa)),
                "latency_mean_s": float(np.mean([r["latency_s"] for r in replies])),
                "replies": replies,
            }
            say(
                f"{name}: {len(replies)} requests, wall {wall:.2f} s, "
                f"audio {audio_s / wall:.1f} s/s, TTFA mean "
                f"{np.mean(ttfa) * 1000:.1f} ms p95 {np.percentile(ttfa, 95) * 1000:.1f} ms"
            )

        async def phase(name: str, jobs: list[Job]) -> None:
            marker(name, "start")
            start = time.perf_counter()
            replies = await asyncio.gather(
                *(reply(f"{name}-{index}", job) for index, job in enumerate(jobs))
            )
            record(name, list(replies), time.perf_counter() - start)
            marker(name, "end")

        async def sequential(name: str, jobs: list[Job]) -> None:
            for index, job in enumerate(jobs):
                await phase(f"{name}-{index}", [job])

        async def probe(name: str) -> None:
            await phase(name, [Job(recordings[1], PROBE_VOICE, False)])

        async def overlap_abort() -> None:
            name = "overlap-abort"
            marker(name, "start")
            a_decoding = asyncio.Event()
            b_decoding = asyncio.Event()
            a_job = Job(decoding, OVERLAP_VOICE, True)
            b_job = Job(recordings[1], OVERLAP_VOICE, True)
            start = time.perf_counter()
            a_task = asyncio.create_task(reply(f"{name}-A", a_job, a_decoding))
            await asyncio.wait_for(a_decoding.wait(), timeout=120)
            b_task = asyncio.create_task(reply(f"{name}-B", b_job, b_decoding))
            await asyncio.wait_for(b_decoding.wait(), timeout=120)
            aborted = await client.abort(f"{name}-A")
            try:
                a_reply = await asyncio.wait_for(a_task, timeout=120)
                a_outcome = f"returned {a_reply['audio_s']:.2f} s of audio"
                audio_blobs[f"{name}/A"] = a_reply.pop("audio")
            except Exception as exc:  # noqa: BLE001 - recorded, not raised
                a_outcome = f"{type(exc).__name__}: {exc}"
            b_reply = await b_task
            record(name, [b_reply], time.perf_counter() - start)
            summary["events"][name] = {"abort": repr(aborted), "A": a_outcome}
            say(f"{name}: abort {aborted!r}; A {a_outcome}")
            marker(name, "end")
            await phase(f"{name}-alone", [b_job])

        async def retract() -> None:
            name = "retract"
            await phase(f"{name}-prime", [Job(recordings[0], RETRACT_VOICE, False)])
            marker(name, "start")
            job = Job(decoding, RETRACT_VOICE, True)
            decoding_started = asyncio.Event()
            start = time.perf_counter()
            task = asyncio.create_task(reply(f"{name}-R", job, decoding_started))
            await asyncio.wait_for(decoding_started.wait(), timeout=120)
            await asyncio.sleep(args.retract_after)
            paused = await client.pause_generation(
                {"mode": "retract"}, stages=[LM_STAGE]
            )
            paused_at_s = time.perf_counter() - start
            await asyncio.sleep(1.0)
            resumed = await client.continue_generation(stages=[LM_STAGE])
            r_reply = await asyncio.wait_for(task, timeout=600)
            record(name, [r_reply], time.perf_counter() - start)
            summary["events"][name] = {
                "pause": repr(paused)[:500],
                "continue": repr(resumed)[:500],
                "paused_at_s": paused_at_s,
            }
            say(f"{name}: paused at {paused_at_s:.2f} s: {repr(paused)[:200]}")
            marker(name, "end")
            await phase(f"{name}-alone", [job])

        seeded_jobs = [
            Job(recording, voice, True)
            for recording, voice in zip(recordings, SEEDED_VOICES, strict=False)
        ]
        marker("warmup", "start")
        await reply("warmup", Job(recordings[0], WARMUP_VOICE, False))
        marker("warmup", "end")
        if args.phases in ("ttfa", "all"):
            await phase("same-voice-prime", [Job(recordings[0], SAME_VOICE, False)])
            for level in levels:
                await phase(
                    f"same-voice-{level}",
                    [
                        Job(recordings[i % len(recordings)], SAME_VOICE, False)
                        for i in range(level)
                    ],
                )
                await phase(
                    f"mixed-voice-{level}",
                    [
                        Job(recordings[i % len(recordings)], MIXED_VOICES[i], False)
                        for i in range(level)
                    ],
                )
        else:
            pass
        if args.phases in ("correctness", "all"):
            await probe("probe-baseline")
            await sequential("seeded-miss", seeded_jobs)
            await sequential("seeded-hit", seeded_jobs)
            for index, job in enumerate(seeded_jobs):
                await phase(
                    f"layout-{index}",
                    [job] + [Job(filler, WARMUP_VOICE, False)] * LAYOUT_FILLERS,
                )
            await overlap_abort()
            await probe("probe-after-overlap-abort")
            await retract()
            await probe("probe-after-retract")
            await phase("partial-prime", [Job(recordings[0], PARTIAL_VOICE, False)])
            await phase(
                "partial-hit",
                [Job(recordings[0], PARTIAL_VOICE, False, ALT_TEXT_PROMPT)],
            )
            await probe("probe-after-partial-hit")
            say("long: watch the LM log for '#cached-token' and '#swa token'")
            await sequential("long", [Job(long_recording, LONG_VOICE, True)] * 2)
            await probe("probe")
        else:
            pass
    finally:
        await runner.stop()
        np.savez_compressed(out_dir / "audio.npz", **audio_blobs)
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        say(f"wrote {out_dir}")


def load(result_dir: str) -> tuple[dict, dict[str, np.ndarray]]:
    root = Path(result_dir)
    summary = json.loads((root / "summary.json").read_text())
    with np.load(root / "audio.npz") as blobs:
        audio = {key: blobs[key] for key in blobs.files}
    return summary, audio


def first_differing_frame(a: np.ndarray, b: np.ndarray) -> int | None:
    """None when equal; else the first 80 ms frame where the samples differ."""
    if len(a) == len(b) and np.array_equal(a, b):
        return None
    else:
        pass
    common = min(len(a), len(b))
    diff = np.nonzero(a[:common] != b[:common])[0]
    sample = int(diff[0]) if len(diff) else common
    return sample // SAMPLES_PER_FRAME


def phase_reply(
    summary: dict, audio: dict, name: str, index: int = 0
) -> tuple[str, np.ndarray]:
    entry = summary["phases"][name]["replies"][index]
    return entry["text"], audio[f"{name}/{entry['request_id']}"]


def numbered(summary: dict, kind: str) -> list[str]:
    return sorted(
        name
        for name in summary["phases"]
        if name.startswith(f"{kind}-") and name[len(kind) + 1 :].isdigit()
    )


def report_pair(
    label: str, left: tuple[str, np.ndarray], right: tuple[str, np.ndarray]
) -> int | None:
    frame = first_differing_frame(left[1], right[1])
    frames = len(left[1]) // SAMPLES_PER_FRAME
    audio = (
        "exact-audio True"
        if frame is None
        else f"first differing frame {frame}/{frames}"
    )
    print(f"  {label}: {audio}, text-equal {left[0] == right[0]}")
    return frame


def report_run(path: str, summary: dict, audio: dict) -> None:
    print(f"{path}: HEAD={summary['head']} keyed={summary['keyed_prompt']}")
    print(f"  stage args: {summary['stage_args']}")
    phases = summary["phases"]
    for miss, hit in zip(
        numbered(summary, "seeded-miss"), numbered(summary, "seeded-hit"), strict=True
    ):
        report_pair(
            f"{hit} vs {miss}",
            phase_reply(summary, audio, hit),
            phase_reply(summary, audio, miss),
        )
    layout_frames = []
    for layout, miss in zip(
        numbered(summary, "layout"), numbered(summary, "seeded-miss"), strict=True
    ):
        frame = report_pair(
            f"{layout} vs {miss} (batch layout)",
            phase_reply(summary, audio, layout),
            phase_reply(summary, audio, miss),
        )
        layout_frames.append(frame)
    differing = [frame for frame in layout_frames if frame is not None]
    if differing:
        print(
            f"  batch-layout first differing frames: {min(differing)}-{max(differing)}"
        )
    elif layout_frames:
        print("  batch-layout: every layout reply is exact")
    else:
        pass
    for name in ("overlap-abort", "retract"):
        if name in phases:
            print(f"  {name} events: {summary['events'].get(name)}")
            report_pair(
                f"{name} vs {name}-alone",
                phase_reply(summary, audio, name),
                phase_reply(summary, audio, f"{name}-alone"),
            )
        else:
            pass


def compare(args: argparse.Namespace) -> None:
    runs = [(path, *load(path)) for path in (args.off_dir, args.on_dir)]
    for path, summary, audio in runs:
        report_run(path, summary, audio)
    (_, off, off_audio), (_, on, on_audio) = runs
    print("off run vs on run (requests that run alone in both):")
    names = (
        numbered(off, "seeded-miss")
        + numbered(off, "seeded-hit")
        + ["long-0", "long-1", "probe"]
    )
    for name in names:
        if name in off["phases"] and name in on["phases"]:
            report_pair(
                name,
                phase_reply(off, off_audio, name),
                phase_reply(on, on_audio, name),
            )
        else:
            pass


def gate(args: argparse.Namespace) -> None:
    """The Q3 gate: keep the full PR only if same-voice TTFA at N=4 or N=8 drops
    by more than twice the A/A difference of the ABBA runs."""
    off = [load(path)[0]["phases"] for path in args.off]
    on = [load(path)[0]["phases"] for path in args.on]
    print(
        "phase: TTFA mean ms off1/off2 -> on1/on2 | A/A ms | drop ms | "
        "p95 ms off -> on | audio s/s off1/off2 -> on1/on2"
    )
    passed = []
    for name in off[0]:
        if not name.startswith(("same-voice-", "mixed-voice-")) or name.endswith(
            "prime"
        ):
            continue
        else:
            pass
        off_ms = [phases[name]["ttfa_mean_s"] * 1000 for phases in off]
        on_ms = [phases[name]["ttfa_mean_s"] * 1000 for phases in on]
        aa = max(abs(off_ms[0] - off_ms[1]), abs(on_ms[0] - on_ms[1]))
        drop = float(np.mean(off_ms) - np.mean(on_ms))
        off_p95 = np.mean([phases[name]["ttfa_p95_s"] * 1000 for phases in off])
        on_p95 = np.mean([phases[name]["ttfa_p95_s"] * 1000 for phases in on])
        off_rate = [phases[name]["audio_s_per_s"] for phases in off]
        on_rate = [phases[name]["audio_s_per_s"] for phases in on]
        print(
            f"  {name}: {off_ms[0]:.1f}/{off_ms[1]:.1f} -> {on_ms[0]:.1f}/{on_ms[1]:.1f}"
            f" | {aa:.1f} | {drop:.1f} | {off_p95:.1f} -> {on_p95:.1f}"
            f" | {off_rate[0]:.1f}/{off_rate[1]:.1f} -> {on_rate[0]:.1f}/{on_rate[1]:.1f}"
        )
        level = int(name.rsplit("-", 1)[1])
        if name.startswith("same-voice-") and level in GATE_LEVELS:
            passed.append(drop > GATE_FACTOR * aa)
        else:
            pass
    verdict = "PASS" if any(passed) else "FAIL"
    print(
        f"Q3 gate (same-voice N in {GATE_LEVELS}, drop > {GATE_FACTOR:g} x A/A): {verdict}"
    )


NEW_TOKENS = re.compile(r"#new-token: (\d+)")
CACHED_TOKENS = re.compile(r"#cached-token: (\d+)")
SWA_TOKENS = re.compile(r"#swa token: (\d+)")
FULL_TOKENS = re.compile(r"#(?:full )?token: (\d+)")
RETRACT = re.compile(r"[Rr]etract")
OOM = re.compile(r"out of memory|OutOfMemory")


def logs(args: argparse.Namespace) -> None:
    """Per phase: prefill rows new and cached, retract and OOM lines, and the
    first and last pool reading of the decode lines."""
    stats: dict[str, dict[str, object]] = {}
    current = None
    for line in Path(args.log).read_text(errors="replace").splitlines():
        if line.startswith(PHASE_MARK):
            _, name, edge = line.split()
            if edge == "start":
                current = name
                stats[name] = {
                    "prefills": 0,
                    "new": 0,
                    "cached": 0,
                    "retract": 0,
                    "oom": 0,
                    "pool_first": None,
                    "pool_last": None,
                }
            else:
                current = None
            continue
        elif current is None or line.startswith("P65 "):
            continue
        else:
            pass
        entry = stats[current]
        if "Prefill batch" in line:
            entry["prefills"] += 1
            for key, pattern in (("new", NEW_TOKENS), ("cached", CACHED_TOKENS)):
                match = pattern.search(line)
                entry[key] += int(match.group(1)) if match else 0
        elif "Decode batch" in line:
            match = SWA_TOKENS.search(line) or FULL_TOKENS.search(line)
            if match:
                if entry["pool_first"] is None:
                    entry["pool_first"] = int(match.group(1))
                else:
                    pass
                entry["pool_last"] = int(match.group(1))
            else:
                pass
        else:
            pass
        entry["retract"] += 1 if RETRACT.search(line) else 0
        entry["oom"] += 1 if OOM.search(line) else 0
    expected = None
    if args.summary:
        summary = json.loads(Path(args.summary).read_text())
        expected = summary["expected"]
        print(f"expected rows: {json.dumps(expected)}")
    else:
        pass
    print(
        "phase: prefills | #new | #cached (if radix on) | retract | OOM | pool first/last"
    )
    for name, entry in stats.items():
        hint = ""
        if expected is not None:
            hint = expected_cached_hint(name, summary, expected)
        else:
            pass
        print(
            f"  {name}: {entry['prefills']} | {entry['new']} | {entry['cached']}{hint}"
            f" | {entry['retract']} | {entry['oom']}"
            f" | {entry['pool_first']}/{entry['pool_last']}"
        )


def expected_cached_hint(name: str, summary: dict, expected: dict) -> str:
    """The #cached-token a radix-on run should show for a hit phase."""
    if name == "partial-hit":
        return f" (expect {expected['partial_hit_cached']})"
    elif name.startswith("seeded-hit-") or (
        name.startswith("same-voice-") and name != "same-voice-prime"
    ):
        replies = summary["phases"].get(name, {}).get("replies", [])
        rows = sum(expected["prompt_rows"][r["voice"]] - 1 for r in replies)
        return f" (expect {rows})"
    else:
        return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--out-dir", required=True)
    run.add_argument("--checkpoint", default="nvidia/personaplex-7b-v1")
    run.add_argument("--recordings", nargs="+", default=list(DEFAULT_RECORDINGS))
    run.add_argument("--min-seconds", type=float, default=10.0)
    run.add_argument("--long-seconds", type=float, default=260.0)
    run.add_argument("--concurrency", default="1,4,8")
    run.add_argument("--phases", choices=("all", "ttfa", "correctness"), default="all")
    run.add_argument("--retract-after", type=float, default=1.0)
    # Note (Jinjie Guo): P2-1 ran at 0.5 on an H100 NVL; the default 0.3 was tuned on H200.
    run.add_argument("--mem-fraction", type=float, default=0.5)
    run.add_argument("--stage-args", default="")
    diff = commands.add_parser("compare")
    diff.add_argument("off_dir")
    diff.add_argument("on_dir")
    gate_parser = commands.add_parser("gate")
    gate_parser.add_argument("--off", nargs=2, required=True)
    gate_parser.add_argument("--on", nargs=2, required=True)
    logs_parser = commands.add_parser("logs")
    logs_parser.add_argument("log")
    logs_parser.add_argument("summary", nargs="?")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "run":
        asyncio.run(run_suite(args))
    elif args.command == "compare":
        compare(args)
    elif args.command == "gate":
        gate(args)
    else:
        logs(args)


if __name__ == "__main__":
    main()
