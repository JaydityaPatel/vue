# Phase 9: Coding interview

The coding round is a text workspace launched from Random Setup when interview style is `Coding`. Its problem records live in `app/data/coding_problems/active.json`; a manifest documents the seed source and license. This is JSON so reviewers can inspect problem statements, references, examples, hidden tests, and verification metadata in version control. `scripts/verify_problem_bank.mjs` is the admission gate: it runs every reference and test case using the same pinned Pyodide 0.27.2 runtime as the browser worker, writes failures to `quarantine.json`, and writes a summary report. Run it from the `main` directory with `node scripts/verify_problem_bank.mjs` before adding or changing problems.

The supplied `LeetCodeDataset-train.jsonl` (about 90 MB) is the source catalog. The user confirmed this Hugging Face data file is Apache-2.0; repository and task IDs are retained per problem. `scripts/convert_leetcode_dataset.py` selects 150 problems across the requested topic groups and extracts test assertions into our JSON invocation format. It writes `catalog.json`; `scripts/verify_problem_bank.py` runs each reference and its extracted cases under Pyodide 0.27.2, admitting only passing entries to `active.json` and recording failures by ID/title in `quarantine.json`.

Monaco 4.6.0 and Pyodide 0.27.2 are pinned. Pyodide runs inside a dedicated ES module Worker, initialized with same-origin runtime files copied into `frontend/dist/pyodide`. The worker has a 7 second total execution deadline per run, reports per-case output/error/timeout, and is terminated at its deadline. This isolates the UI thread and allows stopping CPU-bound loops. Pyodide's in-browser WASM runtime is not a hardened operating-system sandbox: arbitrary Python must not be treated as trusted, and browser resource isolation remains best-effort. Output size is capped after result serialization; browser-enforced memory limits are not available here.

On submission, the browser runs the candidate's submitted Python code against the full problem test set in the Pyodide Worker. Grading compares each actual output with that case's expected output; the backend checks submitted passing outputs against those verified expected values. Neither the worker nor the submission endpoint compares candidate code with the reference solution. The reference solution is used only by the Phase 9B verification pipeline to establish expected outputs. Thus algorithm choice, variable names, and coding style do not affect the result when outputs match. The endpoint records the submitted code, pass count, and routed LLM follow-up evaluation on the session. Follow-up prompts include the actual submitted code and candidate complexity/edge-case analysis. The questions are displayed as text in the coding workspace; this phase does not route them through the voice pipeline. A coding submission creates a standard `Turn` and `TurnScore` using rubric version `coding-v1`, with coding correctness/completeness, analysis/communication, and LLM-judged complexity dimensions.

## Source and license

- `newfacade/LeetCodeDataset` train split supplied by the user, Apache-2.0 as confirmed by the user (`manifest.json`).
- Rebuild selection from `main`: `..\.venv\Scripts\python.exe scripts\convert_leetcode_dataset.py`.
- Verify selected records from `main`: `node scripts/verify_problem_bank.mjs` (or `python scripts/verify_problem_bank.py`).

## Current verification report

- 150 problems selected; 149 passed Pyodide reference verification and are in `active.json`.
- One problem, `Sqrtx`, is quarantined: case 26's reference output is `4294967296`, while the dataset test expects `4294967295`.
- The verifier's deliberately broken self-test is caught and reported separately from the bank count. A separate quadratic Two Sum candidate with different variable names also passed the same output comparisons.
- All 13 requested topic groups are represented. See `data/coding_problems/verification-report.json` for topic and quarantine details.
- Topic groups are tagged on each active problem; tags can overlap.
