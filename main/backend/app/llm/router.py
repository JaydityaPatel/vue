import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.config import settings
from app.llm.providers.base import BaseProvider, LLMResponse, RateLimitError, ProviderError
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.rate_limiter import LocalRateLimiter
from app.logging.logger import log_llm_call


class AllProvidersExhaustedError(Exception):
    """Raised when every model in a task's fallback chain has failed."""


class LLMRouter:
    """Routes a task (e.g. 'next_turn', 'score_answer') to the right model,
    via the right provider, with automatic fallback down a configured chain
    when a model is rate-limited or errors out.

    Business logic should only ever call `router.run(task=..., prompt=...)`
    and never import a provider directly (see AGENTS.md rule 6)."""

    def __init__(
        self,
        rate_limits_path=None,
        providers: dict[str, BaseProvider] | None = None,
        max_retries_per_model: int = 1,
    ):
        path = rate_limits_path or settings.rate_limits_path
        with open(path) as f:
            config = yaml.safe_load(f)

        self.routes: dict[str, list[str]] = config.get("routes", {})
        self.model_limits: dict[str, dict] = config.get("models", {})
        self.limiter = LocalRateLimiter(self.model_limits)
        self.max_retries_per_model = max_retries_per_model

        self.providers = providers or {
            "gemini": GeminiProvider(),
            "ollama": OllamaProvider(),
        }

    def _resolve(self, model_id: str) -> tuple[BaseProvider, str]:
        """'ollama:qwen2.5-3b' -> (OllamaProvider, 'qwen2.5-3b')
        'gemini-2.5-flash' -> (GeminiProvider, 'gemini-2.5-flash')"""
        if model_id.startswith("ollama:"):
            return self.providers["ollama"], model_id.split(":", 1)[1]
        return self.providers["gemini"], model_id

    async def run(
        self,
        task: str,
        prompt: str,
        db: Session | None = None,
        system_prompt: str | None = None,
        thinking_level: str | None = None,
        response_schema: dict | None = None,
        content_parts: list[dict[str, Any]] | None = None,
        response_modalities: list[str] | None = None,
        speech_config: dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        chain = self.routes.get(task)
        if not chain:
            raise ValueError(f"No route configured for task '{task}'")

        primary_model = chain[0]
        last_error: Exception | None = None

        for position, model_id in enumerate(chain):
            is_primary = position == 0
            provider, provider_model = self._resolve(model_id)

            if not self.limiter.can_call(model_id):
                last_error = RateLimitError(f"Local limiter: {model_id} at capacity")
                continue

            for attempt in range(self.max_retries_per_model + 1):
                start = time.perf_counter()
                try:
                    request_args = dict(
                        model=provider_model,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        thinking_level=thinking_level,
                        response_schema=response_schema,
                    )
                    if temperature is not None:
                        request_args["temperature"] = temperature
                    if content_parts is not None or response_modalities is not None or speech_config is not None:
                        request_args.update(
                            content_parts=content_parts,
                            response_modalities=response_modalities,
                            speech_config=speech_config,
                        )
                    response = await provider.generate(**request_args)
                    latency_ms = (time.perf_counter() - start) * 1000
                    self.limiter.record_call(model_id)

                    if db is not None:
                        log_llm_call(
                            db,
                            task=task,
                            model_requested=primary_model,
                            model_used=model_id,
                            status="success",
                            latency_ms=latency_ms,
                            input_tokens=response.input_tokens,
                            output_tokens=response.output_tokens,
                            provisional=not is_primary,
                        )

                    response.raw = {**(response.raw or {}), "provisional": not is_primary}
                    return response

                except RateLimitError as exc:
                    last_error = exc
                    if db is not None:
                        log_llm_call(
                            db,
                            task=task,
                            model_requested=primary_model,
                            model_used=model_id,
                            status="rate_limited",
                            error_message=str(exc),
                        )
                    break  # don't retry same model on 429 — move to next in chain

                except ProviderError as exc:
                    last_error = exc
                    if db is not None:
                        log_llm_call(
                            db,
                            task=task,
                            model_requested=primary_model,
                            model_used=model_id,
                            status="error",
                            error_message=str(exc),
                        )
                    if attempt < self.max_retries_per_model:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    break  # exhausted retries on this model — move to next

        raise AllProvidersExhaustedError(
            f"All models in fallback chain for task '{task}' failed. Last error: {last_error}"
        )

    async def stream(
        self,
        task: str,
        prompt: str,
        db: Session | None = None,
        system_prompt: str | None = None,
        thinking_level: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream chunks through the configured route; fallback is safe before first output."""
        chain = self.routes.get(task)
        if not chain:
            raise ValueError(f"No route configured for task '{task}'")
        primary_model = chain[0]
        last_error: Exception | None = None

        for position, model_id in enumerate(chain):
            is_primary = position == 0
            provider, provider_model = self._resolve(model_id)
            generate_stream = getattr(provider, "generate_stream", None)
            if generate_stream is None:
                last_error = ProviderError(f"Provider for {model_id} does not support streaming")
                continue
            if not self.limiter.can_call(model_id):
                last_error = RateLimitError(f"Local limiter: {model_id} at capacity")
                continue

            started = time.perf_counter()
            emitted = False
            try:
                iterator = generate_stream(
                    model=provider_model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    thinking_level=thinking_level,
                )
                async for chunk in iterator:
                    if not isinstance(chunk, str):
                        raise ProviderError("Streaming provider returned a non-text chunk")
                    if chunk:
                        if not emitted:
                            self.limiter.record_call(model_id)
                            if db is not None:
                                log_llm_call(
                                    db,
                                    task=task,
                                    model_requested=primary_model,
                                    model_used=model_id,
                                    status="success",
                                    latency_ms=(time.perf_counter() - started) * 1000,
                                    provisional=not is_primary,
                                )
                        emitted = True
                        yield chunk
                return
            except (RateLimitError, ProviderError) as exc:
                last_error = exc
                if db is not None:
                    log_llm_call(
                        db,
                        task=task,
                        model_requested=primary_model,
                        model_used=model_id,
                        status="rate_limited" if isinstance(exc, RateLimitError) else "error",
                        error_message=str(exc),
                    )
                # Once output has escaped to the caller, restarting on fallback would
                # duplicate an unknown prefix. Only fall back before first text.
                if emitted:
                    raise
                continue

        raise AllProvidersExhaustedError(
            f"All models in fallback chain for task '{task}' failed. Last error: {last_error}"
        )
