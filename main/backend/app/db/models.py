import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    ForeignKey,
    DateTime,
    JSON,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    sessions: Mapped[list["InterviewSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SkillTag(Base):
    """Controlled taxonomy of skills/topics. Prevents free-text tag drift
    (e.g. 'React hooks' vs 'hooks in React' vs 'useEffect') by giving the
    LLM a fixed list to choose from wherever possible."""

    __tablename__ = "skill_tags"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. "dsa", "system-design", "behavioral"


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    mode: Mapped[str] = mapped_column(String)  # "job" | "resume" | "random"
    status: Mapped[str] = mapped_column(String, default="in_progress")  # in_progress|completed|abandoned
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # role, difficulty, duration, etc.
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
    turns: Mapped[list["Turn"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    report: Mapped["SessionReport | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )


class Turn(Base):
    """One question/answer exchange (including follow-ups) within a session."""

    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id"))
    turn_index: Mapped[int] = mapped_column(Integer)
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String, nullable=True)  # follow_up|challenge|move_on|switch_topic
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    session: Mapped["InterviewSession"] = relationship(back_populates="turns")
    score: Mapped["TurnScore | None"] = relationship(
        back_populates="turn", cascade="all, delete-orphan", uselist=False
    )


class TurnScore(Base):
    __tablename__ = "turn_scores"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    turn_id: Mapped[str] = mapped_column(ForeignKey("turns.id"), unique=True)

    technical_correctness: Mapped[float | None] = mapped_column(Float, nullable=True)  # 1-5
    completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    communication: Mapped[float | None] = mapped_column(Float, nullable=True)
    problem_solving: Mapped[float | None] = mapped_column(Float, nullable=True)

    expected_concepts: Mapped[list] = mapped_column(JSON, default=list)
    missing_concepts: Mapped[list] = mapped_column(JSON, default=list)
    skill_tags: Mapped[list] = mapped_column(JSON, default=list)  # list of SkillTag.name values
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    rubric_version: Mapped[str | None] = mapped_column(String, nullable=True)
    scored_by_model: Mapped[str | None] = mapped_column(String, nullable=True)
    provisional: Mapped[bool] = mapped_column(Boolean, default=False)
    tests_passed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tests_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    complexity_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    edge_cases_identified: Mapped[list | None] = mapped_column(JSON, nullable=True)

    turn: Mapped["Turn"] = relationship(back_populates="score")


class SessionReport(Base):
    __tablename__ = "session_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id"), unique=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    improvement_suggestions: Mapped[list] = mapped_column(JSON, default=list)
    generated_by_model: Mapped[str | None] = mapped_column(String, nullable=True)
    coding_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dimension_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    session: Mapped["InterviewSession"] = relationship(back_populates="report")


class LLMCallLog(Base):
    """Every LLM call, regardless of provider, logged here for latency/token
    tracking and debugging the router's fallback behavior."""

    __tablename__ = "llm_call_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    task: Mapped[str] = mapped_column(String)  # e.g. "next_turn", "score_answer"
    model_requested: Mapped[str] = mapped_column(String)
    model_used: Mapped[str] = mapped_column(String)
    provisional: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String)  # success|error|rate_limited
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
