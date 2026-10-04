import json
import wave
from pathlib import Path

import pytest

from imageskin.voice import Speech, WordTiming, write_speech


def test_write_speech_writes_wav_and_timings(tmp_path: Path) -> None:
    speech = Speech(pcm=b"\x00\x00" * 24000, sample_rate=24000, words=[WordTiming("Hi", 0, 0.4)])
    seconds = write_speech(speech, tmp_path / "s.wav", tmp_path / "s.json")
    assert seconds == pytest.approx(1.0)
    with wave.open(str(tmp_path / "s.wav"), "rb") as w:
        assert (w.getnchannels(), w.getframerate(), w.getnframes()) == (1, 24000, 24000)
    data = json.loads((tmp_path / "s.json").read_text())
    assert data == {"seconds": 1.0, "words": [{"word": "Hi", "start": 0, "end": 0.4}]}
