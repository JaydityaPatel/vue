import logging

from sqlalchemy.orm import Session

from app.db.models import LLMCallLog

logger = logging.getLogger("vue.llm")
logging.basicConfig(level=logging.INFO)


def log_llm_call(
    db: Session,
    *,
    task: str,
    model_requested: str,
    model_used: str,
    status: str,
    latency_ms: float | None = None,
    input_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    output_tokens: int | None = None,
    provisional: bool = False,
    error_message: str | None = None,
) -> None:
    """Persist one LLM call's metadata. Called by the router after every
    attempt (success or failure) so latency/token/fallback patterns are
    queryable later, not just visible in stdout."""
    entry = LLMCallLog(
        task=task,
        model_requested=model_requested,
        model_used=model_used,
        status=status,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        provisional=provisional,
        error_message=error_message,
    )
    db.add(entry)
    # The caller owns the transaction. Committing here would also commit a
    # half-finished interview answer whenever an LLM call is logged.

    logger.info(
        "llm_call task=%s requested=%s used=%s status=%s latency_ms=%s provisional=%s",
        task,
        model_requested,
        model_used,
        status,
        f"{latency_ms:.1f}" if latency_ms is not None else "n/a",
        provisional,
    )
