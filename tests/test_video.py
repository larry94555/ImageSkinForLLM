from __future__ import annotations

import math
import wave
from array import array
from pathlib import Path

import pytest

from imageskin.video import VideoError, mouth_openness, read_pcm16


def tone(seconds: float, amplitude: int, rate: int = 24000) -> array[int]:
    return array("h", (round(amplitude * math.sin(i / 10)) for i in range(int(seconds * rate))))


def test_silence_keeps_the_mouth_closed() -> None:
    assert mouth_openness(array("h", [0] * 24000), 24000) == [0.0] * 25


def test_empty_audio_has_no_frames() -> None:
    assert mouth_openness(array("h"), 24000) == []


def test_loud_speech_opens_and_pauses_close_the_mouth() -> None:
    samples = tone(1, 10000) + array("h", [0] * 24000) + tone(1, 10000)
    openness = mouth_openness(samples, 24000)
    assert len(openness) == 75
    assert openness[10] == pytest.approx(1.0, abs=0.02)
    assert openness[37] == 0.0
    assert openness[60] == pytest.approx(1.0, abs=0.02)
    # Smoothing: the frame next to a pause is partly open.
    assert 0 < openness[25] < 1


def test_quieter_speech_opens_the_mouth_less() -> None:
    openness = mouth_openness(tone(1, 10000) + tone(1, 5000), 24000)
    assert openness[10] == pytest.approx(1.0, abs=0.02)
    assert 0.3 < openness[40] < 0.6


def test_last_partial_frame_is_counted() -> None:
    assert len(mouth_openness(tone(0.5, 10000), 24000)) == 13  # 12.5 frames at 25 fps


def write_wav(path: Path, channels: int = 1, frames: int = 2400) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x01\x00" * frames * channels)


def test_read_pcm16(tmp_path: Path) -> None:
    write_wav(tmp_path / "a.wav")
    samples, rate = read_pcm16(tmp_path / "a.wav")
    assert (len(samples), rate, samples[0]) == (2400, 24000, 1)


def test_read_pcm16_rejects_stereo(tmp_path: Path) -> None:
    write_wav(tmp_path / "a.wav", channels=2)
    with pytest.raises(VideoError, match="mono 16-bit"):
        read_pcm16(tmp_path / "a.wav")


def test_read_pcm16_missing_file(tmp_path: Path) -> None:
    with pytest.raises(VideoError, match="could not read"):
        read_pcm16(tmp_path / "missing.wav")
