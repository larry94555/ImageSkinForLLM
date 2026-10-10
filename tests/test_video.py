from __future__ import annotations

import math
import shutil
import wave
from array import array
from pathlib import Path

import pytest

from imageskin.video import VideoError, mouth_openness, read_pcm16, write_mp4


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


def test_mouth_eases_open_over_several_frames() -> None:
    openness = mouth_openness(array("h", [0] * 24000) + tone(1, 10000), 24000)
    between = [o for o in openness[15:35] if 0.05 < o < 0.95]
    assert len(between) >= 3  # not a jump from closed to open
    assert openness == sorted(openness)  # and it never shuts again on the way up


def ffmpeg_cmd(monkeypatch: pytest.MonkeyPatch, output: Path, **kwargs: object) -> list[str]:
    """The ffmpeg command write_mp4 runs for two frames, without running it."""
    import subprocess

    cmds: list[list[str]] = []

    class Done:
        stdin = __import__("io").BytesIO()
        returncode = 0

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            return b"", b""

    def popen(cmd: list[str], **_: object) -> Done:
        cmds.append(cmd)
        return Done()

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr("imageskin.video.find_ffmpeg", lambda: "ffmpeg")
    write_mp4([b"\0" * 12] * 2, (2, 2), None, output, 10, **kwargs)  # type: ignore[arg-type]
    return cmds[0]


def test_an_mp4_is_written_whole_with_its_index_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cmd = ffmpeg_cmd(monkeypatch, tmp_path / "a.mp4")
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert "-frag_duration" not in cmd and "zerolatency" not in cmd


def test_a_progressive_mp4_is_fragmented_and_flushed_as_it_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cmd = ffmpeg_cmd(monkeypatch, tmp_path / "a.mp4", progressive=True)
    assert cmd[cmd.index("-movflags") + 1] == "frag_keyframe+empty_moov+default_base_moof"
    assert cmd[cmd.index("-frag_duration") + 1] == "500000"
    assert cmd[cmd.index("-flush_packets") + 1] == "1"
    assert cmd[cmd.index("-tune") + 1] == "zerolatency"
    assert "+faststart" not in cmd


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_a_progressive_mp4_can_be_played_from_its_start(tmp_path: Path) -> None:
    # A whole MP4 keeps its index (moov) at the front and one mdat; a progressive one has an
    # empty moov then a movie fragment (moof) per half second, each playable as it lands.
    frames = [bytes([i, 0, 0]) * 16 * 16 for i in range(0, 250, 5)]  # 2 s of a changing frame
    whole, progressive = tmp_path / "whole.mp4", tmp_path / "progressive.mp4"
    write_mp4(frames, (16, 16), None, whole, 30)
    write_mp4(frames, (16, 16), None, progressive, 30, progressive=True)
    assert whole.read_bytes().count(b"moof") == 0
    data = progressive.read_bytes()
    assert data.index(b"moov") < data.index(b"moof") < data.index(b"mdat")
    assert data.count(b"moof") >= 3  # 2 s in fragments of at most half a second
