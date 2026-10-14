import asyncio
import json

import pytest

from app.core.interview_planning import generate_plan_for_session
from app.core.intro_round import (
    INITIAL_INTRO_QUESTION,
    IntroSummary,
    mode_has_intro_round,
    next_intro_question,
    summarize_intro,
)
from app.db.models import InterviewSession
from app.llm.providers.base import LLMResponse
from tests.interview_helpers import PLAN, session_for


class IntroRouter:
    routes = {"next_turn": [], "score_answer": []}

    def __init__(self, *, provisional=False):
        self.calls = []
        self.provisional = provisional

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        schema = kwargs["response_schema"]["properties"]
        if "question_text" in schema:
            output = {"question_text": "What did you own in that project?"}
        elif "background" in schema:
            output = {"background": "Backend engineer with three years of experience.",
                      "stated_strengths": ["debugging"], "notable_projects": ["Kafka pipeline"],
                      "preferred_technologies": ["Python", "React"]}
        else:
            output = PLAN
        return LLMResponse(text=json.dumps(output), model_used="gemini-fallback" if self.provisional else "ollama:qwen2.5:3b",
                           raw={"provisional": self.provisional})


@pytest.mark.asyncio
async def test_intro_followup_and_summary_shapes_and_provisional_provenance(db_session):
    router = IntroRouter(provisional=True)
    assert INITIAL_INTRO_QUESTION == "Tell me about yourself."
    question, model, provisional = await next_intro_question(
        ["I build Python APIs."], router=router, db=db_session
    )
    assert question == "What did you own in that project?"
    assert model == "gemini-fallback" and provisional
    summary, model, provisional = await summarize_intro(
        ["I have three years in backend engineering.", "I like Python.", "I built a Kafka pipeline."],
        router=router,
        db=db_session,
    )
    assert IntroSummary.model_validate(summary).notable_projects == ["Kafka pipeline"]
    assert model == "gemini-fallback" and provisional
    assert router.calls[0]["task"] == router.calls[1]["task"] == "intro_chat"
    assert router.calls[0]["route_override"] == ["gemini-3.5-flash-lite"]
    assert router.calls[0]["db"] is db_session
    assert router.calls[1]["db"] is db_session


def test_intro_mode_gate_excludes_random():
    assert mode_has_intro_round("resume")
    assert mode_has_intro_round("job")
    assert not mode_has_intro_round("random")


@pytest.mark.asyncio
async def test_intro_model_work_can_overlap_document_plan_generation(db_session):
    session: InterviewSession = session_for(db_session)
    session.mode = "resume"
    session.config["source_resume"] = "Built Python services"
    active = 0
    peak = 0
    barrier = asyncio.Event()

    class ConcurrentRouter(IntroRouter):
        async def run(self, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if peak >= 2:
                barrier.set()
            await asyncio.wait_for(barrier.wait(), timeout=1)
            await asyncio.sleep(0)
            active -= 1
            schema = kwargs["response_schema"]["properties"]
            if kwargs["task"] == "build_question_bank":
                output = PLAN
            elif "question_text" in schema:
                output = {"question_text": "What did you learn?"}
            else:
                output = {"background": "Backend developer", "stated_strengths": [],
                          "notable_projects": [], "preferred_technologies": []}
            return LLMResponse(text=json.dumps(output), model_used="model-a", raw={"provisional": False})

    router = ConcurrentRouter()
    await asyncio.gather(
        generate_plan_for_session(session, db=db_session, router=router),
        next_intro_question(["I build software."], router=router, db=db_session),
    )
    assert peak == 2
