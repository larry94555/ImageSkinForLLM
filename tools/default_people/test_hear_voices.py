"""Unit tests for the R24e listening page, with a fake voice (nothing downloaded)."""

import logging
import shutil
from pathlib import Path

import numpy as np
import pytest
from hear_voices import build_page, every_voice, file_name, median_pitch, say_each, to_mp3

from imageskin.default_people import people, voice_of

RATE = 24000


def tone(hz: float, seconds: float = 1.0, loud: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return (loud * np.sin(2 * np.pi * hz * t)).astype(np.float32)


@pytest.mark.parametrize("hz", [100.0, 150.0, 210.0])
def test_the_pitch_of_a_tone_is_found(hz: float) -> None:
    assert median_pitch(tone(hz), RATE) == pytest.approx(hz, rel=0.02)


def test_silence_and_noise_have_no_pitch() -> None:
    assert median_pitch(np.zeros(RATE, np.float32), RATE) == 0.0
    noise = np.random.default_rng(1).normal(0, 0.3, RATE).astype(np.float32)
    assert median_pitch(noise, RATE) == 0.0


def test_every_voice_is_said_once_and_measured(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    said, written = [], []

    def speak(lang: str, voice: str) -> tuple[np.ndarray, int]:
        said.append((lang, voice))
        return tone(200.0 if voice.startswith(("af", "bf")) else 120.0), RATE

    def write(samples: np.ndarray, rate: int, output: Path) -> None:
        written.append(output.name)

    with caplog.at_level(logging.INFO):
        pitches = say_each(speak, tmp_path, write)
    assert said == every_voice() and len(said) == len(set(said))
    assert written == [file_name(v) for _, v in said]
    assert pitches["af_heart"] == pytest.approx(200, rel=0.02)
    assert pitches["bm_lewis"] == pytest.approx(120, rel=0.02)
    assert sum(r.getMessage() == "Voice said" for r in caplog.records) == len(said)


def test_a_voice_that_cant_be_said_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def speak(lang: str, voice: str) -> tuple[np.ndarray, int]:
        raise RuntimeError("no such voice")

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        say_each(speak, tmp_path, lambda *a: None)
    record = next(r for r in caplog.records if r.getMessage() == "Could not say the line")
    assert vars(record)["voice"] == every_voice()[0][1]


def test_the_page_shows_every_face_with_both_voices() -> None:
    pitches = {v: 150.0 for _, v in every_voice()}
    page = build_page(pitches)
    for p in people():
        assert f'src="faces/{p.name}.jpg"' in page
        for accent in ("American", "British"):
            assert f'src="{file_name(voice_of(p.name, accent)[1])}"' in page
    assert page.count("<audio") == 2 * len(people())
    assert "American woman, younger 1" in page and "150 Hz" in page


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_an_mp3_is_written(tmp_path: Path) -> None:
    to_mp3(tone(150.0, 0.5), RATE, tmp_path / "a.mp3")
    assert (tmp_path / "a.mp3").stat().st_size > 1000
