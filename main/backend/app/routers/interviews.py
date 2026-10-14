import copy
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.formparsers import MultiPartException

from app.core.deps import get_current_user
from app.core.evaluation import EvaluationError, generate_report
from app.core.document_preparation import start_document_preparation
from app.core.intro_round import INITIAL_INTRO_QUESTION
from app.core.orchestrator import InterviewConflict, Orchestrator, PlanError, save_session, time_remaining, utc_now
from app.core.parsing import DocumentParsingError, parse_job_description, parse_resume, redact_contact_details
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


MAX_UPLOAD_REQUEST_BYTES = 22 * 1024 * 1024


async def _read_upload(form, field: str) -> tuple[bytes | None, str | None]:
    upload = form.get(field)
    if upload is None:
        return None, None
    if not isinstance(upload, StarletteUploadFile):
        raise HTTPException(status_code=422, detail=f"{field} must be an uploaded file")
    content = await upload.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Documents must be 10 MB or smaller.")
    return content, upload.filename


async def _create_payload(request: Request) -> tuple[str, InterviewConfig, str | None, str | None]:
    content_type = request.headers.get("content-type", "")
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > MAX_UPLOAD_REQUEST_BYTES:
                raise HTTPException(status_code=413, detail="Uploaded documents exceed the 20 MB total limit.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header.") from exc
    if content_type.startswith("application/json"):
        try:
            payload = InterviewCreate.model_validate(await request.json())
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=422, detail="Invalid Random interview request.") from exc
        return payload.mode, payload.config, None, None
    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(status_code=415, detail="Use JSON for Random mode or multipart form data for resume/job mode.")
    try:
        form = await request.form(max_files=2, max_fields=16)
        mode = form.get("mode")
        if mode not in {"resume", "job"}:
            raise HTTPException(status_code=422, detail="Mode must be resume or job for document uploads.")
        resume_bytes, resume_name = await _read_upload(form, "resume_file")
        if resume_bytes is None or resume_name is None:
            raise HTTPException(status_code=422, detail="A resume PDF is required for resume and job interviews.")
        resume = parse_resume(resume_bytes, resume_name)
        jd_text_input = form.get("jd_text")
        jd_text = jd_text_input if isinstance(jd_text_input, str) else None
        if mode == "job":
            # Nonblank pasted text wins; the unused file is not parsed at all.
            jd_bytes, jd_name = ((None, None) if jd_text and jd_text.strip()
                                 else await _read_upload(form, "jd_file"))
            jd = parse_job_description(jd_bytes, jd_text, jd_name)
        else:
            jd = None
        role = str(form.get("role", ""))[:200]
        skills_input = str(form.get("skills", ""))
        config = InterviewConfig.model_validate({
            "role": role or ("Role from job description" if jd else "Resume-based practice"),
            "experience": str(form.get("experience", "As described in the resume")),
            "skills": [skill.strip() for skill in skills_input.split(",") if skill.strip()][:30],
            "difficulty": str(form.get("difficulty", "Balanced")),
            "interview_type": str(form.get("interview_type", "Mixed")),
            "duration": int(str(form.get("duration", "30"))),
        })
        resume, _ = redact_contact_details(resume)
        if jd:
            jd, _ = redact_contact_details(jd)
        return mode, config, resume, jd
    except DocumentParsingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Interview settings are invalid.") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Interview settings are invalid.") from exc
    except MultiPartException as exc:
        raise HTTPException(status_code=422, detail="The multipart upload could not be parsed.") from exc


@router.post("", response_model=InterviewCreated, response_model_exclude_unset=True, status_code=201)
async def create_interview(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    llm: LLMRouter = Depends(get_llm_router),
) -> InterviewCreated:
    mode, config, resume, jd = await _create_payload(request)
    stored_config = config.model_dump()
    if resume is not None:
        stored_config.update({
            "preparation_status": "preparing",
            "intro_round": {"answers": [], "question": INITIAL_INTRO_QUESTION,
                            "follow_up_count": 0, "provisional": False, "models_used": []},
        })
    with interview_transaction(db):
        session = InterviewSession(user_id=user.id, mode=mode, config=stored_config)
        db.add(session)
        db.flush()
        session_id = session.id
        if resume is None:
            orchestrator = Orchestrator(db, llm)
            await orchestrator.generate_plan(session)
            # Random practice stays synchronous and has no intro round.
            session.started_at = utc_now()
            db.flush()
            result = await orchestrator.next_turn(session.id, None)
            if result.next_question is None:
                raise PlanError("Interview setup took too long; please retry")
            response = InterviewCreated(**result.model_dump(exclude_unset=True), first_question=result.next_question)
        else:
            response = InterviewCreated(
                session_id=session_id, turn_id=None, next_question=INITIAL_INTRO_QUESTION,
                is_complete=False, first_question=INITIAL_INTRO_QUESTION,
            )
    if resume is not None:
        documents = {"resume": resume}
        if mode == "job" and jd:
            documents["job_description"] = jd
        start_document_preparation(session_id, documents, llm,
                                  session_factory=sessionmaker(bind=db.get_bind()))
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
    preparing = session.config.get("preparation_status") in {"preparing", "failed"}
    if state is None and not preparing:
        raise HTTPException(status_code=409, detail="Interview has no plan; start a new Random interview")
    state = state or {"current_topic": None, "turns_on_current_topic": 0,
                      "topic_coverage": {}, "completion_reason": None}
    turns = list(db.scalars(select(Turn).where(Turn.session_id == session_id).order_by(Turn.turn_index)))
    return InterviewView(
        session_id=session.id, mode=session.mode, status=session.status,
        config={key: session.config[key] for key in InterviewConfig.model_fields},
        started_at=session.started_at, completed_at=session.completed_at,
        time_remaining=0.0 if session.status == "completed" else time_remaining(session),
        current_topic=state["current_topic"], turns_on_current_topic=state["turns_on_current_topic"],
        topic_coverage=state["topic_coverage"], completion_reason=state["completion_reason"],
        preparation_status=session.config.get("preparation_status", "ready"),
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
