# SPDX-License-Identifier: Apache-2.0
"""P2-1 Depformer micro-benchmark (not committed), real weights on one GPU.

    PYTHONPATH=. python p2-1-depformer-bench.py --checkpoint nvidia/personaplex-7b-v1

For N requests in one LM step, main calls generate N times at batch 1; the
branch calls it once at batch N. The Depformer code is the same on both
checkouts, so this script times both call patterns directly. It also reports
teacher-forced logits of a batched call vs each row alone, in bf16 and fp32.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import torch
from safetensors import safe_open
from torch.autograd import DeviceType
from torch.profiler import ProfilerActivity, profile

from sglang_omni.models.personaplex.architecture import (
    AUDIO_CARD,
    DEFAULT_AUDIO_TEMPERATURE,
    DEFAULT_AUDIO_TOP_K,
    DEPFORMER,
    MOSHI_WEIGHTS_NAME,
    TEXT_CARD,
)
from sglang_omni.models.personaplex.components.depformer import Depformer
from sglang_omni.models.personaplex.sampling import AudioSampling, sample_token
from sglang_omni.utils.checkpoint import resolve_checkpoint

WARMUP_ITERATIONS = 10
TIMED_ITERATIONS = 50


def load_depformer(checkpoint: str, dtype: torch.dtype) -> Depformer:
    path = Path(resolve_checkpoint(checkpoint)) / MOSHI_WEIGHTS_NAME
    with safe_open(str(path), framework="pt", device="cpu") as weights_file:
        weights = {
            name: weights_file.get_tensor(name)
            for name in weights_file.keys()
            if name.startswith(("depformer", "linears."))
        }
    model = Depformer(DEPFORMER)
    model.load_reference_weights(weights)
    return model.to(device="cuda", dtype=dtype).eval()


def wall_ms(run_once) -> float:
    for _ in range(WARMUP_ITERATIONS):
        run_once()
    torch.cuda.synchronize()
    start = time.perf_counter()
    for _ in range(TIMED_ITERATIONS):
        run_once()
    torch.cuda.synchronize()
    return (time.perf_counter() - start) / TIMED_ITERATIONS * 1e3


def device_ops(run_once) -> int:
    run_once()
    torch.cuda.synchronize()
    with profile(activities=[ProfilerActivity.CUDA]) as profiler:
        run_once()
        torch.cuda.synchronize()
    return sum(1 for event in profiler.events() if event.device_type == DeviceType.CUDA)


def benchmark(model: Depformer, levels: list[int]) -> None:
    max_batch = max(levels)
    dtype = next(model.parameters()).dtype
    text_B = torch.randint(0, TEXT_CARD, (max_batch,), device="cuda")
    hidden_BD = torch.randn(max_batch, DEPFORMER.input_dim, device="cuda", dtype=dtype)
    free_BK = torch.full((max_batch, DEPFORMER.steps), -1, device="cuda")
    sampling = AudioSampling(DEFAULT_AUDIO_TEMPERATURE, DEFAULT_AUDIO_TOP_K)

    def sample(logits: torch.Tensor) -> torch.Tensor:
        return sample_token(logits, sampling)

    print(f"\n{dtype}: one frame for N requests (ms wall, CUDA device ops)")
    print("   N  per-request ms  batched ms  speedup  per-request ops  batched ops")
    for level in levels:

        def per_request() -> None:
            for row in range(level):
                model.generate(
                    text_B[row : row + 1],
                    hidden_BD[row : row + 1],
                    free_BK[row : row + 1],
                    sample,
                )

        def batched() -> None:
            model.generate(text_B[:level], hidden_BD[:level], free_BK[:level], sample)

        with torch.inference_mode():
            per_request_ms, batched_ms = wall_ms(per_request), wall_ms(batched)
            per_request_ops, batched_ops = device_ops(per_request), device_ops(batched)
        print(
            f"{level:4d} {per_request_ms:15.2f} {batched_ms:11.2f} "
            f"{per_request_ms / batched_ms:8.2f} {per_request_ops:16d} {batched_ops:12d}"
        )


def logit_diff(model: Depformer, batch: int) -> None:
    dtype = next(model.parameters()).dtype
    generator = torch.Generator(device="cuda").manual_seed(0)
    text_B = torch.randint(0, TEXT_CARD, (batch,), device="cuda", generator=generator)
    hidden_BD = torch.randn(
        batch, DEPFORMER.input_dim, device="cuda", generator=generator
    ).to(dtype)
    forced_BK = torch.randint(
        0, AUDIO_CARD, (batch, DEPFORMER.steps), device="cuda", generator=generator
    )

    def logits_of(rows: slice) -> torch.Tensor:
        captured = []

        def capture(logits: torch.Tensor) -> torch.Tensor:
            captured.append(logits.clone())
            return logits.argmax(dim=-1)

        with torch.inference_mode():
            model.generate(text_B[rows], hidden_BD[rows], forced_BK[rows], capture)
        return torch.stack(captured, dim=1)

    batched = logits_of(slice(0, batch))
    per_row = torch.cat([logits_of(slice(row, row + 1)) for row in range(batch)])
    max_diff = (batched - per_row).abs().max().item()
    scale = per_row.abs().max().item()
    print(
        f"{dtype}, B={batch}, teacher-forced: max |logit diff| batched vs per-row "
        f"{max_diff:.3e} (max |logit| {scale:.3e}, relative {max_diff / scale:.3e})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default="nvidia/personaplex-7b-v1")
    parser.add_argument("--levels", default="1,2,4,8,16")
    args = parser.parse_args()
    levels = [int(level) for level in args.levels.split(",")]
    torch.backends.cuda.matmul.allow_tf32 = False
    print(
        f"gpu={torch.cuda.get_device_name(0)} torch={torch.__version__} "
        f"cuda={torch.version.cuda}"
    )
    bf16_model = load_depformer(args.checkpoint, torch.bfloat16)
    benchmark(bf16_model, levels)
    print()
    logit_diff(bf16_model, batch=8)
    del bf16_model
    fp32_model = load_depformer(args.checkpoint, torch.float32)
    logit_diff(fp32_model, batch=8)


if __name__ == "__main__":
    main()
