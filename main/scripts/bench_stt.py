"""Benchmark faster-whisper over a folder of WAV files."""

from __future__ import annotations

import argparse
import math
import statistics
import time
from pathlib import Path
from typing import Any


CUDA_ERROR_MARKERS = ("cuda", "cublas", "cudnn")


def transcribe(model: Any, wav_path: Path) -> str:
    # faster-whisper is lazy: consume the segments so timing includes inference.
    segments, _ = model.transcribe(
        str(wav_path),
        language="en",
        beam_size=1,
        vad_filter=False,
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


def load_model(wav_path: Path, model_name: str, requested_device: str | None) -> tuple[Any, str, str]:
    from faster_whisper import WhisperModel

    device = requested_device or "cuda"
    compute_type = "int8" if device == "cpu" else "int8_float16"
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        transcribe(model, wav_path)  # Probe real inference; CUDA errors can be lazy.
        actual_device = str(model.model.device)
        actual_compute_type = str(model.model.compute_type)
        if device == "cuda" and actual_device != "cuda":
            raise RuntimeError(f"Requested CUDA but CTranslate2 reports device={actual_device}")
        return model, actual_device, actual_compute_type
    except (RuntimeError, ValueError, OSError) as exc:
        message = str(exc)
        if device != "cuda" or requested_device == "cuda" or not any(
            marker in message.lower() for marker in CUDA_ERROR_MARKERS
        ):
            raise
        print(f"CUDA inference unavailable ({message}); retrying with CPU int8.")
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        transcribe(model, wav_path)  # Warm the CPU path outside the timed trials.
        return model, str(model.model.device), str(model.model.compute_type)


def percentile_90(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(0.9 * len(ordered)) - 1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav_folder", type=Path, help="Folder containing WAV clips")
    parser.add_argument("--model", default="small.en", help="Whisper model (default: small.en)")
    parser.add_argument("--device", choices=("cuda", "cpu"), help="Explicit device; CUDA errors do not fall back")
    args = parser.parse_args()

    if not args.wav_folder.is_dir():
        parser.error(f"not a folder: {args.wav_folder}")
    wav_files = sorted(
        (path for path in args.wav_folder.iterdir() if path.is_file() and path.suffix.lower() == ".wav"),
        key=lambda path: path.name.lower(),
    )
    if not wav_files:
        parser.error(f"no WAV files found in {args.wav_folder}")

    model, device, compute_type = load_model(wav_files[0], args.model, args.device)
    print(f"Model: {args.model} | device: {device} | compute_type: {compute_type}")
    print(f"CUDA actually used: {'YES' if device == 'cuda' else 'NO'}")
    print(f"Warm-up: {wav_files[0].name} (excluded from timings)")
    print("Timed transcription:")

    timings_ms: list[float] = []
    for wav_path in wav_files:
        started = time.perf_counter()
        transcribe(model, wav_path)
        elapsed_ms = (time.perf_counter() - started) * 1000
        timings_ms.append(elapsed_ms)
        print(f"  {wav_path.name}: {elapsed_ms:.1f} ms")

    print("\nSummary (ms):")
    print(f"  files:  {len(timings_ms)}")
    print(f"  min:    {min(timings_ms):.1f}")
    print(f"  max:    {max(timings_ms):.1f}")
    print(f"  mean:   {statistics.mean(timings_ms):.1f}")
    print(f"  median: {statistics.median(timings_ms):.1f}")
    print(f"  p90:    {percentile_90(timings_ms):.1f}")


if __name__ == "__main__":
    main()
