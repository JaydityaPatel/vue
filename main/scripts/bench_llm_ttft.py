"""Measure LLMRouter time-to-first-token for short interview answers."""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import statistics
import sys
import time
from pathlib import Path


PROMPTS = [
    "Tell me about yourself.",
    "I have three years of experience with Python and React.",
    "I led a small team through a difficult production migration.",
    "I improved our API response time by profiling database queries.",
    "I enjoy mentoring junior developers and reviewing code.",
    "A project failure taught me to validate assumptions earlier.",
    "I chose this role because it combines product thinking and engineering.",
    "My strongest skill is explaining technical tradeoffs clearly.",
    "I resolved a disagreement by comparing options against user needs.",
    "In my next role, I want to own larger systems end to end.",
]
TASK = "latency_spike_turn"


def percentile_90(values: list[float]) -> float:
    return sorted(values)[math.ceil(0.9 * len(values)) - 1]


async def run_benchmark(router, answers: list[str], originals) -> list[tuple[float, str]]:
    results: list[tuple[float, str]] = []
    for index, answer in enumerate(answers, 1):
        served: list[str] = []

        # Capture the actual configured provider model that emits the first token,
        # including router fallback, without changing the router implementation.
        for provider_name, provider in router.providers.items():
            if not hasattr(provider, "generate_stream"):
                continue
            original = provider.generate_stream

            async def capture(*, model, prompt, system_prompt=None, thinking_level=None,
                              response_schema=None, _original=original,
                              _provider_name=provider_name, _served=served):
                async for chunk in _original(
                    model=model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    thinking_level=thinking_level,
                    response_schema=response_schema,
                ):
                    if chunk and not _served:
                        _served.append(f"{_provider_name}:{model}")
                    yield chunk

            provider.generate_stream = capture

        prompt = (
            "The following is a candidate's interview answer. Respond with one concise, "
            "relevant follow-up interview question. Candidate answer: " + answer
        )
        started = time.perf_counter()
        first_token_ms: float | None = None
        try:
            async for token in router.stream(
                task=TASK,
                prompt=prompt,
                system_prompt="You are conducting a professional job interview.",
                thinking_level="LOW",
            ):
                if token and first_token_ms is None:
                    first_token_ms = (time.perf_counter() - started) * 1000
                # Drain the response after recording TTFT to close provider streams cleanly.
        finally:
            for provider in router.providers.values():
                if id(provider) in originals:
                    provider.generate_stream = originals[id(provider)]

        if first_token_ms is None:
            raise RuntimeError(f"Call {index} completed without a text token")
        model = served[0] if served else "unknown"
        results.append((first_token_ms, model))
        print(f"{index:02d}. {first_token_ms:.1f} ms | {model} | {answer}")
    return results


async def async_main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "backend",
        help="Backend folder containing app/ (default: project backend)",
    )
    args = parser.parse_args()
    backend_dir = args.backend_dir.resolve()
    if not (backend_dir / "app").is_dir():
        parser.error(f"backend app folder not found: {backend_dir / 'app'}")
    sys.path.insert(0, str(backend_dir))

    if not os.getenv("GEMINI_API_KEY"):
        example_env = backend_dir / ".env.example"
        if example_env.is_file():
            for line in example_env.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("GEMINI_API_KEY="):
                    os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip("\"'")
                    break

    from app.llm.router import LLMRouter

    router = LLMRouter()
    if TASK not in router.routes:
        # This benchmark remains isolated from application config. Reuse the
        # configured Flash-class summarize fallback chain for this run only.
        if "summarize" not in router.routes:
            raise RuntimeError(f"No {TASK!r} or summarize route in rate_limits.yaml")
        router.routes[TASK] = list(router.routes["summarize"])
        print(f"{TASK} is absent from rate_limits.yaml; using in-memory summarize route: {router.routes[TASK]}")
    else:
        print(f"Route {TASK}: {router.routes[TASK]}")

    originals = {
        id(provider): provider.generate_stream
        for provider in router.providers.values()
        if hasattr(provider, "generate_stream")
    }
    print("Timing request start through first nonempty streamed token; remaining text is drained afterward.")
    results = await run_benchmark(router, PROMPTS, originals)
    values = [elapsed for elapsed, _ in results]
    print("\nTTFT summary (ms):")
    print(f"  calls:  {len(values)}")
    print(f"  mean:   {statistics.mean(values):.1f}")
    print(f"  median: {statistics.median(values):.1f}")
    print(f"  p90:    {percentile_90(values):.1f}")


if __name__ == "__main__":
    asyncio.run(async_main())
