# Phase 4: adaptive text interviews

The existing pages are named RandomSetupPage.tsx and InterviewRoomPage.tsx. Random
setup now creates a backend session; the room accepts text answers and restores
its state from GET on refresh. Completed interviews can generate and display a
report in the room.

Start the API from backend with
`..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000`.
Set GEMINI_API_KEY in backend/.env or the environment through app/config.py.
The application does not load credentials from .env.example.

## API

Every route requires `Authorization: Bearer <access_token>`. Sessions owned by
another user return 403; missing sessions return 404.

POST /interviews:

```json
{
  "mode": "random",
  "config": {
    "role": "Backend engineer",
    "experience": "Mid-level",
    "skills": ["Python", "System design"],
    "difficulty": "Balanced",
    "interview_type": "Mixed",
    "duration": 30
  }
}
```

Duration is in minutes (5–120); the existing form offers 10–60. Difficulty uses
Gentle / Balanced / Challenging. Style uses Mixed / Technical / Behavioral /
System design. Creation returns session_id, first_question, next_question,
turn_id, and is_complete=false. Planning time is excluded from practice time.

POST /interviews/{session_id}/answer:

```json
{"answer_text": "I would measure the bottleneck first.", "turn_id": "<current turn id>"}
```

turn_id is optional for simple API callers and is always sent by the browser.
It prevents stale or repeated submissions from answering a different question.
The result contains next_question and is_complete. When complete, next_question
is null and report_generation contains `{"method":"POST","url":"/interviews/{id}/report"}`.
The report reference is absent while the interview is running.

GET /interviews/{id} returns status, setup config, ordered turns (including
scores), topic coverage, current topic, follow-up count, and remaining seconds.
POST /interviews/{id}/report generates the report once; subsequent calls return
the same persisted report without another model call.

Invalid input is 422, stale/concurrent updates are 409, invalid plan/evaluation
output is 502, and exhausted scoring providers return 503. Failed answer
transactions leave the prior question unanswered and may be retried. After an
uncertain network result, reload GET before retrying.

## State and transitions

- The Pro-class build_question_bank route already exists and is retained.
  Plans contain 4–8 distinct topics, 2–3 seeds each, and expected concepts.
  Existing SkillTags are matched by case-insensitive name; only planning can
  create new taxonomy entries.
- InterviewSession.config stores interview_plan, orchestrator_state,
  turn_context (topic, concepts, question model, fallback provenance, and
  transition rationale), and a revision. The original setup fields remain.
  No database column migration is required.
- Each topic starts with one opening question. turns_on_current_topic counts
  subsequent follow_up/challenge questions, from 0 through 3. After the third
  follow-up answer is scored, another follow-up is forbidden and the
  orchestrator advances to the next not_started topic in plan order.
- move_on and switch_topic both cover the current topic and select the next
  planned topic. The model cannot select arbitrary topics, edit coverage,
  modify counters, or end the session.
- Invalid JSON, unknown actions, or missing follow-up question text are logged
  and become deterministic move_on. Failed opening generation uses the stored
  seed. Unavailable evaluation never creates fabricated scores.
- With less than 120 seconds left, the pending answer is scored and the session
  completes without a new question. Time is checked again after question/action
  generation. Covered means the topic was attempted, not mastered. Unvisited
  topics remain not_started when time expires.
- Answers, scores, next questions, state, and LLM logs commit together. The
  logger now adds records to the caller's transaction rather than committing it.
  Revision/config comparison rejects competing writes across separate DB
  sessions; a losing request rolls back its answer and score.

## Evaluation and provenance

Rubric v1 provides written anchors for all five integer values in technical
correctness, completeness, communication, and problem solving. score_turn uses
temperature 0.1, a structured schema, and local validation. The prompt explicitly
allows likely ASR mishearings and treats candidate text as evidence rather than
instructions.

Expected concepts always come from the stored plan. Unknown returned tags and
unknown missing concepts are rejected with warning logs; case variants of known
tags use their canonical name. The evaluator cannot expand the taxonomy.

TurnScore stores rubric_version, scored_by_model, and provisional. Plan and
question provenance are in session config. Reports compute overall_score as the
arithmetic mean of all four dimensions across scored answers; final_evaluation
generates only the summary and suggestions. Report model/provisional metadata
lives in config.report_metadata. A report is provisional if its generator or
any contributing score used a fallback.

The Gemini provider sends standard JSON Schema through responseJsonSchema and
temperature through generationConfig, per the
[GenerateContent API reference](https://ai.google.dev/api/generate-content).
Ollama receives the same schema through format and temperature through options.

## Verification

From backend: `..\..\.venv\Scripts\python.exe -m pytest -q`.
From frontend: `npm test` and `npm run build`.

Tests mock LLMRouter.run and provider HTTP transports; they never call Gemini.
They cover plan validation, taxonomy reuse, hard follow-up limits, deadlines,
malformed proposals, eight-turn interviews, transaction rollback, concurrent
answers, ownership, persisted reports, and the browser submit/reload flow.
