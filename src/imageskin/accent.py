"""The accent the person's voice speaks with (roadmap R26): their own, or American or British.

With their own accent, the clone speaks each line (Chatterbox Turbo, R25). With another accent,
one of Kokoro's ready-made voices of that accent speaks the line, and Chatterbox's converter
changes it into the person's voice, keeping the accent and the timing, so Kokoro's word and sound
timings still drive the mouth. The Kokoro voice is picked to suit the person, as the accent test
(R26a) does: every voice of that accent says a probe line and is converted to their voice, and
the closest after conversion is used.

The choice is saved as accent.json in the app's home folder, so it survives a restart.
"""

import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, get_args

import numpy as np

from imageskin.kokoro_engine import to_pcm16
from imageskin.voice import Speech, VoiceEngine, VoiceError

if TYPE_CHECKING:
    from imageskin.chatterbox_engine import ChatterboxEngine

logger = logging.getLogger(__name__)

Accent = Literal["own", "american", "british"]
ACCENTS: tuple[Accent, ...] = get_args(Accent)
OWN: Accent = "own"
FILENAME = "accent.json"

# Kokoro's English voices by accent (its language code, voices); women and men, so any person has
# a match. The same lists as the accent test (experiments/voice/accent_test.py).
KOKORO_VOICES: dict[Accent, tuple[str, list[str]]] = {
    "american": (
        "a",
        ["am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx"]
        + ["am_puck", "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore"]
        + ["af_nicole", "af_nova", "af_river", "af_sarah", "af_sky"],
    ),
    "british": (
        "b",
        ["bm_daniel", "bm_fable", "bm_george", "bm_lewis"]
        + ["bf_alice", "bf_emma", "bf_isabella", "bf_lily"],
    ),
}
PROBE = "Hello, it's good to see you. What would you like to talk about today?"

Samples = np.ndarray  # 24 kHz float samples
Convert = Callable[[Samples], Samples]


class Converter(Protocol):
    def set_voice(self, reference: Samples) -> None:
        """Learn the person's voice from a stretch of their speech."""
        ...

    def __call__(self, samples: Samples) -> Samples:
        """The same speech in the person's voice."""
        ...


def load_accent(home: Path) -> Accent:
    """The saved accent, or the person's own when none is saved or the file can't be read."""
    path = home / FILENAME
    try:
        accent = json.loads(path.read_text(encoding="utf-8")).get("accent")
    except FileNotFoundError:
        return OWN
    except (OSError, ValueError, AttributeError) as e:
        logger.error("Could not read the accent", extra={"path": str(path), "error": str(e)})
        return OWN
    if accent not in ACCENTS:
        logger.error("Unknown accent saved", extra={"path": str(path), "accent": accent})
        return OWN
    return accent  # type: ignore[no-any-return]


def save_accent(home: Path, accent: Accent) -> None:
    home.mkdir(parents=True, exist_ok=True)
    path = home / FILENAME
    path.write_text(json.dumps({"accent": accent}), encoding="utf-8")
    logger.info("Accent chosen", extra={"accent": accent})


def pcm16_to_float(pcm: bytes) -> Samples:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768


def fit_length(samples: Samples, n: int) -> Samples:
    """Trim or pad with silence to exactly n samples, so the converted audio matches the timings."""
    if len(samples) >= n:
        return samples[:n]
    return np.concatenate([samples, np.zeros(n - len(samples), dtype=samples.dtype)])


def convert_fitted(samples: Samples, convert: Convert) -> Samples:
    """The same speech in the person's voice, the same length, so the timings still hold."""
    return fit_length(np.asarray(convert(samples), dtype=np.float32), len(samples))


def pick_base(
    voices: Sequence[str],
    speak: Callable[[str], Samples],
    convert: Convert,
    alike: Callable[[Samples], float],
) -> tuple[str, list[tuple[str, float]]]:
    """The base voice that sounds most like the person once converted, and the three closest with
    their scores. Every voice is converted: conversion changes which voice is closest, so a
    ranking before it would not do."""
    scores = sorted(
        ((voice, round(alike(convert_fitted(speak(voice), convert)), 3)) for voice in voices),
        key=lambda score: -score[1],
    )
    return scores[0][0], scores[:3]


class AccentEngine:
    """Speaks in the person's voice with the chosen accent. `voice` is the voice sample's path,
    as for the clone. prepare() learns the voice and, for another accent, picks the base voice."""

    def __init__(
        self,
        clone: "ChatterboxEngine",
        kokoro: Callable[[str], VoiceEngine],  # Kokoro for a language code
        converter: Callable[[], Converter],
        voice_print: Callable[[Samples], np.ndarray],  # unit length, compared by dot product
    ) -> None:
        self._clone = clone
        self._kokoro = kokoro
        self._make_converter = converter
        self._voice_print = voice_print
        self._engines: dict[str, VoiceEngine] = {}
        self._converter: Converter | None = None
        self.accent: Accent = OWN
        self.base: str | None = None  # the Kokoro voice speaking, with another accent

    def check_voice_sample(self, voice: str) -> None:
        self._clone.check_voice_sample(voice)

    def prepare(self, voice: str, accent: Accent) -> None:
        start = time.perf_counter()
        self._clone.learn_voice(voice)
        self.accent, self.base = accent, None
        if accent == OWN:
            return
        reference = self._clone.reference(voice)
        converter = self._get_converter()
        try:
            converter.set_voice(reference)
        except Exception as e:  # the model's own errors
            raise VoiceError(f"Chatterbox could not learn the voice for the accent: {e}") from e
        target = self._voice_print(reference)
        lang, voices = KOKORO_VOICES[accent]
        kokoro = self._engine(lang)
        self.base, scores = pick_base(
            voices,
            lambda v: pcm16_to_float(kokoro.speak(v, PROBE).pcm),
            converter,
            lambda samples: float(self._voice_print(samples) @ target),
        )
        logger.info(
            "Picked base voice",
            extra={
                "accent": accent,
                "voice": self.base,
                "scores": scores,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )

    def speak(self, voice: str, text: str) -> Speech:
        if self.accent == OWN or self.base is None:
            return self._clone.speak(voice, text)
        lang, _ = KOKORO_VOICES[self.accent]
        speech = self._engine(lang).speak(self.base, text)
        start = time.perf_counter()
        samples = pcm16_to_float(speech.pcm)
        try:
            out = convert_fitted(samples, self._get_converter())
        except Exception as e:  # the model's own errors
            raise VoiceError(f"Chatterbox could not convert the voice: {e}") from e
        elapsed = time.perf_counter() - start
        audio_s = len(samples) / speech.sample_rate
        logger.info(
            "Converted speech to the person's voice",
            extra={
                "accent": self.accent,
                "base": self.base,
                "audio_s": round(audio_s, 2),
                "duration_ms": round(elapsed * 1000, 1),
                "real_time_factor": round(elapsed / audio_s, 2) if audio_s else None,
            },
        )
        return replace(speech, pcm=to_pcm16(out.tolist()))

    def _engine(self, lang: str) -> VoiceEngine:
        if lang not in self._engines:
            self._engines[lang] = self._kokoro(lang)
        return self._engines[lang]

    def _get_converter(self) -> Converter:
        if self._converter is None:
            start = time.perf_counter()
            try:
                self._converter = self._make_converter()
            except VoiceError:
                raise
            except Exception as e:  # import or model load failure
                raise VoiceError(f"could not load Chatterbox's voice converter: {e}") from e
            logger.info(
                "Loaded voice converter",
                extra={"duration_ms": round((time.perf_counter() - start) * 1000, 1)},
            )
        return self._converter
