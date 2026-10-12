"""Run five staged local and Gemini-hosted voice-pipeline trials."""

from __future__ import annotations

import argparse
import asyncio
from io import BytesIO
import statistics
import sys
import time
import wave
from pathlib import Path
from typing import Callable

from common import (
    BACKEND_DIR,
    LONG_TEXT,
    SAMPLE_TEXT,
    ensure_wav_sample,
    gpu_snapshot,
    hardware_info,
    sample_paths,
    write_json,
)
from stt_bench import load_model, transcribe_audio
from tts_bench import KokoroSynthesizer

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.llm.router import LLMRouter  # noqa: E402
from gemini_voice_bench import STT_MODEL, TTS_MODEL, _audio_part, _router_for

TRIALS = 5
PROMPT_TEMPLATE = "Reply in one concise sentence to this interview answer: {answer}"


def _stream_trial(answer: str, model: str = "gemini-3.8-flash") -> dict:
    async def collect() -> tuple[float, float, str]:
        router = LLMRouter(
            rate_limits_path=settings.rate_limits_path,
            providers={"gemini": __import__("app.llm.providers.gemini", fromlist=["GeminiProvider"]).GeminiProvider()},
            max_retries_per_model=0,
        )
        router.routes["phase3_e2e_stream"] = [model]
        start = time.perf_counter()
        first = None
        chunks = []
        async for chunk in router.stream(
            task="phase3_e2e_stream",
            prompt=PROMPT_TEMPLATE.format(answer=answer),
            thinking_level="LOW",
        ):
            if first is None:
                first = time.perf_counter() - start
            chunks.append(chunk)
        return first or (time.perf_counter() - start), time.perf_counter() - start, "".join(chunks)

    first, total, text = asyncio.run(collect())
    return {"ttft_seconds": first, "total_seconds": total, "text": text}


def _local_trial(audio_path: Path, tts: KokoroSynthesizer) -> dict:
    before = gpu_snapshot()
    start = time.perf_counter()
    transcript, stt_seconds = transcribe_audio(str(audio_path))
    llm = None
    llm_error = None
    if settings.gemini_api_key:
        try:
            llm = _stream_trial(transcript)
        except Exception as exc:
            llm_error = f"{type(exc).__name__}: {exc}"
    else:
        llm_error = "GEMINI_API_KEY is not configured"
    reply = llm["text"] if llm else "I would clarify the goal and agree on the next step."
    audio, tts_seconds = tts.synthesize_first_chunk(reply)
    end_to_end = time.perf_counter() - start if llm else None
    after = gpu_snapshot()
    return {
        "stt_seconds": stt_seconds,
        "llm_ttft_seconds": llm["ttft_seconds"] if llm else None,
        "llm_total_seconds": llm["total_seconds"] if llm else None,
        "tts_first_audio_seconds": tts_seconds,
        "end_to_end_seconds": end_to_end,
        "status": "success" if llm else "partial",
        "llm_error": llm_error,
        "transcript": transcript,
        "reply": reply,
        "tts_audio_bytes": len(audio),
        "gpu_before": before,
        "gpu_after": after,
    }


async def _hosted_trial(audio_path: Path) -> dict:
    from gemini_voice_bench import transcribe, synthesize

    start = time.perf_counter()
    stt = await transcribe(audio_path)
    if stt.get("status") != "success":
        return {"status": stt.get("status"), "error": stt.get("error")}
    router = await _router_for("gemini-3.8-flash")
    llm_start = time.perf_counter()
    response = await router.run(
        task="phase3_hosted_audio",
        prompt=PROMPT_TEMPLATE.format(answer=stt["text"]),
    )
    llm_seconds = time.perf_counter() - llm_start
    try:
        audio, tts_seconds = await synthesize(response.text)
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "status": "success",
        "stt_seconds": stt["latency_seconds"],
        "llm_ttft_seconds": llm_seconds,
        "llm_total_seconds": llm_seconds,
        "tts_first_audio_seconds": tts_seconds,
        "end_to_end_seconds": time.perf_counter() - start,
        "transcript": stt["text"],
        "reply": response.text,
        "tts_audio_bytes": len(audio),
    }


def _stage_summary(rows: list[dict], keys: list[str]) -> dict:
    summary = {}
    for key in keys:
        values = [row[key] for row in rows if row.get(key) is not None]
        summary[key] = (
            {name: round(value, 4) for name, value in _stats(values).items()}
            if values else {"status": "unavailable"}
        )
    return summary


def _stats(values: list[float]) -> dict:
    return {
        "min": min(values),
        "max": max(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
    }


def _print_table(title: str, summary: dict) -> None:
    print(f"\n{title}")
    print(f"{'Stage':32} {'min':>9} {'max':>9} {'mean':>9} {'median':>9}")
    print("-" * 73)
    for stage, values in summary.items():
        if "mean" not in values:
            print(f"{stage:32} {'unavailable':>9}")
        else:
            print(
                f"{stage:32} {values['min']:>9.4f} {values['max']:>9.4f} "
                f"{values['mean']:>9.4f} {values['median']:>9.4f}"
            )


def _render_text(title: str, summary: dict, rows: list[dict], status: str) -> str:
    lines = [
        title,
        f"Status: {status}",
        f"Hardware: {hardware_info()}",
        f"Trials requested: {TRIALS}; trials completed: {len(rows)}",
        "Timings exclude model initialization/warmup; values are seconds. TTS is time to first Kokoro stream chunk.",
        "",
        f"{'Stage':32} {'min':>9} {'max':>9} {'mean':>9} {'median':>9}",
        "-" * 73,
    ]
    for stage, values in summary.items():
        if "mean" not in values:
            lines.append(f"{stage:32} unavailable")
        else:
            lines.append(
                f"{stage:32} {values['min']:>9.4f} {values['max']:>9.4f} "
                f"{values['mean']:>9.4f} {values['median']:>9.4f}"
            )
    lines.extend(["", "Individual trials:"])
    for idx, row in enumerate(rows, 1):
        lines.append(f"{idx}. {row}")
    if not rows:
        lines.append("No measurements: " + status)
    return "\n".join(lines) + "\n"


def _create_spoken_fixture(tts: KokoroSynthesizer) -> Path:
    import numpy as np

    phrases = [
        "I would begin by understanding the customer's needs.",
        "Then I would agree on a plan with the team and measure the result.",
    ]
    speech_parts = []
    for phrase in phrases:
        wav_bytes, _ = tts.synthesize(phrase)
        with wave.open(BytesIO(wav_bytes), "rb") as wav:
            source_rate = wav.getframerate()
            source = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32)
        target_length = round(len(source) * 16_000 / source_rate)
        source_positions = np.arange(len(source), dtype=np.float32)
        resampled = np.interp(
            np.linspace(0, max(0, len(source) - 1), target_length, dtype=np.float32),
            source_positions,
            source,
        ).astype("<i2")
        speech_parts.append(resampled)
    combined = np.concatenate([
        speech_parts[0],
        np.zeros(8_000, dtype="<i2"),
        speech_parts[1],
    ])
    output_path = Path(__file__).parent / "samples" / "kokoro_synthetic.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(combined.tobytes())
    return output_path


def run_local(samples: list[Path]) -> tuple[list[dict], str, list[Path]]:
    try:
        tts = KokoroSynthesizer()
        tts.synthesize("Model initialization warmup.")
        if all(sample.name == "synthetic_fallback.wav" for sample in samples):
            samples = [_create_spoken_fixture(tts)]
            print(f"Generated synthetic spoken sample with Kokoro: {samples[0]}")
        load_model()
        from vad_bench import detect_speech_segments

        detect_speech_segments(str(samples[0]))
        transcribe_audio(str(samples[0]))  # warmup
    except Exception as exc:
        return [], f"unavailable during initialization: {type(exc).__name__}: {exc}", samples
    rows = []
    for index in range(TRIALS):
        sample = samples[index % len(samples)]
        try:
            rows.append(_local_trial(sample, tts))
        except Exception as exc:
            rows.append({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
    status = "completed" if all(row.get("status") == "success" for row in rows) else "partial: local stages ran, Gemini stream was unavailable or failed"
    return rows, status, samples


async def run_hosted(samples: list[Path]) -> tuple[list[dict], str]:
    if not settings.gemini_api_key:
        return [], "unavailable: GEMINI_API_KEY is not configured"
    rows = []
    for index in range(TRIALS):
        sample = samples[index % len(samples)]
        try:
            rows.append(await _hosted_trial(sample))
        except Exception as exc:
            rows.append({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
    successes = [row for row in rows if row.get("status") == "success"]
    return successes, "completed" if successes else "all hosted trials failed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path)
    args = parser.parse_args()
    samples = [args.audio] if args.audio else sample_paths()
    print(f"Benchmark input: {samples[0].name} (Kokoro TTS-generated if no user recording is present)")
    gpu_before = gpu_snapshot()
    local_rows, local_status, samples = run_local(samples)
    sample_name = samples[0].name
    gpu_after_local = gpu_snapshot()
    local_keys = ["stt_seconds", "llm_ttft_seconds", "llm_total_seconds", "tts_first_audio_seconds", "end_to_end_seconds"]
    local_summary = _stage_summary(local_rows, local_keys)
    local_text = _render_text("PHASE 3 LOCAL PIPELINE BENCHMARK", local_summary, local_rows, local_status)
    local_path = Path(__file__).parent / "results_local.txt"
    local_path.write_text(local_text, encoding="utf-8")
    _print_table("Local pipeline", local_summary)
    print(f"GPU before={gpu_before}; after local={gpu_after_local}")

    hosted_rows, hosted_status = asyncio.run(run_hosted(samples))
    hosted_summary = _stage_summary(hosted_rows, local_keys)
    hosted_text = _render_text("PHASE 3 GEMINI-HOSTED PIPELINE BENCHMARK", hosted_summary, hosted_rows, hosted_status)
    hosted_path = Path(__file__).parent / "results_gemini_hosted.txt"
    hosted_path.write_text(hosted_text, encoding="utf-8")
    _print_table("Gemini-hosted pipeline", hosted_summary)
    hosted_path.write_text(
        hosted_text + f"\nGPU before all runs={gpu_before}; after local={gpu_after_local}; after hosted={gpu_snapshot()}\n",
        encoding="utf-8",
    )
    write_json(Path(__file__).parent / "results.json", {
        "sample_audio": sample_name,
        "hardware": hardware_info(),
        "gpu_before": gpu_before,
        "gpu_after_local": gpu_after_local,
        "local": {"status": local_status, "rows": local_rows, "summary": local_summary},
        "gemini_hosted": {"status": hosted_status, "rows": hosted_rows, "summary": hosted_summary},
    })
    print(f"Reports written to {local_path} and {hosted_path}")


if __name__ == "__main__":
    main()
