"""Hosted Gemini STT/TTS comparison, routed through LLMRouter."""

from __future__ import annotations

import argparse
import asyncio
import base64
import statistics
import sys
import time
import wave
from pathlib import Path

from common import BACKEND_DIR, SAMPLE_TEXT, ensure_wav_sample, hardware_info, write_json

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.llm.router import LLMRouter  # noqa: E402

STT_MODEL = "gemini-3.5-transcribe"
TTS_MODEL = "gemini-3.8-flash-tts"


def _audio_part(path: Path) -> dict:
    with wave.open(str(path), "rb") as audio:
        if audio.getframerate() != 16_000 or audio.getnchannels() != 1:
            raise ValueError("Hosted STT benchmark expects a 16 kHz mono WAV")
        payload = base64.b64encode(audio.readframes(audio.getnframes())).decode("ascii")
    return {"inlineData": {"mimeType": "audio/pcm;rate=16000", "data": payload}}


async def _router_for(model: str) -> LLMRouter:
    router = LLMRouter(
        rate_limits_path=settings.rate_limits_path,
        providers={"gemini": __import__("app.llm.providers.gemini", fromlist=["GeminiProvider"]).GeminiProvider()},
        max_retries_per_model=0,
    )
    router.routes["phase3_hosted_audio"] = [model]
    return router


async def transcribe(path: Path) -> dict:
    if not settings.gemini_api_key:
        return {"status": "unavailable", "error": "GEMINI_API_KEY is not configured"}
    router = await _router_for(STT_MODEL)
    started = time.perf_counter()
    try:
        response = await router.run(
            task="phase3_hosted_audio",
            prompt="Transcribe the audio exactly. Return only the spoken words.",
            content_parts=[_audio_part(path)],
        )
        return {"status": "success", "text": response.text, "latency_seconds": time.perf_counter() - started}
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}", "latency_seconds": time.perf_counter() - started}


async def synthesize(text: str) -> tuple[bytes, float]:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    router = await _router_for(TTS_MODEL)
    started = time.perf_counter()
    response = await router.run(
        task="phase3_hosted_audio",
        prompt=text,
        response_modalities=["AUDIO"],
        speech_config={"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}},
    )
    if not response.audio_bytes:
        raise RuntimeError("Gemini TTS response did not contain audio")
    return response.audio_bytes, time.perf_counter() - started


async def run(audio_path: Path | None = None) -> dict:
    sample = audio_path or ensure_wav_sample()
    stt_runs = [await transcribe(sample) for _ in range(3)] if settings.gemini_api_key else [await transcribe(sample)]
    tts_runs = []
    if settings.gemini_api_key:
        for text in ("This is a short hosted speech benchmark.", SAMPLE_TEXT):
            try:
                audio, seconds = await synthesize(text)
                tts_runs.append({"status": "success", "latency_seconds": seconds, "audio_bytes": len(audio), "word_count": len(text.split())})
            except Exception as exc:
                tts_runs.append({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
    else:
        tts_runs.append({"status": "unavailable", "error": "GEMINI_API_KEY is not configured"})
    return {
        "stt_model": STT_MODEL,
        "stt_runs": stt_runs,
        "stt_latency_stats": _stats([row["latency_seconds"] for row in stt_runs if row.get("status") == "success"]),
        "tts_model": TTS_MODEL,
        "tts_runs": tts_runs,
        "tts_latency_stats": _stats([row["latency_seconds"] for row in tts_runs if row.get("status") == "success"]),
        "sample_audio": sample.name,
    }


def _stats(values: list[float]) -> dict:
    if not values:
        return {}
    return {"min": min(values), "max": max(values), "mean": statistics.mean(values), "median": statistics.median(values)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", nargs="?", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "gemini_voice_result.json")
    args = parser.parse_args()
    results = asyncio.run(run(args.audio))
    payload = {"stage": "gemini_hosted_voice", "results": results, "hardware": hardware_info()}
    write_json(args.output, payload)
    print(payload)


if __name__ == "__main__":
    main()
