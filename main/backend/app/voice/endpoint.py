"""Sample-clock endpointing, independent of network and inference delays."""
from dataclasses import dataclass

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512


@dataclass
class Endpoint:
    silence_ms: int = 1800
    min_speech_ms: int = 256
    speaking_samples: int = 0
    silence_samples: int = 0
    started: bool = False

    def feed(self, probability: float, samples: int = FRAME_SAMPLES) -> bool:
        if probability >= 0.5:
            self.started = True
            self.speaking_samples += samples
            self.silence_samples = 0
        elif self.started:
            self.silence_samples += samples
        if (self.speaking_samples * 1000 < self.min_speech_ms * SAMPLE_RATE
                and self.silence_samples * 1000 >= self.silence_ms * SAMPLE_RATE):
            self.reset()  # A brief noise must not accumulate into a later answer.
        return (self.speaking_samples * 1000 >= self.min_speech_ms * SAMPLE_RATE
                and self.silence_samples * 1000 >= self.silence_ms * SAMPLE_RATE)

    def reset(self) -> None:
        self.speaking_samples = self.silence_samples = 0
        self.started = False
