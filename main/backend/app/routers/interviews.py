import copy
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.evaluation import EvaluationError, generate_report
from app.core.orchestrator import InterviewConflict, Orchestrator, PlanError, save_session, time_remaining, utc_now
from app.db.database import get_db
from app.db.models import InterviewSession, Turn, User
from app.llm.router import AllProvidersExhaustedError, LLMRouter
from app.schemas.interviews import (
    AnswerInput, InterviewConfig, InterviewCreate, InterviewCreated, InterviewView, ReportReference,
    ReportView, ScoreView, TurnResult, TurnView,
)

router = APIRouter(prefix="/interviews", tags=["interviews"])


@lru_cache
def get_llm_router() -> LLMRouter:
    return LLMRouter()


def owned_session(session_id: str, db: Session, user: User) -> InterviewSession:
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="This interview belongs to another user")
    return session


@contextmanager
def interview_transaction(db: Session) -> Iterator[None]:
    try:
        yield
        db.commit()
    except InterviewConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (EvaluationError, PlanError) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except AllProvidersExhaustedError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Interview models are unavailable; please retry shortly") from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="The interview changed concurrently; please retry") from exc
    except OperationalError as exc:
        db.rollback()
        if "locked" not in str(exc).lower():
            raise
        raise HTTPException(status_code=409, detail="Another interview update is in progress; please retry") from exc
    except Exception:
        db.rollback()
        raise


@router.post("", response_model=InterviewCreated, response_model_exclude_unset=True, status_code=201)
async def create_interview(
    payload: InterviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    llm: LLMRouter = Depends(get_llm_router),
) -> InterviewCreated:
    with interview_transaction(db):
        session = InterviewSession(user_id=user.id, mode=payload.mode, config=payload.config.model_dump())
        db.add(session)
        db.flush()
        orchestrator = Orchestrator(db, llm)
        await orchestrator.generate_plan(session)
        # Planning is setup time, before the candidate sees a question.
        session.started_at = utc_now()
        db.flush()
        result = await orchestrator.next_turn(session.id, None)
        if result.next_question is None:
            raise PlanError("Interview setup took too long; please retry")
        response = InterviewCreated(**result.model_dump(exclude_unset=True), first_question=result.next_question)
    return response


@router.post("/{session_id}/answer", response_model=TurnResult, response_model_exclude_unset=True)
async def answer_interview(
    session_id: str,
    payload: AnswerInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    llm: LLMRouter = Depends(get_llm_router),
) -> TurnResult:
    owned_session(session_id, db, user)
    with interview_transaction(db):
        result = await Orchestrator(db, llm).next_turn(session_id, payload.answer_text, turn_id=payload.turn_id)
    return result


@router.get("/{session_id}", response_model=InterviewView)
def get_interview(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> InterviewView:
    session = owned_session(session_id, db, user)
    state = session.config.get("orchestrator_state")
    if state is None:
        raise HTTPException(status_code=409, detail="Interview has no plan; start a new Random interview")
    turns = list(db.scalars(select(Turn).where(Turn.session_id == session_id).order_by(Turn.turn_index)))
    return InterviewView(
        session_id=session.id, status=session.status,
        config={key: session.config[key] for key in InterviewConfig.model_fields},
        started_at=session.started_at, completed_at=session.completed_at,
        time_remaining=0.0 if session.status == "completed" else time_remaining(session),
        current_topic=state["current_topic"], turns_on_current_topic=state["turns_on_current_topic"],
        topic_coverage=state["topic_coverage"], completion_reason=state["completion_reason"],
        report_generation=ReportReference(url=f"/interviews/{session.id}/report") if session.status == "completed" else None,
        turns=[TurnView(
            id=turn.id, turn_index=turn.turn_index, question_text=turn.question_text,
            answer_text=turn.answer_text, action_taken=turn.action_taken,
            topic=session.config["turn_context"][turn.id]["topic"],
            generated_by_model=session.config["turn_context"][turn.id]["generated_by_model"],
            provisional=session.config["turn_context"][turn.id]["provisional"],
            score=ScoreView.model_validate(turn.score, from_attributes=True) if turn.score else None,
        ) for turn in turns],
    )


@router.post("/{session_id}/report", response_model=ReportView)
async def create_report(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    llm: LLMRouter = Depends(get_llm_router),
) -> ReportView:
    session = owned_session(session_id, db, user)
    if session.status != "completed":
        raise HTTPException(status_code=409, detail="Finish the interview before generating its report")
    with interview_transaction(db):
        original = copy.deepcopy(session.config)
        existing = session.report is not None
        report, provisional = await generate_report(session, db=db, router=llm)
        if not existing:
            config = copy.deepcopy(original)
            config["report_metadata"] = {"model_used": report.generated_by_model, "provisional": provisional}
            save_session(db, session, original, config)
        result = ReportView(
            id=report.id, session_id=session.id, summary=report.summary,
            improvement_suggestions=report.improvement_suggestions,
            overall_score=report.overall_score, generated_by_model=report.generated_by_model,
            provisional=provisional,
        )
    return result
