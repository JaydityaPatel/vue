"""Shared helpers for reproducible, standalone voice benchmarks."""

from __future__ import annotations

import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BENCH_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent
SAMPLES_DIR = BENCH_DIR / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
TASK_TEMP_DIR = BENCH_DIR / ".tmp"
TASK_TEMP_DIR.mkdir(parents=True, exist_ok=True)
os.environ["TEMP"] = str(TASK_TEMP_DIR)
os.environ["TMP"] = str(TASK_TEMP_DIR)
tempfile.tempdir = str(TASK_TEMP_DIR)
SAMPLE_TEXT = (
    "I would begin by understanding the customer's needs, then work with the team "
    "to build a clear plan. After that, I would measure the result and share what "
    "we learned so we could improve the next release."
)
SHORT_TEXT = "I would first understand the problem, then work with my team to test a practical solution."
LONG_TEXT = (
    "In my previous role, a release was falling behind because several teams had different assumptions. "
    "I brought the owners together, listed the open decisions, and divided the work into small milestones. "
    "We reviewed progress each morning and raised risks early. The release shipped on the revised date, "
    "and we used the same checklist for later projects. The most useful lesson was to make ownership and "
    "success measures clear before implementation begins."
)


def ensure_project_imports() -> None:
    backend_path = str(BACKEND_DIR)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


def ensure_wav_sample(path: Path | None = None) -> Path:
    """Create deterministic speech-like audio if no recording was supplied.

    This fallback is deliberately labeled synthetic. Actual spoken samples should
    be preferred when available; accuracy metrics are not inferred from this tone.
    """
    target = path or SAMPLES_DIR / "synthetic_fallback.wav"
    if target.exists():
        return target
    rate = 16_000
    seconds = 2.4
    with wave.open(str(target), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        frames = bytearray()
        for index in range(int(rate * seconds)):
            t = index / rate
            # Two voiced bands separated by a natural pause.
            active = t < 0.95 or 1.35 <= t < 2.25
            if active:
                envelope = min(1.0, (t % 0.18) / 0.025, (0.18 - (t % 0.18)) / 0.025)
                frequency = 175 + 24 * __import__("math").sin(2 * __import__("math").pi * 3.2 * t)
                sample = int(5_000 * max(0, envelope) * __import__("math").sin(2 * __import__("math").pi * frequency * t))
            else:
                sample = 0
            frames.extend(int(sample).to_bytes(2, "little", signed=True))
        output.writeframes(frames)
    return target


def sample_paths() -> list[Path]:
    candidates = sorted(
        path for path in SAMPLES_DIR.glob("*.wav")
        if path.name != "synthetic_fallback.wav"
    )
    if not candidates:
        candidates = [ensure_wav_sample()]
    return candidates[:3]


def gpu_snapshot() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        name, used, total, utilization = completed.stdout.strip().split(",", 3)
        return {
            "name": name.strip(),
            "memory_used_mib": int(used.strip()),
            "memory_total_mib": int(total.strip()),
            "utilization_percent": int(utilization.strip()),
        }
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"available": False}


def hardware_info() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_logical_cores": os.cpu_count(),
        "gpu": gpu_snapshot(),
    }


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    return {
        "min": min(values),
        "max": max(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
    }


def timed(function: Any, *args: Any, **kwargs: Any) -> tuple[Any, float]:
    started = time.perf_counter()
    value = function(*args, **kwargs)
    return value, time.perf_counter() - started


def write_json(path: Path, data: dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
