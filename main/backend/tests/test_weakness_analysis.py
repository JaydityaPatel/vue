from datetime import timedelta

import pytest

from app.core.orchestrator import utc_now
from app.core.weakness_analysis import get_recurring_weaknesses
from app.db.models import InterviewSession, SkillTag, Turn, TurnScore
from tests.interview_helpers import CONFIG


def make_user(db):
    from app.db.models import User
    user = User(email="weakness@example.com", hashed_password="unused")
    db.add(user); db.flush()
    tag = SkillTag(name="API reliability")
    db.add(tag); db.flush()
    return user, tag


def add_session(db, user, tag, index, scores, *, status="completed"):
    session = InterviewSession(user_id=user.id, mode="random", status=status, config=dict(CONFIG),
                              started_at=utc_now() + timedelta(days=index),
                              completed_at=utc_now() + timedelta(days=index) if status == "completed" else None)
    db.add(session); db.flush()
    for turn_index, value in enumerate(scores):
        turn = Turn(session_id=session.id, turn_index=turn_index, question_text="How do you handle retries?",
                    answer_text="Use backoff.")
        db.add(turn); db.flush()
        db.add(TurnScore(turn_id=turn.id, technical_correctness=value, completeness=value,
                         communication=4, problem_solving=4, expected_concepts=[], missing_concepts=[],
                         skill_tags=[tag.name], feedback="", rubric_version="v1", scored_by_model="test"))
    return session


def test_tag_seen_multiple_times_in_one_session_is_not_recurring(db_session):
    user, tag = make_user(db_session)
    add_session(db_session, user, tag, 0, [1, 2, 2])
    assert get_recurring_weaknesses(user.id, db_session) == []


def test_low_tag_average_across_three_sessions_is_flagged(db_session):
    user, tag = make_user(db_session)
    for index, value in enumerate([2, 1, 2]):
        add_session(db_session, user, tag, index, [value])
    result = get_recurring_weaknesses(user.id, db_session)
    assert result[0]["skill_tag"] == tag.name
    assert result[0]["session_count"] == 3
    assert result[0]["average_scores"] == {"technical_correctness": pytest.approx(5 / 3, abs=.01),
                                            "completeness": pytest.approx(5 / 3, abs=.01)}


def test_high_scores_are_not_weaknesses(db_session):
    user, tag = make_user(db_session)
    for index in range(3):
        add_session(db_session, user, tag, index, [4, 5])
    assert get_recurring_weaknesses(user.id, db_session) == []


@pytest.mark.parametrize(("values", "expected"), [
    ([1, 1, 2, 2], "improving"),
    ([2, 2, 1, 1], "declining"),
    ([2, 2, 2, 2], "flat"),
])
def test_trend_compares_early_and_late_completed_sessions(db_session, values, expected):
    user, tag = make_user(db_session)
    for index, value in enumerate(values):
        add_session(db_session, user, tag, index, [value])
    assert get_recurring_weaknesses(user.id, db_session)[0]["trend"] == expected


def test_zero_completed_sessions_returns_empty(db_session):
    user, tag = make_user(db_session)
    add_session(db_session, user, tag, 0, [1], status="in_progress")
    assert get_recurring_weaknesses(user.id, db_session) == []
