import pytest

from app.llm.providers.base import ProviderError
from app.llm.router import AllProvidersExhaustedError


@pytest.mark.asyncio
async def test_primary_success_not_provisional(router, db_session):
    response = await router.run(task="test_task", prompt="hi", db=db_session)
    assert response.model_used == "model-a"
    assert response.raw["provisional"] is False


@pytest.mark.asyncio
async def test_falls_back_on_rate_limit(router, fake_gemini, db_session):
    fake_gemini.set_behavior("model-a", "rate_limit")
    response = await router.run(task="test_task", prompt="hi", db=db_session)
    assert response.model_used == "model-b"
    assert response.raw["provisional"] is True


@pytest.mark.asyncio
async def test_falls_back_on_provider_error(router, fake_gemini, db_session):
    fake_gemini.set_behavior("model-a", "error")
    response = await router.run(task="test_task", prompt="hi", db=db_session)
    assert response.model_used == "model-b"
    assert response.raw["provisional"] is True


@pytest.mark.asyncio
async def test_falls_through_to_ollama(router, fake_gemini, db_session):
    fake_gemini.set_behavior("model-a", "rate_limit")
    fake_gemini.set_behavior("model-b", "error")
    response = await router.run(task="test_task", prompt="hi", db=db_session)
    assert response.model_used == "local-model"
    assert response.raw["provisional"] is True


@pytest.mark.asyncio
async def test_all_providers_exhausted_raises(router, fake_gemini, fake_ollama, db_session):
    fake_gemini.set_behavior("model-a", "error")
    fake_gemini.set_behavior("model-b", "error")
    fake_ollama.set_behavior("local-model", "error")
    with pytest.raises(AllProvidersExhaustedError):
        await router.run(task="test_task", prompt="hi", db=db_session)


@pytest.mark.asyncio
async def test_unknown_task_raises_value_error(router, db_session):
    with pytest.raises(ValueError):
        await router.run(task="nonexistent_task", prompt="hi", db=db_session)


@pytest.mark.asyncio
async def test_local_rate_limiter_skips_exhausted_model(router, db_session):
    # model-a has rpm=2 — burn both slots, 3rd call should skip straight to model-b
    await router.run(task="test_task", prompt="1", db=db_session)
    await router.run(task="test_task", prompt="2", db=db_session)
    response = await router.run(task="test_task", prompt="3", db=db_session)
    assert response.model_used == "model-b"
    from app.db.models import LLMCallLog

    local_limit_logs = db_session.query(LLMCallLog).filter_by(
        model_used="model-a", status="rate_limited"
    ).all()
    assert len(local_limit_logs) == 1
    assert "Local limiter" in local_limit_logs[0].error_message


@pytest.mark.asyncio
async def test_single_model_route_no_fallback_available(router, fake_gemini, db_session):
    fake_gemini.set_behavior("model-c", "error")
    with pytest.raises(AllProvidersExhaustedError):
        await router.run(task="no_fallback_task", prompt="hi", db=db_session)


@pytest.mark.asyncio
async def test_successful_calls_are_logged(router, db_session):
    from app.db.models import LLMCallLog

    await router.run(task="test_task", prompt="hi", db=db_session)
    logs = db_session.query(LLMCallLog).all()
    assert len(logs) == 1
    assert logs[0].status == "success"
    assert logs[0].model_used == "model-a"


@pytest.mark.asyncio
async def test_rate_limited_attempt_is_logged_before_fallback(router, fake_gemini, db_session):
    from app.db.models import LLMCallLog

    fake_gemini.set_behavior("model-a", "rate_limit")
    await router.run(task="test_task", prompt="hi", db=db_session)
    statuses = [log.status for log in db_session.query(LLMCallLog).all()]
    assert "rate_limited" in statuses
    assert "success" in statuses


@pytest.mark.asyncio
async def test_stream_falls_back_before_first_chunk(router, fake_gemini, db_session):
    fake_gemini.set_behavior("model-a", "error")
    chunks = [chunk async for chunk in router.stream("test_task", "hi", db=db_session)]
    assert chunks == ["first from model-b", " second from model-b"]
    from app.db.models import LLMCallLog

    success = db_session.query(LLMCallLog).filter_by(status="success").one()
    assert success.model_used == "model-b"
    assert success.provisional is True


@pytest.mark.asyncio
async def test_stream_does_not_fallback_after_yielding_partial_text(router, fake_gemini):
    fake_gemini.set_behavior("model-a", "partial_error")
    chunks = []
    with pytest.raises(ProviderError, match="after emitting"):
        async for chunk in router.stream("test_task", "hi"):
            chunks.append(chunk)
    assert chunks == ["prefix from model-a"]
    assert fake_gemini.calls == ["model-a"]


@pytest.mark.asyncio
async def test_stream_counts_one_request_not_one_request_per_chunk(router, fake_gemini):
    for _ in range(2):
        [chunk async for chunk in router.stream("test_task", "hi")]
    chunks = [chunk async for chunk in router.stream("test_task", "hi")]
    assert chunks == ["first from model-b", " second from model-b"]
    assert fake_gemini.calls == ["model-a", "model-a", "model-b"]
