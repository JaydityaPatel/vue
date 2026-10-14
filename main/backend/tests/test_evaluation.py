import json

import pytest

from app.core.evaluation import EvaluationError, RUBRIC, score_turn
from app.db.models import SkillTag, Turn, TurnScore
from app.llm.router import LLMRouter
from tests.interview_helpers import CONFIG, session_for


def answered_turn(db):
    session = session_for(db)
    db.add(SkillTag(name="Python"))
    turn = Turn(session_id=session.id, turn_index=0, question_text="How would you validate it?", answer_text="I would test assumptions.")
    db.add(turn)
    db.flush()
    return turn


async def test_score_fields_schema_rubric_and_temperature(db_session, interview_llm):
    turn = answered_turn(db_session)
    score = await score_turn(turn, ["validation", "tradeoffs"], db=db_session, router=LLMRouter())
    db_session.flush()
    assert score.technical_correctness == 3
    assert score.completeness == 3
    assert score.communication == 4
    assert score.problem_solving == 3
    assert score.expected_concepts == ["validation", "tradeoffs"]
    assert score.missing_concepts == ["tradeoffs"]
    assert score.skill_tags == ["Python"]
    assert score.feedback
    assert score.rubric_version == "v1"
    assert score.scored_by_model == "mock-primary"
    assert score.provisional is False
    call = interview_llm.calls[0]
    assert call["temperature"] == 0.1
    assert call["response_schema"]["properties"]["technical_correctness"]["minimum"] == 1
    assert call["response_schema"]["properties"]["technical_correctness"]["maximum"] == 5
    assert "ASR transcription artifacts" in call["system_prompt"]
    assert json.loads(call["prompt"])["controlled_skill_tags"] == ["Python"]
    assert json.loads(call["prompt"])["interview_config"] == CONFIG
    for number in range(1, 6):
        assert RUBRIC.count(f"{number} =") == 4


async def test_unknown_tags_rejected_logged_and_expected_concepts_kept(db_session, interview_llm, caplog):
    turn = answered_turn(db_session)
    interview_llm.score_override = {
        "technical_correctness": 3, "completeness": 3, "communication": 4, "problem_solving": 2,
        "expected_concepts": ["invented"], "missing_concepts": ["validation", "invented"],
        "skill_tags": ["python", "New made-up tag", "Python"], "feedback": "Explain validation.",
    }
    score = await score_turn(turn, ["validation"], db=db_session, router=LLMRouter())
    assert score.skill_tags == ["Python"]
    assert db_session.query(SkillTag).count() == 1
    assert score.expected_concepts == ["validation"]
    assert score.missing_concepts == ["validation"]
    assert "evaluation_unknown_skill_tag" in caplog.text
    assert "evaluation_expected_concepts_mismatch" in caplog.text
    assert "evaluation_unknown_missing_concepts" in caplog.text


@pytest.mark.parametrize("value", [0, 6, 2.5, "3", True])
async def test_invalid_score_cannot_be_persisted(db_session, interview_llm, value):
    turn = answered_turn(db_session)
    interview_llm.score_override = {
        "technical_correctness": value, "completeness": 3, "communication": 4, "problem_solving": 2,
        "expected_concepts": ["validation"], "missing_concepts": [],
        "skill_tags": ["Python"], "feedback": "Feedback",
    }
    with pytest.raises(EvaluationError):
        await score_turn(turn, ["validation"], db=db_session, router=LLMRouter())
    assert db_session.query(TurnScore).count() == 0


async def test_score_is_idempotent_and_records_fallback(db_session, interview_llm):
    turn = answered_turn(db_session)
    interview_llm.provisional = True
    first = await score_turn(turn, ["validation"], db=db_session, router=LLMRouter())
    second = await score_turn(turn, ["validation"], db=db_session, router=LLMRouter())
    assert first is second
    assert len(interview_llm.calls) == 1
    assert first.provisional is True and first.scored_by_model == "mock-fallback"
