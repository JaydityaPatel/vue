from app.core.intro_round import (
    CONSTRAINED_VRAM_BUDGET_MB,
    estimated_concurrent_vram_mb,
    allows_local_intro_concurrency,
    intro_route,
)
from app.llm.router import LLMRouter


def test_constrained_over_budget_skips_local_ollama():
    assert estimated_concurrent_vram_mb() > CONSTRAINED_VRAM_BUDGET_MB
    assert not allows_local_intro_concurrency("constrained")
    assert intro_route("constrained") == ["gemini-3.5-flash-lite"]


def test_unknown_tier_is_safe_by_default():
    assert not allows_local_intro_concurrency("unknown")
    assert intro_route("unknown") == ["gemini-3.5-flash-lite"]
    assert intro_route("") == ["gemini-3.5-flash-lite"]


def test_high_tier_allows_local_intro_route():
    assert allows_local_intro_concurrency("high")
    assert intro_route("high") == ["ollama:qwen2.5:3b", "gemini-3.5-flash-lite"]


def test_intro_is_limited_to_document_modes():
    from app.core.intro_round import mode_has_intro_round

    assert mode_has_intro_round("resume")
    assert mode_has_intro_round("job")
    assert not mode_has_intro_round("random")


async def test_router_obeys_unknown_and_high_tier_intro_routes(rate_limits_file, fake_gemini, fake_ollama):
    router = LLMRouter(rate_limits_path=rate_limits_file,
                       providers={"gemini": fake_gemini, "ollama": fake_ollama}, max_retries_per_model=0)
    safe_route = intro_route("unknown")
    await router.run("intro_chat", "hello", route_override=safe_route)
    assert fake_ollama.calls == []
    assert fake_gemini.calls == ["gemini-3.5-flash-lite"]

    router = LLMRouter(rate_limits_path=rate_limits_file,
                       providers={"gemini": fake_gemini, "ollama": fake_ollama}, max_retries_per_model=0)
    await router.run("intro_chat", "hello", route_override=intro_route("high"))
    assert fake_ollama.calls == ["qwen2.5:3b"]
