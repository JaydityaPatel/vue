"""Benchmark local Kokoro ONNX speech synthesis."""

from __future__ import annotations

import argparse
import asyncio
import os
import types
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any

from common import LONG_TEXT, SHORT_TEXT, hardware_info, write_json

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin"
ASSETS_DIR = Path(__file__).parent / "assets"


def _download_if_missing(path: Path, url: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Kokoro model asset: {path.name}")
    urllib.request.urlretrieve(url, path)


class KokoroSynthesizer:
    def __init__(self) -> None:
        import numpy as np
        from kokoro_onnx import Kokoro

        self.model_path = Path(os.getenv("KOKORO_MODEL", ASSETS_DIR / "kokoro-v1.0.onnx"))
        self.voices_path = Path(os.getenv("KOKORO_VOICES", ASSETS_DIR / "voices-v1.0.bin"))
        _download_if_missing(self.model_path, MODEL_URL)
        _download_if_missing(self.voices_path, VOICES_URL)
        self.engine: Any = Kokoro(str(self.model_path), str(self.voices_path))
        self.voice = os.getenv("KOKORO_VOICE", "af_heart")
        # kokoro-onnx 0.4.9 sends int32 speed for newer input_ids exports,
        # while the v1.0 model currently published by upstream declares float.
        # Follow the model's own ONNX metadata to select the accepted dtype.
        speed_input = next(item for item in self.engine.sess.get_inputs() if item.name == "speed")
        speed_dtype = np.dtype({
            "tensor(float)": np.float32,
            "tensor(int32)": np.int32,
            "tensor(int64)": np.int64,
        }[speed_input.type])

        def create_audio(engine: Any, phonemes: str, voice: Any, speed: float):
            from kokoro_onnx import SAMPLE_RATE, MAX_PHONEME_LENGTH

            phonemes = phonemes[:MAX_PHONEME_LENGTH]
            tokens = np.asarray(engine.tokenizer.tokenize(phonemes), dtype=np.int64)
            voice_style = voice[len(tokens)]
            if "input_ids" in [item.name for item in engine.sess.get_inputs()]:
                inputs = {
                    "input_ids": [[0, *tokens.tolist(), 0]],
                    "style": np.asarray(voice_style, dtype=np.float32),
                    "speed": np.asarray([speed], dtype=speed_dtype),
                }
            else:
                inputs = {
                    "tokens": [[0, *tokens.tolist(), 0]],
                    "style": np.asarray(voice_style, dtype=np.float32),
                    "speed": np.asarray([speed], dtype=speed_dtype),
                }
            return engine.sess.run(None, inputs)[0], SAMPLE_RATE

        self.engine._create_audio = types.MethodType(create_audio, self.engine)

    def synthesize(self, text: str) -> tuple[bytes, float]:
        started = time.perf_counter()
        samples, sample_rate = self.engine.create(text, voice=self.voice, speed=1.0, lang="en-us")
        import numpy as np

        pcm = np.asarray(samples, dtype=np.float32)
        pcm16 = (np.clip(pcm, -1, 1) * 32767).astype("<i2")
        from io import BytesIO

        output = BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm16.tobytes())
        return output.getvalue(), time.perf_counter() - started

    def synthesize_first_chunk(self, text: str) -> tuple[bytes, float]:
        async def first_chunk() -> tuple[bytes, float]:
            from io import BytesIO
            import numpy as np

            started = time.perf_counter()
            stream = self.engine.create_stream(text, voice=self.voice, speed=1.0, lang="en-us")
            samples, sample_rate = await anext(stream)
            elapsed = time.perf_counter() - started
            output = BytesIO()
            with wave.open(output, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
            await stream.aclose()
            return output.getvalue(), elapsed

        return asyncio.run(first_chunk())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "tts_result.json")
    args = parser.parse_args()
    engine = KokoroSynthesizer()
    engine.synthesize("This is a short warmup sentence.")
    measurements = []
    for label, text in (("short_15_words", SHORT_TEXT), ("long_60_words", LONG_TEXT)):
        audio, seconds = engine.synthesize(text)
        measurements.append({
            "case": label,
            "word_count": len(text.split()),
            "latency_seconds": seconds,
            "audio_bytes": len(audio),
        })
    result = {
        "stage": "local_tts",
        "model": "Kokoro-82M ONNX",
        "measurements": measurements,
        "hardware": hardware_info(),
    }
    write_json(args.output, result)
    print(result)


if __name__ == "__main__":
    main()
