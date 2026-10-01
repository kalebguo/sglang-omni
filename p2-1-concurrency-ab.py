# SPDX-License-Identifier: Apache-2.0
"""P2-1 GPU validation driver (not committed): one pipeline start per checkout.

Run mode (from the repo root, once on main and once on the branch):

    PYTHONPATH=. python p2-1-concurrency-ab.py run --out-dir /results/main

Phases, all against one running pipeline:
  seeded         each recording once, seed 7, one request in flight
  greedy-1/-2    G distinct greedy requests submitted together, twice
                 (the second run is the same-checkout noise floor)
  throughput-N   M unseeded default-sampling requests, N in flight

Compare mode:

    PYTHONPATH=. python p2-1-concurrency-ab.py compare /results/main /results/branch

The engine's max_running_requests is the largest concurrency used; a client
semaphore limits the batch to N for each phase, so one startup covers every N.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import soundfile
import torch

from benchmarks.eval.personaplex_parity import DEFAULT_ATOL, compare_frames
from sglang_omni.client.client import Client
from sglang_omni.client.types import GenerateRequest, SamplingParams
from sglang_omni.config.manager import ConfigManager
from sglang_omni.models.personaplex.architecture import SAMPLE_RATE, SAMPLES_PER_FRAME
from sglang_omni.models.personaplex.config import PersonaPlexPipelineConfig
from sglang_omni.models.personaplex.model_runner import PersonaPlexModelRunner
from sglang_omni.pipeline.mp_runner import MultiProcessPipelineRunner
from sglang_omni.proto.request import EXPLICIT_GENERATION_PARAMS_KEY
from sglang_omni.utils.checkpoint import resolve_checkpoint

DEFAULT_RECORDINGS = (
    "tests/data/query_to_cars.wav",
    "tests/data/query_to_draw.wav",
    "tests/data/cough.wav",
)
DEFAULT_VOICES = ("NATF2", "NATM1", "NATF0", "NATM0")
SEED = 7


class MemoryPoller:
    """Peak device memory in MiB from nvidia-smi; stage processes own the memory."""

    def __init__(self, interval_seconds: float = 0.5) -> None:
        visible = os.environ.get("CUDA_VISIBLE_DEVICES", "0").split(",")[0]
        self.command = [
            "nvidia-smi",
            "--query-gpu=memory.used",
            "--format=csv,noheader,nounits",
            "-i",
            visible,
        ]
        self.interval_seconds = interval_seconds
        self.peak_mib = 0
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.poll, daemon=True)

    def poll(self) -> None:
        while not self.stopped.is_set():
            output = subprocess.run(self.command, capture_output=True, text=True)
            if output.returncode == 0 and output.stdout.strip():
                self.peak_mib = max(self.peak_mib, int(output.stdout.split()[0]))
            else:
                pass
            self.stopped.wait(self.interval_seconds)

    def __enter__(self) -> "MemoryPoller":
        self.thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stopped.set()
        self.thread.join()


def tiled_recordings(paths: list[str], min_seconds: float, out_dir: Path) -> list[Path]:
    """Repeat each recording until it lasts at least min_seconds."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tiled = []
    for path in paths:
        audio, rate = soundfile.read(path, dtype="float32", always_2d=True)
        mono = audio[:, 0]
        repeats = max(1, int(np.ceil(min_seconds * rate / len(mono))))
        target = out_dir / f"{Path(path).stem}_{min_seconds:g}s.wav"
        soundfile.write(str(target), np.tile(mono, repeats), rate)
        tiled.append(target)
    return tiled


def git_head() -> str:
    output = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return output.stdout.strip()


async def run_suite(args: argparse.Namespace) -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("needs CUDA")
    else:
        pass
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    batched_runner = hasattr(PersonaPlexModelRunner, "spell_frames")
    head = git_head()
    print(f"code under test: HEAD={head} batched_depformer={batched_runner}")

    recordings = tiled_recordings(
        list(args.recordings), args.min_seconds, out_dir / "inputs"
    )
    throughput_levels = [int(level) for level in args.concurrency.split(",")]
    max_running = max(throughput_levels + [args.greedy_requests])
    checkpoint = Path(resolve_checkpoint(args.checkpoint))
    config = PersonaPlexPipelineConfig(model_path=str(checkpoint))
    overrides = [
        "--lm.engine.max_running_requests",
        str(max_running),
        *shlex.split(args.stage_args),
    ]
    manager = ConfigManager(config)
    config = manager.merge_config(manager.parse_extra_args(overrides))
    runner = MultiProcessPipelineRunner(config)
    await runner.start(
        timeout=float(os.environ.get("SGLANG_OMNI_STARTUP_TIMEOUT", "900"))
    )
    summary = {
        "head": head,
        "batched_depformer": batched_runner,
        "max_running_requests": max_running,
        "stage_args": overrides,
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "phases": {},
    }
    audio_blobs: dict[str, np.ndarray] = {}
    try:
        client = Client(runner.coordinator)

        async def reply(
            request_id: str, recording: Path, voice: str, mode: str
        ) -> dict[str, object]:
            extra: dict[str, object] = {"voice": voice}
            if mode == "greedy":
                extra["audio_temperature"] = 0.0
                sampling = SamplingParams(temperature=0.0)
                explicit = ["temperature"]
            elif mode == "seeded":
                extra["seed"] = SEED
                sampling = SamplingParams()
                explicit = []
            else:
                sampling = SamplingParams()
                explicit = []
            request = GenerateRequest(
                model=config.name,
                prompt={"audio_path": str(recording)},
                sampling=sampling,
                extra_params=extra,
                metadata={EXPLICIT_GENERATION_PARAMS_KEY: explicit},
                output_modalities=["text", "audio"],
                stream=False,
            )
            start = time.perf_counter()
            result = await client.completion(
                request, request_id=request_id, audio_format="pcm"
            )
            latency = time.perf_counter() - start
            if result.audio is None:
                raise RuntimeError(f"{request_id}: no audio")
            else:
                pass
            blob = result.audio.data
            pcm = base64.b64decode(blob) if isinstance(blob, str) else blob
            audio = np.frombuffer(pcm, dtype="<i2").copy()
            return {
                "request_id": request_id,
                "recording": recording.name,
                "voice": voice,
                "text": result.text or "",
                "audio": audio,
                "latency_s": latency,
                "audio_s": len(audio) / SAMPLE_RATE,
            }

        async def phase(
            name: str, count: int, in_flight: int, mode: str
        ) -> None:
            limiter = asyncio.Semaphore(in_flight)

            async def limited(index: int) -> dict[str, object]:
                async with limiter:
                    return await reply(
                        f"{name}-{index}",
                        recordings[index % len(recordings)],
                        args.voices[index % len(args.voices)],
                        mode,
                    )

            with MemoryPoller() as memory:
                start = time.perf_counter()
                replies = await asyncio.gather(*(limited(i) for i in range(count)))
                wall = time.perf_counter() - start
            audio_seconds = sum(r["audio_s"] for r in replies)
            frames = sum(len(r["audio"]) // SAMPLES_PER_FRAME for r in replies)
            for r in replies:
                audio_blobs[f"{name}/{r['request_id']}"] = r.pop("audio")
            summary["phases"][name] = {
                "mode": mode,
                "requests": count,
                "in_flight": in_flight,
                "wall_s": wall,
                "audio_s": audio_seconds,
                "audio_s_per_s": audio_seconds / wall,
                "frames_per_s": frames / wall,
                "mean_latency_s": float(np.mean([r["latency_s"] for r in replies])),
                "mean_rtf": float(
                    np.mean([r["latency_s"] / r["audio_s"] for r in replies])
                ),
                "peak_memory_mib": memory.peak_mib,
                "replies": replies,
            }
            print(
                f"{name}: {count} requests, {in_flight} in flight, wall {wall:.1f} s, "
                f"{audio_seconds / wall:.2f} audio-s/s, peak {memory.peak_mib} MiB"
            )

        await reply("warmup", recordings[0], args.voices[0], "default")
        await phase("seeded", len(recordings), 1, "seeded")
        await phase("greedy-1", args.greedy_requests, args.greedy_requests, "greedy")
        await phase("greedy-2", args.greedy_requests, args.greedy_requests, "greedy")
        for level in throughput_levels:
            await phase(f"throughput-{level}", args.requests, level, "default")
    finally:
        await runner.stop()
        np.savez_compressed(out_dir / "audio.npz", **audio_blobs)
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        print(f"wrote {out_dir}")


def load(result_dir: str) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    root = Path(result_dir)
    summary = json.loads((root / "summary.json").read_text())
    with np.load(root / "audio.npz") as audio:
        return summary, {name: audio[name] for name in audio.files}


def compare_phase(
    label: str,
    phase_a: str,
    run_a: tuple[dict[str, object], dict[str, np.ndarray]],
    phase_b: str,
    run_b: tuple[dict[str, object], dict[str, np.ndarray]],
    atol: float,
) -> None:
    summary_a, audio_a = run_a
    summary_b, audio_b = run_b
    replies_a = summary_a["phases"][phase_a]["replies"]
    replies_b = summary_b["phases"][phase_b]["replies"]
    print(f"\n{label} (atol {atol:g})")
    print("request                 frames  identical  text-equal  exact-audio")
    for reply_a, reply_b in zip(replies_a, replies_b, strict=True):
        assert reply_a["recording"] == reply_b["recording"]
        wave_a = audio_a[f"{phase_a}/{reply_a['request_id']}"].astype(np.float32)
        wave_b = audio_b[f"{phase_b}/{reply_b['request_id']}"].astype(np.float32)
        parity = compare_frames(wave_a / 32768.0, wave_b / 32768.0, atol)
        print(
            f"{reply_a['recording'][:22]:22s} {parity.total_frames:7d} "
            f"{parity.identical_frames:10d} {str(reply_a['text'] == reply_b['text']):>11s} "
            f"{str(np.array_equal(wave_a, wave_b)):>12s}"
        )


def compare(args: argparse.Namespace) -> None:
    main_run, branch_run = load(args.main_dir), load(args.branch_dir)
    for label, run in (("main", main_run), ("branch", branch_run)):
        print(
            f"{label}: HEAD={run[0]['head']} "
            f"batched_depformer={run[0]['batched_depformer']} gpu={run[0]['gpu']} "
            f"torch={run[0]['torch']} cuda={run[0]['cuda']}"
        )
    compare_phase("seeded, 1 in flight: main vs branch", "seeded", main_run,
                  "seeded", branch_run, 0.0)
    compare_phase("greedy: main run 1 vs main run 2 (noise floor)", "greedy-1",
                  main_run, "greedy-2", main_run, DEFAULT_ATOL)
    compare_phase("greedy: branch run 1 vs branch run 2 (noise floor)", "greedy-1",
                  branch_run, "greedy-2", branch_run, DEFAULT_ATOL)
    compare_phase("greedy: main run 1 vs branch run 1", "greedy-1", main_run,
                  "greedy-1", branch_run, DEFAULT_ATOL)
    print("\nthroughput        main audio-s/s  branch audio-s/s  speedup  "
          "main RTF  branch RTF  main MiB  branch MiB")
    for name, main_phase in main_run[0]["phases"].items():
        if not name.startswith("throughput-"):
            continue
        else:
            pass
        branch_phase = branch_run[0]["phases"][name]
        print(
            f"{name:16s} {main_phase['audio_s_per_s']:15.2f} "
            f"{branch_phase['audio_s_per_s']:17.2f} "
            f"{branch_phase['audio_s_per_s'] / main_phase['audio_s_per_s']:8.2f} "
            f"{main_phase['mean_rtf']:9.3f} {branch_phase['mean_rtf']:11.3f} "
            f"{main_phase['peak_memory_mib']:9d} {branch_phase['peak_memory_mib']:11d}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--out-dir", required=True)
    run.add_argument("--checkpoint", default="nvidia/personaplex-7b-v1")
    run.add_argument("--recordings", nargs="+", default=list(DEFAULT_RECORDINGS))
    run.add_argument("--voices", nargs="+", default=list(DEFAULT_VOICES))
    run.add_argument("--min-seconds", type=float, default=30.0)
    run.add_argument("--greedy-requests", type=int, default=4)
    run.add_argument("--concurrency", default="1,2,4,8")
    run.add_argument("--requests", type=int, default=16)
    run.add_argument(
        "--stage-args",
        default="--lm.engine.mem_fraction_static 0.5",
        help="extra pipeline overrides",
    )
    diff = commands.add_parser("compare")
    diff.add_argument("main_dir")
    diff.add_argument("branch_dir")
    return parser.parse_args()


if __name__ == "__main__":
    parsed = parse_args()
    if parsed.command == "run":
        asyncio.run(run_suite(parsed))
    else:
        compare(parsed)
