# Vue frontend — Phase 2

React 18 + TypeScript + Vite + Tailwind, with the public landing, signup/login, and protected interview practice pages. The Phase 2 interview room uses a lightweight CSS and Framer Motion orb placeholder; the WebGL interview orb belongs to Phase 5.

## Run locally

In one PowerShell window, run the FastAPI backend from `backend/`:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

In another window, start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The API defaults to http://localhost:8000. Copy `.env.example` to `.env.local` to use a different `VITE_API_BASE_URL`.

For local backend configuration, copy `backend/.env.example` to `backend/.env`. Set `JWT_SECRET` to a long random value before deployment. Replace the development Gemini placeholder if using an LLM provider later.

## Checks

```powershell
npm test
npm run build
```

The pages intentionally use empty states for future interview and report data. Upload selection and setup are navigation scaffolds; file parsing and session persistence are later phases.
