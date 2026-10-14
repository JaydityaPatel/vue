import json

import httpx
import pytest

from app.llm.providers.base import ProviderError, RateLimitError
from app.llm.providers.gemini import GeminiProvider


@pytest.mark.asyncio
async def test_generate_stream_yields_text_and_keeps_api_key_out_of_url():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                "data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": "hello"}]}}]})
                + "\n\n"
                + "data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": " world"}]}}]})
                + "\n\n"
            ),
        )

    provider = GeminiProvider(api_key="test-secret")
    provider._client_factory = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    chunks = [chunk async for chunk in provider.generate_stream("gemini-test", "prompt")]

    assert chunks == ["hello", " world"]
    assert "test-secret" not in str(requests[0].url)
    assert requests[0].headers["x-goog-api-key"] == "test-secret"


@pytest.mark.asyncio
async def test_generate_stream_maps_429():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "2"}, text="busy")

    provider = GeminiProvider(api_key="test-secret")
    provider._client_factory = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    with pytest.raises(RateLimitError) as raised:
        _ = [chunk async for chunk in provider.generate_stream("gemini-test", "prompt")]
    assert raised.value.retry_after_seconds == 2


@pytest.mark.asyncio
async def test_generate_stream_maps_malformed_sse():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="data: not-json\n\n")

    provider = GeminiProvider(api_key="test-secret")
    provider._client_factory = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    with pytest.raises(ProviderError, match="response shape"):
        _ = [chunk async for chunk in provider.generate_stream("gemini-test", "prompt")]


@pytest.mark.asyncio
async def test_explicit_cache_creation_and_cached_generate_account_for_tokens():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, json.loads(request.content)))
        if request.url.path.endswith("cachedContents"):
            return httpx.Response(200, json={"name": "cachedContents/cache-123"})
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "question"}]}}],
            "usageMetadata": {"promptTokenCount": 1200, "cachedContentTokenCount": 1000,
                              "candidatesTokenCount": 15},
        })

    provider = GeminiProvider(api_key="test-secret")
    provider._client_factory = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    cache_name = await provider.create_cached_content("gemini-2.5-flash", "stable candidate context")
    response = await provider.generate("gemini-2.5-flash", "Generate next question",
                                       cached_content=cache_name)

    assert cache_name == "cachedContents/cache-123"
    assert requests[0][0].endswith("/cachedContents")
    assert requests[0][1]["ttl"] == "7200s"
    assert requests[0][1]["model"] == "models/gemini-2.5-flash"
    assert requests[1][1]["cachedContent"] == cache_name
    assert response.input_tokens == 200
    assert response.raw["cached_input_tokens"] == 1000
    assert response.output_tokens == 15
