# Vue Phases 1–8 End-to-End Verification

Run date: 2026-10-14. The detailed turn-by-turn record is included below; machine-readable evidence is in [`phase1-8-evidence.json`](phase1-8-evidence.json).

## Summary

**Mostly works end to end.** Real signup, Random, Resume, and Job sessions completed through the live FastAPI service and Gemini; Resume and Job also completed three real audio turns through VAD and Whisper over the interview WebSocket, and all three modes generated reports. The main issue is Gemini quota: this run recorded 40 rate-limited attempts, and 41 of 47 successful LLM results used the Flash Lite fallback and were marked provisional. Job web research was attempted separately against the completed test plan but both configured Gemini models returned HTTP 429, so the optional enrichment correctly left the base plan unchanged. The CUDA path cannot be verified here because this environment has a CPU-only PyTorch build.

## Environment and method

- `GEMINI_API_KEY` is present in `main/backend/.env` and is not a placeholder. A real Gemini 3.8 Flash call returned `OK`; a real Gemini 3.5 Flash Lite call also returned `OK` before the interview workload. No key value is included in this report.
- Backend `/health` returned `200` on the existing port 8000. I used a fresh backend on port 8002 for the E2E walkthrough so it loaded the route edits. Its test-only settings were `VOICE_STT_DEVICE=cpu` and `VOICE_STT_COMPUTE_TYPE=int8` because `torch 2.14.1+cpu` reports no CUDA build/device.
- Vite was already bound to port 5173; the requested `npm run dev -- --port 5173` command started a second instance on 5174. Both served the app HTML with HTTP 200. Headless Edge did not yield a rendered DOM in this environment, so UI interaction and visible orb animation were not claimed as verified.
- Ollama was already running at port 11434 with `qwen2.5:3b`. A real local `OllamaProvider` generation returned `OK`. The app's `hardware_tier=unknown` policy selected the Gemini-only intro route, so Ollama did not serve any of the recorded sessions.
- At the start of the first inspection, SQLite (`main/backend/vue.db`) contained 3 users, 2 in-progress Resume sessions, and 12 LLM call logs. Verification accounts and sessions were intentionally left in the database. Current totals are 6 users and 8 sessions: 4 completed, 1 abandoned, and 3 in progress. The original two in-progress Resume sessions remain; the other in-progress record is from an exploratory quota-limited Job attempt.
- A test account was registered and authenticated through `/auth/register`, `/auth/login`, and `/auth/me`. Resume and JD fixtures are in `main/scripts/e2e-fixtures/`; the generated PDF parses as one page and contains the Kafka throughput and PostgreSQL latency claims.
- The real session flows were driven with HTTP requests matching the frontend API and WebSocket controls/audio. Intro answers were locally synthesized Kokoro WAV files, then passed through the actual VAD and faster-whisper path. They were not human microphone recordings.

Commands used / service state:

```powershell
# Existing production-style service, already present on port 8000
cd main\backend
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Test backend used for this run (CPU override because CUDA is unavailable here)
$env:VOICE_STT_DEVICE='cpu'
$env:VOICE_STT_COMPUTE_TYPE='int8'
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002

# Frontend; 5173 was occupied, so Vite selected 5174 for the extra instance
cd main\frontend
npm run dev -- --port 5173

# Ollama was already running; this command was not needed
ollama serve
```

The temporary backend on 8002 and the extra Vite instance on 5174 were stopped after verification. Existing services on 8000, 5173, and Ollama were left alone.

## Per-mode results

### Random — Pass

The actual opening question tested Python concurrency. The tailored strong answer scored **4/3/4/3** (technical/completeness/communication/problem solving), after which the orchestrator requested a follow-up for missing asyncio mechanics. The vague answer scored **1/1/1/1** and triggered a challenge. The evasive answer scored **1/1/2/1** and caused a topic switch. These decisions matched the answer content. The session saved six answers, then the supported WebSocket End control completed it; a seventh question was pending and correctly remained unanswered. The generated report score was **2.21/5**, by `gemini-3.5-flash-lite`, provisional.

### Resume — Pass, with answer-depth weakness

The PDF parser and plan generation worked. The plan produced five `resume_jd` topics. The intro asked “Tell me about yourself,” then adapted follow-ups to the candidate's service scaling and Kafka pipeline. All three WAV answers were transcribed; the final intro summary named the 10,000-events/sec pipeline and technologies. The first main question explicitly asked about that Kafka pipeline, idempotency, bounded retries, and p95 latency under 200 ms. This is consistent with the intro summary, though the same claim was also in the resume, so the intro's independent effect cannot be isolated.

The session saved five answered main turns and one unanswered follow-up. Questions were resume-specific. Repeating high-level resume bullets instead of answering follow-up details led to lower scores and reasonable move-on decisions. The report score was **2.70/5**, generated by `gemini-3.5-flash-lite`, provisional.

### Job — Pass for base plan and interview; enrichment unavailable under current quota

The Job plan used both documents and included a direct gap probe: “Given that your resume does not explicitly mention payments, how would you approach learning ledger design and ensuring double-entry consistency?” It then followed up on debit/credit balance invariants. Kafka delivery semantics and PostgreSQL trade-offs were also probed. Five answers were saved and the report score was **2.90/5**, generated by `gemini-3.5-flash-lite`, provisional.

All plan topics were tagged `resume_jd`; there were no `web_research` tags or citations in the session. A separate real invocation of the Phase 8 enrichment function against this same plan returned `False`: Gemini 3.8 Flash and Gemini 3.5 Flash Lite both returned HTTP 429. The function logged the failure, and I rolled back the diagnostic transaction. The base plan and completed Job session were unaffected, as required for optional enrichment.

## Voice pipeline

Verified with three synthesized WAV answer clips through the real `/ws/intro/{session_id}` protocol, Silero VAD endpointing, CPU int8 faster-whisper, transcript messages, adaptive intro follow-ups, summary generation, and handoff to the first main interview question. Transcript similarity against the spoken source text was **0.997**, **0.894**, and **1.000**. WebSocket question chunks and transcript/state messages arrived; audio bytes were sent as 16 kHz mono PCM frames with trailing silence.

This is a partial substitute for a real browser/microphone session. The browser's visible orb states and audible browser `speechSynthesis` output were not verified; the headless Edge process did not render a usable DOM in this environment. A human should still test a real mic answer, transcript accuracy, orb changes, and audible question playback.

## Quality findings

- Random scoring distinguished the matched technical answer from weak and evasive answers. Strong: 4/3/4/3; vague: 1/1/1/1; dodge: 1/1/2/1. Follow-up/challenge/switch-topic decisions were supported by the recorded rationales.
- Resume and Job plans were clearly tied to the uploaded documents. Resume questions referenced the Kafka throughput claim and PostgreSQL improvement; Job questions addressed payments/ledger as a gap rather than asserting the candidate had that experience.
- Resume and Job test answers often repeated résumé-level claims rather than supplying implementation detail. Scores of 2.70 and 2.90 and the report feedback reflected that gap. The generated feedback was specific rather than generic boilerplate.
- The first Resume answer's scoring response logged an `evaluation_expected_concepts_mismatch` warning; the server retained the plan's expected concepts, as designed.
- The longest recorded Random setup request was **19.35 s**; the longest answer request was **23.32 s**. No measured API request exceeded 30 s. Loading-indicator behavior was not browser-tested.
- Phase 8 web search success was not observed because the real provider quota rejected both grounded-route models. Failure/fallback behavior did preserve the base Job plan.

## Silent failures found

- The final E2E window had **90 LLM log entries**: 47 successful calls, 40 rate-limited attempts, and 3 transient error attempts. **41 successful results were provisional** because the router used Flash Lite after primary-model throttling. All three final reports and most later turns were therefore provisional, even though the UI flow completed.
- The 3 logged error attempts were followed by retries/fallbacks that produced usable outputs. No unhandled exception was found in the three final completed sessions. An earlier quota-burst attempt did produce a logged failed document preparation and left an incomplete test Job session in SQLite.
- Intro-round model calls are not represented in `LLMCallLog` (the intro helper invokes `LLMRouter.run` without passing the DB). Their actual models are recorded in session metadata as `gemini-3.5-flash-lite`; this is an observability gap when auditing all LLM calls.
- A `job_web_research` call that the local rate limiter skips before contacting a provider may not create an `LLMCallLog` entry. The direct diagnostic call did log both provider 429s and the enrichment failure.

## Bugs found and fixed

1. The Ollama fallback route used `ollama:qwen2.5-3b`, but the installed model is `qwen2.5:3b`; a real call using the configured name returned 404. I corrected the `next_turn`, `score_answer`, and `intro_chat` route tags and the matching `LLMRouter` docstring example.
2. The configured `gemini-2.5-flash` fallback returned HTTP 404 for this key, with Google's response directing clients to Gemini 3.8. I replaced the `next_turn` and `score_answer` fallbacks with the live-verified `gemini-3.5-flash-lite` model. I also changed final evaluation and summary routes to live-verified Gemini 3.8 / 3.5 Flash Lite IDs so those tasks could complete with this account. The completed reports used Flash Lite after Gemini 3.8 rate limits.

The route edits are in `main/backend/app/llm/rate_limits.yaml`; I also corrected the matching example in the `LLMRouter` docstring. No other application behavior was changed during this verification.

## Automated checks

- Backend: **141 passed**, 2 dependency deprecation warnings, 18.24 s.
- Frontend: **46 passed**, 7 test files; React Router future-flag warnings only.
- Frontend production build: passed. Vite emitted the existing 844 kB Interview Room chunk warning (>500 kB).

## What I still need to verify myself

- Run on the actual RTX 3050 machine with CUDA-enabled PyTorch/CTranslate2 and confirm Whisper uses the GPU; this environment cannot validate CUDA.
- Speak naturally into the real frontend and verify transcript fidelity, listening/thinking/speaking orb transitions, and audible question speech.
- Retry Phase 8 enrichment after Gemini quota recovers and confirm a relevant grounded topic has `source: web_research` plus source URLs. The base Job interview already worked without it.

No commit or push was made. Existing unrelated working-tree changes were preserved.

## Turn-by-turn evidence

The following records reproduce the actual questions, answers, orchestrator decisions and rationales, and rubric scores from the three completed final sessions.

### Random transcript

#### Turn 0 — Python Fundamentals and Asynchronous Programming

**Question:** To kick off our discussion on Python concurrency, could you explain how the Global Interpreter Lock (GIL) impacts multithreading in Python, and how an asynchronous approach using asyncio and the event loop differs when handling concurrent I/O-bound tasks?

**Answer:** In standard CPython the GIL allows only one thread to execute Python bytecode at a time. For I/O-bound work I use asyncio for many cooperative operations, or threads around blocking I/O; for CPU-bound parallel work I use multiprocessing or a native library that releases the GIL. I would benchmark and account for coordination and serialization overhead.

**Orchestrator:** requested follow_up, executed follow_up. The candidate provided an accurate high-level summary of the GIL and concurrency models, but did not delve into the mechanics of asyncio. Following up on how coroutines and the event loop function under the hood will evaluate their concrete understanding of Python's cooperative concurrency model.

**Scores (technical / completeness / communication / problem-solving):** 4.0 / 3.0 / 4.0 / 3.0.

**Evaluator feedback:** You accurately defined the GIL in CPython and appropriately identified when to use asyncio, threading, or multiprocessing. However, your answer was quite brief and did not explicitly explain how the event loop operates, what coroutines are, or the fundamental difference between cooperative concurrency in a single thread versus OS-level thread scheduling.

#### Turn 1 — Python Fundamentals and Asynchronous Programming

**Question:** Could you drill down into how asyncio operates under the hood? Specifically, how do coroutines and the event loop coordinate when an `await` expression is reached during an I/O operation?

**Answer:** I try to write clean code, communicate well, and ask for help when needed. I do not have a specific example right now.

**Orchestrator:** requested challenge, executed challenge. The candidate failed to answer the previous technical question about asyncio internals and gave a generic response. Since they are a junior backend engineer, I should pivot slightly or challenge them with a more foundational conceptual question regarding the difference between concurrency and parallelism to ensure we assess their understanding.

**Scores (technical / completeness / communication / problem-solving):** 1.0 / 1.0 / 1.0 / 1.0.

**Evaluator feedback:** The response did not address the question about how asyncio, coroutines, and the event loop function under the hood during I/O operations.

#### Turn 2 — Python Fundamentals and Asynchronous Programming

**Question:** Let's step back for a moment. Can you explain the practical difference between concurrency and parallelism, and give a simple real-world or coding example of when you would apply each?

**Answer:** I think teamwork and communication are important for every project. Could we move to another question?

**Orchestrator:** requested switch_topic, executed switch_topic. The candidate has repeatedly avoided answering technical questions on Python fundamentals and asynchronous programming, providing non-technical responses and asking to move on. It is best to switch to another topic in the interview plan, such as PostgreSQL, to gauge their knowledge in a different area.

**Scores (technical / completeness / communication / problem-solving):** 1.0 / 1.0 / 2.0 / 1.0.

**Evaluator feedback:** The candidate avoided the question entirely and provided an unrelated response about teamwork, failing to address concurrency, parallelism, or any associated technical concepts.

#### Turn 3 — PostgreSQL Data Modeling and Query Optimization

**Question:** How would you design a relational schema in PostgreSQL for a high-traffic transactional system, and what factors do you consider when choosing between different indexing strategies like B-tree and GIN?

**Answer:** I used PostgreSQL query plans and indexes to reduce a reporting API's p95 latency by 42%. I checked representative plans and write cost, then tested concurrent updates and rollback behavior before releasing the schema change.

**Orchestrator:** requested follow_up, executed follow_up. The candidate mentioned query plans and indexes, but completely missed core schema design concepts like normalization, foreign keys, and ACID properties for a transactional system. A follow-up is necessary to address those missing expected concepts before moving on.

**Scores (technical / completeness / communication / problem-solving):** 3.0 / 2.0 / 3.0 / 3.0.

**Evaluator feedback:** The candidate mentions query plans and indexing strategies, but completely misses schema design concepts such as normalization, foreign keys, and ACID properties for a transactional system.

#### Turn 4 — PostgreSQL Data Modeling and Query Optimization

**Question:** Building on your experience with query plans and indexes, could you walk through how you ensure data integrity and handle normalization versus denormalization when designing the actual tables and foreign key constraints for this high-traffic transactional system?

**Answer:** I use a multi-stage build, pin dependencies, order stable layers for cache reuse, and exclude local files with .dockerignore. I run as a non-root user, keep secrets out of the image, and use volumes only for data that needs persistence. I check image size and startup behavior in CI.

**Orchestrator:** requested move_on, executed move_on. The candidate's responses on PostgreSQL and concurrency have been increasingly irrelevant or evasive, drifting into Docker practices when asked about database normalization. Given the difficulty and interview type, it is best to transition to the Docker topic plan.

**Scores (technical / completeness / communication / problem-solving):** 1.0 / 1.0 / 2.0 / 1.0.

**Evaluator feedback:** The candidate provided an answer entirely about Docker and containerization best practices, which is completely irrelevant to the database design, normalization, foreign keys, and query planning question asked.

#### Turn 5 — Containerization and Docker Workflow

**Question:** Moving on to Docker and containerization, when building Docker images for Python applications, what best practices do you follow to keep images secure and lightweight? In particular, how do you approach base image selection, managing image layers, and utilizing multi-stage builds?

**Answer:** I use a multi-stage build, pin dependencies, order stable layers for cache reuse, and exclude local files with .dockerignore. I run as a non-root user, keep secrets out of the image, and use volumes only for data that needs persistence. I check image size and startup behavior in CI.

**Orchestrator:** requested follow_up, executed follow_up. The candidate provided a strong overview of Docker best practices but missed discussing base image selection and network security. I will follow up to probe deeper into those specific missing concepts.

**Scores (technical / completeness / communication / problem-solving):** 4.0 / 3.0 / 4.0 / 3.0.

**Evaluator feedback:** You identified several core containerization best practices, such as multi-stage builds, layer caching, non-root user execution, and .dockerignore usage. However, you omitted base image selection (such as evaluating slim, alpine, or distroless images for Python) which was explicitly prompted, as well as network security practices.

#### Turn 6 — Containerization and Docker Workflow

**Question:** You mentioned several great practices like multi-stage builds and non-root users. Could you expand on how you select appropriate base images for Python applicationsâ€”such as comparing alpine, slim, or distrolessâ€”and how you handle network security and isolation between containers?

No answer/action/score: this next question was pending when the supported WebSocket End control completed the session.

### Resume transcript

#### Turn 0 — Kafka Real-Time Event Pipeline at Meridian Analytics

**Question:** Can you walk through how you designed the Kafka event pipeline at Meridian Analytics to handle 10,000 events per second, and how you implemented idempotent consumers and bounded retries while keeping p95 latency below 200 ms?

**Answer:** I owned a Kafka pipeline processing about 10,000 events per second. I used idempotent consumers, bounded retries, and monitoring for delayed or duplicate events. We measured p95 processing latency below 200 milliseconds and tested replay behavior before rollout.

**Orchestrator:** requested follow_up, executed follow_up. The candidate's initial answer was too high-level and lacked technical depth regarding partition strategy, retry bounds, and dead-letter queues. A follow-up is necessary to probe deeper into the specific implementation details of the idempotent consumers and how they handled the bounded retries without violating the latency threshold.

**Scores (technical / completeness / communication / problem-solving):** 3.0 / 3.0 / 4.0 / 3.0.

**Evaluator feedback:** The candidate mentions the key elements like idempotent consumers and p95 latency, but the explanation is too high-level and lacks specific technical details on how the partition strategy, retry bounds, dead-letter queues, or latency profiling were implemented.

#### Turn 1 — Kafka Real-Time Event Pipeline at Meridian Analytics

**Question:** Could you dive a bit deeper into the technical specifics? Specifically, how did you choose your partition strategy to maintain throughput at 10,000 events per second, and how did you implement the bounded retries and dead-letter queue mechanism without letting retries spike your p95 latency?

**Answer:** I owned a Kafka pipeline processing about 10,000 events per second. I used idempotent consumers, bounded retries, and monitoring for delayed or duplicate events. We measured p95 processing latency below 200 milliseconds and tested replay behavior before rollout.

**Orchestrator:** requested move_on, executed move_on. The candidate has repeated the same high-level resume bullet points twice without answering the specific technical probes about partition strategy, retry bounds, or dead-letter queues. To keep the interview moving productively, it is best to transition to the next topic in the plan.

**Scores (technical / completeness / communication / problem-solving):** 2.0 / 2.0 / 3.0 / 2.0.

**Evaluator feedback:** The candidate repeated general high-level metrics from their resume but failed to address the specific technical details asked in the prompt, such as partition strategy, dead-letter queue implementation details, and how retries were isolated to prevent latency spikes.

#### Turn 2 — PostgreSQL Performance Tuning and Indexing

**Question:** What specific changes did you make to the PostgreSQL indexes and query plans for the reporting API that resulted in a 42% reduction in p95 latency, and how did you ensure correctness while handling concurrent updates?

**Answer:** I used PostgreSQL query plans and indexes to reduce a reporting API's p95 latency by 42%. I checked representative plans and write cost, then tested concurrent updates and rollback behavior before releasing the schema change.

**Orchestrator:** requested follow_up, executed follow_up. The candidate has twice provided high-level summaries without detailing the specifics of EXPLAIN ANALYZE, index types, or multicolumn index design. A direct follow-up targeting these missing concepts is necessary to properly evaluate their PostgreSQL tuning depth.

**Scores (technical / completeness / communication / problem-solving):** 3.0 / 3.0 / 3.0 / 3.0.

**Evaluator feedback:** The candidate mentions looking at query plans and testing concurrent updates, but omits specific details regarding EXPLAIN ANALYZE, index types, or multicolumn index design.

#### Turn 3 — PostgreSQL Performance Tuning and Indexing

**Question:** Could you walk through the exact steps you took with EXPLAIN ANALYZE to identify the bottlenecks in the reporting queries, and what specific index types or multicolumn structures you chose to achieve that 42% latency reduction?

**Answer:** I would clarify the reliability and correctness requirements first, then compare a simple implementation with the operational cost of the alternatives. I would test failure cases, define a measurable SLO, and use production metrics to validate the result.

**Orchestrator:** requested move_on, executed move_on. The candidate has repeatedly provided generic, high-level responses instead of addressing specific technical questions across multiple topics. Since we need to cover containerization and Docker workflow within the remaining interview time, it is best to move on to the next topic.

**Scores (technical / completeness / communication / problem-solving):** 1.0 / 1.0 / 3.0 / 1.0.

**Evaluator feedback:** The candidate provided a generic response about reliability, failure cases, and metrics, but completely failed to answer the specific technical question asked about EXPLAIN ANALYZE, index types, multicolumn structures, and the query optimization process.

#### Turn 4 — Containerization and Docker Workflow

**Question:** How did you structure the Docker-based local environments and CI checks for the Python and FastAPI services at Meridian Analytics, and in what ways did this containerization work improve your deployment rollbacks and on-call runbooks?

**Answer:** I use a multi-stage build, pin dependencies, order stable layers for cache reuse, and exclude local files with .dockerignore. I run as a non-root user, keep secrets out of the image, and use volumes only for data that needs persistence. I check image size and startup behavior in CI.

**Orchestrator:** requested follow_up, executed follow_up. The candidate gave good technical details on Docker best practices for FastAPI, but completely missed the second part of the question regarding how this containerization work specifically improved deployment rollbacks and on-call runbooks. A follow-up is needed to cover that aspect of their resume experience.

**Scores (technical / completeness / communication / problem-solving):** 4.0 / 3.0 / 4.0 / 3.0.

**Evaluator feedback:** The candidate provides solid technical practices for containerizing Python and FastAPI services, such as multi-stage builds, non-root users, and caching. However, the response completely misses the second half of the question regarding how this work specifically improved deployment rollbacks and on-call runbooks.

#### Turn 5 — Containerization and Docker Workflow

**Question:** Building on your Docker practices, could you specifically explain how containerization helped improve your deployment rollback procedures and on-call runbooks during incidents at Meridian Analytics?

No answer/action/score: this next question was pending when the supported WebSocket End control completed the session.

### Job transcript

#### Turn 0 — Distributed Systems and Message Delivery Semantics

**Question:** In your work at Meridian Analytics with the Kafka-based event pipeline, how did you implement idempotent consumers, and what strategies did you use to handle out-of-order event delivery?

**Answer:** I owned a Kafka pipeline processing about 10,000 events per second. I used idempotent consumers, bounded retries, and monitoring for delayed or duplicate events. We measured p95 processing latency below 200 milliseconds and tested replay behavior before rollout.

**Orchestrator:** requested follow_up, executed follow_up. The candidate mentioned using idempotent consumers and replay testing in their Kafka pipeline, but omitted the technical details of how deduplication (such as idempotency keys or stores) and out-of-order event handling were implemented. A follow-up is necessary to probe these specifics before moving on.

**Scores (technical / completeness / communication / problem-solving):** 3.0 / 3.0 / 4.0 / 3.0.

**Evaluator feedback:** The candidate mentions using idempotent consumers and testing replay behavior, but does not explain the underlying mechanism such as idempotency keys, state deduplication, or how out-of-order messages were specifically managed.

#### Turn 1 — Distributed Systems and Message Delivery Semantics

**Question:** Could you dive deeper into the mechanism you used for deduplication? Specifically, how did you store and check idempotency keys, and how did your consumer handle cases where an event arrived significantly out of order?

**Answer:** I owned a Kafka pipeline processing about 10,000 events per second. I used idempotent consumers, bounded retries, and monitoring for delayed or duplicate events. We measured p95 processing latency below 200 milliseconds and tested replay behavior before rollout.

**Orchestrator:** requested move_on, executed move_on. The candidate has twice repeated identical high-level resume bullet points without answering the specific technical questions about idempotency key storage or out-of-order event handling. To keep the interview productive, I should move on to database performance tuning.

**Scores (technical / completeness / communication / problem-solving):** 2.0 / 2.0 / 3.0 / 2.0.

**Evaluator feedback:** The candidate's answer repeats general high-level details from the resume summary rather than diving deeper into the specific mechanisms requested, such as how idempotency keys were stored/checked or how out-of-order events were handled by the consumer.

#### Turn 2 — PostgreSQL Performance Tuning and Indexing

**Question:** You mentioned reworking PostgreSQL indexes and query plans for a reporting API to reduce p95 query latency by 42%. Walk me through your process of diagnosing those slow queries and how you evaluated the trade-offs of the new indexes while maintaining correctness for concurrent updates.

**Answer:** I used PostgreSQL query plans and indexes to reduce a reporting API's p95 latency by 42%. I checked representative plans and write cost, then tested concurrent updates and rollback behavior before releasing the schema change.

**Orchestrator:** requested follow_up, executed follow_up. The candidate has mentioned checking query plans and considering write costs, but has not yet addressed the specific index types used, index maintenance overhead, or how concurrent updates and locks were managed during the schema updates. I will follow up to probe deeper into these specifics.

**Scores (technical / completeness / communication / problem-solving):** 3.0 / 3.0 / 3.0 / 3.0.

**Evaluator feedback:** The candidate's answer covers the general steps of checking query plans and considering write costs, but lacks specific details on index types (like B-trees) and index maintenance overhead. More depth on how concurrent updates and locks were handled would improve the response.

#### Turn 3 — PostgreSQL Performance Tuning and Indexing

**Question:** Could you elaborate on the specific index types you selectedâ€”such as B-tree or partial indexesâ€”and how you accounted for the index maintenance overhead and write locking implications during concurrent updates on that reporting table?

**Answer:** I would clarify the reliability and correctness requirements first, then compare a simple implementation with the operational cost of the alternatives. I would test failure cases, define a measurable SLO, and use production metrics to validate the result.

**Orchestrator:** requested move_on, executed move_on. The candidate's responses on PostgreSQL performance tuning have repeatedly drifted into generic, high-level talking points without addressing specific technical mechanisms like index types, write locking, or maintenance overhead. It is best to move on to the next topic to maintain interview momentum.

**Scores (technical / completeness / communication / problem-solving):** 2.0 / 2.0 / 3.0 / 2.0.

**Evaluator feedback:** The candidate's answer is entirely generic and avoids addressing the specific technical details asked in the question, such as B-tree versus partial indexes, index maintenance overhead, and write locking implications on concurrent updates.

#### Turn 4 — Financial Domain and Ledger Concepts

**Question:** The role requires familiarity with payment lifecycles, ledger concepts, and reconciliation. Given that your resume does not explicitly mention payments, how would you approach learning ledger design and ensuring double-entry consistency?

**Answer:** I have not built a payment ledger directly. I would first map the invariants and lifecycle, then use immutable entries, idempotency keys, transactional writes, reconciliation, and audit trails. My closest experience is making Kafka consumers safe under retries and duplicate delivery.

**Orchestrator:** requested follow_up, executed follow_up. The candidate provided a good high-level approach to learning ledger design and drawing parallels from their transactional experience, but missed the core concept of double-entry bookkeeping fundamentals. I will follow up to ensure they address how debits and credits equal zero and how immutable ledger entries guarantee balance.

**Scores (technical / completeness / communication / problem-solving):** 4.0 / 3.0 / 4.0 / 4.0.

**Evaluator feedback:** The candidate provides a solid approach to learning the domain and highlights relevant transferable skills like idempotency and transactional safety from their Kafka and database background. However, they omit explicit mention of double-entry bookkeeping fundamentals.

#### Turn 5 — Financial Domain and Ledger Concepts

**Question:** You outlined a solid approach using immutable entries and transactional writes. To build on that, how would you model double-entry bookkeeping in the database schema to ensure that every transaction maintains the fundamental invariant where debits equal credits?

No answer/action/score: this next question was pending when the supported WebSocket End control completed the session.

### Intro transcription and handoff evidence

#### Resume mode

**Initial intro question:** Tell me about yourself.

- **Transcript** (similarity 0.997): I am a back-end engineer with about four years of experience. I have mainly worked with Python, Kafka, and PostgreSQL, and I enjoy designing services that stay reliable as traffic grows.
  - **Adaptive follow-up:** Could you walk me through a specific project where you scaled a service using Kafka and PostgreSQL under high traffic?

- **Transcript** (similarity 0.894): One project I owned was a Kafka pipeline processing around 10,000 events per second. I built idempotent consumers and retries for duplicates and delayed events and tracked P90 latency under 200 milliseconds.
  - **Adaptive follow-up:** Could you elaborate on the approach you took to keep the P90 latency under 200 milliseconds while handling duplicate and delayed events in your Kafka pipeline?

- **Transcript** (similarity 1.0): I am interested in payment systems because correctness and reliability matter as much as throughput. I have not worked directly with a payment ledger yet, but I have handled transactional data and production incidents, and I would be deliberate about learning reconciliation requirements.

**Structured intro summary:** {"background":"Back-end engineer with about four years of experience, mainly working with Python, Kafka, and PostgreSQL. Enjoys designing services that stay reliable as traffic grows and is interested in payment systems.","stated_strengths":["Designing reliable services for growing traffic","Handling transactional data and production incidents"],"notable_projects":["Kafka pipeline processing around 10,000 events per second with idempotent consumers and retries for duplicates and delayed events, maintaining P90 latency under 200 milliseconds"],"preferred_technologies":["Python","Kafka","PostgreSQL"]}

**Intro model:** gemini-3.5-flash-lite; provisional=False.

**First main-interview question:** Can you walk through how you designed the Kafka event pipeline at Meridian Analytics to handle 10,000 events per second, and how you implemented idempotent consumers and bounded retries while keeping p95 latency below 200 ms?

#### Job mode

**Initial intro question:** Tell me about yourself.

- **Transcript** (similarity 0.997): I am a back-end engineer with about four years of experience. I have mainly worked with Python, Kafka, and PostgreSQL, and I enjoy designing services that stay reliable as traffic grows.
  - **Adaptive follow-up:** Could you tell me more about a specific service you designed that scaled well, and what role you played in managing that traffic growth?

- **Transcript** (similarity 0.894): One project I owned was a Kafka pipeline processing around 10,000 events per second. I built idempotent consumers and retries for duplicates and delayed events and tracked P90 latency under 200 milliseconds.
  - **Adaptive follow-up:** Could you elaborate on the approach you took to keep the P90 latency under 200 milliseconds while handling duplicate and delayed events in your Kafka pipeline?

- **Transcript** (similarity 1.0): I am interested in payment systems because correctness and reliability matter as much as throughput. I have not worked directly with a payment ledger yet, but I have handled transactional data and production incidents, and I would be deliberate about learning reconciliation requirements.

**Structured intro summary:** {"background":"Back-end engineer with about four years of experience, mainly working with Python, Kafka, and PostgreSQL, focusing on designing reliable services and handling transactional data.","stated_strengths":["Designing services that stay reliable as traffic grows","Handling transactional data and production incidents"],"notable_projects":["Kafka pipeline processing around 10,000 events per second with idempotent consumers and retries for duplicates and delayed events, maintaining a P90 latency under 200 milliseconds"],"preferred_technologies":["Python","Kafka","PostgreSQL"]}

**Intro model:** gemini-3.5-flash-lite; provisional=False.

**First main-interview question:** In your work at Meridian Analytics with the Kafka-based event pipeline, how did you implement idempotent consumers, and what strategies did you use to handle out-of-order event delivery?
