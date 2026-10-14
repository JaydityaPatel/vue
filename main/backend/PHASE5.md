# Phase 5: voice interview room

The interview room now uses an AudioWorklet microphone, authenticated
WebSocket, Silero endpointing, faster-whisper, the existing Phase 4 orchestrator,
sentence-buffered browser speech synthesis, and the original orb demo shaders
ported into React Three Fiber. Resume and Job sessions enter through the Phase 7
spoken intro before reaching this shared room.

## Run locally

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r main/backend/requirements-voice.txt
```

Copy `backend/.env.example` to `backend/.env` if it does not already exist. Set
your Gemini key and JWT secret. The default voice configuration is `small.en`,
`cuda`, `int8_float16`. Install a compatible CUDA 12/cuDNN runtime and make its
DLLs discoverable by CTranslate2. Model weights download on first use if absent.
CUDA errors are surfaced; they do not trigger a hidden CPU fallback.

For explicit CPU operation set `VOICE_STT_DEVICE=cpu` and
`VOICE_STT_COMPUTE_TYPE=int8` in `.env`, then restart the backend. This is a
functional alternative, not a simulation of RTX 3050 performance.

Start the API and frontend as described in the root README. Use localhost or
HTTPS, sign in, create a Random interview, click **Start voice**, and allow the
microphone. Chrome/Edge with WebGL, AudioWorklet, and an installed English speech
voice are suitable for the local check. Mic permission and TTS playback failures
are shown in the room. Reconnecting reloads saved history and replays the pending
question; an unfinished, unsaved utterance is discarded.

**End interview** discards unfinished speech and finishes the saved answers. If
there are no answered turns, the session is abandoned without a report. After
one or more saved answers, the existing report generator is available.

## Accepted TTS behavior

The user approved keeping `speechSynthesis` after confirming that its output is
not exposed as a Web Audio stream. The orb's **speaking** state starts at actual
`SpeechSynthesisUtterance.onstart`; playback completion gates microphone resume.
Speaking has a distinct glow with ambient motion, but **no invented output
amplitude**. Only live microphone RMS from `AnalyserNode` drives deformation
while listening. Output amplitude analysis remains unavailable with this API.

## Protocol

Connect to `/ws/interview/{session_id}`. Send an initial JSON message within ten
seconds: `{"type":"auth","token":"<JWT>"}`. Tokens are never put in the URL.
Ownership and the selected room mode are checked before initializing inference.

Client controls:

- `{"type":"playback_done","turn_id":"..."}` after all question sentences end.
- `{"type":"mute","muted":true}` (or false). Discards current unsaved audio.
- `{"type":"end"}` to finish saved work.
- Binary frames: exactly 512 mono signed PCM16 samples, little endian, 16 kHz.
  The AudioWorklet resamples the actual capture rate and emits 1024-byte frames.

Server messages (see `app/voice/protocol.py` and `src/voice/protocol.ts`):

- `snapshot`: persisted session and ordered turns.
- `state`: `idle`, `listening`, or `thinking`, with `stt_active`.
- `transcript`: turn ID, text, and `final` boolean. Partial hypotheses replace
  earlier hypotheses; they are never appended as extra persisted answers.
- `question_start`, `question_chunk`, `question_end`: same committed turn ID.
- `error`: readable failure. Reconnect before attempting another answer.

The server discards microphone frames while awaiting playback acknowledgement.
The browser additionally disables the microphone track and worklet delivery.
There is no barge-in. Noisy bursts shorter than 256 ms are discarded after the
silence threshold. Normal speech endpoints require 1.8 seconds of silence, counted
in audio samples rather than network time. Answers are bounded to two minutes.

Partial transcription reruns Whisper on the growing utterance about every four
seconds; it is not a native streaming Whisper decoder. Those hypotheses may be
revised. Final STT and all partial inference run off the ASGI event loop and share
a lock that prevents overlapping Whisper GPU allocations. Silero recurrent state
is isolated per connection. The normal local server uses one worker; the active
socket guard is per process, while Phase 4's database compare-and-swap still
rejects stale answer transitions across processes.

## Validated questions and performance

The orchestrator generates structured actions and validates them before saving.
The voice adapter streams chunks of the **validated, committed question**; it
does not speak raw provider tokens or rejected action proposals. Consequently,
Phase 4's scoring and structured generation finish before question playback.
Sentence buffering starts TTS when a full sentence arrives and flushes the final
fragment at `question_end`. This implementation does not claim provider-token
latency optimizations or any measured end-to-end latency target.

The orb preserves the original ring and folded-particle shaders. It uses a quad
and 27,648 shader-driven points, 30 fps maximum foreground rendering, no rendering
while hidden, and 10 fps with one particle layer and DPR 1 during STT. Reduced
motion is respected. Three.js/R3F are imported only through the lazy room route.

## Verification

```powershell
cd main/backend
..\..\.venv\Scripts\python.exe -m pytest -q
cd ../frontend
npm test
npm run build
```

Tests cover endpoint timing, short pauses/noise, protocol validation, authentication
and ownership, PCM-to-orchestrator persistence and scoring, playback/mute gates,
reconnection, stale turn rejection, sentence boundaries, PCM resampling, transcript
ordering/scroll, room lifecycle, and speech-event-driven orb state. Network model
calls and speech devices are mocked in the suites; they use no API quota.

The final local suites passed: **96 backend tests**, **42 frontend tests**, and
the production build. The room bundle is separate from the main application
bundle; Vite still reports its expected large Three.js chunk warning.

For the actual WebGL layout smoke check, install the existing `orb-demo` dev
dependencies and its Playwright Chromium browser, start the frontend on port
5175, then run `node scripts/verify-voice-room.mjs` from `main/frontend`. It uses
fixture HTTP responses, checks route lazy loading and desktop/mobile layout, and
saves screenshots under ignored `test-results/phase5`. It also exercises the real
AudioWorklet with Chromium's synthetic microphone. The local check received 45
correctly sized PCM frames, measured nonzero input amplitude, and confirmed that
muting stopped delivery. There were no browser/WebGL errors. It does not claim
to test live LLM responses or physical speaker output.

Local runtime check: real Silero + `small.en` CPU/int8 successfully endpointed and
transcribed the existing prerecorded WAV. Default CUDA warmup failed with
`Library cublas64_12.dll is not found or cannot be loaded`. No Gemini API key is
configured in the current backend settings. A full live CUDA/LLM/browser-speech
session therefore remains an environment verification step, not a passed test.
