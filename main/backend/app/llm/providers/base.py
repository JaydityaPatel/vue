from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    text: str
    model_used: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict | None = None
    audio_bytes: bytes | None = None


class RateLimitError(Exception):
    """Raised when a provider reports a 429 / quota-exhausted response."""

    def __init__(self, message: str, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderError(Exception):
    """Raised for any other provider failure (network, 5xx, malformed response)."""


class BaseProvider(ABC):
    name: str

    @abstractmethod
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
        """Run a single generation call. Must raise RateLimitError on 429 and
        ProviderError on any other failure so the router can act on it."""
        raise NotImplementedError
