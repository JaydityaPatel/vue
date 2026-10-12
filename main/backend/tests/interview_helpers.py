import copy
import json
from collections import deque
from typing import Any

from app.db.models import InterviewSession, User
from app.llm.providers.base import LLMResponse

CONFIG = {
    "role": "Backend engineer", "experience": "Mid-level", "skills": ["Python", "System design"],
    "difficulty": "Balanced", "interview_type": "Mixed", "duration": 30,
}
PLAN = {"topics": [
    {"name": name, "question_seeds": [f"Explain {name}.", f"Give an example of {name}."],
     "expected_concepts": [f"{name} fundamentals", f"{name} tradeoffs"]}
    for name in ("Python", "System design", "Communication", "Problem solving")
]}


def session_for(db) -> InterviewSession:
    user = User(email="candidate@example.com", hashed_password="unused")
    db.add(user)
    db.flush()
    session = InterviewSession(user_id=user.id, mode="random", config=copy.deepcopy(CONFIG))
    db.add(session)
    db.flush()
    return session


class ScriptedInterviewLLM:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.actions: deque[str | dict[str, Any]] = deque()
        self.plan: dict[str, Any] = copy.deepcopy(PLAN)
        self.score_override: dict[str, Any] | str | None = None
        self.provisional = False
        self.fail_task: str | None = None

    async def run(self, **kwargs: Any) -> LLMResponse:
        from app.llm.router import AllProvidersExhaustedError

        self.calls.append(kwargs)
        task = kwargs["task"]
        if task == self.fail_task:
            raise AllProvidersExhaustedError("Scripted outage")
        payload = json.loads(kwargs["prompt"])
        if task == "build_question_bank":
            output = self.plan
        elif task == "score_answer":
            output = self.score_override if self.score_override is not None else {
                "technical_correctness": 3, "completeness": 3, "communication": 4, "problem_solving": 3,
                "expected_concepts": payload["expected_concepts"],
                "missing_concepts": payload["expected_concepts"][-1:],
                "skill_tags": payload["controlled_skill_tags"][:1],
                "feedback": "Explain how you validated the approach and discuss an alternative.",
            }
        elif task == "next_turn":
            if "action" in kwargs["response_schema"]["properties"]:
                output = self.actions.popleft() if self.actions else "move_on"
                if output in ("move_on", "switch_topic", "follow_up", "challenge"):
                    output = {
                        "action": output, "rationale": "Scripted assessment of the answer.",
                        "question_text": "How would you validate that approach?" if output in ("follow_up", "challenge") else "",
                    }
            else:
                output = {"question_text": payload["topic"]["question_seeds"][0]}
        elif task == "final_evaluation":
            output = {"summary": "You explained the core approaches clearly.", "improvement_suggestions": ["Discuss tradeoffs and validation."]}
        else:
            raise AssertionError(f"Unexpected LLM task: {task}")
        return LLMResponse(
            text=output if isinstance(output, str) else json.dumps(output),
            model_used="mock-fallback" if self.provisional else "mock-primary",
            raw={"provisional": self.provisional},
        )
