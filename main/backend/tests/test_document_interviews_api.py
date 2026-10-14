import json
import time

from tests.test_interviews_api import login
from tests.test_parsing import pdf_with_text
from tests.test_voice import authenticate, until
from tests.test_voice import voice_runtime as _voice_runtime_fixture


def post_document(client, headers, *, mode="resume", resume=None, jd_text=None, jd_file=None):
    data = {"mode": mode, "role": "Backend engineer", "experience": "Senior",
            "difficulty": "Balanced", "interview_type": "Mixed", "duration": "30"}
    files = {}
    if resume is not None:
        files["resume_file"] = ("resume.pdf", resume, "application/pdf")
    if jd_text is not None:
        data["jd_text"] = jd_text
    if jd_file is not None:
        files["jd_file"] = jd_file
    return client.post("/interviews", headers=headers, data=data, files=files)


def wait_for_plan(client, headers, session_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/interviews/{session_id}", headers=headers)
        assert response.status_code == 200, response.text
        state = response.json()
        if state["preparation_status"] == "ready":
            return state
        if state["preparation_status"] == "failed":
            raise AssertionError("Background plan generation failed")
        time.sleep(0.01)
    raise AssertionError("Background plan generation did not finish")


def test_resume_multipart_creates_shared_orchestrator_plan_and_redacts_before_llm(client, interview_llm, caplog):
    headers = login(client)
    resume = pdf_with_text("Jane Candidate jane@example.com +1 (415) 555-2671 built a real-time Kafka pipeline")
    response = post_document(client, headers, resume=resume)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["first_question"] == "Tell me about yourself."
    assert created["turn_id"] is None
    state = wait_for_plan(client, headers, created["session_id"])
    assert len(state["turns"]) == 0
    assert state["mode"] == "resume"
    assert state["config"]["role"] == "Backend engineer"
    prompt = json.loads(interview_llm.calls[0]["prompt"])
    extracted = prompt["candidate_documents"]["resume"]
    assert "Jane Candidate" in extracted and "Kafka pipeline" in extracted
    assert "jane@example.com" not in extracted and "555-2671" not in extracted
    assert "email_count=1 phone_count=1" in caplog.text
    assert "jane@example.com" not in caplog.text
    assert not any(call["task"] == "job_web_research" for call in interview_llm.calls)


def test_job_mode_cross_references_resume_and_pasted_jd_preferred_over_file(client, interview_llm):
    headers = login(client)
    response = post_document(client, headers, mode="job",
        resume=pdf_with_text("Built services using Kafka"),
        jd_text="Production role requiring Kubernetes and observability",
        jd_file=("ignored.txt", b"this content must lose to pasted text", "text/plain"))
    assert response.status_code == 201, response.text
    wait_for_plan(client, headers, response.json()["session_id"])
    prompt = json.loads(interview_llm.calls[0]["prompt"])
    assert prompt["candidate_documents"] == {
        "resume": "Built services using Kafka",
        "job_description": "Production role requiring Kubernetes and observability",
    }
    saved = client.get(f"/interviews/{response.json()['session_id']}", headers=headers).json()
    assert saved["status"] == "in_progress"
    assert any(call["task"] == "job_web_research" for call in interview_llm.calls)


def test_job_research_failure_does_not_fail_base_plan_or_session(client, interview_llm, caplog, monkeypatch):
    from app.llm.router import AllProvidersExhaustedError

    original_run = interview_llm.run
    async def run_with_research_failure(**kwargs):
        if kwargs["task"] == "job_web_research":
            raise AllProvidersExhaustedError("Scripted web research outage")
        return await original_run(**kwargs)
    monkeypatch.setattr(interview_llm, "run", run_with_research_failure)
    headers = login(client)
    response = post_document(client, headers, mode="job",
        resume=pdf_with_text("Built secure APIs"), jd_text="Backend role at Example Corp")
    assert response.status_code == 201, response.text
    state = wait_for_plan(client, headers, response.json()["session_id"])

    assert state["preparation_status"] == "ready"
    assert any(call["task"] == "build_question_bank" for call in interview_llm.calls)
    assert "job_web_research_failed" in caplog.text


def test_job_mode_accepts_uploaded_text_job_description(client, interview_llm):
    headers = login(client)
    response = post_document(client, headers, mode="job",
        resume=pdf_with_text("Built Python services"),
        jd_file=("role.txt", b"Build secure APIs", "text/plain"))
    assert response.status_code == 201, response.text
    wait_for_plan(client, headers, response.json()["session_id"])
    prompt = json.loads(interview_llm.calls[0]["prompt"])
    assert prompt["candidate_documents"]["job_description"] == "Build secure APIs"


def test_missing_resume_or_job_description_returns_422(client, interview_llm):
    headers = login(client)
    assert client.post("/interviews", headers=headers, data={"mode": "resume"}).status_code == 415
    assert post_document(client, headers, mode="job", resume=pdf_with_text("Resume text")).status_code == 422
    assert not interview_llm.calls


def test_corrupt_pdf_and_unauthenticated_upload_return_422_and_401(client, interview_llm):
    headers = login(client)
    response = post_document(client, headers, resume=b"%PDF-not-readable")
    assert response.status_code == 422
    assert "PDF" in response.json()["detail"]
    assert client.post("/interviews", data={"mode": "resume"}).status_code == 401
    assert not interview_llm.calls


def test_job_intro_round_uses_shared_voice_endpoint_and_transitions_to_main_room(
    client, interview_llm, _voice_runtime_fixture,
):
    headers = login(client)
    response = post_document(client, headers, mode="job",
        resume=pdf_with_text("Built Python APIs"),
        jd_file=("role.pdf", pdf_with_text("Lead secure cloud platform"), "application/pdf"))
    assert response.status_code == 201, response.text
    wait_for_plan(client, headers, response.json()["session_id"])
    created = response.json()
    with client.websocket_connect(f"/ws/intro/{created['session_id']}") as ws:
        authenticate(ws, headers)
        messages = until(ws, "question_end")
        snapshot = next(message for message in messages if message["type"] == "snapshot")
        assert snapshot["session"]["session_id"] == created["session_id"]
        assert snapshot["session"]["status"] == "in_progress"
        assert len(snapshot["session"]["turns"]) == 0
        assert "Tell me about yourself" in "".join(
            message.get("text", "") for message in messages if message["type"] == "question_chunk"
        )
        for answer_index in range(3):
            question_start = next(message for message in messages if message["type"] == "question_start")
            ws.send_json({"type": "playback_done", "turn_id": question_start["turn_id"]})
            for _ in range(130):
                ws.send_bytes(bytes([1, 0]) * 512)
            for _ in range(57):
                ws.send_bytes(bytes(1024))
            messages = until(ws, "intro_complete" if answer_index == 2 else "question_end")
        completed_snapshot = next(message for message in messages if message["type"] == "snapshot")
        assert len(completed_snapshot["session"]["turns"]) == 1
        assert any(message["type"] == "intro_complete" for message in messages)
    persisted = client.get(f"/interviews/{created['session_id']}", headers=headers).json()
    assert persisted["preparation_status"] == "ready"
    assert len(persisted["turns"]) == 1
    assert _voice_runtime_fixture.instances[0].calls


