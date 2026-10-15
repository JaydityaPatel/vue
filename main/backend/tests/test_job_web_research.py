import asyncio
import copy
import json

import pytest

from app.core.job_web_research import maybe_enrich_job_plan
from app.db.models import SkillTag
from app.llm.providers.base import LLMResponse
from tests.interview_helpers import session_for


def _job_session(db_session, mode="job"):
    session = session_for(db_session)
    session.mode = mode
    session.config = {
        **session.config,
        "role": "Backend engineer",
        "interview_plan": {
            "topics": [{
                "name": "Python",
                "question_seeds": ["Base question one?", "Base question two?"],
                "question_seed_sources": ["resume_jd", "resume_jd"],
                "expected_concepts": ["typing"],
                "skill_tag_id": "python-tag",
                "source": "resume_jd",
                "source_tags": ["resume_jd"],
            }],
            "generated_by_model": "phase6-model",
            "provisional": False,
        },
        "orchestrator_state": {"topic_coverage": {"Python": "not_started"}},
    }
    return session


class ResearchRouter:
    def __init__(self, *, behavior="success"):
        self.calls = []
        self.behavior = behavior

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.behavior == "timeout":
            await asyncio.sleep(1)
        if self.behavior == "failure":
            raise RuntimeError("provider unavailable")
        if self.behavior == "empty":
            return LLMResponse(text='{"topics":[]}', model_used="gemini-3.8-flash",
                               raw={"grounding_metadata": {"groundingChunks": []}})
        return LLMResponse(
            text=json.dumps({"topics": [
                {"name": "Python", "question_seeds": [
                    "How do you profile a Python service?", "How do you diagnose a memory leak?",
                ], "expected_concepts": ["profiling", "memory management"]},
                {"name": "Company API design", "question_seeds": [
                    "How would you version a public API?", "How do you handle breaking changes?",
                ], "expected_concepts": ["compatibility", "versioning"]},
            ]}),
            model_used="gemini-3.8-flash",
            raw={"provisional": False, "grounding_metadata": {"groundingChunks": [
                {"web": {"uri": "https://example.com/guide", "title": "Interview guide"}},
            ]}},
        )


@pytest.mark.asyncio
async def test_grounded_findings_merge_as_additional_source_tagged_topics(db_session):
    session = _job_session(db_session)
    db_session.add(SkillTag(name="Python")); db_session.flush()
    router = ResearchRouter()

    changed = await maybe_enrich_job_plan(
        session, db=db_session, router=router,
        job_description="Backend engineer at Example Corp; build high-scale APIs.",
    )

    assert changed is True
    assert len(router.calls) == 1
    call = router.calls[0]
    assert call["task"] == "job_web_research"
    assert call["tools"] == [{"google_search": {}}]
    payload = json.loads(call["prompt"])
    assert payload["role"] == "Backend engineer"
    assert payload["job_description"].startswith("Backend engineer at Example Corp")
    assert payload["existing_skill_tags"] == ["Python"]
    assert "authoritative taxonomy" in call["system_prompt"]
    plan = session.config["interview_plan"]
    python = next(topic for topic in plan["topics"] if topic["name"] == "Python")
    assert python["question_seeds"][0] == "Base question one?"
    assert python["question_seeds"][-1] == "How do you diagnose a memory leak?"
    assert python["question_seed_sources"] == ["resume_jd", "resume_jd", "web_research", "web_research"]
    assert python["expected_concept_sources"] == ["resume_jd", "web_research", "web_research"]
    assert python["source_tags"] == ["resume_jd", "web_research"]
    research_topic = next(topic for topic in plan["topics"] if topic["name"] == "Company API design")
    assert research_topic["source"] == "web_research"
    assert research_topic["skill_tag"] == research_topic["name"]
    assert research_topic["question_seed_sources"] == ["web_research", "web_research"]
    assert session.config["orchestrator_state"]["topic_coverage"]["Company API design"] == "not_started"
    assert plan["web_research"]["generated_by_model"] == "gemini-3.8-flash"
    assert plan["web_research"]["sources"] == [{"url": "https://example.com/guide", "title": "Interview guide"}]


@pytest.mark.parametrize("behavior,log_marker", [
    ("timeout", "job_web_research_timeout"),
    ("failure", "job_web_research_failed"),
    ("empty", "job_web_research_no_useful_grounded_findings"),
])
@pytest.mark.asyncio
async def test_enrichment_timeout_or_failure_leaves_base_plan_unchanged_and_is_logged(
    behavior, log_marker, db_session, caplog,
):
    session = _job_session(db_session)
    before = copy.deepcopy(session.config["interview_plan"])
    router = ResearchRouter(behavior=behavior)

    with caplog.at_level("WARNING", logger="vue.job_web_research"):
        changed = await maybe_enrich_job_plan(
            session, db=db_session, router=router, job_description="Example Corp backend role",
            timeout_seconds=0.01,
        )

    assert changed is False
    assert session.config["interview_plan"] == before
    assert log_marker in caplog.text


@pytest.mark.parametrize("mode", ["random", "resume"])
@pytest.mark.asyncio
async def test_non_job_modes_do_not_call_web_research(mode, db_session):
    session = _job_session(db_session, mode=mode)
    router = ResearchRouter()

    assert await maybe_enrich_job_plan(
        session, db=db_session, router=router, job_description="Should not be searched",
    ) is False
    assert router.calls == []
