"""Recurring weakness summaries over completed sessions and controlled tags."""
from __future__ import annotations

import statistics
from collections import defaultdict

from sqlalchemy import String, cast, func, select, true
from sqlalchemy.orm import Session

from app.db.models import InterviewSession, SkillTag, Turn, TurnScore

WEAKNESS_SCORE_THRESHOLD = 2.5
MIN_DISTINCT_SESSIONS = 2
DIMENSIONS = ("technical_correctness", "completeness")


def get_recurring_weaknesses(user_id: str, db: Session) -> list[dict]:
    """Use a joined GROUP BY query, then compare session means chronologically."""
    if db.get_bind().dialect.name == "sqlite":
        score_tag = func.json_each(TurnScore.skill_tags).table_valued("value").alias("score_tag")
        grouped = db.execute(
            select(SkillTag.name, InterviewSession.id, InterviewSession.started_at,
                   func.count(TurnScore.id), func.avg(TurnScore.technical_correctness),
                   func.avg(TurnScore.completeness))
            .select_from(InterviewSession)
            .join(Turn, Turn.session_id == InterviewSession.id)
            .join(TurnScore, TurnScore.turn_id == Turn.id)
            .join(score_tag, true())
            .join(SkillTag, cast(score_tag.c.value, String) == SkillTag.name)
            .where(InterviewSession.user_id == user_id, InterviewSession.status == "completed")
            .group_by(SkillTag.name, InterviewSession.id, InterviewSession.started_at)
            .order_by(InterviewSession.started_at, InterviewSession.id)
        ).all()
        by_tag: dict[str, list[tuple[str, object, int, float, float]]] = defaultdict(list)
        for tag, session_id, started_at, count, technical, completeness in grouped:
            by_tag[tag].append((session_id, started_at, count, technical, completeness))
    else:
        # Other SQL dialects can use a different JSON-array unnest operator.
        # Keep their results correct with the same controlled-tag filter.
        rows = db.execute(
            select(InterviewSession.id, InterviewSession.started_at, TurnScore)
            .join(Turn, Turn.session_id == InterviewSession.id)
            .join(TurnScore, TurnScore.turn_id == Turn.id)
            .where(InterviewSession.user_id == user_id, InterviewSession.status == "completed")
            .order_by(InterviewSession.started_at, InterviewSession.id, Turn.turn_index)
        ).all()
        taxonomy = {tag.name for tag in db.scalars(select(SkillTag))}
        by_tag = defaultdict(list)
        for session_id, started_at, score in rows:
            for tag in set(score.skill_tags or []) & taxonomy:
                by_tag[tag].append((session_id, started_at, 1, score.technical_correctness, score.completeness))

    result = []
    for tag, occurrences in by_tag.items():
        sessions = {row[0] for row in occurrences}
        if len(sessions) < MIN_DISTINCT_SESSIONS:
            continue
        total_count = sum(row[2] for row in occurrences)
        averages = {
            "technical_correctness": round(sum(row[3] * row[2] for row in occurrences) / total_count, 2),
            "completeness": round(sum(row[4] * row[2] for row in occurrences) / total_count, 2),
        }
        weak_dimensions = [dimension for dimension, value in averages.items() if value < WEAKNESS_SCORE_THRESHOLD]
        if not weak_dimensions:
            continue

        first_dimension = weak_dimensions[0]
        dimension_index = 3 if first_dimension == "technical_correctness" else 4
        session_means = []
        for session_id in sessions:
            rows = [row for row in occurrences if row[0] == session_id]
            count = sum(row[2] for row in rows)
            mean = sum(row[dimension_index] * row[2] for row in rows) / count
            session_means.append((min(row[1] for row in rows), session_id, mean))
        session_means.sort(key=lambda row: (row[0], row[1]))
        ordered = [row[2] for row in session_means]
        midpoint = len(ordered) // 2
        delta = statistics.mean(ordered[midpoint:]) - statistics.mean(ordered[:midpoint])
        trend = "improving" if delta > 0.25 else "declining" if delta < -0.25 else "flat"
        result.append({
            "skill_tag": tag,
            "occurrence_count": total_count,
            "session_count": len(sessions),
            "average_scores": averages,
            "weak_dimensions": weak_dimensions,
            "trend": trend,
            "trend_delta": round(delta, 2),
        })
    return sorted(result, key=lambda item: (min(item["average_scores"][d] for d in item["weak_dimensions"]), item["skill_tag"]))
