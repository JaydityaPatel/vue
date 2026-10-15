"""Authenticated PCM input; all interview transitions use Phase 4's transaction."""
import asyncio
import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.orchestrator import Orchestrator, utc_now
from app.core.evaluation import generate_report
from app.core.document_preparation import wait_for_document_preparation
from app.core.intro_round import INITIAL_INTRO_QUESTION, INTRO_MIN_FOLLOW_UPS, intro_route, mode_has_intro_round, next_intro_question, summarize_intro
from app.config import settings
from app.core.security import decode_access_token
from app.db.database import get_db
from app.db.models import InterviewSession, Turn, User
from app.llm.router import LLMRouter
from app.routers.interviews import get_interview, get_llm_router, interview_transaction, owned_session
from app.voice.endpoint import Endpoint, FRAME_SAMPLES, SAMPLE_RATE
from app.voice.protocol import Authenticate, CodingSubmitted, End, Error, IntroComplete, Mute, PlaybackDone, Question, Snapshot, State, Transcript, controls
from app.voice.runtime import VoiceRuntime

router = APIRouter()
logger = logging.getLogger("vue.voice")
_active: set[str] = set()


@router.websocket("/ws/interview/{session_id}")
async def interview_voice(
    ws: WebSocket, session_id: str, db: Session = Depends(get_db),
    llm: LLMRouter = Depends(get_llm_router),
) -> None:
    await _voice_session(ws, session_id, db=db, llm=llm, intro=False)


@router.websocket("/ws/intro/{session_id}")
async def intro_voice(
    ws: WebSocket, session_id: str, db: Session = Depends(get_db),
    llm: LLMRouter = Depends(get_llm_router),
) -> None:
    await _voice_session(ws, session_id, db=db, llm=llm, intro=True)


async def _voice_session(ws: WebSocket, session_id: str, *, db: Session,
                         llm: LLMRouter, intro: bool) -> None:
    await ws.accept()
    claimed = False
    runtime = VoiceRuntime()

    async def send(message: Snapshot | State | Transcript | Question | Error | IntroComplete) -> None:
        await ws.send_json(message.model_dump(mode="json"))

    try:
        auth = Authenticate.model_validate_json(await asyncio.wait_for(ws.receive_text(), 10))
        user = db.get(User, decode_access_token(auth.token))
        if user is None:
            raise HTTPException(401, "Invalid authentication")
        session = owned_session(session_id, db, user)
        if intro and not mode_has_intro_round(session.mode):
            raise HTTPException(409, "The intro round is only available for resume and job interviews")
        if not intro and session.config.get("preparation_status") in {"preparing", "failed"}:
            raise HTTPException(409, "Finish the intro round before opening the interview room")
        if intro and session.config.get("preparation_status") == "failed":
            raise HTTPException(503, "Interview preparation failed. Check backend logs and create a new interview.")
        if session_id in _active:
            raise HTTPException(409, "This interview already has a voice connection")
        _active.add(session_id)
        claimed = True

        async def snapshot() -> None:
            db.expire_all()
            await send(Snapshot(session=get_interview(session_id, db, user)))

        await snapshot()
        if session.status != "in_progress":
            await ws.close(code=1000)
            return
        await send(State(state="thinking", stt_active=True))
        await runtime.prepare()
        intro_state = session.config.get("intro_round", {}) if intro else {}
        endpoint = Endpoint()
        audio = bytearray()
        preroll = bytearray()
        listening = False
        muted = False
        last_partial = 0
        pending_id = ""

        def reset_audio() -> None:
            nonlocal last_partial
            audio.clear()
            preroll.clear()
            endpoint.reset()
            runtime.reset()
            last_partial = 0

        async def question(turn_id: str, text: str) -> None:
            nonlocal pending_id, listening
            pending_id = turn_id
            listening = False
            await send(State(state="thinking"))
            await send(Question(type="question_start", turn_id=turn_id))
            # Only speak the orchestrator's validated, committed question. Raw
            # structured model deltas can contain rejected actions or JSON.
            for start in range(0, len(text), 80):
                await send(Question(type="question_chunk", turn_id=turn_id, text=text[start:start + 80]))
            await send(Question(type="question_end", turn_id=turn_id))

        if intro:
            if intro_state.get("status") == "completed":
                raise HTTPException(409, "This intro round is already complete; open the interview room")
            await question(f"intro-{len(intro_state.get('answers', []))}",
                           intro_state.get("question") or INITIAL_INTRO_QUESTION)
        else:
            with interview_transaction(db):
                opening = await Orchestrator(db, llm).next_turn(session_id, None)
            if opening.is_complete:
                await snapshot()
                await ws.close(code=1000)
                return
            await question(opening.turn_id or "", opening.next_question or "")
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("text") is not None:
                control = controls.validate_json(message["text"])
                if isinstance(control, End):
                    # An unanswered question is retained; only scored answers
                    # contribute to the report. End discards an unfinished utterance.
                    db.expire_all()
                    session = owned_session(session_id, db, user)
                    if intro:
                        session.config = {**session.config, "intro_round": {
                            **session.config.get("intro_round", {}), "status": "abandoned",
                        }}
                        session.status = "abandoned"
                        session.completed_at = utc_now()
                        db.commit()
                    else:
                        with interview_transaction(db):
                            Orchestrator(db, llm).end_interview(session_id)
                            ended_session = db.get(InterviewSession, session_id)
                            if ended_session.status == "completed":
                                report, provisional = await generate_report(ended_session, db=db, router=llm)
                                ended_session.config = {**ended_session.config, "report_metadata": {
                                    "model_used": report.generated_by_model, "provisional": provisional,
                                }}
                    await snapshot()
                    await ws.close(code=1000)
                    return
                if isinstance(control, Mute):
                    muted = control.muted
                    reset_audio()
                    await send(Transcript(turn_id=pending_id, text="", final=False))
                    await send(State(state="listening" if listening and not muted else "idle"))
                elif isinstance(control, PlaybackDone):
                    if control.turn_id != pending_id or listening:
                        raise HTTPException(409, "Unexpected playback acknowledgement")
                    reset_audio()
                    db.expire_all()
                    current_session = owned_session(session_id, db, user)
                    topic_name = current_session.config.get("orchestrator_state", {}).get("current_topic")
                    topic = next((item for item in current_session.config.get("interview_plan", {}).get("topics", [])
                                  if item["name"] == topic_name), None)
                    coding = current_session.config.get("coding_topics", {}).get(topic_name, {})
                    waiting_for_editor = bool(topic and topic.get("topic_type") == "coding" and coding.get("status") != "submitted")
                    listening = not waiting_for_editor
                    await send(State(state="idle" if muted or waiting_for_editor else "listening"))
                elif isinstance(control, CodingSubmitted):
                    db.expire_all()
                    current_session = owned_session(session_id, db, user)
                    topic_name = current_session.config.get("orchestrator_state", {}).get("current_topic")
                    coding = current_session.config.get("coding_topics", {}).get(topic_name, {})
                    if coding.get("status") != "submitted":
                        raise HTTPException(409, "Submit the coding exercise before returning to voice")
                    pending_turn = next((turn for turn in reversed(db.scalars(
                        select(Turn).where(Turn.session_id == session_id).order_by(Turn.turn_index)
                    ).all()) if turn.answer_text is None and not current_session.config.get("turn_context", {}).get(
                        turn.id, {}).get("transition_only")), None)
                    if pending_turn is None:
                        raise HTTPException(409, "The coding discussion question is unavailable")
                    await snapshot()
                    reset_audio()
                    await question(pending_turn.id, pending_turn.question_text)
                continue
            pcm = message.get("bytes")
            if pcm is None or len(pcm) != FRAME_SAMPLES * 2:
                raise HTTPException(400, "Expected 512 mono PCM16LE samples at 16000 Hz")
            if not listening or muted:
                continue  # Drain frames already in flight when playback started.
            ended = endpoint.feed(runtime.probability(pcm))
            if not endpoint.started:
                audio.clear()
                last_partial = 0
                preroll.extend(pcm)
                del preroll[:-SAMPLE_RATE]  # Half a second protects initial consonants.
                continue
            if not audio:
                audio.extend(preroll)
            audio.extend(pcm)
            if len(audio) > SAMPLE_RATE * 2 * 120:
                raise HTTPException(400, "Answer exceeded two minutes; reconnect and try a shorter answer")
            if ended:
                listening = False
                await send(State(state="thinking", stt_active=True))
                # Keep 200 ms trailing silence, discard the endpointing wait.
                trim = max(0, endpoint.silence_samples - SAMPLE_RATE // 5) * 2
                text = await runtime.transcribe(bytes(audio[:-trim] if trim else audio))
                await send(State(state="thinking"))
                if not text:
                    reset_audio()
                    listening = True
                    await send(Transcript(turn_id=pending_id, text="", final=False))
                    await send(State(state="listening"))
                    continue
                await send(Transcript(turn_id=pending_id, text=text, final=True))
                if intro:
                    db.expire_all()
                    session = owned_session(session_id, db, user)
                    intro_state = dict(session.config.get("intro_round", {}))
                    answers = list(intro_state.get("answers", []))
                    answers.append(text)
                    route = intro_route(settings.hardware_tier)
                    models_used = list(intro_state.get("models_used", []))
                    provisional = bool(intro_state.get("provisional", False))
                    if len(answers) < INTRO_MIN_FOLLOW_UPS + 1:
                        follow_up, model, is_provisional = await next_intro_question(
                            answers, router=llm, db=db, route=route
                        )
                        models_used.append(model)
                        provisional = provisional or is_provisional
                        intro_state.update({"answers": answers, "question": follow_up,
                                            "follow_up_count": len(answers), "models_used": models_used,
                                            "provisional": provisional})
                        session.config = {**session.config, "intro_round": intro_state}
                        db.commit()
                        reset_audio()
                        await question(f"intro-{len(answers)}", follow_up)
                        continue

                    summary, model, summary_provisional = await summarize_intro(
                        answers, router=llm, db=db, route=route
                    )
                    models_used.append(model)
                    provisional = provisional or summary_provisional or any(
                        used != route[0] for used in models_used
                    )
                    intro_state.update({"answers": answers, "question": "", "follow_up_count": len(answers) - 1,
                                        "models_used": models_used, "provisional": provisional,
                                        "status": "completed"})
                    session.config = {**session.config, "intro_round": intro_state,
                                      "candidate_intro_summary": summary,
                                      "candidate_intro_metadata": {"model_used": model, "provisional": provisional}}
                    db.commit()
                    try:
                        await wait_for_document_preparation(session)
                    except RuntimeError as exc:
                        raise HTTPException(503, str(exc)) from exc
                    db.expire_all()
                    session = owned_session(session_id, db, user)
                    with interview_transaction(db):
                        session.started_at = utc_now()
                        opening = await Orchestrator(db, llm).next_turn(session_id, None)
                    if opening.next_question is None:
                        raise HTTPException(503, "The interview plan is not ready yet; reconnect shortly")
                    await snapshot()
                    await ws.send_json(IntroComplete().model_dump(mode="json"))
                    await ws.close(code=1000)
                    return
                db.expire_all()
                with interview_transaction(db):
                    result = await Orchestrator(db, llm).next_turn(session_id, text, turn_id=pending_id)
                    if result.is_complete:
                        completed_session = db.get(InterviewSession, session_id)
                        report, provisional = await generate_report(completed_session, db=db, router=llm)
                        completed_session.config = {**completed_session.config, "report_metadata": {
                            "model_used": report.generated_by_model, "provisional": provisional,
                        }}
                await snapshot()
                if result.is_complete:
                    await send(State(state="idle"))
                    await ws.close(code=1000)
                    return
                reset_audio()
                await question(result.turn_id or "", result.next_question or "")
            elif len(audio) - last_partial >= SAMPLE_RATE * 2 * 4:
                last_partial = len(audio)
                await send(State(state="listening", stt_active=True))
                text = await runtime.transcribe(bytes(audio))
                await send(Transcript(turn_id=pending_id, text=text, final=False))
                await send(State(state="listening"))
    except WebSocketDisconnect:
        pass
    except (jwt.InvalidTokenError, asyncio.TimeoutError):
        await send(Error(message="Authentication failed; sign in again"))
        await ws.close(code=4401)
    except (ValidationError, HTTPException) as exc:
        db.rollback()
        await send(Error(message=exc.detail if isinstance(exc, HTTPException) else "Invalid voice message"))
        await ws.close(code=4400)
    except Exception:
        db.rollback()
        logger.exception("Voice connection failed for interview %s", session_id)
        try:
            await send(Error(message="Voice processing failed. Check the server's voice model/CUDA configuration, then reconnect. Your saved turns are retained."))
            await ws.close(code=1011)
        except (WebSocketDisconnect, RuntimeError):
            pass
    finally:
        if claimed:
            _active.discard(session_id)
