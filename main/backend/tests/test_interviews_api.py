import pytest

from tests.interview_helpers import CONFIG


def login(client, email="candidate@example.com"):
    account = {"email": email, "password": "a-good-password"}
    assert client.post("/auth/register", json=account).status_code == 201
    token = client.post("/auth/login", json=account).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create(client, headers):
    response = client.post("/interviews", json={"mode": "random", "config": CONFIG}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_get_real_persisted_session(client, interview_llm):
    headers = login(client)
    created = create(client, headers)
    assert created["first_question"] == created["next_question"] == "Explain Python."
    assert created["is_complete"] is False
    assert "report_generation" not in created
    response = client.get(f"/interviews/{created['session_id']}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["config"] == CONFIG
    assert body["current_topic"] == "Python"
    assert len(body["turns"]) == 1
    assert body["turns"][0]["id"] == created["turn_id"]
    assert body["topic_coverage"]["Python"] == "in_progress"
    assert 0 < body["time_remaining"] <= 1800


@pytest.mark.parametrize("method,suffix", [("get", ""), ("post", "/answer"), ("post", "/report")])
def test_wrong_user_gets_403(client, interview_llm, method, suffix):
    owner = login(client)
    other = login(client, "other@example.com")
    created = create(client, owner)
    kwargs = {"headers": other}
    if suffix == "/answer":
        kwargs["json"] = {"answer_text": "Trying another user's session"}
    response = getattr(client, method)(f"/interviews/{created['session_id']}{suffix}", **kwargs)
    assert response.status_code == 403


@pytest.mark.parametrize("method,path,payload", [
    ("post", "/interviews", {"mode": "random", "config": CONFIG}),
    ("get", "/interviews/unknown", None),
    ("post", "/interviews/unknown/answer", {"answer_text": "An answer"}),
    ("post", "/interviews/unknown/report", None),
])
def test_auth_required(client, method, path, payload):
    kwargs = {"json": payload} if payload is not None else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401


def test_completion_and_idempotent_report(client, interview_llm):
    headers = login(client)
    created = create(client, headers)
    path = f"/interviews/{created['session_id']}"
    assert client.post(f"{path}/report", headers=headers).status_code == 409
    for index in range(4):
        response = client.post(f"{path}/answer", headers=headers, json={"answer_text": f"Candidate answer {index}"})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["is_complete"] == (index == 3)
        if index < 3:
            assert "report_generation" not in result
    assert result["next_question"] is None
    assert result["report_generation"] == {"method": "POST", "url": f"{path}/report"}
    snapshot = client.get(path, headers=headers).json()
    assert snapshot["status"] == "completed"
    assert snapshot["completed_at"]
    assert len(snapshot["turns"]) == 4
    assert all(turn["score"]["rubric_version"] == "v1" for turn in snapshot["turns"])
    assert all(value == "covered" for value in snapshot["topic_coverage"].values())
    report = client.post(f"{path}/report", headers=headers)
    assert report.status_code == 200, report.text
    assert report.json()["overall_score"] == 3.25
    assert report.json()["provisional"] is False
    count = len(interview_llm.calls)
    assert client.post(f"{path}/report", headers=headers).json() == report.json()
    assert len(interview_llm.calls) == count


def test_scoring_failure_rolls_back_answer_and_allows_retry(client, interview_llm):
    headers = login(client)
    created = create(client, headers)
    path = f"/interviews/{created['session_id']}"
    interview_llm.score_override = "invalid JSON"
    result = client.post(f"{path}/answer", headers=headers, json={"answer_text": "My answer", "turn_id": created["turn_id"]})
    assert result.status_code == 502
    state = client.get(path, headers=headers).json()
    assert len(state["turns"]) == 1
    assert state["turns"][0]["answer_text"] is None
    assert state["turns"][0]["score"] is None
    interview_llm.score_override = None
    assert client.post(f"{path}/answer", headers=headers, json={"answer_text": "My answer", "turn_id": created["turn_id"]}).status_code == 200


def test_stale_turn_and_blank_answer_rejected(client, interview_llm):
    headers = login(client)
    created = create(client, headers)
    path = f"/interviews/{created['session_id']}"
    assert client.post(f"{path}/answer", headers=headers, json={"answer_text": "   "}).status_code == 422
    payload = {"answer_text": "The answer", "turn_id": created["turn_id"]}
    assert client.post(f"{path}/answer", headers=headers, json=payload).status_code == 200
    assert client.post(f"{path}/answer", headers=headers, json=payload).status_code == 409
    assert client.get(path, headers=headers).json()["turns"][-1]["answer_text"] is None


def test_provider_outage_returns_retryable_error(client, interview_llm):
    headers = login(client)
    created = create(client, headers)
    path = f"/interviews/{created['session_id']}"
    interview_llm.fail_task = "score_answer"
    result = client.post(f"{path}/answer", headers=headers, json={"answer_text": "An answer"})
    assert result.status_code == 503
    assert client.get(path, headers=headers).json()["turns"][0]["answer_text"] is None


def test_plan_failure_does_not_leave_partial_session_or_taxonomy(client, interview_llm):
    from app.db.database import get_db
    from app.db.models import InterviewSession, SkillTag
    from app.main import app

    headers = login(client)
    interview_llm.plan["topics"] = interview_llm.plan["topics"][:1]
    response = client.post("/interviews", json={"mode": "random", "config": CONFIG}, headers=headers)
    assert response.status_code == 502
    get_test_db = app.dependency_overrides[get_db]()
    db = next(get_test_db)
    try:
        assert db.query(InterviewSession).count() == 0
        assert db.query(SkillTag).count() == 0
    finally:
        get_test_db.close()


@pytest.mark.parametrize("patch", [{"duration": 0}, {"duration": 0.5}, {"interview_type": "Coding"}, {"skills": [""]}])
def test_invalid_config_rejected_before_llm(client, interview_llm, patch):
    headers = login(client)
    result = client.post("/interviews", headers=headers, json={"mode": "random", "config": {**CONFIG, **patch}})
    assert result.status_code == 422
    assert not interview_llm.calls
