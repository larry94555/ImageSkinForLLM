"""Voice engine interface: speak text and report when each word is said."""

import json
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


class VoiceError(Exception):
    """Text could not be spoken."""


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
    def speak(self, voice: str, text: str) -> Speech:
        """Speak text in the named voice; return the audio and when each word is said."""
        ...


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
