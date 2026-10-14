import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.db import models  # noqa: F401
from app.main import app
from app.llm.providers.base import LLMResponse, RateLimitError, ProviderError
from app.llm.router import LLMRouter


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth-test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Keep TestClient startup isolated from the developer's configured database.
    monkeypatch.setattr("app.main.init_db", lambda: None)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def rate_limits_file(tmp_path):
    config = {
        "models": {
            "model-a": {"rpm": 2, "tpm": 100000, "rpd": 100},
            "model-b": {"rpm": 10, "tpm": 100000, "rpd": 100},
            "model-c": {"rpm": 10, "tpm": 100000, "rpd": 100},
        },
        "routes": {
            "test_task": ["model-a", "model-b", "ollama:local-model"],
            "no_fallback_task": ["model-c"],
        },
    }
    path = tmp_path / "rate_limits.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


class FakeProvider:
    """A controllable fake provider for exercising router fallback logic
    without hitting real network/API endpoints."""

    def __init__(self, name: str):
        self.name = name
        self.calls: list[str] = []
        self.last_tools = None
        self._behavior = {}  # model -> "success" | "rate_limit" | "error"

    def set_behavior(self, model: str, behavior: str):
        self._behavior[model] = behavior

    async def generate(self, model, prompt, system_prompt=None, thinking_level=None, response_schema=None, temperature=None, tools=None):
        self.calls.append(model)
        self.last_tools = tools
        behavior = self._behavior.get(model, "success")
        if behavior == "rate_limit":
            raise RateLimitError(f"{model} rate limited")
        if behavior == "error":
            raise ProviderError(f"{model} errored")
        return LLMResponse(text=f"response from {model}", model_used=model, input_tokens=10, output_tokens=20)

    async def generate_stream(self, model, prompt, system_prompt=None, thinking_level=None):
        self.calls.append(model)
        behavior = self._behavior.get(model, "success")
        if behavior == "rate_limit":
            raise RateLimitError(f"{model} rate limited")
        if behavior == "error":
            raise ProviderError(f"{model} errored")
        if behavior == "partial_error":
            yield f"prefix from {model}"
            raise ProviderError(f"{model} failed after emitting text")
        yield f"first from {model}"
        yield f" second from {model}"


@pytest.fixture()
def fake_gemini():
    return FakeProvider("gemini")


@pytest.fixture()
def fake_ollama():
    return FakeProvider("ollama")


@pytest.fixture()
def router(rate_limits_file, fake_gemini, fake_ollama):
    return LLMRouter(
        rate_limits_path=rate_limits_file,
        providers={"gemini": fake_gemini, "ollama": fake_ollama},
        max_retries_per_model=0,
    )


@pytest.fixture()
def interview_llm(monkeypatch):
    from tests.interview_helpers import ScriptedInterviewLLM

    scripted = ScriptedInterviewLLM()

    async def run(_router, **kwargs):
        return await scripted.run(**kwargs)

    monkeypatch.setattr(LLMRouter, "run", run)
    return scripted
