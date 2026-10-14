import time
from typing import Any

import httpx

from app.config import settings
from app.llm.providers.base import BaseProvider, LLMResponse, ProviderError


class OllamaProvider(BaseProvider):
    """Local Ollama provider with an inference-sized timeout and keep-alive."""

    name = "ollama"

    def __init__(self, base_url: str | None = None, timeout: float | None = None,
                 keep_alive: str | None = None):
        self.base_url = base_url or settings.ollama_base_url
        # A warmed 3B prompt took ~0.58 s on the development machine. Three
        # minutes gives substantial margin for cold loads and slower hardware.
        self.timeout = timeout or settings.ollama_timeout_seconds
        self.keep_alive = keep_alive or settings.ollama_keep_alive
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
        cached_content: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if tools:
            raise ProviderError("Ollama provider does not support external grounding tools")
        url = f"{self.base_url}/api/generate"
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        body = {"model": model, "prompt": full_prompt, "stream": False,
                "keep_alive": self.keep_alive}
        if temperature is not None:
            body["options"] = {"temperature": temperature}
        if response_schema is not None:
            body["format"] = response_schema

        start = time.perf_counter()
        try:
            async with self._client_factory(timeout=self.timeout) as client:
                resp = await client.post(url, json=body)
        except httpx.RequestError as exc:
            raise ProviderError(f"Could not reach Ollama at {self.base_url}: {type(exc).__name__}") from exc
        latency_ms = (time.perf_counter() - start) * 1000

        if resp.status_code >= 400:
            raise ProviderError(f"Ollama error {resp.status_code}: {resp.text[:500]}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError("Ollama returned malformed JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("response"), str):
            detail = data.get("error", "unexpected response shape") if isinstance(data, dict) else "unexpected response shape"
            raise ProviderError(f"Ollama could not generate with model {model}: {detail}")
        return LLMResponse(
            text=data.get("response", ""),
            model_used=model,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            raw={"latency_ms": latency_ms},
        )
