# Phase 3 verdict

The five-run benchmark is being run on an RTX 4000 Ada Generation (20 GB), not the brief's RTX 3050 (4 GB) target, so any local latency conclusion applies only to this machine. GPU snapshots are device-wide WDDM readings; they cannot isolate Whisper/Kokoro from other processes.

The requested cloud comparison requires a configured `GEMINI_API_KEY`. This checkout currently has no key configured, so hosted STT, Gemini streaming, and Gemini TTS cannot be measured here. The hosted report records that as unavailable rather than presenting guessed values.

The conclusion below is generated from the actual `results_local.txt` and `results_gemini_hosted.txt` output after the run. Treat a result as a pipeline verdict only when all local stages completed using spoken audio and all relevant hosted stages completed. The deterministic tone fallback is not human or synthetic speech and cannot support a recommendation about transcription quality.
