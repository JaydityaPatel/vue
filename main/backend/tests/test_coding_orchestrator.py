import json

from app.core.problem_bank import load_active_problems
from app.db.models import InterviewSession
from tests.interview_helpers import CONFIG


def login(client):
    account = {"email": "coding@example.com", "password": "a-good-password"}
    assert client.post("/auth/register", json=account).status_code == 201
    token = client.post("/auth/login", json=account).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def coding_config():
    return {**CONFIG, "interview_type": "Coding"}


def test_coding_focused_session_uses_existing_verified_problem_id(client, interview_llm):
    headers = login(client)
    created = client.post("/interviews", json={"mode": "random", "config": coding_config()}, headers=headers)
    assert created.status_code == 201, created.text
    problem = client.get(f"/interviews/{created.json()['session_id']}/coding/problem", headers=headers)
    assert problem.status_code == 200
    assert problem.json()["id"] in {item["id"] for item in load_active_problems()}
    assert problem.json()["difficulty"] == "Medium"
    assert not interview_llm.calls


def test_problem_selection_rejects_non_bank_id():
    from app.core.problem_bank import select_problem

    try:
        select_problem("Easy", problem_id="invented-problem")
    except LookupError:
        return
    raise AssertionError("Selection accepted a generated problem ID")


def test_coding_problem_list_reports_real_bank_count(client):
    headers = login(client)
    response = client.get("/interviews/coding/problems", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["problems"]) >= 100
    assert any(problem["id"] == "two-sum" for problem in payload["problems"])
    assert "Apache-2.0" in payload["dataset"]["license"]
    assert "test_cases" not in payload["problems"][0]


def test_submission_counts_server_checked_results_and_follows_up_on_actual_code(client, interview_llm):
    headers = login(client)
    created = client.post("/interviews", json={"mode": "random", "config": coding_config()}, headers=headers).json()
    problem = client.get(f"/interviews/{created['session_id']}/coding/problem", headers=headers).json()
    interview_llm.coding_evaluation = {"questions": ["Why does your complement lookup happen before insertion?"], "complexity_correct": True, "edge_cases_identified": ["duplicate values"], "feedback": "Good."}
    cases = client.post(f"/interviews/{created['session_id']}/coding/run", headers=headers,
                        json={"problem_id": problem["id"], "sample_only": False}).json()["cases"]
    results = [{"status": "passed", "actual": case["expected"], "expected": case["expected"]} for case in cases]
    response = client.post(f"/interviews/{created['session_id']}/coding/submit", headers=headers, json={
        "problem_id": problem["id"], "submitted_code": "class Solution: ...", "results": results,
        "user_analysis": "O(n) time, O(n) space; duplicates need earlier index tracking.",
    })
    assert response.status_code == 200, response.text
    assert response.json()["passed"] == response.json()["total"]
    prompt = json.loads(interview_llm.calls[-1]["prompt"])
    assert prompt["candidate_submitted_code"] == "class Solution: ..."
    assert "duplicates" in prompt["candidate_complexity_and_edge_case_analysis"]
    snapshot = client.get(f"/interviews/{created['session_id']}", headers=headers).json()
    assert snapshot["turns"][0]["score"]["rubric_version"] == "coding-v1"


def test_client_cannot_claim_wrong_expected_value_as_pass(client, interview_llm):
    headers = login(client)
    created = client.post("/interviews", json={"mode": "random", "config": coding_config()}, headers=headers).json()
    problem = client.get(f"/interviews/{created['session_id']}/coding/problem", headers=headers).json()
    cases = client.post(f"/interviews/{created['session_id']}/coding/run", headers=headers,
                        json={"problem_id": problem["id"], "sample_only": False}).json()["cases"]
    results = [{"status": "passed", "actual": [99], "expected": case["expected"]} for case in cases]
    response = client.post(f"/interviews/{created['session_id']}/coding/submit", headers=headers, json={
        "problem_id": problem["id"], "submitted_code": "pass", "results": results,
    })
    assert response.status_code == 422


def test_mixed_session_enters_coding_then_returns_to_voice_discussion(client, interview_llm):
    headers = login(client)
    created = client.post("/interviews", json={"mode": "random", "config": CONFIG}, headers=headers)
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]
    first_answer = client.post(f"/interviews/{session_id}/answer", headers=headers,
                               json={"answer_text": "I test the implementation against edge cases."})
    assert first_answer.status_code == 200, first_answer.text
    snapshot = client.get(f"/interviews/{session_id}", headers=headers).json()
    assert snapshot["current_topic_type"] == "coding"
    assert snapshot["coding_status"] == "in_progress"
    assert first_answer.json()["next_question"].startswith("Let's switch to a coding exercise")

    problem = client.get(f"/interviews/{session_id}/coding/problem", headers=headers)
    assert problem.status_code == 200, problem.text
    cases = client.post(f"/interviews/{session_id}/coding/run", headers=headers,
                        json={"problem_id": problem.json()["id"], "sample_only": False}).json()["cases"]
    results = [{"status": "passed", "actual": case["expected"], "expected": case["expected"]} for case in cases]
    submitted = client.post(f"/interviews/{session_id}/coding/submit", headers=headers, json={
        "problem_id": problem.json()["id"], "submitted_code": "class Solution: pass", "results": results,
    })
    assert submitted.status_code == 200, submitted.text
    snapshot = client.get(f"/interviews/{session_id}", headers=headers).json()
    coding_turn = next(turn for turn in snapshot["turns"] if turn["action_taken"] == "coding_submission")
    assert coding_turn["score"]["tests_passed"] == len(cases)
    assert coding_turn["score"]["tests_total"] == len(cases)
    assert coding_turn["score"]["complexity_correct"] is None

    discussion = client.post(f"/interviews/{session_id}/answer", headers=headers,
                             json={"answer_text": "The solution is linear time and handles duplicate values."})
    assert discussion.status_code == 200, discussion.text
    snapshot = client.get(f"/interviews/{session_id}", headers=headers).json()
    assert snapshot["current_topic_type"] == "discussion"
    assert discussion.json()["next_question"].startswith("Good, let's go back to discussing your experience.")
    saved_code_turn = next(turn for turn in snapshot["turns"] if turn["id"] == coding_turn["id"])
    assert saved_code_turn["score"]["complexity_correct"] is True
    assert saved_code_turn["score"]["edge_cases_identified"]
