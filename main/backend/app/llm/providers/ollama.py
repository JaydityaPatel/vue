import time
from typing import Any

import httpx

from app.config import settings
from app.llm.providers.base import BaseProvider, LLMResponse, ProviderError


class OllamaProvider(BaseProvider):
    """Local Ollama provider. Minimal implementation for Phase 1 — enough for
    the router's fallback-chain tests to exercise a second real provider.
    Full integration (model pulls, keep_alive tuning, GPU contention
    handling) lands in Phase 7."""

    name = "ollama"

    def __init__(self, base_url: str | None = None, timeout: float = 60.0):
        self.base_url = base_url or settings.ollama_base_url
        self.timeout = timeout

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
        url = f"{self.base_url}/api/generate"
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        body = {"model": model, "prompt": full_prompt, "stream": False}
        if temperature is not None:
            body["options"] = {"temperature": temperature}
        if response_schema is not None:
            body["format"] = response_schema

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=body)
        except httpx.RequestError as exc:
            raise ProviderError(f"Network error calling Ollama: {exc}") from exc
        latency_ms = (time.perf_counter() - start) * 1000

        if resp.status_code >= 400:
            raise ProviderError(f"Ollama error {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        return LLMResponse(
            text=data.get("response", ""),
            model_used=model,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            raw={"latency_ms": latency_ms},
        )
