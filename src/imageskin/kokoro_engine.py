"""Voice engine adapter for Kokoro-82M, a small open-source text to speech model that runs on CPU.

Kokoro speaks with ready-made voices (it does not clone) and reports when each word starts and
ends. It also reports how long it makes each sound (phoneme), in 25 ms steps that add up exactly
to the audio's length, so the mouth shapes line up with the voice.
The model (about 330 MB) is downloaded from Hugging Face on first use and cached.
"""

import functools
import logging
import sys
import time
from array import array
from collections.abc import Callable, Container, Iterable, Sequence
from typing import Any

from imageskin.visemes import SoundTiming, sound_timings
from imageskin.voice import Speech, VoiceError, WordTiming

logger = logging.getLogger(__name__)

REPO_ID = "hexgrad/Kokoro-82M"
LANG_CODE = "a"  # American English; "b" is British English
SAMPLE_RATE = 24000
DEFAULT_VOICE = "af_heart"
STEP_S = 600 / SAMPLE_RATE  # one step of Kokoro's sound durations: 25 ms
INSTALL_HINT = 'Kokoro is not installed; run: pip install -e ".[voice]"'


def to_pcm16(samples: Sequence[float]) -> bytes:
    """Convert float samples in [-1, 1] to 16-bit little-endian PCM, clipping values outside."""
    pcm = array("h", (round(max(-1.0, min(1.0, s)) * 32767) for s in samples))
    if sys.byteorder == "big":
        pcm.byteswap()
    return pcm.tobytes()


def chunk_sounds(
    phonemes: str, steps: Sequence[float], offset: float, vocab: Container[str] | None
) -> list[SoundTiming]:
    """Sound timings for one chunk, from its phonemes and Kokoro's duration steps.

    Kokoro drops phonemes it has no token for, then adds a padding token at each end; the
    padding is shown as "." so the mouth rests there. Returns [] if the counts don't match.
    """
    kept = phonemes if vocab is None else "".join(ch for ch in phonemes if ch in vocab)
    if len(steps) != len(kept) + 2:
        logger.warning(
            "Sound timings skipped for a chunk",
            extra={"phonemes": phonemes, "steps": len(steps), "kept": len(kept)},
        )
        return []
    return sound_timings("." + kept + ".", [s * STEP_S for s in steps], offset)


def speech_from_results(results: Iterable[Any], vocab: Container[str] | None = None) -> Speech:
    """Join Kokoro's per-chunk results into one Speech.

    Each result has `audio` (float samples), `tokens` with `text`, `start_ts` and `end_ts` in
    seconds from the start of that chunk, and `phonemes` with `pred_dur` (each phoneme's length
    in steps), so chunk offsets are added to get times in the whole clip. Punctuation tokens are
    left out of the word timings. `vocab` is the model's phoneme set, when known.
    """
    pcm = bytearray()
    words: list[WordTiming] = []
    sounds: list[SoundTiming] = []
    for result in results:
        if result.audio is None:
            continue
        offset = len(pcm) / 2 / SAMPLE_RATE
        for token in result.tokens or []:
            if token.start_ts is None or token.end_ts is None:
                continue
            if not any(ch.isalnum() for ch in token.text):
                continue
            words.append(
                WordTiming(
                    token.text,
                    round(offset + token.start_ts, 3),
                    round(offset + token.end_ts, 3),
                )
            )
        if result.pred_dur is not None:
            steps = [float(d) for d in result.pred_dur.tolist()]
            sounds += chunk_sounds(result.phonemes, steps, offset, vocab)
        pcm += to_pcm16(result.audio.tolist())
    return Speech(pcm=bytes(pcm), sample_rate=SAMPLE_RATE, words=words, sounds=sounds)


def _load_pipeline(lang_code: str = LANG_CODE) -> Callable[..., Iterable[Any]]:
    try:
        from kokoro import KPipeline
    except ImportError as e:
        if e.name == "kokoro":
            raise VoiceError(INSTALL_HINT) from e
        # Kokoro is installed but one of its dependencies (often PyTorch) failed to load.
        logger.exception("Could not import Kokoro")
        raise VoiceError(f"Kokoro is installed but could not be loaded: {e}") from e
    pipeline: Callable[..., Iterable[Any]] = KPipeline(
        lang_code=lang_code, repo_id=REPO_ID, device="cpu"
    )
    return pipeline


class KokoroEngine:
    def __init__(self, load: Callable[[], Callable[..., Iterable[Any]]] = _load_pipeline) -> None:
        self._load = load
        self._pipeline: Callable[..., Iterable[Any]] | None = None

    def speak(self, voice: str, text: str) -> Speech:
        if not text.strip():
            raise VoiceError("no text to speak")
        pipeline = self._get_pipeline()
        start = time.perf_counter()
        try:
            vocab = getattr(getattr(pipeline, "model", None), "vocab", None)
            speech = speech_from_results(pipeline(text, voice=voice), vocab)
        except Exception as e:  # the model's own errors (unknown voice, download failure)
            raise VoiceError(f"Kokoro could not speak with voice {voice!r}: {e}") from e
        elapsed = time.perf_counter() - start
        audio_s = len(speech.pcm) / 2 / SAMPLE_RATE
        logger.info(
            "Spoke text",
            extra={
                "voice": voice,
                "chars": len(text),
                "words": len(speech.words),
                "sounds": len(speech.sounds),
                "audio_s": round(audio_s, 2),
                "duration_ms": round(elapsed * 1000, 1),
                # Below 1.0 means faster than real time.
                "real_time_factor": round(elapsed / audio_s, 2) if audio_s else None,
            },
        )
        return speech

    def _get_pipeline(self) -> Callable[..., Iterable[Any]]:
        if self._pipeline is None:
            start = time.perf_counter()
            try:
                self._pipeline = self._load()
            except VoiceError:
                raise
            except Exception as e:  # download or model load failure
                raise VoiceError(f"could not load the Kokoro model: {e}") from e
            logger.info(
                "Loaded Kokoro model",
                extra={
                    "repo_id": REPO_ID,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
        return self._pipeline


def kokoro_for(lang_code: str) -> KokoroEngine:
    """Kokoro speaking with the accent of a language code, such as "b" for British English."""
    return KokoroEngine(functools.partial(_load_pipeline, lang_code))
