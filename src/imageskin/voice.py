"""Voice engine interface: clone a voice from a sample, then speak text with word timings."""

import hashlib
import json
import logging
import wave
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class VoiceError(Exception):
    """A voice could not be cloned, or text could not be spoken."""


@dataclass(frozen=True)
class WordTiming:
    word: str
    start: float  # seconds from the start of the audio
    end: float


@dataclass(frozen=True)
class Speech:
    pcm: bytes  # 16-bit mono little-endian samples
    sample_rate: int
    words: list[WordTiming]


class VoiceEngine(Protocol):
    name: str

    def clone(self, sample: Path) -> str:
        """Create a voice from a WAV sample and return its id."""
        ...

    def speak(self, voice_id: str, text: str) -> Speech:
        """Speak text in the voice; return the audio and when each word is said."""
        ...


def words_from_characters(
    chars: Sequence[str], starts: Sequence[float], ends: Sequence[float]
) -> list[WordTiming]:
    """Group per-character timings into words, splitting on whitespace."""
    words: list[WordTiming] = []
    word, start, end = "", 0.0, 0.0
    for ch, s, e in zip(chars, starts, ends, strict=True):
        if ch.isspace():
            if word:
                words.append(WordTiming(word, start, end))
            word = ""
            continue
        if not word:
            start = s
        word += ch
        end = e
    if word:
        words.append(WordTiming(word, start, end))
    return words


def write_speech(speech: Speech, wav_path: Path, timings_path: Path) -> float:
    """Write the audio as WAV and the word timings as JSON; return the length in seconds."""
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(speech.sample_rate)
        w.writeframes(speech.pcm)
    seconds = len(speech.pcm) / 2 / speech.sample_rate
    data = {"seconds": round(seconds, 3), "words": [asdict(w) for w in speech.words]}
    timings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return seconds


def voice_for_sample(engine: VoiceEngine, sample: Path) -> str:
    """Return the voice id for a sample, cloning only when the sample is new or has changed.

    The id is kept next to the sample in `<sample>.<engine>.json`, so repeated runs reuse one
    cloned voice instead of creating a new one each time.
    """
    try:
        digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    except OSError as e:
        raise VoiceError(f"could not read voice sample {sample}: {e}") from e
    cache = sample.with_name(f"{sample.name}.{engine.name}.json")
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("sha256") == digest and isinstance(cached.get("voice_id"), str):
            logger.info("Reusing cloned voice", extra={"voice_id": cached["voice_id"]})
            return str(cached["voice_id"])
    except (OSError, ValueError, AttributeError):
        pass  # no usable cache: clone below
    voice_id = engine.clone(sample)
    cache.write_text(json.dumps({"sha256": digest, "voice_id": voice_id}) + "\n", encoding="utf-8")
    return voice_id
