import shutil
import subprocess
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from imageskin.audio import (
    CHANNELS,
    SAMPLE_RATE,
    AudioError,
    join_wavs,
    make_voice_sample,
    to_wav,
)

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def write_wav(path: Path, seconds: float, rate: int = SAMPLE_RATE) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return path


def make_tone(path: Path, seconds: float) -> Path:
    """Write a test tone in the format implied by the file's suffix, using real ffmpeg."""
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi"]
    cmd += ["-i", f"sine=frequency=440:duration={seconds}", "-ac", "2", "-ar", "44100", str(path)]
    subprocess.run(cmd, check=True)
    return path


def test_join_wavs_concatenates_in_order(tmp_path: Path) -> None:
    parts = [write_wav(tmp_path / "a.wav", 1.0), write_wav(tmp_path / "b.wav", 0.5)]
    seconds = join_wavs(parts, tmp_path / "out.wav")
    assert seconds == pytest.approx(1.5)
    with wave.open(str(tmp_path / "out.wav"), "rb") as w:
        assert w.getnframes() == int(1.5 * SAMPLE_RATE)


def test_join_wavs_rejects_mixed_formats(tmp_path: Path) -> None:
    parts = [write_wav(tmp_path / "a.wav", 0.1), write_wav(tmp_path / "b.wav", 0.1, rate=16000)]
    with pytest.raises(AudioError, match="format differs"):
        join_wavs(parts, tmp_path / "out.wav")


def test_join_wavs_needs_parts(tmp_path: Path) -> None:
    with pytest.raises(AudioError, match="no recordings"):
        join_wavs([], tmp_path / "out.wav")


def test_to_wav_rejects_unsupported_type(tmp_path: Path) -> None:
    with pytest.raises(AudioError, match="unsupported file type"):
        to_wav(tmp_path / "notes.txt", tmp_path / "out.wav")


def test_to_wav_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AudioError, match="file not found"):
        to_wav(tmp_path / "missing.m4a", tmp_path / "out.wav")


def test_to_wav_reports_missing_ffmpeg(tmp_path: Path) -> None:
    src = write_wav(tmp_path / "a.wav", 0.1)
    with patch("shutil.which", return_value=None), pytest.raises(AudioError, match="ffmpeg not"):
        to_wav(src, tmp_path / "out.wav")


def test_to_wav_reports_timeout(tmp_path: Path) -> None:
    src = write_wav(tmp_path / "a.wav", 0.1)
    with (
        patch("shutil.which", return_value="ffmpeg"),
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 2)),
        pytest.raises(AudioError, match="longer than 2 seconds"),
    ):
        to_wav(src, tmp_path / "out.wav", timeout_s=2)


@needs_ffmpeg
def test_to_wav_reports_ffmpeg_error(tmp_path: Path) -> None:
    src = tmp_path / "broken.m4a"
    src.write_bytes(b"not audio")
    with pytest.raises(AudioError, match="ffmpeg could not convert it"):
        to_wav(src, tmp_path / "out.wav")


@needs_ffmpeg
def test_make_voice_sample_from_m4a_mp3_and_wav(tmp_path: Path) -> None:
    recordings = [
        make_tone(tmp_path / "one.m4a", 1.0),
        make_tone(tmp_path / "two.mp3", 1.0),
        make_tone(tmp_path / "three.wav", 0.5),
    ]
    out = tmp_path / "sample.wav"
    seconds = make_voice_sample(recordings, out)
    # M4A and MP3 encoders pad a few milliseconds, so allow a small difference.
    assert seconds == pytest.approx(2.5, abs=0.1)
    with wave.open(str(out), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, SAMPLE_RATE)


@needs_ffmpeg
def test_make_voice_sample_reports_unwritable_output(tmp_path: Path) -> None:
    src = make_tone(tmp_path / "one.wav", 0.2)
    with pytest.raises(AudioError, match="could not write"):
        make_voice_sample([src], tmp_path / "no-such-dir" / "sample.wav")
