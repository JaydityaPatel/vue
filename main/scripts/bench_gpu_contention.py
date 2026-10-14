#!/usr/bin/env python
"""Provisional concurrent STT/Ollama/TTS stress check (not a target benchmark)."""
from __future__ import annotations

import argparse
import concurrent.futures
import ctypes
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
BENCHMARKS = BACKEND / "benchmarks"
for path in (str(BACKEND), str(BENCHMARKS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.config import settings  # noqa: E402
from app.llm.providers.ollama import OllamaProvider  # noqa: E402
from benchmarks.common import ensure_wav_sample, gpu_snapshot, hardware_info, write_json  # noqa: E402

WARNING = "MEASURED ON DEV HARDWARE — NOT REPRESENTATIVE OF TARGET HARDWARE (RTX 3050 4GB)"


def _windows_cpu_times() -> tuple[int, int, int] | None:
    if os.name != "nt":
        return None
    class FILETIME(ctypes.Structure):
        _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]
    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    combine = lambda value: (value.high << 32) | value.low
    return combine(idle), combine(kernel), combine(user)


def _cpu_percent(previous: tuple[int, int, int] | None) -> tuple[float | None, tuple[int, int, int] | None]:
    current = _windows_cpu_times()
    if current is not None:
        if previous is None:
            return None, current
        idle = current[0] - previous[0]
        total = (current[1] - previous[1]) + (current[2] - previous[2])
        return (100.0 * (1 - idle / total) if total else 0.0), current
    try:
        return os.getloadavg()[0] * 100 / (os.cpu_count() or 1), None
    except (AttributeError, OSError):
        return None, None


def _make_stt() -> tuple[Any, str]:
    from faster_whisper import WhisperModel
    model_name = settings.voice_stt_model
    requested_device = settings.voice_stt_device
    compute_type = settings.voice_stt_compute_type
    try:
        return WhisperModel(model_name, device=requested_device, compute_type=compute_type), f"{requested_device}/{compute_type}"
    except (RuntimeError, ValueError, OSError) as exc:
        if requested_device != "cuda":
            raise
        print(f"STT CUDA initialization failed ({type(exc).__name__}); contention run will use CPU int8.")
        return WhisperModel(model_name, device="cpu", compute_type="int8"), "cpu/int8 (CUDA init failed)"


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "mean": None, "max": None}
    return {"min": round(min(values), 1), "mean": round(statistics.mean(values), 1),
            "max": round(max(values), 1)}


def main() -> int:
    parser = argparse.ArgumentParser(description=WARNING)
    parser.add_argument("--duration", type=float, default=60.0, help="stress duration in seconds (default: 60)")
    parser.add_argument("--interval", type=float, default=1.0, help="resource sampling interval in seconds")
    parser.add_argument("--output", type=Path, default=ROOT / "backend" / "benchmarks" / "gpu_contention_dev.json")
    args = parser.parse_args()

    print(WARNING)
    print("This run checks concurrent code for failures only; its numbers are not a ship/target-hardware verdict.")
    temp_root = ROOT / "scripts" / ".tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = os.environ["TMP"] = str(temp_root)
    tempfile.tempdir = str(temp_root)
    wav_path = ensure_wav_sample()
    stt_model, stt_runtime = _make_stt()
    from tts_bench import KokoroSynthesizer
    # tts_bench imports ``common`` by its standalone-script name. That loads
    # a second copy of benchmarks.common, which resets tempfile.tempdir to
    # backend/benchmarks/.tmp. Restore the harness-local writable temp path
    # after that import and before phonemizer creates its temporary DLL copy.
    os.environ["TEMP"] = os.environ["TMP"] = str(temp_root)
    tempfile.tempdir = str(temp_root)
    tts = KokoroSynthesizer()
    ollama = OllamaProvider(timeout=max(180, settings.ollama_timeout_seconds), keep_alive="30m")
    # Warm all three components before the timed interval.
    with open(wav_path, "rb") as source:
        import wave
        with wave.open(source, "rb") as wav:
            stt_audio = wav.readframes(wav.getnframes())
    import numpy as np
    audio = np.frombuffer(stt_audio, dtype="<i2").astype(np.float32) / 32768.0
    try:
        list(stt_model.transcribe(audio, language="en", beam_size=1, vad_filter=False)[0])
    except RuntimeError as exc:
        if not stt_runtime.startswith("cuda") or not any(
            marker in str(exc).casefold() for marker in ("cuda", "cublas", "cudnn", "out of memory")
        ):
            raise
        print(f"STT CUDA warm-up failed ({type(exc).__name__}); reloading CPU int8 for this sanity run.")
        from faster_whisper import WhisperModel
        stt_model = WhisperModel(settings.voice_stt_model, device="cpu", compute_type="int8")
        stt_runtime = "cpu/int8 (CUDA warm-up failed)"
        list(stt_model.transcribe(audio, language="en", beam_size=1, vad_filter=False)[0])
    tts.synthesize_first_chunk("The warm-up checks that local speech generation is ready.")
    # Provider is async by contract; each worker owns an event loop/client call.
    import asyncio
    async def ollama_call():
        return await ollama.generate("qwen2.5:3b", "Reply in one short sentence: what is a good interview opening?")
    asyncio.run(ollama_call())

    deadline = time.monotonic() + max(1.0, args.duration)
    stop = threading.Event()
    lock = threading.Lock()
    measurements: dict[str, list[float]] = {"stt": [], "ollama": [], "tts": []}
    errors: list[dict[str, str]] = []
    samples: list[dict[str, Any]] = []
    first_cpu = _windows_cpu_times()
    base = time.monotonic()

    def record(stage: str, seconds: float) -> None:
        with lock:
            measurements[stage].append(seconds * 1000)

    def worker(stage: str, action) -> None:
        while not stop.is_set() and time.monotonic() < deadline:
            started = time.perf_counter()
            try:
                action()
                record(stage, time.perf_counter() - started)
            except Exception as exc:  # Record stage failure so the other stressors still run.
                with lock:
                    errors.append({"stage": stage, "error": f"{type(exc).__name__}: {exc}"[:400]})
                if any(marker in str(exc).casefold() for marker in ("out of memory", "oom", "cublas", "cuda")):
                    stop.set()
                break

    def run_stt() -> None:
        list(stt_model.transcribe(audio, language="en", beam_size=1, vad_filter=False)[0])

    def run_tts() -> None:
        tts.synthesize_first_chunk("A candidate described a project and how they measured its impact.")

    def run_ollama() -> None:
        asyncio.run(ollama_call())

    previous_cpu = first_cpu
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(worker, "stt", run_stt), pool.submit(worker, "ollama", run_ollama),
                   pool.submit(worker, "tts", run_tts)]
        while time.monotonic() < deadline and not stop.is_set():
            cpu, previous_cpu = _cpu_percent(previous_cpu)
            sample = {"elapsed_seconds": round(time.monotonic() - base, 2), "cpu_percent": cpu,
                      "gpu": gpu_snapshot()}
            with lock:
                samples.append(sample)
            time.sleep(max(0.1, args.interval))
        stop.set()
        for future in futures:
            future.result()

    all_measurements = {stage: _stats(values) for stage, values in measurements.items()}
    degradation = {}
    for stage, values in measurements.items():
        if len(values) >= 6:
            first_half = statistics.mean(values[:max(1, len(values) // 3)])
            last_half = statistics.mean(values[-max(1, len(values) // 3):])
            degradation[stage] = round((last_half / first_half - 1) * 100, 1) if first_half else None
        else:
            degradation[stage] = None
    result = {
        "warning": WARNING,
        "purpose": "concurrency crash/OOM sanity check only; no target-hardware performance conclusion",
        "requested_duration_seconds": args.duration,
        "actual_duration_seconds": round(time.monotonic() - base, 2),
        "stt_runtime": stt_runtime,
        "stt_input": "synthetic fallback WAV used for inference load; not an accuracy sample",
        "hardware": hardware_info(),
        "measurements_ms": all_measurements,
        "degradation_first_to_last_third_percent": degradation,
        "resource_samples": samples,
        "errors": errors,
        "oom_or_crash_flag": bool(errors) or stop.is_set() and time.monotonic() < deadline,
        "status": "success" if not errors else "partial_with_errors",
    }
    write_json(args.output, result)
    print(json.dumps({key: value for key, value in result.items() if key != "resource_samples"}, indent=2))
    print(f"Resource samples written to: {args.output}")
    print(WARNING)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
