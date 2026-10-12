import json
import time
import base64
from typing import Any
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.llm.providers.base import BaseProvider, LLMResponse, RateLimitError, ProviderError

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self.api_key = api_key or settings.gemini_api_key
        self.timeout = timeout
        self._client_factory = httpx.AsyncClient

    async def generate(
        self,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        thinking_level: str | None = None,
        response_schema: dict | None = None,
        content_parts: list[dict[str, Any]] | None = None,
        response_modalities: list[str] | None = None,
        speech_config: dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY is not configured")

        url = f"{GEMINI_BASE_URL}/{model}:generateContent"

        parts = [{"text": prompt}, *(content_parts or [])]
        contents = [{"role": "user", "parts": parts}]
        body: dict = {"contents": contents}

        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        generation_config: dict = {}
        if response_schema:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseJsonSchema"] = response_schema
        if temperature is not None:
            generation_config["temperature"] = temperature
        if thinking_level:
            # Keep thinking budget low for latency-sensitive per-turn calls.
            generation_config["thinkingConfig"] = {"thinkingLevel": thinking_level}
        if response_modalities:
            generation_config["responseModalities"] = response_modalities
        if speech_config:
            generation_config["speechConfig"] = speech_config
        if generation_config:
            body["generationConfig"] = generation_config

        start = time.perf_counter()
        try:
            async with self._client_factory(timeout=self.timeout) as client:
                resp = await client.post(url, headers={"x-goog-api-key": self.api_key}, json=body)
        except httpx.RequestError as exc:
            raise ProviderError(f"Network error calling Gemini: {exc}") from exc
        latency_ms = (time.perf_counter() - start) * 1000

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            raise RateLimitError(
                f"Gemini rate limit hit for model {model}",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if resp.status_code >= 400:
            raise ProviderError(f"Gemini error {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        try:
            response_parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"Unexpected Gemini response shape: {data}") from exc

        text = "".join(part.get("text", "") for part in response_parts)
        audio_bytes = None
        for part in response_parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and inline_data.get("data"):
                audio_bytes = base64.b64decode(inline_data["data"])
                break
        if not text and audio_bytes is None:
            raise ProviderError(f"Unexpected Gemini response parts: {response_parts}")
        usage = data.get("usageMetadata", {})
        return LLMResponse(
            text=text,
            model_used=model,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            raw={"latency_ms": latency_ms, "mime_type": (inline_data or {}).get("mimeType") if audio_bytes else None},
            audio_bytes=audio_bytes,
        )

    async def generate_stream(
        self,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        thinking_level: str | None = None,
        response_schema: dict | None = None,
    ) -> AsyncIterator[str]:
        """Yield text fragments from Gemini's server-sent-event stream."""
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY is not configured")

        body: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        generation_config: dict = {}
        if response_schema:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = response_schema
        if thinking_level:
            generation_config["thinkingConfig"] = {"thinkingLevel": thinking_level}
        if generation_config:
            body["generationConfig"] = generation_config

        url = f"{GEMINI_BASE_URL}/{model}:streamGenerateContent"
        try:
            async with self._client_factory(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    params={"alt": "sse"},
                    headers={"x-goog-api-key": self.api_key},
                    json=body,
                ) as response:
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        raise RateLimitError(
                            f"Gemini rate limit hit for model {model}",
                            retry_after_seconds=float(retry_after) if retry_after else None,
                        )
                    if response.status_code >= 400:
                        error_body = (await response.aread()).decode("utf-8", errors="replace")
                        raise ProviderError(f"Gemini error {response.status_code}: {error_body[:500]}")

                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload or payload == "[DONE]":
                            continue
                        try:
                            event = json.loads(payload)
                            parts = event["candidates"][0]["content"]["parts"]
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                            raise ProviderError("Unexpected Gemini streaming response shape") from exc
                        for part in parts:
                            if isinstance(part.get("text"), str) and part["text"]:
                                yield part["text"]
        except httpx.RequestError as exc:
            raise ProviderError(f"Network error calling Gemini stream: {exc}") from exc
