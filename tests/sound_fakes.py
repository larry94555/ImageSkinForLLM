"""Made-up recordings for the sound check tests: syllable-like bursts with pauses between them,
over steady background noise."""

import io
import wave

import numpy as np

RATE = 24000


def speechlike(
    seconds: float, level: float = 0.3, noise: float = 0.001, seed: int = 0
) -> np.ndarray:
    """Samples scaled to -1..1: 250 ms bursts of a 200 Hz voice-like tone, every 400 ms."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * RATE)) / RATE
    on = (t % 0.4) < 0.25
    voice = level * np.sin(2 * np.pi * 200 * t) * on
    return voice + rng.normal(0, noise, len(t))


def wav_of(samples: np.ndarray, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()
