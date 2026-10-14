import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.db.models import User
from app.llm.providers.base import LLMResponse
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.ollama import OllamaProvider


async def test_router_forwards_temperature(router, fake_gemini):
    fake_gemini.generate = AsyncMock(return_value=LLMResponse(text="{}", model_used="model-a"))
    await router.run(task="test_task", prompt="score", temperature=0.1)
    assert fake_gemini.generate.call_args.kwargs["temperature"] == 0.1


async def test_router_forwards_provider_tools(router, fake_gemini):
    tools = [{"google_search": {}}]
    await router.run(task="test_task", prompt="research", tools=tools)
    assert fake_gemini.last_tools == tools


async def test_logging_does_not_commit_partial_application_state(router, db_session):
    db_session.add(User(email="not-committed@example.com", hashed_password="unused"))
    await router.run(task="test_task", prompt="hello", db=db_session)
    db_session.rollback()
    assert db_session.query(User).count() == 0


@pytest.mark.parametrize("kind", ["gemini", "ollama"])
async def test_provider_sends_temperature_and_structured_schema(monkeypatch, kind):
    requests = []
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}, "required": ["score"]}
    async def handler(request):
        requests.append(json.loads(request.content))
        if kind == "gemini":
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"score":3}'}]}}]})
        return httpx.Response(200, json={"response": '{"score":3}'})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    provider = GeminiProvider(api_key="fake") if kind == "gemini" else OllamaProvider()
    await provider.generate("test-model", "Score this", temperature=0.1, response_schema=schema)
    body = requests[0]
    if kind == "gemini":
        assert body["generationConfig"]["temperature"] == 0.1
        assert body["generationConfig"]["responseJsonSchema"] == schema
        assert body["generationConfig"]["responseMimeType"] == "application/json"
    else:
        assert body["options"]["temperature"] == 0.1
        assert body["format"] == schema


@pytest.mark.asyncio
async def test_gemini_sends_search_grounding_tool_and_preserves_citations(monkeypatch):
    requests = []
    metadata = {"groundingChunks": [{"web": {"uri": "https://example.com/guide", "title": "Guide"}}]}

    async def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{
            "content": {"parts": [{"text": '{"topics":[]}'}]},
            "groundingMetadata": metadata,
        }]})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    provider = GeminiProvider(api_key="fake")
    tools = [{"google_search": {}}]
    response = await provider.generate("gemini-3.8-flash", "Research interviews", tools=tools)
    assert requests[0]["tools"] == tools
    assert response.raw["grounding_metadata"] == metadata
