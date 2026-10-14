import json

import httpx
import pytest

from app.llm.providers.base import LLMResponse, ProviderError
from app.llm.providers.ollama import OllamaProvider
from app.llm.router import LLMRouter


@pytest.mark.asyncio
async def test_successful_call_parses_usage_and_sends_keep_alive():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"response": "Hello.", "prompt_eval_count": 12, "eval_count": 3})

    provider = OllamaProvider(base_url="http://ollama.test", timeout=12, keep_alive="30m")
    provider._client_factory = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    result = await provider.generate("qwen2.5:3b", "Hi")

    assert isinstance(result, LLMResponse)
    assert (result.text, result.model_used, result.input_tokens, result.output_tokens) == (
        "Hello.", "qwen2.5:3b", 12, 3,
    )
    assert seen[0]["keep_alive"] == "30m"
    assert seen[0]["stream"] is False


@pytest.mark.asyncio
async def test_connection_failure_is_provider_error_and_router_falls_back(fake_gemini, rate_limits_file):
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    local = OllamaProvider(base_url="http://127.0.0.1:1", timeout=0.2)
    local._client_factory = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    router = LLMRouter(rate_limits_path=rate_limits_file,
                       providers={"ollama": local, "gemini": fake_gemini}, max_retries_per_model=0)
    router.routes["test_task"] = ["ollama:qwen2.5:3b", "model-b"]

    result = await router.run("test_task", "Hello")
    assert result.model_used == "model-b"
    assert fake_gemini.calls == ["model-b"]


@pytest.mark.asyncio
async def test_missing_model_response_becomes_provider_error():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found; pull it first"})

    provider = OllamaProvider()
    provider._client_factory = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    with pytest.raises(ProviderError, match="Ollama error 404"):
        await provider.generate("missing-model", "Hello")
