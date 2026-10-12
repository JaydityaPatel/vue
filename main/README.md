# Vue — AI interview practice

Phase 1 provides FastAPI, SQLite, and the LLM router. Phase 2 adds authentication and the React pages. Phase 4 makes Random practice a persistent, adaptive text interview with anchored evaluation and reports. The separate [`orb-demo/`](orb-demo/README.md) is an audio-reactive visualization experiment.

## Run the app

Open two PowerShell windows from the project root. Start the API in the first:

```powershell
cd backend
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Start the web app in the second:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The web app connects to http://localhost:8000 by default; set `VITE_API_BASE_URL` in `frontend/.env.local` to change it.

## Local configuration

Copy `backend/.env.example` to `backend/.env`. Set `JWT_SECRET` to a long, randomly generated secret before deploying. The frontend stores the short-lived API access token in local storage; the backend expires tokens after seven days. Never commit `.env` files or real provider keys.

## Checks

```powershell
cd backend
..\..\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm test
npm run build
```

Sign in, choose Random practice, and submit the setup form. Type answers in the interview room. Refreshing the room restores its saved questions and answers. On completion, Generate report displays the persisted evaluation in the room.

See [Phase 4 API and state rules](backend/PHASE4.md) for request examples, follow-up limits, scoring policy, and transaction behavior. Job/resume setup, the separate report/history pages, and voice remain outside this phase.

