"""Lazy local inference. CUDA errors are surfaced, never silently downgraded."""
import asyncio
import threading
from typing import Any

from app.config import settings

_model: Any = None
_model_lock = threading.Lock()


def _transcribe(pcm: bytes) -> str:
    import numpy as np
    from faster_whisper import WhisperModel

    global _model
    # A single inference at a time bounds GPU memory across connections.
    with _model_lock:
        if _model is None:
            _model = WhisperModel(settings.voice_stt_model, device=settings.voice_stt_device,
                                  compute_type=settings.voice_stt_compute_type)
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        segments, _ = _model.transcribe(audio, language="en", beam_size=1, vad_filter=False,
                                       condition_on_previous_text=False)
        return " ".join(segment.text.strip() for segment in segments).strip()


class VoiceRuntime:
    def __init__(self) -> None:
        self.vad: Any = None

    async def prepare(self) -> None:
        def load() -> Any:
            from silero_vad import load_silero_vad
            return load_silero_vad(onnx=True)
        self.vad = await asyncio.to_thread(load)
        # Warm the actual selected device before accepting a person's answer.
        await self.transcribe(bytes(16000 * 2))

    def probability(self, pcm: bytes) -> float:
        import numpy as np
        import torch
        audio = torch.from_numpy(np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0)
        return float(self.vad(audio, 16000).item())

    def reset(self) -> None:
        self.vad.reset_states()

    async def transcribe(self, pcm: bytes) -> str:
        return await asyncio.to_thread(_transcribe, pcm)
