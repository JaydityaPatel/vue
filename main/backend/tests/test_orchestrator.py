import asyncio
import copy
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.orchestrator import InterviewConflict, Orchestrator, PlanError, save_session, time_remaining
from app.db.database import Base
from app.db.models import SkillTag, Turn, TurnScore
from app.llm.router import LLMRouter
from tests.interview_helpers import session_for


async def start(db, interview_llm):
    session = session_for(db)
    engine = Orchestrator(db, LLMRouter())
    await engine.generate_plan(session)
    result = await engine.next_turn(session.id, None)
    return session, engine, result


async def test_plan_structure_reuses_case_insensitive_taxonomy_and_runs_once(db_session, interview_llm):
    existing = SkillTag(name="python")
    db_session.add(existing)
    db_session.flush()
    session = session_for(db_session)
    engine = Orchestrator(db_session, LLMRouter())
    await engine.generate_plan(session)
    await engine.generate_plan(session)
    plan = session.config["interview_plan"]
    assert len(plan["topics"]) == 4
    assert plan["topics"][0]["skill_tag_id"] == existing.id
    assert plan["topics"][0]["name"] == "python"
    assert all(2 <= len(topic["question_seeds"]) <= 3 and topic["expected_concepts"] for topic in plan["topics"])
    assert set(session.config["orchestrator_state"]["topic_coverage"].values()) == {"not_started"}
    assert len(list(db_session.scalars(select(SkillTag)))) == 4
    assert len(interview_llm.calls) == 1
    db_session.commit()
    db_session.expire_all()
    assert session.config["interview_plan"] == plan


@pytest.mark.parametrize("invalid", ["too_few", "duplicate"])
async def test_invalid_plan_is_rejected(db_session, interview_llm, invalid):
    if invalid == "too_few":
        interview_llm.plan["topics"] = interview_llm.plan["topics"][:2]
    else:
        interview_llm.plan["topics"][1]["name"] = "PYTHON"
    session = session_for(db_session)
    with pytest.raises(PlanError):
        await Orchestrator(db_session, LLMRouter()).generate_plan(session)
    assert "interview_plan" not in session.config


async def test_opening_question_and_resume_are_idempotent(db_session, interview_llm):
    session, engine, first = await start(db_session, interview_llm)
    assert first.next_question == "Explain Python."
    assert first.report_generation is None
    assert session.config["orchestrator_state"]["topic_coverage"]["Python"] == "in_progress"
    assert session.config["orchestrator_state"]["turns_on_current_topic"] == 0
    again = await engine.next_turn(session.id, None)
    assert again.turn_id == first.turn_id
    assert len(engine.turn_history(session.id)) == 1


@pytest.mark.parametrize("action", ["follow_up", "challenge"])
async def test_follow_up_stays_on_topic_and_increments(db_session, interview_llm, action):
    session, engine, _ = await start(db_session, interview_llm)
    interview_llm.actions.append(action)
    result = await engine.next_turn(session.id, "I would measure it and compare alternatives.")
    assert not result.is_complete
    assert session.config["orchestrator_state"]["current_topic"] == "Python"
    assert session.config["orchestrator_state"]["turns_on_current_topic"] == 1
    assert engine.turn_history(session.id)[-1].action_taken == action
    assert engine.turn_history(session.id)[0].score is not None


async def test_three_follow_ups_force_topic_switch_despite_model(db_session, interview_llm):
    session, engine, _ = await start(db_session, interview_llm)
    interview_llm.actions.extend(["follow_up"] * 4)
    for count in range(1, 4):
        await engine.next_turn(session.id, f"Answer {count}")
        assert session.config["orchestrator_state"]["turns_on_current_topic"] == count
        assert session.config["orchestrator_state"]["current_topic"] == "Python"
    result = await engine.next_turn(session.id, "Answer the third follow-up")
    assert not result.is_complete
    state = session.config["orchestrator_state"]
    assert state["current_topic"] == "System design"
    assert state["turns_on_current_topic"] == 0
    assert state["topic_coverage"]["Python"] == "covered"
    assert len(engine.turn_history(session.id)) == 5
    decision = session.config["turn_context"][engine.turn_history(session.id)[-2].id]["decision"]
    assert decision["requested_action"] == "follow_up"
    assert decision["executed_action"] == "move_on"


async def test_low_time_scores_last_answer_and_completes_without_new_topic(db_session, interview_llm):
    session, engine, _ = await start(db_session, interview_llm)
    engine.clock = lambda: session.started_at + timedelta(minutes=29)
    calls = len(interview_llm.calls)
    result = await engine.next_turn(session.id, "This is the final answer.")
    assert result.is_complete and result.next_question is None
    assert result.completion_reason == "time_limit"
    assert result.report_generation.url == f"/interviews/{session.id}/report"
    assert len(interview_llm.calls) == calls + 1  # score only
    assert engine.turn_history(session.id)[0].score is not None
    assert session.config["orchestrator_state"]["topic_coverage"]["System design"] == "not_started"
    assert session.completed_at is not None


async def test_timeout_crossed_during_action_call_prevents_next_question(db_session, interview_llm):
    session, engine, _ = await start(db_session, interview_llm)
    interview_llm.actions.append("follow_up")
    before = session.started_at + timedelta(minutes=27)
    after = session.started_at + timedelta(minutes=29)
    ticks = iter([before, before, after])
    engine.clock = lambda: next(ticks, after)
    result = await engine.next_turn(session.id, "An answer")
    assert result.is_complete
    assert len(engine.turn_history(session.id)) == 1


async def test_all_topics_covered_ends_and_does_not_rescore_on_repeat(db_session, interview_llm):
    session, engine, _ = await start(db_session, interview_llm)
    for _ in range(4):
        result = await engine.next_turn(session.id, "An answer addressing the topic.")
    assert result.is_complete
    assert all(value == "covered" for value in session.config["orchestrator_state"]["topic_coverage"].values())
    calls = len(interview_llm.calls)
    again = await engine.next_turn(session.id, "Late duplicate")
    assert again.is_complete
    assert len(interview_llm.calls) == calls
    assert len(engine.turn_history(session.id)) == 4


@pytest.mark.parametrize("malformed", [
    "this is not JSON", '{"action":"end_session","rationale":"because","question_text":""}',
    '{"action":"follow_up","rationale":"because","question_text":" "}',
])
async def test_invalid_action_falls_back_and_logs(db_session, interview_llm, caplog, malformed):
    session, engine, _ = await start(db_session, interview_llm)
    interview_llm.actions.append(malformed)
    result = await engine.next_turn(session.id, "An answer")
    assert not result.is_complete
    assert session.config["orchestrator_state"]["current_topic"] == "System design"
    assert "llm_action_rejected" in caplog.text


async def test_full_eight_turn_interview_persists_history(db_session, interview_llm):
    session, engine, _ = await start(db_session, interview_llm)
    interview_llm.actions.extend(["follow_up", "move_on"] * 4)
    for index in range(8):
        result = await engine.next_turn(session.id, f"Detailed candidate answer {index}")
        db_session.commit()
        db_session.expire_all()
        assert result.is_complete == (index == 7)
    history = engine.turn_history(session.id)
    assert [turn.turn_index for turn in history] == list(range(8))
    assert all(turn.answer_text and turn.score and turn.score.rubric_version == "v1" for turn in history)
    assert session.status == "completed"


async def test_stale_question_rejected_without_mutation(db_session, interview_llm):
    session, engine, first = await start(db_session, interview_llm)
    await engine.next_turn(session.id, "Answer", turn_id=first.turn_id)
    with pytest.raises(InterviewConflict):
        await engine.next_turn(session.id, "Duplicate", turn_id=first.turn_id)
    assert engine.turn_history(session.id)[-1].answer_text is None


async def test_compare_and_swap_rejects_stale_session_revision(db_session, interview_llm):
    session, engine, _ = await start(db_session, interview_llm)
    original = copy.deepcopy(session.config)
    await engine.next_turn(session.id, "First writer")
    db_session.commit()
    with pytest.raises(InterviewConflict):
        save_session(db_session, session, original, copy.deepcopy(original))
    db_session.rollback()
    assert len(engine.turn_history(session.id)) == 2


async def test_fallback_provenance_is_persisted(db_session, interview_llm):
    interview_llm.provisional = True
    session, engine, first = await start(db_session, interview_llm)
    await engine.next_turn(session.id, "An answer")
    assert session.config["interview_plan"]["provisional"] is True
    assert session.config["turn_context"][first.turn_id]["generated_by_model"] == "mock-fallback"
    assert session.config["turn_context"][first.turn_id]["provisional"] is True
    assert engine.turn_history(session.id)[0].score.provisional is True


def test_time_remaining_handles_sqlite_naive_utc(db_session):
    session = session_for(db_session)
    now = session.started_at
    session.started_at = now.replace(tzinfo=None)
    assert time_remaining(session, now + timedelta(minutes=10)) == 1200


async def test_concurrent_answers_cannot_overwrite_or_duplicate_turns(tmp_path, interview_llm, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    with sessions() as setup_db:
        session, _, first = await start(setup_db, interview_llm)
        session_id = session.id
        setup_db.commit()
    barrier = asyncio.Event()
    waiting = 0
    original_run = LLMRouter.run

    async def synchronized_run(router, **kwargs):
        nonlocal waiting
        if kwargs["task"] == "score_answer":
            waiting += 1
            if waiting == 2:
                barrier.set()
            await asyncio.wait_for(barrier.wait(), timeout=5)
        return await original_run(router, **kwargs)

    monkeypatch.setattr(LLMRouter, "run", synchronized_run)

    async def answer(text):
        with sessions() as db:
            try:
                await Orchestrator(db, LLMRouter()).next_turn(session_id, text, turn_id=first.turn_id)
                db.commit()
                return "saved", text
            except InterviewConflict:
                db.rollback()
                return "conflict", text

    results = await asyncio.gather(answer("Writer one"), answer("Writer two"))
    assert sorted(status for status, _ in results) == ["conflict", "saved"]
    winner = next(text for status, text in results if status == "saved")
    with sessions() as db:
        turns = list(db.scalars(select(Turn).order_by(Turn.turn_index)))
        assert len(turns) == 2
        assert turns[0].answer_text == winner
        assert turns[1].answer_text is None
        assert db.query(TurnScore).count() == 1
    engine.dispose()


async def test_action_outage_uses_deterministic_topic_and_saved_seed(db_session, interview_llm, caplog):
    session, engine, _ = await start(db_session, interview_llm)
    interview_llm.fail_task = "next_turn"
    result = await engine.next_turn(session.id, "Candidate answer")
    assert result.next_question == "Explain System design."
    assert session.config["orchestrator_state"]["current_topic"] == "System design"
    assert "llm_action_rejected" in caplog.text
    assert "opening_question_rejected" in caplog.text
