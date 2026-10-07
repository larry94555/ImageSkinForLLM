"""One-speaker check on an uploaded recording (roadmap R11): flags a recording in which a second
person can be heard talking, since a voice made from it would mix the two.

Each 1.5 second stretch of speech (pauses skipped) gets a voice print: 512 numbers from CAM++, a
speaker recognition model from 3D-Speaker (Apache 2.0, trained on VoxCeleb), run on the CPU with
ONNX Runtime (MIT). The model (28 MB) is downloaded on first use. The voice prints are split into
the two groups that sound most different. One person's groups still sound alike; two people's do
not, and then the smaller group is the other person. A minute of sound takes about a second.
"""

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from imageskin.download import DownloadError, download
from imageskin.sound_checks import FRAME_S, frame_levels, speech_frames

logger = logging.getLogger(__name__)

# sherpa-onnx's ONNX export of iic/speech_campplus_sv_en_voxceleb_16k from ModelScope.
MODEL_URL = (
    "https://huggingface.co/csukuangfj/speaker-embedding-models/resolve/"
    "0743f301363dec56491a490f6d6cbc9d67f9a3bf/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx"
)
MODEL_SIZE = 29596978
MODEL_SHA256 = "357a834f702b80161e5b981182c038e18553c1f2ca752ed6cec2052365d4129b"
MODEL_RATE = 16000
MEL_BANDS = 80

# Stretches of 1.5 s every 0.75 s; a stretch counts when at least half of it is speech.
WINDOW_S = 1.5
HOP_S = 0.75
MIN_SPEECH_SHARE = 0.5
# Measured on LibriSpeech dev-clean (40 readers): one-minute recordings of one reader, some with
# background noise, and of two readers taking turns, the second reading for 2 to 30 seconds. The
# two groups' average voice prints are alike by 0.63 to 0.95 (cosine) for one reader and -0.08
# to 0.51 for two; two people in a real conversation measured 0.15 to 0.52. One reader recorded
# on two different days, joined, can measure as low as 0.26: a change of microphone or room
# halfway through also changes how the voice sounds.
SAME_VOICE = 0.55
# Fewer stretches than this in the smaller group (about 3 seconds of speech) are a cough or a
# laugh rather than another person. Two readers with the second reading for 4 seconds or more
# were all found; for 2 seconds, 85%.
MIN_OTHER = 3
BATCH = 64

TWO_VOICES = (
    "Someone else can be heard talking in this recording. Record again where only you are"
    " speaking, with the TV and radio off."
)


class SpeakerCheckError(Exception):
    """The speaker model could not be downloaded or loaded."""


@dataclass(frozen=True)
class VoiceMeasure:
    stretches: int  # 1.5 s stretches of speech that got a voice print
    other: int = 0  # stretches in the smaller group
    alike: float = 1.0  # how alike the two groups' average voices are, -1 to 1


def problems(m: VoiceMeasure) -> list[str]:
    if m.alike < SAME_VOICE and m.other >= MIN_OTHER:
        return [TWO_VOICES]
    return []


def to_model_rate(samples: NDArray[np.float64], rate: int) -> NDArray[np.float64]:
    """Resample to 16 kHz by cutting the spectrum, which also removes what 16 kHz can't hold."""
    if rate == MODEL_RATE or len(samples) == 0:
        return samples
    count = round(len(samples) * MODEL_RATE / rate)
    spectrum = np.fft.rfft(samples)[: count // 2 + 1]
    out: NDArray[np.float64] = np.fft.irfft(spectrum, count) * (count / len(samples))
    return out


def _mel(hz: NDArray[np.float64] | float) -> Any:
    return 1127.0 * np.log(1.0 + np.asarray(hz) / 700.0)


def fbank(samples: NDArray[np.float64]) -> NDArray[np.float64]:
    """The model's input: log energy in 80 mel bands for each 25 ms frame, every 10 ms, made as
    Kaldi does by default (the model was trained on that), from 16 kHz samples scaled to -1..1."""
    size, step, n_fft = 400, 160, 512
    count = 1 + (len(samples) - size) // step
    if count <= 0:
        return np.zeros((0, MEL_BANDS))
    frames = samples[np.arange(size)[None, :] + step * np.arange(count)[:, None]]
    frames = frames - frames.mean(axis=1, keepdims=True)
    frames = np.concatenate(  # pre-emphasis
        [frames[:, :1] * 0.03, frames[:, 1:] - 0.97 * frames[:, :-1]], axis=1
    )
    window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(size) / (size - 1))) ** 0.85  # Povey
    power = np.abs(np.fft.rfft(frames * window, n_fft)) ** 2
    edges = np.linspace(_mel(20.0), _mel(MODEL_RATE / 2), MEL_BANDS + 2)
    bins = _mel(np.arange(n_fft // 2 + 1) * MODEL_RATE / n_fft)
    low, mid, high = edges[:-2, None], edges[1:-1, None], edges[2:, None]
    weights = np.maximum(0.0, np.minimum((bins - low) / (mid - low), (high - bins) / (high - mid)))
    weights[:, -1] = 0.0  # Kaldi leaves out the top bin
    energies: NDArray[np.float64] = np.log(np.maximum(power @ weights.T, np.finfo(np.float32).eps))
    return energies


def speech_stretches(samples: NDArray[np.float64]) -> NDArray[np.float32]:
    """The model input for each 1.5 s stretch that is mostly speech, from 16 kHz samples:
    shape (stretches, 150, 80), each band's average over the stretch taken away."""
    is_speech = speech_frames(frame_levels(samples, MODEL_RATE))
    features = fbank(samples)
    size, step = round(WINDOW_S * 100), round(HOP_S * 100)  # in 10 ms feature frames
    per_level = round(FRAME_S * 100)  # feature frames per loudness frame
    stretches = []
    for start in range(0, len(features) - size + 1, step):
        speech = is_speech[start // per_level : (start + size) // per_level]
        if len(speech) and speech.mean() >= MIN_SPEECH_SHARE:
            stretch = features[start : start + size]
            stretches.append(stretch - stretch.mean(axis=0))
    if not stretches:
        return np.zeros((0, size, MEL_BANDS), np.float32)
    return np.stack(stretches).astype(np.float32)


def two_groups(prints: NDArray[np.float64]) -> VoiceMeasure:
    """Split unit-length voice prints into the two groups that sound most different."""
    if len(prints) < 2:
        return VoiceMeasure(stretches=len(prints))
    # Start from the print least like the average, and the print least like that one.
    average = prints.mean(axis=0)
    second = prints[np.argmin(prints @ average)]
    centres = np.stack([prints[np.argmin(prints @ second)], second])
    for _ in range(20):
        group = np.argmax(prints @ centres.T, axis=1)
        for g in (0, 1):
            if np.any(group == g):
                centre = prints[group == g].mean(axis=0)
                centres[g] = centre / np.linalg.norm(centre)
    sizes = np.bincount(group, minlength=2)
    return VoiceMeasure(
        stretches=len(prints),
        other=int(sizes.min()),
        alike=round(float(centres[0] @ centres[1]), 3),
    )


class SpeakerChecker:
    """Checks recordings one at a time, from the upload request. The model is loaded once."""

    def __init__(self, models_dir: Path) -> None:
        self._model_file = models_dir / "campplus_voxceleb_16k.onnx"
        self._lock = threading.Lock()
        self._session: Any = None
        self._broken: str | None = None

    def _load(self) -> Any:
        if self._broken is not None:
            raise SpeakerCheckError(self._broken)
        if self._session is None:
            import onnxruntime

            start = time.perf_counter()
            try:
                download(MODEL_URL, self._model_file, MODEL_SIZE, MODEL_SHA256)
                options = onnxruntime.SessionOptions()
                options.log_severity_level = 3  # errors only
                self._session = onnxruntime.InferenceSession(
                    str(self._model_file), options, providers=["CPUExecutionProvider"]
                )
            except (DownloadError, OSError, RuntimeError) as e:
                # Don't retry on every recording: a failed download retries for minutes.
                self._broken = f"the speaker model could not be loaded: {e}"
                logger.error("Speaker checks are off until restart", extra={"error": str(e)})
                raise SpeakerCheckError(self._broken) from e
            logger.info(
                "Speaker model ready",
                extra={
                    "path": str(self._model_file),
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
        return self._session

    def prepare(self) -> None:
        """Download and load the model now, so the first recording isn't held up by it. A
        failure is logged and leaves the check off."""
        with self._lock:
            try:
                self._load()
            except SpeakerCheckError:
                return  # already logged

    def voice_prints(self, stretches: NDArray[np.float32]) -> NDArray[np.float64]:
        """One unit-length voice print per stretch."""
        session = self._load()
        prints = np.concatenate(
            [
                session.run(None, {"x": stretches[i : i + BATCH]})[0]
                for i in range(0, len(stretches), BATCH)
            ]
        ).astype(np.float64)
        normalized: NDArray[np.float64] = prints / np.linalg.norm(prints, axis=1, keepdims=True)
        return normalized

    def check(self, samples: NDArray[np.float64], rate: int) -> list[str]:
        """The problem when someone else is talking in the recording; [] when not."""
        start = time.perf_counter()
        stretches = speech_stretches(to_model_rate(samples, rate))
        with self._lock:  # one recording at a time keeps memory and CPU use down
            prints = self.voice_prints(stretches) if len(stretches) else np.zeros((0, 1))
        m = two_groups(prints)
        found = problems(m)
        logger.info(
            "Speaker checked",
            extra={
                "stretches": m.stretches,
                "other": m.other,
                "alike": m.alike,
                "problems": len(found),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return found
