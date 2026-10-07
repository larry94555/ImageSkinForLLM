"""Sound checks on an uploaded recording (roadmap R10): enough speech, not clipped (too loud),
and little background noise. Each failed check gives a fixed message a nontechnical person can
act on.

Works on the stored 24 kHz mono 16-bit WAV (see audio.to_wav), cut into 20 ms frames. The
quietest frames, in the pauses between words, give the background noise; the loudest give the
speech level. No model is needed, so the checks take well under a second per minute of sound.
"""

import logging
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# Speech is counted in frames that stand out from the background noise, so pauses don't count.
# The recording guide's sections each hold a minute or more of speech. A voice-conversion model
# (roadmap R25) needs about 30 seconds of the person's voice in all, so the combined voice
# sample needs at least that, and each recording a share of it.
MIN_SPEECH_S = 15.0
MIN_SAMPLE_SPEECH_S = 30.0
# Clipped: a sample within 1% of the loudest a 16-bit file can hold. A few clipped peaks are
# not heard. Speech turned up 6 dB past the top, then saved as M4A, has 0.08% of its samples
# clipped; 12 dB past, 0.8%. A recording normalized to just below the top has none.
CLIP_LEVEL = 0.99
MAX_CLIPPED = 0.0005
# Background noise: the speech level (the loudest 5% of frames) over the noise level (the
# quietest 10% of frames), in dB. Measured on 20 to 40 second recordings joined from the
# VoiceBank-DEMAND test set: the clean studio recordings measure 29 to 38, the same speech with
# cafe, street or office noise mixed in at 12.5 dB (audible, but the voice is clear) 22 to 25,
# and at 7.5 dB or less (the noise competes with the voice) 13 to 20.
MIN_SNR_DB = 20.0

FRAME_S = 0.02
# Frames this far above the noise level, and no more than SPEECH_RANGE_DB below the speech
# level, count as speech.
SPEECH_ABOVE_NOISE_DB = 6.0
SPEECH_RANGE_DB = 35.0

TOO_SHORT = (
    "This recording has only {speech:.0f} seconds of speech. Each recording needs at least"
    f" {MIN_SPEECH_S:.0f} seconds: read the whole section from the recording guide."
)
CLIPPED = (
    "The recording is too loud, so parts of it are distorted. Turn the microphone volume down"
    " or move a little further from it, and record again."
)
NOISY = (
    "There is too much background noise. Record in a quiet room, away from fans, open windows,"
    " music or a TV."
)


@dataclass(frozen=True)
class SoundMeasure:
    speech_s: float  # seconds of speech, pauses not counted
    clipped: float  # share of speech samples that are clipped
    snr_db: float  # speech level over background noise level


@dataclass(frozen=True)
class SoundResult:
    """What the sound checks found ([] when the recording passed), and its seconds of speech."""

    problems: list[str]
    speech_s: float


def frame_levels(samples: NDArray[np.float64], rate: int) -> NDArray[np.float64]:
    """Loudness of each 20 ms frame in dB below full scale (0 dB is the loudest possible)."""
    size = round(rate * FRAME_S)
    count = len(samples) // size
    frames = samples[: count * size].reshape(count, size)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    levels: NDArray[np.float64] = 20 * np.log10(np.maximum(rms, 1e-6))
    return levels


def measure(samples: NDArray[np.float64], rate: int) -> SoundMeasure:
    """Measure samples scaled to -1..1."""
    levels = frame_levels(samples, rate)
    if len(levels) == 0:
        return SoundMeasure(speech_s=0.0, clipped=0.0, snr_db=0.0)
    # Pauses that are digital silence, such as from a recorder's noise suppression, give a
    # very low noise level: right, since there is no noise in them.
    noise = float(np.percentile(levels, 10))
    speech = float(np.percentile(levels, 95))
    threshold = max(noise + SPEECH_ABOVE_NOISE_DB, speech - SPEECH_RANGE_DB)
    is_speech = levels > threshold
    size = round(rate * FRAME_S)
    speech_samples = samples[: len(levels) * size].reshape(len(levels), size)[is_speech]
    clipped = float(np.mean(np.abs(speech_samples) >= CLIP_LEVEL)) if speech_samples.size else 0.0
    return SoundMeasure(
        speech_s=round(float(np.sum(is_speech)) * FRAME_S, 2),
        clipped=clipped,
        snr_db=round(speech - noise, 1),
    )


def problems(m: SoundMeasure) -> list[str]:
    found = []
    if m.speech_s < MIN_SPEECH_S:
        found.append(TOO_SHORT.format(speech=m.speech_s))
    if m.clipped > MAX_CLIPPED:
        found.append(CLIPPED)
    # Noise can't be judged without speech to compare it with.
    if m.speech_s > 0 and m.snr_db < MIN_SNR_DB:
        found.append(NOISY)
    return found


def read_wav(path: Path) -> tuple[NDArray[np.float64], int]:
    """A 16-bit mono WAV as samples scaled to -1..1, and its sample rate."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError(f"{path.name}: expected 16-bit mono WAV")
        rate = w.getframerate()
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype="<i2").astype(np.float64) / 32768.0, rate


def check(path: Path) -> SoundResult:
    """Run the sound checks on a stored recording."""
    start = time.perf_counter()
    m = measure(*read_wav(path))
    found = problems(m)
    logger.info(
        "Sound checked",
        extra={
            "sound": path.name,
            "speech_s": m.speech_s,
            "clipped": round(m.clipped, 5),
            "snr_db": m.snr_db,
            "problems": len(found),
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return SoundResult(problems=found, speech_s=m.speech_s)
