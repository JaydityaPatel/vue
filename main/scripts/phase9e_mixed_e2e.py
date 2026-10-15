"""Live Mixed-session voice -> coding -> voice walkthrough; requires configured LLM and voice models."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import tempfile
import time
import wave
from pathlib import Path

import httpx
import websockets
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO = PROJECT.parent
BACKEND = PROJECT / "backend"
FRONTEND = PROJECT / "frontend"
BASE = os.getenv("E2E_API_BASE_URL", "http://127.0.0.1:8002").rstrip("/")
REPORT = REPO / "reports" / "phase9e-mixed-e2e.json"

sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
load_dotenv(BACKEND / ".env")
from app.core.problem_bank import ACTIVE_PATH  # noqa: E402


def wav_to_pcm(wav_bytes: bytes) -> bytes:
    import audioop
    from io import BytesIO

    with wave.open(BytesIO(wav_bytes), "rb") as source:
        rate, channels, width = source.getframerate(), source.getnchannels(), source.getsampwidth()
        pcm = source.readframes(source.getnframes())
    if width != 2:
        pcm = audioop.lin2lin(pcm, width, 2)
    if channels == 2:
        pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
    if rate != 16000:
        pcm, _ = audioop.ratecv(pcm, 2, 1, rate, 16000, None)
    return pcm


async def read_question(ws, evidence: dict) -> tuple[dict, str, str]:
    snapshot = evidence.get("session", {})
    turn_id, chunks = "", []
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=300)
        if isinstance(raw, bytes):
            continue
        message = json.loads(raw)
        kind = message.get("type")
        evidence.setdefault("events", []).append(kind)
        if kind == "error":
            raise RuntimeError(message.get("message", "voice WebSocket error"))
        if kind == "snapshot":
            snapshot = message["session"]
            evidence["session"] = snapshot
        elif kind == "question_start":
            turn_id, chunks = message["turn_id"], []
        elif kind == "question_chunk":
            chunks.append(message.get("text", ""))
        elif kind == "question_end":
            question = "".join(chunks)
            evidence.setdefault("questions", []).append(question)
            return snapshot, turn_id or message["turn_id"], question


async def play_answer(ws, turn_id: str, pcm: bytes, evidence: dict) -> str:
    await ws.send(json.dumps({"type": "playback_done", "turn_id": turn_id}))
    padded = pcm + bytes((-len(pcm)) % 1024)
    for offset in range(0, len(padded), 1024):
        await ws.send(padded[offset:offset + 1024])
    for _ in range(64):
        await ws.send(bytes(1024))
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=300))
        evidence.setdefault("events", []).append(message.get("type"))
        if message.get("type") == "error":
            raise RuntimeError(message.get("message", "voice WebSocket error"))
        if message.get("type") == "transcript" and message.get("final"):
            evidence.setdefault("transcripts", []).append(message["text"])
            return message["text"]


async def wait_for_editor_pause(ws, evidence: dict) -> None:
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        evidence.setdefault("events", []).append(message.get("type"))
        if message.get("type") == "error":
            raise RuntimeError(message.get("message", "voice WebSocket error"))
        if message.get("type") == "state" and message.get("state") == "idle":
            return


async def run_live(session_id: str, token: str, synth) -> dict:
    import phase1_8_e2e as prior

    evidence: dict = {"transport": "live FastAPI WebSocket + real VAD/Whisper", "audio_source": "locally synthesized Kokoro speech"}
    async with httpx.AsyncClient(base_url=BASE, headers={"Authorization": f"Bearer {token}"}, timeout=300) as client:
        async with websockets.connect(prior.ws_url(f"/ws/interview/{session_id}"), open_timeout=120,
                                      close_timeout=10, max_size=8_000_000) as ws:
            await ws.send(json.dumps({"type": "auth", "token": token}))
            session, turn_id, question = await read_question(ws, evidence)
            code_topic = False
            # Answer discussion topics until the planned coding exercise is reached.
            for index in range(8):
                if session.get("current_topic_type") == "coding" and session.get("coding_status") != "submitted":
                    code_topic = True
                    await ws.send(json.dumps({"type": "playback_done", "turn_id": turn_id}))
                    await wait_for_editor_pause(ws, evidence)
                    break
                pcm = wav_to_pcm(synth("I start by clarifying the constraints, then compare a simple approach with its edge cases. In my last backend project I measured latency and checked retry behavior before release."))
                transcript = await play_answer(ws, turn_id, pcm, evidence)
                evidence.setdefault("answers", []).append({"question": question, "transcript": transcript,
                                                           "topic_type": session.get("current_topic_type")})
                session, turn_id, question = await read_question(ws, evidence)
            if not code_topic:
                raise RuntimeError("No coding topic was reached within the 8-topic walkthrough bound")

            problem_response = await client.get(f"/interviews/{session_id}/coding/problem")
            problem_response.raise_for_status()
            problem = problem_response.json()
            case_response = await client.post(f"/interviews/{session_id}/coding/run", json={
                "problem_id": problem["id"], "sample_only": False,
            })
            case_response.raise_for_status()
            cases = case_response.json()["cases"]
            catalog = json.loads(ACTIVE_PATH.read_text(encoding="utf-8"))["problems"]
            record = next(item for item in catalog if item["id"] == problem["id"])
            candidate_code = record["reference_solution"]
            with tempfile.TemporaryDirectory(prefix="phase9e-") as tmp:
                payload_path = Path(tmp) / "candidate.json"
                payload_path.write_text(json.dumps({"code": candidate_code, "entry_point": problem["entry_point"],
                                                    "test_cases": cases}), encoding="utf-8")
                result = await asyncio.to_thread(
                    __import__("subprocess").run,
                    ["node", str(PROJECT / "scripts" / "run_pyodide_candidate.mjs"), str(payload_path)],
                    cwd=PROJECT, capture_output=True, text=True, timeout=300,
                )
                if result.returncode:
                    raise RuntimeError(result.stderr)
                results = json.loads(result.stdout)
            if not results or any(result.get("status") != "passed" for result in results):
                raise RuntimeError("The candidate solution did not pass the live coding test set")
            submitted = await client.post(f"/interviews/{session_id}/coding/submit", json={
                "problem_id": problem["id"], "submitted_code": candidate_code, "results": results,
            })
            submitted.raise_for_status()
            evidence["coding"] = {"problem": problem["title"], "problem_id": problem["id"],
                                  "tests_passed": submitted.json()["passed"], "tests_total": submitted.json()["total"],
                                  "candidate_source": "locally executed verified reference implementation in Pyodide"}
            await ws.send(json.dumps({"type": "coding_submitted"}))
            session, turn_id, question = await read_question(ws, evidence)
            returned_to_discussion = False
            for _ in range(5):
                topic_type = session.get("current_topic_type")
                is_return_transition = topic_type == "discussion" and question.startswith("Good, let's go back")
                if is_return_transition:
                    returned_to_discussion = True
                    break
                spoken = ("Sorting plus the two-pointer scan is quadratic time and the sort is n log n. The extra space depends on the output. I skip duplicates and check short arrays, repeated values, and inputs with no matching triplet." if topic_type == "coding" else
                          "I clarify the constraints, test the main path and boundary cases, and compare the result with the expected behavior before shipping.")
                transcript = await play_answer(ws, turn_id, wav_to_pcm(synth(spoken)), evidence)
                evidence.setdefault("answers", []).append({"question": question, "transcript": transcript,
                                                           "topic_type": topic_type})
                session, turn_id, question = await read_question(ws, evidence)
            if not returned_to_discussion:
                raise RuntimeError("The coding discussion did not transition back to a discussion topic")
            # Answer one ordinary voice question after returning, then end through the existing voice control.
            transcript = await play_answer(ws, turn_id, wav_to_pcm(synth("I would validate with representative traffic, monitor error rates and latency, then adjust based on the results.")), evidence)
            evidence.setdefault("answers", []).append({"question": question, "transcript": transcript,
                                                       "topic_type": "discussion"})
            # The orchestrator has a new pending voice question; End completes the same session.
            await read_question(ws, evidence)
            await ws.send(json.dumps({"type": "end"}))
            while True:
                try:
                    message = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                except websockets.ConnectionClosed:
                    break
                evidence.setdefault("events", []).append(message.get("type"))
                if message.get("type") == "snapshot":
                    evidence["final_status"] = message.get("session", {}).get("status")
                    if evidence["final_status"] == "completed":
                        break
                if message.get("type") == "error":
                    raise RuntimeError(message.get("message", "error ending voice session"))
        view = (await client.get(f"/interviews/{session_id}")).json()
        evidence["turns"] = [{"question": turn["question_text"], "answer": turn["answer_text"],
                              "topic": turn["topic"], "topic_type": turn.get("topic_type"),
                              "action_taken": turn["action_taken"], "score": turn["score"]}
                             for turn in view["turns"] if turn["score"] is not None]
        report_response = await client.post(f"/interviews/{session_id}/report")
        report_response.raise_for_status()
        evidence["report"] = report_response.json()
        evidence["session_id"] = session_id
        evidence["topic_coverage"] = view["topic_coverage"]
        evidence["session_status"] = view["status"]
        return evidence


def main() -> None:
    import phase1_8_e2e as prior
    sys.path.insert(0, str(BACKEND / "benchmarks"))
    from tts_bench import KokoroSynthesizer
    from app.core.orchestrator import utc_now
    from app.db.models import InterviewSession, SkillTag, Turn, User
    from app.db.database import SessionLocal
    from sqlalchemy import select

    with httpx.Client(base_url=BASE, timeout=300) as client:
        email = f"phase9e-{secrets.token_hex(5)}@example.com"
        password = "phase9e-review-only-password"
        registered = client.post("/auth/register", json={"email": email, "password": password})
        registered.raise_for_status()
        logged_in = client.post("/auth/login", json={"email": email, "password": password})
        logged_in.raise_for_status()
        token = logged_in.json()["access_token"]
        # Plan generation is seeded because the configured Gemini route is
        # currently unavailable and local Qwen cannot satisfy PlanOutput.
        # The persisted session, interview WebSocket, scoring, Pyodide submit,
        # topic transitions, and report all use the real application path.
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email))
            topics = [
                {"name": "Backend Engineering", "topic_type": "discussion",
                 "question_seeds": ["Tell me about a backend project and how you measured reliability.", "What tradeoffs did you consider?"],
                 "expected_concepts": ["ownership", "reliability metrics", "tradeoffs"]},
                {"name": "Coding Exercise", "topic_type": "coding",
                 "question_seeds": ["Let's work through a coding exercise.", "Explain your approach to the coding problem."],
                 "expected_concepts": ["correctness", "time and space complexity", "edge case analysis"]},
                {"name": "System Design", "topic_type": "discussion",
                 "question_seeds": ["How would you scale a read-heavy service?", "How do you validate a design?"],
                 "expected_concepts": ["scaling", "reliability", "validation"]},
            ]
            stored_topics = []
            for topic in topics:
                tag = db.scalar(select(SkillTag).where(SkillTag.name == topic["name"]))
                if tag is None:
                    tag = SkillTag(name=topic["name"])
                    db.add(tag); db.flush()
                stored_topics.append({**topic, "skill_tag_id": tag.id, "source": "manual-e2e-seed",
                                      "source_tags": ["manual-e2e-seed"],
                                      "question_seed_sources": ["manual-e2e-seed"] * len(topic["question_seeds"]),
                                      "expected_concept_sources": ["manual-e2e-seed"] * len(topic["expected_concepts"])})
            session = InterviewSession(user_id=user.id, mode="random", started_at=utc_now(), config={
                "role": "Backend Engineer", "experience": "Mid-level", "skills": ["Python", "Algorithms", "Backend"],
                "difficulty": "Balanced", "interview_type": "Mixed", "duration": 30,
                "interview_plan": {"topics": stored_topics, "generated_by_model": "manual-e2e-seed", "provisional": False},
                "orchestrator_state": {"topic_coverage": {topic["name"]: ("in_progress" if index == 0 else "not_started")
                                                              for index, topic in enumerate(stored_topics)},
                                       "current_topic": stored_topics[0]["name"], "turns_on_current_topic": 0,
                                       "completion_reason": None},
                "turn_context": {},
            })
            db.add(session); db.flush()
            first = Turn(session_id=session.id, turn_index=0, question_text=stored_topics[0]["question_seeds"][0])
            db.add(first); db.flush()
            session.config = {**session.config, "turn_context": {first.id: {
                "topic": stored_topics[0]["name"], "topic_type": "discussion",
                "skill_tag_id": stored_topics[0]["skill_tag_id"],
                "expected_concepts": stored_topics[0]["expected_concepts"],
                "generated_by_model": "manual-e2e-seed", "provisional": False,
            }}}
            session_id = session.id
            db.commit()
        plan, _ = prior.internal_session(session_id)
        EVIDENCE = {"session_id": session_id, "plan_generation": "seeded for the live walkthrough because the configured Gemini plan route returned 503/quota errors; Mixed plan policy is covered by backend tests", "plan": [
            {"name": topic["name"], "topic_type": topic["topic_type"]}
            for topic in plan.get("interview_plan", {}).get("topics", [])
        ], "voice_session": None}
        print("Mixed plan: " + json.dumps(EVIDENCE["plan"]), flush=True)
        synth = KokoroSynthesizer()
        def speak(text: str) -> bytes:
            return synth.synthesize(text)[0]
        result = asyncio.run(run_live(session_id, token, speak))
        EVIDENCE["voice_session"] = result
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(EVIDENCE, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"report_file": str(REPORT), "status": result["session_status"],
                          "coding": result["coding"], "overall_score": result["report"]["overall_score"],
                          "coding_breakdown": result["report"].get("coding_breakdown"),
                          "transcripts": result["transcripts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
