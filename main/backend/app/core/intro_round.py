"""Document-mode conversational warm-up and conservative hardware-tier routing."""
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.llm.router import LLMRouter

CONSTRAINED_VRAM_BUDGET_MB = 4096
WHISPER_SMALL_EN_VRAM_MB = 1000
OLLAMA_3B_Q4_VRAM_MB = 2500
# CUDA context, Silero/VAD allocations, and allocator fragmentation. These are
# planning reserves, not benchmark measurements.
CONCURRENT_RUNTIME_OVERHEAD_MB = 768
INTRO_MAX_FOLLOW_UPS = 3
INTRO_MIN_FOLLOW_UPS = 2
INITIAL_INTRO_QUESTION = "Tell me about yourself."


def mode_has_intro_round(mode: str) -> bool:
    return mode in {"resume", "job"}


class IntroFollowUp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_text: str = Field(min_length=1, max_length=1000)


class IntroSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    background: str = Field(max_length=2000)
    stated_strengths: list[str] = Field(max_length=12)
    notable_projects: list[str] = Field(max_length=12)
    preferred_technologies: list[str] = Field(max_length=12)


def estimated_concurrent_vram_mb(
    whisper_mb: int = WHISPER_SMALL_EN_VRAM_MB,
    ollama_mb: int = OLLAMA_3B_Q4_VRAM_MB,
    overhead_mb: int = CONCURRENT_RUNTIME_OVERHEAD_MB,
) -> int:
    return whisper_mb + ollama_mb + overhead_mb


def allows_local_intro_concurrency(
    hardware_tier: str,
    *,
    whisper_mb: int = WHISPER_SMALL_EN_VRAM_MB,
    ollama_mb: int = OLLAMA_3B_Q4_VRAM_MB,
    overhead_mb: int = CONCURRENT_RUNTIME_OVERHEAD_MB,
) -> bool:
    """Unknown is safe-by-default; high is an explicit operator override."""
    if hardware_tier.casefold() == "high":
        return True
    if hardware_tier.casefold() not in {"unknown", "constrained"}:
        return False
    return estimated_concurrent_vram_mb(whisper_mb, ollama_mb, overhead_mb) <= CONSTRAINED_VRAM_BUDGET_MB


def intro_route(hardware_tier: str | None = None) -> list[str]:
    route = ["ollama:qwen2.5:3b", "gemini-3.5-flash-lite"]
    if allows_local_intro_concurrency(hardware_tier or settings.hardware_tier):
        return route
    # A cloud-only path avoids sharing the target GPU with Whisper.
    return ["gemini-3.5-flash-lite"]


async def next_intro_question(
    answers: list[str], *, router: LLMRouter, db: Session | None = None,
    route: list[str] | None = None,
) -> tuple[str, str, bool]:
    response = await router.run(
        task="intro_chat",
        db=db,
        route_override=route or intro_route(),
        prompt=json.dumps({"intro_answers": answers}, ensure_ascii=False),
        system_prompt=(
            "You are conducting a brief, welcoming interview introduction. Ask one concise adaptive follow-up "
            "about the candidate's background, strengths, project ownership, or preferred technologies. "
            "Do not ask multiple questions or invent facts. Return JSON with question_text."
        ),
        response_schema=IntroFollowUp.model_json_schema(),
        temperature=0.3,
    )
    try:
        output = IntroFollowUp.model_validate_json(response.text)
        return output.question_text, response.model_used, bool((response.raw or {}).get("provisional", False))
    except ValidationError:
        # A deterministic open prompt keeps the microphone flow usable if a
        # provider returns malformed structured output.
        fallback = "What project or accomplishment best shows how you work?"
        return fallback, response.model_used, True


async def summarize_intro(
    answers: list[str], *, router: LLMRouter, db: Session | None = None,
    route: list[str] | None = None,
) -> tuple[dict[str, Any], str, bool]:
    response = await router.run(
        task="intro_chat",
        db=db,
        route_override=route or intro_route(),
        prompt=json.dumps({"intro_answers": answers}, ensure_ascii=False),
        system_prompt=(
            "Summarize only evidence explicitly present in the candidate's introduction answers. "
            "Extract background, stated strengths, notable projects, and preferred technologies. "
            "Use empty strings or lists when evidence is absent. Return JSON matching the supplied schema."
        ),
        response_schema=IntroSummary.model_json_schema(),
        temperature=0.1,
    )
    try:
        summary = IntroSummary.model_validate_json(response.text)
    except ValidationError as exc:
        raise ValueError("The intro summary model returned invalid structured output") from exc
    return summary.model_dump(), response.model_used, bool((response.raw or {}).get("provisional", False))
