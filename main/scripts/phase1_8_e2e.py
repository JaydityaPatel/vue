"""Real API / WebSocket walkthrough for Phases 1–8; no provider mocks."""
from __future__ import annotations

import asyncio
import audioop
import difflib
import json
import os
import secrets
import sys
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap

import httpx
import websockets
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO = PROJECT.parent
BACKEND = PROJECT / "backend"
FIXTURES = HERE / "e2e-fixtures"
AUDIO = FIXTURES / "audio"
REPORTS = REPO / "reports"
RESUME_TEXT = FIXTURES / "sample-resume.txt"
RESUME_PDF = FIXTURES / "sample-resume.pdf"
JOB_TEXT = FIXTURES / "sample-job-description.md"
BASE = os.getenv("E2E_API_BASE_URL", "http://127.0.0.1:8002").rstrip("/")

sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
load_dotenv(BACKEND / ".env")
from app.db.database import SessionLocal, engine  # noqa: E402
from app.db.models import InterviewSession, LLMCallLog, User  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

EVIDENCE: dict = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "api_base": BASE,
    "fixture_resume": str(RESUME_PDF.relative_to(REPO)),
    "fixture_job_description": str(JOB_TEXT.relative_to(REPO)),
    "timings": [],
    "modes": {},
}
RUN_STARTED = datetime.now(timezone.utc).replace(tzinfo=None)


def save_evidence() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "phase1-8-evidence.json").write_text(
        json.dumps(EVIDENCE, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def make_pdf() -> None:
    """Write a small, valid one-page PDF from the committed text fixture."""
    lines: list[str] = []
    for line in RESUME_TEXT.read_text(encoding="utf-8").splitlines():
        plain = line.replace("—", "-").replace("–", "-").replace("•", "-")
        lines.extend(wrap(plain, width=92) or [""])
    commands = ["BT", "/F1 9 Tf", "48 748 Td", "13 TL"]
    for index, line in enumerate(lines[:52]):
        safe = line.encode("ascii", errors="replace").decode("ascii")
        safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index:
            commands.append("T*")
        commands.append(f"({safe}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    RESUME_PDF.write_bytes(output)


def db_snapshot() -> dict:
    db = SessionLocal()
    try:
        return {
            "database": str(engine.url),
            "users": db.scalar(select(func.count()).select_from(User)),
            "sessions": db.scalar(select(func.count()).select_from(InterviewSession)),
            "sessions_by_mode": dict(db.execute(
                select(InterviewSession.mode, func.count()).group_by(InterviewSession.mode)
            ).all()),
            "sessions_by_status": dict(db.execute(
                select(InterviewSession.status, func.count()).group_by(InterviewSession.status)
            ).all()),
        }
    finally:
        db.close()


def internal_session(session_id: str) -> tuple[dict, list[dict]]:
    db = SessionLocal()
    try:
        session = db.get(InterviewSession, session_id)
        if session is None:
            return {}, []
        config = dict(session.config)
        contexts = config.get("turn_context", {})
        turns = sorted(session.turns, key=lambda turn: turn.turn_index)
        detail = []
        for turn in turns:
            item = {
                "turn_index": turn.turn_index,
                "question": turn.question_text,
                "answer": turn.answer_text,
                "action_taken": turn.action_taken,
                "topic": contexts.get(turn.id, {}).get("topic"),
                "generated_by_model": contexts.get(turn.id, {}).get("generated_by_model"),
                "provisional": contexts.get(turn.id, {}).get("provisional"),
                "decision": contexts.get(turn.id, {}).get("decision"),
            }
            if turn.score:
                item["score"] = {
                    name: getattr(turn.score, name)
                    for name in ("technical_correctness", "completeness", "communication", "problem_solving")
                }
                item["missing_concepts"] = turn.score.missing_concepts
                item["feedback"] = turn.score.feedback
                item["scored_by_model"] = turn.score.scored_by_model
                item["score_provisional"] = turn.score.provisional
            detail.append(item)
        return config, detail
    finally:
        db.close()


def logs_since_start() -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.scalars(select(LLMCallLog).where(LLMCallLog.created_at >= RUN_STARTED)
                          .order_by(LLMCallLog.created_at)).all()
        return [{
            "task": row.task,
            "model_requested": row.model_requested,
            "model_used": row.model_used,
            "status": row.status,
            "provisional": row.provisional,
            "latency_ms": row.latency_ms,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        } for row in rows]
    finally:
        db.close()


def timed_request(name: str, response: httpx.Response) -> dict:
    entry = {"stage": name, "status_code": response.status_code}
    return entry


def make_account(client: httpx.Client) -> tuple[str, str]:
    email = f"vue.phase18.{uuid.uuid4().hex[:12]}@example.com"
    password = secrets.token_urlsafe(24)
    start = time.perf_counter()
    response = client.post("/auth/register", json={
        "email": email, "password": password, "full_name": "Phase 1–8 E2E Candidate",
    })
    response.raise_for_status()
    EVIDENCE["timings"].append(timed_request("signup", response) | {
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 1),
    })
    login = client.post("/auth/login", json={"email": email, "password": password})
    login.raise_for_status()
    token = login.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    me.raise_for_status()
    EVIDENCE["test_account"] = {"created_through_api": True, "email": email, "me_status": me.status_code}
    client.headers["Authorization"] = f"Bearer {token}"
    return token, email


def answer_for_question(question: str, index: int) -> str:
    q = question.casefold()
    if any(word in q for word in ("gil", "asyncio", "multiprocessing", "concurrency", "thread")):
        return ("In standard CPython the GIL allows only one thread to execute Python bytecode at a time. "
                "For I/O-bound work I use asyncio for many cooperative operations, or threads around blocking I/O; "
                "for CPU-bound parallel work I use multiprocessing or a native library that releases the GIL. "
                "I would benchmark and account for coordination and serialization overhead.")
    if any(word in q for word in ("docker", "container", "image", "build")):
        return ("I use a multi-stage build, pin dependencies, order stable layers for cache reuse, and exclude local "
                "files with .dockerignore. I run as a non-root user, keep secrets out of the image, and use volumes "
                "only for data that needs persistence. I check image size and startup behavior in CI.")
    if any(word in q for word in ("rest", "api version", "backwards compatibility", "http")):
        return ("I preserve existing fields and behavior, make additive changes first, and version only when a breaking "
                "contract is unavoidable. I use idempotent methods where appropriate, validate status codes, document "
                "deprecation windows, and test old and new clients against the contract.")
    if any(word in q for word in ("kafka", "event", "stream", "duplicate", "delivery")):
        return ("I owned a Kafka pipeline processing about 10,000 events per second. I used idempotent consumers, "
                "bounded retries, and monitoring for delayed or duplicate events. We measured p95 processing "
                "latency below 200 milliseconds and tested replay behavior before rollout.")
    if any(word in q for word in ("payment", "ledger", "reconciliation", "risk", "fraud")):
        return ("I have not built a payment ledger directly. I would first map the invariants and lifecycle, then use "
                "immutable entries, idempotency keys, transactional writes, reconciliation, and audit trails. "
                "My closest experience is making Kafka consumers safe under retries and duplicate delivery.")
    if any(word in q for word in ("postgres", "database", "query", "transaction", "sql")):
        return ("I used PostgreSQL query plans and indexes to reduce a reporting API's p95 latency by 42%. "
                "I checked representative plans and write cost, then tested concurrent updates and rollback behavior "
                "before releasing the schema change.")
    if any(word in q for word in ("incident", "conflict", "challenge", "failure", "team")):
        return ("During a delayed release, I brought the owners together, listed the unresolved decisions, and split "
                "the work into milestones with clear owners. We checked risks daily, shipped on the revised date, "
                "and reused the checklist. I learned to agree on success measures early.")
    return ("I would clarify the reliability and correctness requirements first, then compare a simple implementation "
            "with the operational cost of the alternatives. I would test failure cases, define a measurable SLO, "
            "and use production metrics to validate the result.")


RANDOM_ANSWERS = [
    "I owned a Kafka pipeline processing about 10,000 events per second. I used idempotent consumers, bounded retries, and partition-aware processing. We monitored delayed events and measured p95 processing latency below 200 milliseconds, then validated replay behavior before rollout.",
    "I try to write clean code, communicate well, and ask for help when needed. I do not have a specific example right now.",
    "I think teamwork and communication are important for every project. Could we move to another question?",
    "For PostgreSQL performance, I inspect the query plan with representative data, check indexes and write amplification, then compare p95 latency and correctness under concurrent updates before shipping.",
    "A release was delayed because teams had different assumptions. I gathered the owners, clarified decisions, split the work into milestones, and raised risks daily. We shipped on the revised date and adopted the same checklist for later releases.",
    "Could you clarify whether you want the API design or the data consistency trade-offs? I would approach those differently.",
]


async def receive_json(ws, timeout: float = 240) -> dict:
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    if isinstance(raw, bytes):
        return {"type": "binary_server_message"}
    return json.loads(raw)


def ws_url(path: str) -> str:
    return BASE.replace("https://", "wss://").replace("http://", "ws://") + path


async def end_session_over_ws(session_id: str, token: str) -> dict:
    evidence = {"attempted": True, "events": []}
    async with websockets.connect(ws_url(f"/ws/interview/{session_id}"), open_timeout=90,
                                  close_timeout=8, max_size=8_000_000) as ws:
        await ws.send(json.dumps({"type": "auth", "token": token}))
        question_end = False
        while True:
            message = await receive_json(ws, timeout=240)
            kind = message.get("type")
            evidence["events"].append(kind)
            if kind == "error":
                evidence["error"] = message.get("message")
                return evidence
            if kind == "question_end":
                question_end = True
                break
        if question_end:
            await ws.send(json.dumps({"type": "end"}))
            while True:
                try:
                    message = await receive_json(ws, timeout=30)
                except websockets.ConnectionClosed:
                    break
                evidence["events"].append(message.get("type"))
                if message.get("type") == "snapshot":
                    evidence["final_status"] = message.get("session", {}).get("status")
                if message.get("type") == "error":
                    evidence["error"] = message.get("message")
                    break
    return evidence


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        rate, channels, width = source.getframerate(), source.getnchannels(), source.getsampwidth()
        pcm = source.readframes(source.getnframes())
    if width != 2:
        pcm = audioop.lin2lin(pcm, width, 2)
    if channels == 2:
        pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
    elif channels != 1:
        raise ValueError(f"Expected mono or stereo audio: {path}")
    if rate != 16000:
        pcm, _ = audioop.ratecv(pcm, 2, 1, rate, 16000, None)
    return pcm


async def intro_over_ws(session_id: str, token: str) -> dict:
    """Use recorded Kokoro WAV answers through the actual VAD/Whisper socket."""
    result: dict = {"transport": "real WebSocket", "audio_source": "local Kokoro-generated WAV fixtures",
                    "answers": [], "messages": []}
    paths = [AUDIO / f"intro-{index}.wav" for index in (1, 2, 3)]
    async with websockets.connect(ws_url(f"/ws/intro/{session_id}"), open_timeout=120,
                                  close_timeout=10, max_size=8_000_000) as ws:
        await ws.send(json.dumps({"type": "auth", "token": token}))

        async def next_question_end() -> tuple[str, str]:
            turn_id = ""
            chunks: list[str] = []
            while True:
                msg = await receive_json(ws, timeout=300)
                result["messages"].append(msg.get("type"))
                if msg.get("type") == "error":
                    raise RuntimeError(msg.get("message", "WebSocket error"))
                if msg.get("type") == "question_start":
                    turn_id = msg.get("turn_id", "")
                    chunks = []
                elif msg.get("type") == "question_chunk":
                    chunks.append(msg.get("text", ""))
                elif msg.get("type") == "question_end":
                    return turn_id or msg.get("turn_id", ""), "".join(chunks)

        turn_id, question = await next_question_end()
        result["initial_question"] = question
        for index, audio_path in enumerate(paths):
            pcm = read_pcm(audio_path)
            await ws.send(json.dumps({"type": "playback_done", "turn_id": turn_id}))
            padded = pcm + bytes((-len(pcm)) % 1024)
            for offset in range(0, len(padded), 1024):
                await ws.send(padded[offset:offset + 1024])
            # 2.048s of 16kHz silence exceeds the configured 1.8s endpoint.
            for _ in range(64):
                await ws.send(bytes(1024))

            transcript = None
            while transcript is None:
                msg = await receive_json(ws, timeout=300)
                result["messages"].append(msg.get("type"))
                if msg.get("type") == "error":
                    raise RuntimeError(msg.get("message", "WebSocket error"))
                if msg.get("type") == "transcript" and msg.get("final"):
                    transcript = msg.get("text", "")
            similarity = difflib.SequenceMatcher(
                None, "".join(transcript.casefold().split()), "".join(
                    ("I am a backend engineer with about four years of experience. I have mainly worked with Python, Kafka, and PostgreSQL, and I enjoy designing services that stay reliable as traffic grows." if index == 0 else
                     "One project I owned was a Kafka pipeline processing around ten thousand events per second. I built idempotent consumers and retries for duplicates and delayed events, and tracked p ninety latency under two hundred milliseconds." if index == 1 else
                     "I am interested in payment systems because correctness and reliability matter as much as throughput. I have not worked directly with a payment ledger yet, but I have handled transactional data and production incidents, and I would be deliberate about learning reconciliation requirements.").casefold().split())
            ).ratio()
            result["answers"].append({
                "audio_file": str(audio_path.relative_to(REPO)),
                "transcript": transcript,
                "text_similarity": round(similarity, 3),
            })
            if index < 2:
                turn_id, question = await next_question_end()
                result["answers"][-1]["next_question"] = question
            else:
                main_chunks: list[str] = []
                while True:
                    msg = await receive_json(ws, timeout=300)
                    result["messages"].append(msg.get("type"))
                    if msg.get("type") == "error":
                        raise RuntimeError(msg.get("message", "WebSocket error"))
                    if msg.get("type") == "intro_complete":
                        result["intro_complete"] = True
                    elif msg.get("type") == "question_start":
                        main_chunks = []
                    elif msg.get("type") == "question_chunk":
                        main_chunks.append(msg.get("text", ""))
                    elif msg.get("type") == "question_end":
                        result["main_interview_first_question"] = "".join(main_chunks)
                    elif msg.get("type") == "snapshot":
                        result["main_session_status"] = msg.get("session", {}).get("status")
                    if result.get("intro_complete"):
                        break
    return result


def wait_preparation(client: httpx.Client, session_id: str) -> dict:
    started = time.perf_counter()
    for _ in range(240):
        response = client.get(f"/interviews/{session_id}")
        response.raise_for_status()
        view = response.json()
        if view.get("preparation_status") == "ready":
            return {"view": view, "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}
        if view.get("preparation_status") == "failed":
            config, _ = internal_session(session_id)
            raise RuntimeError(f"Document preparation failed; config metadata keys={sorted(config)}")
        time.sleep(1)
    raise TimeoutError("Document plan did not become ready within 240 seconds")


def capture_session(client: httpx.Client, session_id: str) -> tuple[dict, list[dict]]:
    view = client.get(f"/interviews/{session_id}")
    view.raise_for_status()
    config, internal_turns = internal_session(session_id)
    return view.json(), internal_turns


def run_random(client: httpx.Client, token: str) -> dict:
    payload = {
        "mode": "random",
        "config": {"role": "Backend Engineer", "experience": "2 years",
                   "skills": ["Python", "PostgreSQL", "Docker"], "difficulty": "Balanced",
                   "interview_type": "Mixed", "duration": 20},
    }
    started = time.perf_counter()
    created = client.post("/interviews", json=payload)
    created.raise_for_status()
    value = created.json()
    session_id = value["session_id"]
    mode = {"session_id": session_id, "setup_elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "first_question": value.get("first_question"), "intro_round_present": False, "turns": []}
    for index, canned_answer in enumerate(RANDOM_ANSWERS):
        current = client.get(f"/interviews/{session_id}").json()
        if current["status"] == "completed":
            break
        unanswered = next((turn for turn in reversed(current["turns"]) if turn["answer_text"] is None), None)
        if unanswered is None:
            break
        answer = (answer_for_question(unanswered["question_text"], index)
                  if index == 0 or index >= 3 else canned_answer)
        start = time.perf_counter()
        response = client.post(f"/interviews/{session_id}/answer", json={
            "answer_text": answer, "turn_id": unanswered["id"],
        })
        response.raise_for_status()
        mode.setdefault("answer_timings_ms", []).append(round((time.perf_counter() - start) * 1000, 1))
        if response.json().get("is_complete"):
            break
    mode["end_websocket"] = asyncio.run(end_session_over_ws(session_id, token))
    _, mode["turns"] = capture_session(client, session_id)
    mode["status"] = client.get(f"/interviews/{session_id}").json()["status"]
    return mode


def create_document_session(client: httpx.Client, mode: str) -> dict:
    fields = {
        "mode": mode, "role": "Backend Engineer", "experience": "4 years",
        "skills": "Python, Kafka, PostgreSQL, Docker", "difficulty": "Balanced",
        "interview_type": "Mixed", "duration": "20",
    }
    files = {"resume_file": (RESUME_PDF.name, RESUME_PDF.read_bytes(), "application/pdf")}
    if mode == "job":
        fields["jd_text"] = JOB_TEXT.read_text(encoding="utf-8")
    started = time.perf_counter()
    response = client.post("/interviews", data=fields, files=files)
    response.raise_for_status()
    created = response.json()
    prepared = wait_preparation(client, created["session_id"])
    return {
        "session_id": created["session_id"],
        "initial_question": created.get("first_question"),
        "preparation_elapsed_ms": prepared["elapsed_ms"],
        "create_and_prepare_elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "preparation_status": prepared["view"]["preparation_status"],
        "plan_topics": internal_session(created["session_id"])[0].get("interview_plan", {}).get("topics", []),
    }


def run_document_turns(client: httpx.Client, mode: dict, count: int = 5) -> None:
    session_id = mode["session_id"]
    timings = []
    for _ in range(count):
        view = client.get(f"/interviews/{session_id}").json()
        if view["status"] == "completed":
            break
        unanswered = next((turn for turn in reversed(view["turns"]) if turn["answer_text"] is None), None)
        if unanswered is None:
            break
        answer = answer_for_question(unanswered["question_text"], len(view["turns"]))
        start = time.perf_counter()
        response = client.post(f"/interviews/{session_id}/answer", json={
            "answer_text": answer, "turn_id": unanswered["id"],
        })
        response.raise_for_status()
        timings.append(round((time.perf_counter() - start) * 1000, 1))
        if response.json().get("is_complete"):
            break
        if len(timings) == 3 and count > 3:
            print("Waiting one provider quota window before final document-mode turns.", flush=True)
            time.sleep(65)
    mode["answer_timings_ms"] = timings


def generate_report(client: httpx.Client, mode: dict) -> None:
    session_id = mode["session_id"]
    response = client.post(f"/interviews/{session_id}/report")
    if response.status_code == 200:
        mode["report"] = response.json()
    else:
        mode["report_error"] = {"status_code": response.status_code, "detail": response.text[:400]}


def finish_and_capture(client: httpx.Client, mode: dict, token: str) -> None:
    session_id = mode["session_id"]
    if client.get(f"/interviews/{session_id}").json()["status"] != "completed":
        mode["end_websocket"] = asyncio.run(end_session_over_ws(session_id, token))
    view, turns = capture_session(client, session_id)
    mode["status"] = view["status"]
    mode["turns"] = turns
    config, _ = internal_session(session_id)
    if config.get("report_metadata"):
        mode["report_metadata"] = config["report_metadata"]
    if view["status"] == "completed":
        generate_report(client, mode)


def run() -> None:
    make_pdf()
    with httpx.Client(base_url=BASE, timeout=httpx.Timeout(300)) as client:
        health = client.get("/health")
        health.raise_for_status()
        EVIDENCE["health"] = health.json()
        EVIDENCE["database_before"] = db_snapshot()
        token, _ = make_account(client)
        print("Created and authenticated a test user through /auth/register and /auth/login.", flush=True)

        random = run_random(client, token)
        EVIDENCE["modes"]["random"] = random
        save_evidence()
        print(f"Random: {len(random['turns'])} turns, status={random['status']}, "
              f"setup={random['setup_elapsed_ms']}ms", flush=True)
        if random.get("status") == "completed":
            print("Waiting one provider quota window before report generation and document modes.", flush=True)
            time.sleep(65)
            generate_report(client, random)
            save_evidence()

        for mode_name in ("resume", "job"):
            if mode_name == "job":
                print("Waiting one provider quota window before Job mode.", flush=True)
                time.sleep(65)
            try:
                mode = create_document_session(client, mode_name)
            except Exception as exc:
                EVIDENCE["modes"][mode_name] = {
                    "status": "setup_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                save_evidence()
                print(f"{mode_name.title()} setup failed: {type(exc).__name__}: {exc}", flush=True)
                continue
            try:
                mode["intro_voice"] = asyncio.run(intro_over_ws(mode["session_id"], token))
            except Exception as exc:
                mode["intro_voice"] = {"transport": "real WebSocket attempted", "error": f"{type(exc).__name__}: {exc}"}
            config, _ = internal_session(mode["session_id"])
            mode["intro_summary"] = config.get("candidate_intro_summary")
            mode["intro_metadata"] = config.get("candidate_intro_metadata")
            mode["intro_round"] = config.get("intro_round")
            mode["main_interview_first_question"] = (
                mode["intro_voice"].get("main_interview_first_question")
                or (client.get(f"/interviews/{mode['session_id']}").json().get("turns") or [{}])[0].get("question_text")
            )
            run_document_turns(client, mode, count=5)
            finish_and_capture(client, mode, token)
            view = client.get(f"/interviews/{mode['session_id']}").json()
            mode["topic_coverage"] = view.get("topic_coverage")
            config, _ = internal_session(mode["session_id"])
            mode["candidate_intro_summary_used_in_plan"] = config.get("candidate_intro_summary")
            mode["web_research_sources"] = [
                {"topic": topic.get("name"), "source": topic.get("source"),
                 "source_tags": topic.get("source_tags")}
                for topic in config.get("interview_plan", {}).get("topics", [])
                if topic.get("source") == "web_research" or "web_research" in topic.get("source_tags", [])
            ]
            EVIDENCE["modes"][mode_name] = mode
            save_evidence()
            print(f"{mode_name.title()}: status={mode.get('status')}, "
                  f"intro={bool(mode.get('intro_round', {}).get('status') == 'completed')}, "
                  f"turns={len(mode.get('turns', []))}, report={bool(mode.get('report'))}", flush=True)

        # Retry the Random session's supported voice End control after STT warm-up.
        random = EVIDENCE["modes"]["random"]
        if random.get("status") != "completed":
            random["end_websocket_after_stt_warmup"] = asyncio.run(end_session_over_ws(random["session_id"], token))
            random_view, random["turns"] = capture_session(client, random["session_id"])
            random["status"] = random_view["status"]
            if random["status"] == "completed":
                generate_report(client, random)

        EVIDENCE["llm_call_logs"] = logs_since_start()
        EVIDENCE["database_after"] = db_snapshot()
        save_evidence()
        print("E2E evidence saved to reports/phase1-8-evidence.json", flush=True)
        for name, mode in EVIDENCE["modes"].items():
            if not isinstance(mode, dict):
                continue
            print(f"{name}: status={mode.get('status')}, turns={len(mode.get('turns', []))}, "
                  f"report_model={(mode.get('report') or {}).get('generated_by_model')}")
        logs = EVIDENCE["llm_call_logs"]
        print("LLM logs: " + json.dumps({
            "count": len(logs),
            "by_status": {status: sum(row["status"] == status for row in logs)
                          for status in sorted({row["status"] for row in logs})},
            "models": sorted({row["model_used"] for row in logs}),
            "provisional": sum(bool(row["provisional"]) for row in logs),
        }))


if __name__ == "__main__":
    run()
