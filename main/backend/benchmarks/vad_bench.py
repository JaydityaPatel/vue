"""Measure Silero VAD segmentation on mono 16 kHz WAV files."""

from __future__ import annotations

import argparse
import array
import time
import wave
from pathlib import Path

from common import hardware_info, sample_paths, write_json

_model = None


def detect_speech_segments(audio_path: str) -> tuple[list[tuple[float, float]], float]:
    import numpy as np
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad

    global _model
    if _model is None:
        _model = load_silero_vad()
    with wave.open(audio_path, "rb") as wav:
        if wav.getframerate() != 16_000 or wav.getnchannels() != 1:
            raise ValueError("VAD benchmark input must be 16 kHz mono WAV")
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    audio = torch.from_numpy(samples)
    started = time.perf_counter()
    timestamps = get_speech_timestamps(audio, _model, sampling_rate=16_000)
    latency = time.perf_counter() - started
    segments = [
        (item["start"] / 16_000, item["end"] / 16_000)
        for item in timestamps
    ]
    return segments, latency


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", nargs="?", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "vad_result.json")
    args = parser.parse_args()
    samples = [args.audio] if args.audio else sample_paths()
    measurements = []
    for sample in samples:
        detect_speech_segments(str(sample))  # lazy import/model initialization warmup
        segments, seconds = detect_speech_segments(str(sample))
        measurements.append({"audio": sample.name, "segments": segments, "latency_seconds": seconds})
    result = {
        "stage": "local_vad",
        "model": "Silero VAD",
        "measurements": measurements,
        "hardware": hardware_info(),
    }
    write_json(args.output, result)
    print(result)


if __name__ == "__main__":
    main()
