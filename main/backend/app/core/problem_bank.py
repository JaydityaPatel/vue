"""Static coding problem bank. A problem is selectable only after Pyodide verification."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

BANK_DIR = Path(__file__).resolve().parents[1] / "data" / "coding_problems"
ACTIVE_PATH = BANK_DIR / "active.json"


@lru_cache(maxsize=1)
def load_active_problems() -> tuple[dict[str, Any], ...]:
    if not ACTIVE_PATH.exists():
        return ()
    payload = json.loads(ACTIVE_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported coding problem bank schema")
    problems = payload.get("problems", [])
    if not isinstance(problems, list):
        raise ValueError("Coding problem bank must contain a problems list")
    if any(problem.get("verified") is not True for problem in problems):
        raise ValueError("Active coding bank contains an unverified problem; run scripts/verify_problem_bank.mjs")
    return tuple(problems)


def select_problem(difficulty: str, topics: list[str] | None = None, problem_id: str | None = None) -> dict[str, Any]:
    available = load_active_problems()
    if problem_id:
        match = next((item for item in available if item["id"] == problem_id), None)
        if match is None:
            raise LookupError("Problem is not in the verified active bank")
        return match
    difficulty = {"Gentle": "Easy", "Balanced": "Medium", "Challenging": "Hard"}.get(difficulty, difficulty)
    preferred = {topic.casefold() for topic in topics or []}
    ranked = sorted(available, key=lambda item: (
        item.get("difficulty") != difficulty,
        not bool(preferred.intersection(tag.casefold() for tag in item.get("topics", []))),
        item["id"],
    ))
    if not ranked:
        raise LookupError("No verified coding problems are available")
    return ranked[0]
