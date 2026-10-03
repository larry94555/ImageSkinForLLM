import json
import wave
from pathlib import Path

import pytest

from imageskin.voice import (
    Speech,
    VoiceError,
    WordTiming,
    voice_for_sample,
    words_from_characters,
    write_speech,
)


class FakeEngine:
    name = "fake"

    def __init__(self) -> None:
        self.clones = 0

    def clone(self, sample: Path) -> str:
        self.clones += 1
        return f"voice-{self.clones}"

    def speak(self, voice_id: str, text: str) -> Speech:
        raise NotImplementedError


def test_words_from_characters_groups_on_whitespace() -> None:
    chars = list(" Hi  you.")
    starts = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    ends = [s + 0.1 for s in starts]
    words = words_from_characters(chars, starts, ends)
    got = [(w.word, w.start, round(w.end, 6)) for w in words]
    assert got == [("Hi", 0.1, 0.3), ("you.", 0.5, 0.9)]


def test_words_from_characters_empty() -> None:
    assert words_from_characters([], [], []) == []


def test_write_speech_writes_wav_and_timings(tmp_path: Path) -> None:
    speech = Speech(pcm=b"\x00\x00" * 24000, sample_rate=24000, words=[WordTiming("Hi", 0, 0.4)])
    seconds = write_speech(speech, tmp_path / "s.wav", tmp_path / "s.json")
    assert seconds == pytest.approx(1.0)
    with wave.open(str(tmp_path / "s.wav"), "rb") as w:
        assert (w.getnchannels(), w.getframerate(), w.getnframes()) == (1, 24000, 24000)
    data = json.loads((tmp_path / "s.json").read_text())
    assert data == {"seconds": 1.0, "words": [{"word": "Hi", "start": 0, "end": 0.4}]}


def test_voice_for_sample_reuses_clone_until_sample_changes(tmp_path: Path) -> None:
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"one")
    engine = FakeEngine()
    assert voice_for_sample(engine, sample) == "voice-1"
    assert voice_for_sample(engine, sample) == "voice-1"
    assert (tmp_path / "sample.wav.fake.json").is_file()
    sample.write_bytes(b"two")
    assert voice_for_sample(engine, sample) == "voice-2"
    assert engine.clones == 2


def test_voice_for_sample_ignores_broken_cache(tmp_path: Path) -> None:
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"one")
    (tmp_path / "sample.wav.fake.json").write_text("not json")
    assert voice_for_sample(FakeEngine(), sample) == "voice-1"


def test_voice_for_sample_missing_sample(tmp_path: Path) -> None:
    with pytest.raises(VoiceError, match="could not read voice sample"):
        voice_for_sample(FakeEngine(), tmp_path / "missing.wav")
