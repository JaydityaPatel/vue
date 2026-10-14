# Phase 7: intro warm-up and hardware-aware routing

Job and Resume sessions now open a brief voice warm-up before their normal Phase 4 interview. The document plan runs in a background task while the candidate answers the warm-up over `/ws/intro/{session_id}`. After the initial “Tell me about yourself” question and two adaptive follow-ups, the backend stores an evidence-only structured summary and model provenance, waits for plan preparation if needed, creates the ordinary opening turn, and signals the browser to navigate to the shared `/interview/{session_id}` room. Random mode does not use the intro route.

The intro reuses Phase 5's microphone, VAD, Whisper, orb, WebSocket protocol, and browser speech playback. Candidate intro summaries are included in future opening/follow-up prompts. The app stores the summary, answers, model names, and provisional state in session config; the original documents remain in the background task's memory and are not added to the session config.

## Ollama and local timeout

`OllamaProvider` sends configured `keep_alive` (default `30m`) and uses a 180-second request timeout (`OLLAMA_TIMEOUT_SECONDS`). On this development machine a warm `qwen2.5:3b` prompt completed in 583 ms wall time. The timeout is deliberately much larger for cold starts and the slower deployment target; 583 ms is a floor measurement only, not a target estimate. Connection errors, timeouts, missing models (404), malformed JSON, and invalid response bodies become `ProviderError`, allowing router fallback.

`intro_chat` is configured as `ollama:qwen2.5:3b` followed by `gemini-3.5-flash-lite`. Explicit `HARDWARE_TIER=high` allows that local route. `unknown` (the default) and `constrained` use Gemini Flash-Lite alone. This prevents intro generation from reserving local GPU memory alongside Whisper on the target tier.

## VRAM planning assumptions

These are assumptions for choosing a route, not measured memory data:

| Resource | Estimated VRAM |
|---|---:|
| 4 GB target budget | 4,096 MB |
| Whisper small.en | 1,000 MB |
| Ollama Q4 3B | 2,500 MB |
| Runtime/context reserve | 768 MB |
| Estimated concurrent total | 4,268 MB |

The estimate exceeds the budget by 172 MB, so `unknown` and `constrained` skip Ollama for the intro. Setting `hardware_tier=high` explicitly opts into the local path; the contention benchmark cannot set or validate that policy for the RTX 3050 laptop.

## Setup and checks

Set `HARDWARE_TIER=unknown` or `HARDWARE_TIER=constrained` in `backend/.env` for the target machine. Keep Ollama running with `qwen2.5:3b` installed if testing the high-tier path. Start the backend from `backend/` and run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm test
npm run build
cd ..
..\.venv\Scripts\python.exe scripts\bench_gpu_contention.py --duration 60
```

The stress script overlaps faster-whisper, Ollama, and Kokoro, and records CPU/GPU samples plus per-stage timing/degradation and failures in `backend/benchmarks/gpu_contention_dev.json`. Its banner and result explicitly say that it was measured on the development machine and is not representative of the RTX 3050 4 GB target. Use its result only to catch crashes/OOMs in the concurrent path.

**Target-laptop validation:** Set `hardware_tier=constrained` in `.env` before running on the actual RTX 3050 laptop, and re-run `bench_gpu_contention.py` there for the real verdict.
