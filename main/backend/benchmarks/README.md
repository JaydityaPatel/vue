# Phase 3 voice latency benchmarks

These scripts benchmark backend stages only. They do not add microphone, WebSocket, or UI code. Install the optional packages in the project venv with:

```powershell
..\.venv\Scripts\python.exe -m pip install -r backend\benchmarks\requirements.txt
```

Place actual recordings in `backend/benchmarks/samples/` as mono, 16 kHz PCM WAV files. If none are present, a deterministic 2.4-second tone fixture with a pause is created and labeled synthetic. A tone is useful for timing the audio-loading path, but it is not speech and cannot validate transcription accuracy; use recorded speech for STT evaluation.

Run the standalone stages from the repository root:

```powershell
..\.venv\Scripts\python.exe backend\benchmarks\stt_bench.py
..\.venv\Scripts\python.exe backend\benchmarks\vad_bench.py
..\.venv\Scripts\python.exe backend\benchmarks\tts_bench.py
..\.venv\Scripts\python.exe backend\benchmarks\llm_stream_bench.py
..\.venv\Scripts\python.exe backend\benchmarks\gemini_voice_bench.py
..\.venv\Scripts\python.exe backend\benchmarks\run_full_pipeline.py
```

Each stage accepts an optional WAV path. JSON detail files are written next to the scripts. The full runner warms up each local model before five timed trials and prints/records min, max, mean, and median for STT, first Gemini text, completed Gemini response, first Kokoro audio chunk, and end-to-end wall time. Local inference uses faster-whisper `small.en` with CUDA float16 when CTranslate2 can load it; otherwise it retries CPU int8. The requested result text files and structured `results.json` are written to this folder even when an environment/model is unavailable, with the reason stated instead of invented timings.

## Hardware and runtime

The reference target in the Phase 3 brief was an i5 11th generation, RTX 3050 with about 4 GB VRAM, and 16 GB system memory. This run environment reports an NVIDIA RTX 4000 Ada Generation with 20,475 MiB total GPU memory; it is not comparable to that target. `nvidia-smi` snapshots record total GPU memory use and utilization before and after local/hosted runs. On WDDM, those are device-wide values and include other processes; they are not per-process attribution.

The installed driver reports CUDA 13.0. faster-whisper's current CTranslate2 builds require CUDA 12 cuBLAS and cuDNN 9 for GPU inference, in addition to a compatible driver. The driver version alone does not mean those runtime libraries are installed. Check the emitted `runtime.device` field: `cuda` means GPU inference; `cpu` means the CUDA load failed and int8 CPU fallback was used. If the GPU load fails, install matching CUDA 12/cuDNN 9 Windows runtime libraries and put their DLL directory on `PATH`, then rerun. Silero VAD uses PyTorch and downloads its model on first use; this benchmark reads PCM WAV through the standard library rather than torchaudio. Kokoro ONNX downloads its model and voice file to `assets/` on first use; `KOKORO_MODEL`, `KOKORO_VOICES`, and `KOKORO_VOICE` can point to local assets/settings.

## Hosted Gemini

Hosted calls read `GEMINI_API_KEY` from the backend `.env` through `app.config.settings`; the key is never printed. Requests go through `LLMRouter`, including streaming text, audio transcription, and audio generation. Model access/quota is account-dependent. If the key is missing, or Gemini rejects a requested model, the report records unavailable/error and does not substitute simulated timings. The streaming test measures time to first returned text chunk; the hosted voice test uses inline 16 kHz PCM for transcription and requests audio from the TTS model.

## Tests and failure modes

From the repository root, run `..\.venv\Scripts\python.exe -m pytest backend\tests -q`. Tests mock Gemini's SSE responses and do not require credentials or network access. Common benchmark failures include missing CUDA/cuDNN DLLs (Whisper CPU fallback), first-run model downloads being blocked, unavailable Kokoro assets, malformed/non-PCM WAV files, missing `GEMINI_API_KEY`, or models not enabled for the configured Gemini account. Model download and initialization time are reported separately or excluded from timed steady-state trials; benchmark the cold-start separately if that matters for deployment.
