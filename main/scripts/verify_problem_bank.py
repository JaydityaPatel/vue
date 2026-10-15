"""Permanent CI-style entry point; the execution engine is the pinned Pyodide runtime."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = subprocess.run(["node", "scripts/verify_problem_bank.mjs"], cwd=ROOT, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
