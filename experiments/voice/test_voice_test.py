"""Unit tests for the R25a voice cloning test, with fake voice tools (no models needed)."""

import json
import logging
from pathlib import Path

import numpy as np
import pytest
from page import Clip, Line, build_page, summary
from run_test import CLONE, CONVERSION, KOKORO, run, write_results, write_wav
from voice_tools import (
    SAMPLE_RATE,
    converted,
    fit_length,
    pcm16_to_float,
    reference_clip,
    start_of_speech,
)

from imageskin.kokoro_engine import to_pcm16
from imageskin.visemes import SoundTiming
from imageskin.voice import Speech, WordTiming


def fake_speech(text: str) -> Speech:
    samples = np.full(SAMPLE_RATE // 2, 0.25, dtype=np.float32)  # half a second
    return Speech(
        to_pcm16(samples.tolist()),
        SAMPLE_RATE,
        [WordTiming(text.split()[0], 0.0, 0.5)],
        [SoundTiming("h", 0.0, 0.1), SoundTiming("a", 0.1, 0.5)],
    )


def test_pcm_round_trip_and_clipping() -> None:
    samples = np.array([0.0, 0.5, -0.5, 2.0, -2.0], dtype=np.float32)
    back = pcm16_to_float(to_pcm16(samples.tolist()))
    assert back == pytest.approx([0.0, 0.5, -0.5, 1.0, -1.0], abs=1e-4)


def test_fit_length_trims_and_pads() -> None:
    samples = np.arange(5, dtype=np.float32)
    assert list(fit_length(samples, 3)) == [0, 1, 2]
    assert list(fit_length(samples, 7)) == [0, 1, 2, 3, 4, 0, 0]


def test_reference_clip_skips_leading_silence() -> None:
    samples = np.concatenate([np.zeros(1000), np.full(30 * SAMPLE_RATE, 0.5)]).astype(np.float32)
    assert start_of_speech(samples) == 1000
    assert start_of_speech(np.zeros(10)) == 0
    assert len(reference_clip(samples)) == 10 * SAMPLE_RATE


def test_converted_keeps_timings_and_length() -> None:
    speech = fake_speech("Hello there")
    voiced = converted(speech, lambda s: np.full(len(s) + 99, -0.5))  # converters drift a little
    assert len(voiced.pcm) == len(speech.pcm)
    assert voiced.words == speech.words and voiced.sounds == speech.sounds
    assert pcm16_to_float(voiced.pcm)[0] == pytest.approx(-0.5, abs=1e-4)


def test_run_makes_every_voice_and_logs_timings(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rendered: list[str] = []

    def render(wav: Path, video: Path) -> None:
        assert wav.with_suffix(".json").exists()  # sound timings for the mouth
        rendered.append(wav.name)
        video.write_bytes(b"mp4")

    with caplog.at_level(logging.INFO):
        lines = run(
            ["Hello there.", "Good morning!"],
            tmp_path,
            fake_speech,
            convert=lambda s: s * 2,
            clone=lambda text: np.zeros(SAMPLE_RATE, dtype=np.float32),
            similarity=lambda path: 0.5 if "kokoro" in path.name else 0.75,
            render=render,
        )
    assert [list(line.clips) for line in lines] == [[KOKORO, CONVERSION, CLONE]] * 2
    first = lines[0].clips
    assert first[KOKORO].speech_s == 0.5 and first[CLONE].speech_s == 1.0
    assert first[CONVERSION].similarity == 0.75 and first[KOKORO].similarity == 0.5
    assert first[CONVERSION].video == "line1_conversion.mp4" and first[CLONE].video == ""
    assert rendered == [f"line{i}_{v}.wav" for i in (1, 2) for v in ("kokoro", "conversion")]
    timings = json.loads((tmp_path / "line2_conversion.json").read_text())
    assert [w["word"] for w in timings["words"]] == ["Good"]
    made = [r for r in caplog.records if r.getMessage() == "Made line"]
    assert len(made) == 6 and all(hasattr(r, "duration_ms") for r in made)


def test_run_with_kokoro_only(tmp_path: Path) -> None:
    lines = run(["Hi."], tmp_path, fake_speech)
    assert list(lines[0].clips) == [KOKORO] and lines[0].clips[KOKORO].similarity is None
    page = write_results(tmp_path, "your_recording.wav", lines)
    assert "Conversion" not in page.read_text()
    assert json.loads((tmp_path / "results.json").read_text())[0]["text"] == "Hi."


def test_write_wav_length(tmp_path: Path) -> None:
    assert write_wav(np.zeros(SAMPLE_RATE * 2, dtype=np.float32), tmp_path / "a.wav") == 2.0


def test_summary_and_page() -> None:
    lines = [
        Line("One <b>", {KOKORO: Clip("k.wav", 2, 1000, 0.1), CONVERSION: Clip("c.wav", 2, 500)}),
        Line("Two", {KOKORO: Clip("k2.wav", 2.0, 1000, 0.3, video="k2.mp4")}),
    ]
    assert summary(lines, KOKORO) == (0.5, pytest.approx(0.2))
    assert summary(lines, CONVERSION) == (0.25, None)
    assert summary(lines, CLONE) == (0.0, None)
    html = build_page("me.wav", {KOKORO: "ready-made", CONVERSION: "yours", CLONE: "cloned"}, lines)
    assert "One &lt;b&gt;" in html and 'src="k2.mp4"' in html and 'src="me.wav"' in html
    assert "not made" in html  # line 2 has no conversion
    assert "0.50 s per second of speech, mean similarity 0.20" in html
