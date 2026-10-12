"""Measure router-routed Gemini streaming time-to-first-text and completion."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from common import BACKEND_DIR, hardware_info, write_json

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.llm.router import LLMRouter  # noqa: E402


PROMPT = "In one sentence, describe how you would resolve a disagreement with a teammate."
MODELS = ("gemini-3.8-flash", "gemini-2.5-flash")


async def measure_model(model: str) -> dict:
    if not settings.gemini_api_key:
        return {"model": model, "status": "unavailable", "error": "GEMINI_API_KEY is not configured"}
    router = LLMRouter(
        rate_limits_path=settings.rate_limits_path,
        providers={"gemini": __import__("app.llm.providers.gemini", fromlist=["GeminiProvider"]).GeminiProvider()},
        max_retries_per_model=0,
    )
    router.routes["phase3_latency"] = [model]
    chunks: list[str] = []
    started = time.perf_counter()
    first_chunk = None
    try:
        async for chunk in router.stream(
            task="phase3_latency",
            prompt=PROMPT,
            thinking_level="LOW",
        ):
            if first_chunk is None:
                first_chunk = time.perf_counter() - started
            chunks.append(chunk)
        total = time.perf_counter() - started
        return {
            "model": model,
            "status": "success",
            "time_to_first_chunk_seconds": first_chunk,
            "total_generation_seconds": total,
            "text": "".join(chunks),
        }
    except Exception as exc:
        return {"model": model, "status": "error", "error": f"{type(exc).__name__}: {exc}"}


async def run() -> list[dict]:
    results = []
    for model in MODELS:
        # One warmup per model, then three short measurements to reduce API cost.
        warmup = await measure_model(model)
        trials = [await measure_model(model) for _ in range(3)] if warmup["status"] == "success" else []
        successful = [trial for trial in trials if trial["status"] == "success"]
        results.append({
            "model": model,
            "status": "success" if successful else warmup["status"],
            "warmup": warmup,
            "trials": trials,
            "ttfc_stats_seconds": _stats(trial["time_to_first_chunk_seconds"] for trial in successful),
            "total_stats_seconds": _stats(trial["total_generation_seconds"] for trial in successful),
        })
    return results


def _stats(values) -> dict:
    import statistics

    items = list(values)
    if not items:
        return {}
    return {"min": min(items), "max": max(items), "mean": statistics.mean(items), "median": statistics.median(items)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "llm_result.json")
    args = parser.parse_args()
    results = asyncio.run(run())
    payload = {"stage": "gemini_stream", "results": results, "hardware": hardware_info()}
    write_json(args.output, payload)
    print(payload)


if __name__ == "__main__":
    main()
