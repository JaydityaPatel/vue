# Phase 6: resume and job interviews

Resume and Job setup create ordinary Phase 4 interview plans. Once setup finishes, both modes use the same persisted `PlanOutput`, `Orchestrator`, turn endpoint, and Phase 5 voice room as Random practice.

## Documents and privacy

- Resumes accept selectable-text PDFs. Job descriptions accept pasted text, PDFs, or UTF-8 `.txt` files. When pasted JD text and a file are both submitted, the pasted text takes precedence and the file is ignored.
- Parsing uses `pypdf`; it does not run OCR. Scanned image-only, encrypted, corrupt, empty, unsupported, and over-size uploads receive a clear 422 response. Each file is limited to 10 MB and extracted text to 100,000 characters.
- Email addresses and phone numbers are redacted before planning and logged as counts only. Candidate names are retained.
- Raw parsed documents exist only while the setup request is running. The session stores a redacted extractive context summary and optional short-lived Gemini cache references, not the original documents.

## Planning and context

The `build_question_bank` route creates 4–8 topics with question seeds and expected concepts, validated against the Phase 4 `PlanOutput`. Resume prompts probe claimed experience and projects; Job prompts compare stated evidence with role requirements and formulate fair questions about areas with less evidence. Existing `SkillTag` names are reused case-insensitively. The selected role, experience, difficulty, and interview style are included in planning input.

Per-turn prompts reference the redacted context summary for follow-up continuity. For document contexts of at least 20,000 characters, setup attempts a model-bound Gemini explicit cache (TTL 2 hours) for each distinct Gemini model configured on the `next_turn` and `score_answer` routes. This is a conservative character-count heuristic for current Gemini model minimums (2,048 tokens on Gemini 2.5 and 4,096 tokens on Gemini 3.x), not an exact token count; the API may reject a cache that is still too small, in which case the summary fallback is used. Shorter contexts skip explicit caching and use the summary directly. Cache creation or reference failures fall back to that same summary and do not fail setup. Cache token accounting separates `cached_input_tokens` from uncached `input_tokens` in `llm_call_logs`; the provider's full prompt count is their sum.

Whether explicit caching is enabled for a given Gemini account depends on its key, tier, model availability, and quota. The account-specific availability and a real token reduction comparison have not been verified. During a real run, check `context_cache_active`, `context_cache_skipped_short`, or `context_cache_create_failed` log entries and compare `input_tokens` plus `cached_input_tokens` for `next_turn`/`score_answer` against similar Random sessions. Tests use fake providers and mocked transport, not live Gemini calls.

## Run and verify

From the `backend/` directory:

```powershell
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
..\..\.venv\Scripts\python.exe -m pytest -q
```

The API accepts Random JSON requests as before and multipart requests for `resume` or `job` with `resume_file`, optional `jd_text`/`jd_file`, role, experience, difficulty, style, and duration. The frontend's upload setup shows parsing/model errors and navigates to the shared `/interview/:sessionId` room after plan creation.
