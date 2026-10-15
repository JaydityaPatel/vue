import pytest

from app.core.evaluation import generate_report
from app.core.orchestrator import utc_now
from app.db.models import Turn, TurnScore
from app.llm.router import LLMRouter
from tests.interview_helpers import session_for


def add_score(db, session, index, topic, value, *, code=False, discussion=False):
    turn = Turn(session_id=session.id, turn_index=index, question_text=f"Question {index}",
                answer_text="Candidate answer", action_taken="coding_submission" if code else None)
    db.add(turn)
    db.flush()
    db.add(TurnScore(
        turn_id=turn.id, technical_correctness=value, completeness=value,
        communication=value, problem_solving=value, expected_concepts=["concept"],
        missing_concepts=[], skill_tags=[], feedback="Scored answer.", rubric_version="coding-v1" if code else "v1",
        scored_by_model="mock", tests_passed=2 if code else None, tests_total=3 if code else None,
        complexity_correct=True if code else None, edge_cases_identified=["empty input"] if code else None,
    ))
    context = {"topic": topic, "topic_type": "coding" if code or discussion else "discussion"}
    if code:
        context["coding_submission"] = True
    session.config.setdefault("turn_context", {})[turn.id] = context
    return turn


@pytest.mark.asyncio
async def test_report_folds_coding_submission_once_and_surfaces_breakdown(db_session, interview_llm):
    session = session_for(db_session)
    session.status = "completed"
    session.completed_at = utc_now()
    add_score(db_session, session, 0, "Python", 2)
    add_score(db_session, session, 1, "System design", 4)
    add_score(db_session, session, 2, "Coding Exercise", 5, code=True)
    add_score(db_session, session, 3, "Coding Exercise", 1, discussion=True)

    report, provisional = await generate_report(session, db=db_session, router=LLMRouter())

    assert provisional is False
    assert report.overall_score == pytest.approx(11 / 3, abs=0.01)
    assert report.coding_breakdown == {
        "problems_solved": 0, "problems_total": 1, "tests_passed": 2,
        "tests_total": 3, "complexity_correct": 1, "complexity_total": 1,
    }
    assert report.dimension_breakdown == {
        "technical_correctness": pytest.approx(11 / 3, abs=0.01),
        "completeness": pytest.approx(11 / 3, abs=0.01),
        "communication": pytest.approx(11 / 3, abs=0.01),
        "problem_solving": pytest.approx(11 / 3, abs=0.01),
    }
    assert all(getattr(turn.score, "complexity_correct", None) is None for turn in session.turns[:2])


@pytest.mark.asyncio
async def test_older_discussion_only_session_reports_without_coding_fields(db_session, interview_llm):
    session = session_for(db_session)
    session.status = "completed"
    session.completed_at = utc_now()
    add_score(db_session, session, 0, "Python", 3)
    add_score(db_session, session, 1, "Behavioral", 4)

    report, _ = await generate_report(session, db=db_session, router=LLMRouter())

    assert report.overall_score == 3.5
    assert report.coding_breakdown is None


@pytest.mark.asyncio
async def test_report_prompt_contains_specific_turn_evidence(db_session, interview_llm):
    session = session_for(db_session)
    session.status = "completed"
    session.completed_at = utc_now()
    turn = add_score(db_session, session, 2, "API reliability", 2)
    turn.question_text = "How do you handle retry storms?"
    turn.answer_text = "I retry immediately."
    turn.score.missing_concepts = ["backoff"]
    turn.score.skill_tags = ["API reliability"]
    session.config["turn_context"] = {turn.id: {"topic": "API reliability", "topic_type": "discussion"}}
    report, _ = await generate_report(session, db=db_session, router=LLMRouter())
    call = next(call for call in interview_llm.calls if call["task"] == "final_evaluation")
    assert "How do you handle retry storms?" in call["prompt"]
    assert "I retry immediately." in call["prompt"]
    assert "backoff" in call["prompt"]
    assert "API reliability" in call["prompt"]
    assert turn.id in call["prompt"]
    assert turn.id in report.improvement_suggestions[0]
    assert "backoff" in report.improvement_suggestions[0]
