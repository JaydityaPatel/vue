# AGENTS.md — Standing rules for Codex on the Vue project

## Every phase, no exceptions
1. After implementing a phase's build sub-phase, WRITE tests for it (pytest for
   backend, Playwright/RTL for frontend once it exists), RUN them, and FIX
   failures yourself before declaring the phase done. Do not ask the user to
   run tests manually unless a tool/environment is unavailable to you.
2. Do not mark a phase complete if any test is failing or skipped without a
   documented reason in the PR/commit message.
3. At the end of each work session, stage and commit with a clear,
   conventional-commit-style message (e.g. `feat(llm): add provider fallback
   chain`, `test(router): cover 429 fallback path`), then push to GitHub.
4. Never hardcode API keys. Read from `.env` via `app/config.py`. If a key is
   missing, fail with a clear error, don't silently skip.
5. Pin exact model version strings for anything that affects scoring
   consistency (interview evaluation, rubric generation). Do not use `-latest`
   aliases for these. `-latest` aliases are acceptable only for low-stakes
   tasks like summarization.
6. Every LLM call must go through `app/llm/router.py`. Never call a provider
   SDK directly from business logic.
7. Any result produced by a fallback (non-primary) model must be tagged
   `provisional: true` with the model name recorded, wherever it's persisted.

## Reasoning effort guidance (if using GPT-6 Astra / Codex)
- Architecture, state machines, orchestrator logic, Pyodide test verification:
  high or xhigh.
- Scaffolding, CRUD, config, boilerplate: medium.
- Test-writing: medium-high — bad tests are worse than no tests.

## Code style
- Python: type hints everywhere, Pydantic models for all request/response
  schemas, no bare `except:`.
- Keep provider-specific code isolated in `app/llm/providers/`. The router and
  business logic should never know which provider is active.

## When in doubt
Prefer the simplest implementation that passes the tests for the current
phase. Don't implement future-phase features early (e.g. don't build RAG
logic during Phase 1 just because it's mentioned in the roadmap).
