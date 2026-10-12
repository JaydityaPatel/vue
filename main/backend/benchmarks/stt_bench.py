"""Benchmark faster-whisper small.en on a 16 kHz mono WAV."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from common import ensure_project_imports, hardware_info, sample_paths, write_json


_model: Any = None
_runtime: dict[str, str] = {}


def load_model() -> Any:
    global _model, _runtime
    if _model is not None:
        return _model
    from faster_whisper import WhisperModel

    try:
        _model = WhisperModel("small.en", device="cuda", compute_type="float16")
        _runtime = {"device": "cuda", "compute_type": "float16"}
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"CUDA faster-whisper initialization failed ({exc}); retrying CPU int8.")
        _model = WhisperModel("small.en", device="cpu", compute_type="int8")
        _runtime = {"device": "cpu", "compute_type": "int8", "cuda_error": str(exc)}
    return _model


def transcribe_audio(audio_path: str) -> tuple[str, float]:
    global _model, _runtime
    model = load_model()
    started = time.perf_counter()
    try:
        segments, _ = model.transcribe(audio_path, language="en", beam_size=1, vad_filter=False)
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
    except RuntimeError as exc:
        message = str(exc).lower()
        if _runtime.get("device") != "cuda" or not any(
            marker in message for marker in ("cuda", "cudnn", "cublas")
        ):
            raise
        from faster_whisper import WhisperModel

        print(f"CUDA inference failed ({exc}); reloading small.en on CPU int8.")
        _model = WhisperModel("small.en", device="cpu", compute_type="int8")
        _runtime = {"device": "cpu", "compute_type": "int8", "cuda_error": str(exc)}
        started = time.perf_counter()
        segments, _ = _model.transcribe(audio_path, language="en", beam_size=1, vad_filter=False)
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
    return transcript, time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", nargs="?", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "stt_result.json")
    args = parser.parse_args()
    samples = [args.audio] if args.audio else sample_paths()
    load_model()
    # First transcription materializes the lazy generator and is a warmup.
    warmup_transcript, warmup_seconds = transcribe_audio(str(samples[0]))
    measurements = []
    for sample in samples:
        transcript, seconds = transcribe_audio(str(sample))
        measurements.append({
            "audio": sample.name,
            "transcript": transcript,
            "latency_seconds": seconds,
        })
    result = {
        "stage": "local_stt",
        "model": "faster-whisper small.en",
        "runtime": _runtime,
        "warmup_seconds": warmup_seconds,
        "warmup_transcript": warmup_transcript,
        "measurements": measurements,
        "hardware": hardware_info(),
    }
    write_json(args.output, result)
    print(result)


if __name__ == "__main__":
    main()
