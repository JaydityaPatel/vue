"""Single-process background preparation for the app's single-worker local runtime."""
import asyncio
import logging
from dataclasses import dataclass
from sqlalchemy.orm import sessionmaker

from app.core.job_web_research import maybe_enrich_job_plan
from app.core.interview_planning import generate_plan_for_session
from app.db.database import SessionLocal
from app.db.models import InterviewSession
from app.llm.router import LLMRouter

logger = logging.getLogger("vue.document_preparation")


@dataclass
class PreparationJob:
    task: asyncio.Task[None]
    error: str | None = None


_jobs: dict[str, PreparationJob] = {}


def start_document_preparation(
    session_id: str, documents: dict[str, str], router: LLMRouter,
    session_factory: sessionmaker | None = None,
) -> None:
    """Plan in a separate DB session while the candidate completes the intro round."""
    if session_id in _jobs and not _jobs[session_id].task.done():
        return
    factory = session_factory or SessionLocal
    job = PreparationJob(task=asyncio.create_task(_prepare(session_id, documents, router, factory)))
    _jobs[session_id] = job


async def _prepare(session_id: str, documents: dict[str, str], router: LLMRouter,
                   session_factory: sessionmaker) -> None:
    db = session_factory()
    try:
        session = db.get(InterviewSession, session_id)
        if session is None:
            raise ValueError("Interview session disappeared before planning")
        await generate_plan_for_session(session, db=db, router=router, documents=documents)
        if session.mode == "job":
            await maybe_enrich_job_plan(
                session, db=db, router=router,
                job_description=documents.get("job_description", ""),
            )
        session.config = {**session.config, "preparation_status": "ready"}
        db.commit()
        logger.info("document_plan_ready session_id=%s mode=%s", session_id, session.mode)
    except Exception as exc:
        db.rollback()
        job = _jobs.get(session_id)
        if job:
            job.error = f"Interview preparation failed ({type(exc).__name__}). Check backend logs and retry."
        session = db.get(InterviewSession, session_id)
        if session is not None:
            session.config = {**session.config, "preparation_status": "failed"}
            db.commit()
        logger.exception("document_plan_failed session_id=%s", session_id)
    finally:
        db.close()


async def wait_for_document_preparation(session: InterviewSession, timeout: float = 240.0) -> None:
    job = _jobs.get(session.id)
    if job is None:
        if session.config.get("preparation_status") == "ready":
            return
        raise RuntimeError("Document preparation is unavailable; reconnect to the running backend or create a new interview.")
    try:
        await asyncio.wait_for(asyncio.shield(job.task), timeout=timeout)
    except TimeoutError as exc:
        raise RuntimeError("Interview preparation is still running; reconnect in a moment.") from exc
    if job.error:
        raise RuntimeError(job.error)


def clear_finished_job(session_id: str) -> None:
    job = _jobs.get(session_id)
    if job and job.task.done():
        _jobs.pop(session_id, None)
