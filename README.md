# Vue Interview Practice

An AI-assisted interview practice platform with a FastAPI backend and a React/Vite frontend. The current working flow is the text-based Random interview: the setup form creates a persistent session, the backend generates a structured interview plan, the orchestrator selects follow-ups under hard limits, and completed sessions can generate an anchored evaluation report.

The repository also contains the Phase 3 latency benchmark scripts and the separate `main/orb-demo` audio-reactive visualization experiment. Voice interaction, resume/JD parsing, coding rounds, and RAG are not part of the current interview flow.

## Requirements

- Windows PowerShell, macOS, or Linux
- Python 3.12 recommended
- Node.js 18 or newer
- A Gemini API key for live plan, question, scoring, and report generation

## Project layout

```text
main/
  backend/       FastAPI app, SQLAlchemy models, LLM router, tests
  frontend/      React/Vite application and frontend tests
  scripts/       Standalone Phase 3 latency benchmark scripts
  orb-demo/      Separate browser visualization experiment
```

## Backend setup

From `main/backend`, create a virtual environment and install dependencies:

```powershell
cd main/backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` and set:

```dotenv
GEMINI_API_KEY=your-key-here
JWT_SECRET=replace-with-a-long-random-secret
DATABASE_URL=sqlite:///./vue.db
```

Never commit `.env` or a real API key. `.env.example` is only a template.

Start the API from the repository root:

```powershell
cd main/backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`; health is exposed at `/health`.

## Frontend setup

In another terminal:

```powershell
cd main/frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open `http://localhost:5173`. The default API URL is `http://localhost:8000`. Change `VITE_API_BASE_URL` in `frontend/.env.local` when the backend runs elsewhere.

Register an account, choose Random practice, complete the setup form, and answer in the text interview room. The room reloads its state from the API, so refreshing the browser does not lose the interview.

## Tests and build

Backend tests:

```powershell
cd main/backend
..\.venv\Scripts\python.exe -m pytest -q
```

Frontend tests and production build:

```powershell
cd main/frontend
npm test
npm run build
```

The tests mock LLM calls and provider HTTP requests; they do not consume API quota.

## Interview API

All interview endpoints require the JWT returned by `/auth/login`:

- `POST /interviews` creates a Random interview and returns the first question.
- `POST /interviews/{session_id}/answer` scores the current answer and returns the next question or completion state.
- `GET /interviews/{session_id}` returns persisted state, topic coverage, turn history, and scores.
- `POST /interviews/{session_id}/report` generates the persisted report after completion.

See [backend/PHASE4.md](main/backend/PHASE4.md) for request examples, state-machine rules, follow-up limits, evaluation provenance, and transaction behavior.

## Phase 3 benchmark scripts

The scripts are standalone and are not wired into the interview UI:

```powershell
cd main
..\.venv\Scripts\python.exe scripts/bench_stt.py backend/benchmarks/samples --model small.en --device cpu
..\.venv\Scripts\python.exe scripts/bench_llm_ttft.py
```

The STT benchmark requires faster-whisper and a locally available model. CUDA inference also requires a working CTranslate2/CUDA runtime on the machine.

## Git hygiene

The root `.gitignore` excludes virtual environments, secrets, caches, databases, dependency folders, build output, test artifacts, editor files, and local archives. Keep source code, lockfiles, environment templates, benchmark scripts, and documentation tracked.
