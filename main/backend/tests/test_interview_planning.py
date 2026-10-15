import asyncio
import json

import pytest
from sqlalchemy import select

from app.core.interview_planning import (
    InterviewPlan, generate_plan_for_session, generate_plan_from_resume,
    generate_plan_from_resume_and_jd,
)
from app.db.models import InterviewSession, SkillTag
from app.llm.providers.base import LLMResponse
from tests.interview_helpers import session_for


def plan_payload():
    return {"topics": [{"name": name, "question_seeds": [f"Question about {name}?", f"Another {name} question?"],
                       "expected_concepts": [f"{name} evidence", f"{name} tradeoffs"]}
                      for name in ("Python", "Kafka", "Leadership", "System design")]}


class RecordingRouter:
    def __init__(self):
        self.calls = []
        self.routes = {"next_turn": ["gemini-a", "ollama:local"], "score_answer": ["gemini-a", "gemini-b"]}
        self.payload = plan_payload()

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return LLMResponse(text=json.dumps(self.payload), model_used="gemini-a", raw={"provisional": False})

    async def create_context_cache(self, model, text):
        self.calls.append({"cache_model": model, "cache_chars": len(text)})
        return None


@pytest.mark.asyncio
async def test_resume_plan_matches_shared_phase4_schema():
    router = RecordingRouter()
    plan = await generate_plan_from_resume("Built Kafka consumer groups at scale", router=router)
    assert isinstance(plan, InterviewPlan)
    assert len(plan.topics) == 4
    assert plan.topics[1].question_seeds[0] == "Question about Kafka?"
    prompt = json.loads(router.calls[0]["prompt"])
    assert prompt["candidate_documents"]["resume"] == "Built Kafka consumer groups at scale"


@pytest.mark.asyncio
async def test_job_prompt_includes_both_documents_and_gap_guidance():
    router = RecordingRouter()
    plan = await generate_plan_from_resume_and_jd(
        "Built services with Kafka", "Requires Kubernetes and production observability", router=router)
    call = router.calls[0]
    prompt = json.loads(call["prompt"])
    assert prompt["candidate_documents"] == {
        "resume": "Built services with Kafka", "job_description": "Requires Kubernetes and production observability"}
    assert "does not clearly demonstrate" in call["system_prompt"]
    assert "grounded in the named project" in call["system_prompt"]
    assert len(plan.topics) == 4


@pytest.mark.parametrize("mode", ["resume", "job"])
@pytest.mark.asyncio
async def test_plan_install_reuses_skill_tags_and_keeps_followup_summary(mode, db_session):
    user_session = session_for(db_session)
    user_session.mode = mode
    user_session.config["source_resume"] = "Jane Candidate\nBuilt a real-time Kafka pipeline. " + "achievement detail. " * 1400
    user_session.config["source_jd"] = "Must know Kubernetes. " * 100 if mode == "job" else ""
    python = SkillTag(name="Python")
    db_session.add(python); db_session.flush()
    router = RecordingRouter()
    await generate_plan_for_session(user_session, db=db_session, router=router)
    db_session.flush()
    plan = user_session.config["interview_plan"]
    assert len(plan["topics"]) == 4
    assert all(topic["source"] == "resume_jd" for topic in plan["topics"])
    assert all(set(topic["question_seed_sources"]) == {"resume_jd"} for topic in plan["topics"])
    assert plan["topics"][0]["skill_tag_id"] == python.id
    assert len(db_session.scalars(select(SkillTag).where(SkillTag.name == "Python")).all()) == 1
    assert user_session.config["candidate_context_summary"]
    assert "source_resume" not in user_session.config and "source_jd" not in user_session.config
    assert router.calls[0]["db"] is db_session
    planning_call = next(call for call in router.calls if "cache_model" not in call)
    assert json.loads(planning_call["prompt"])["interview_config"]["role"] == "Backend engineer"
    cache_models = [call["cache_model"] for call in router.calls if "cache_model" in call]
    assert cache_models == ["gemini-a", "gemini-b"]


@pytest.mark.asyncio
async def test_plan_calls_reuse_exact_selected_tag_across_paraphrased_topics(db_session):
    user_session = session_for(db_session)
    user_session.mode = "random"
    canonical = SkillTag(name="PostgreSQL Performance Tuning and Indexing")
    db_session.add(canonical); db_session.flush()
    router = RecordingRouter()
    router.payload = {"topics": [
        {"name": "PostgreSQL index tuning project", "skill_tag": canonical.name,
         "question_seeds": ["How did you tune indexes?", "What did you measure?"], "expected_concepts": ["index selection"]},
        *plan_payload()["topics"][1:],
    ]}
    await generate_plan_for_session(user_session, db=db_session, router=router)
    first_topic = user_session.config["interview_plan"]["topics"][0]
    assert json.loads(router.calls[0]["prompt"])["existing_skill_tags"] == [canonical.name]
    assert "authoritative taxonomy" in router.calls[0]["system_prompt"]
    assert first_topic["name"] == "PostgreSQL index tuning project"
    assert first_topic["skill_tag"] == canonical.name
    assert first_topic["skill_tag_id"] == canonical.id

    second_session = InterviewSession(user_id=user_session.user_id, mode="random", config=dict(user_session.config))
    second_session.config.pop("interview_plan")
    second_session.config.pop("orchestrator_state")
    second_session.config.pop("turn_context")
    db_session.add(second_session); db_session.flush()
    router.payload = {"topics": [
        {"name": "PostgreSQL query plan optimization", "skill_tag": canonical.name,
         "question_seeds": ["How did you inspect query plans?", "Which tradeoffs mattered?"], "expected_concepts": ["query plans"]},
        *plan_payload()["topics"][1:],
    ]}
    await generate_plan_for_session(second_session, db=db_session, router=router)
    second_topic = second_session.config["interview_plan"]["topics"][0]
    assert second_topic["name"] == "PostgreSQL query plan optimization"
    assert second_topic["skill_tag_id"] == canonical.id
    assert len(db_session.scalars(select(SkillTag).where(SkillTag.name == canonical.name)).all()) == 1


@pytest.mark.asyncio
async def test_short_documents_skip_explicit_cache_and_log_fallback(db_session, caplog):
    user_session = session_for(db_session)
    user_session.mode = "resume"
    user_session.config["source_resume"] = "Built APIs with Python."
    router = RecordingRouter()
    await generate_plan_for_session(user_session, db=db_session, router=router)
    assert not any("cache_model" in call for call in router.calls)
    assert "context_cache_skipped_short" in caplog.text
