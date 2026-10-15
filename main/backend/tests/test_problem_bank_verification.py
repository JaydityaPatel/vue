import json
import subprocess
from pathlib import Path

from app.core.problem_bank import BANK_DIR, load_active_problems, select_problem


def test_committed_bank_passes_pyodide_verification_and_broken_solution_is_caught():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["python", "scripts/verify_problem_bank.py"], cwd=root, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((BANK_DIR / "verification-report.json").read_text(encoding="utf-8"))
    assert report["passed"] >= 100
    quarantine = json.loads((BANK_DIR / "quarantine.json").read_text(encoding="utf-8"))["problems"]
    committed_quarantine = [item for item in quarantine if item["id"] != "__broken-verification-self-test__"]
    assert report["committed_bank_quarantined"] == len(committed_quarantine)
    assert report["passed"] + report["committed_bank_quarantined"] == len(
        json.loads((BANK_DIR / "catalog.json").read_text(encoding="utf-8"))["problems"]
    )
    assert report["self_test_caught_broken_reference"] is True
    assert report["alternate_correct_algorithm_passed"] is True
    assert "no candidate/reference source comparison" in report["grading_design"]
    assert report["quarantine_reasons"][-1]["id"] == "__broken-verification-self-test__"


def test_active_bank_contains_only_verified_problem_and_selection_is_existing_id():
    load_active_problems.cache_clear()
    problems = load_active_problems()
    assert problems
    selected = select_problem("Easy")
    assert selected["verified"] is True
    assert selected["id"] in {problem["id"] for problem in problems}
    try:
        select_problem("Easy", problem_id="fabricated-id")
    except LookupError:
        pass
    else:
        raise AssertionError("Problem selection accepted an ID absent from the verified bank")
