import json
import logging
import wave
from pathlib import Path

import numpy as np
import pytest

from imageskin.pauses import LEAD_S, PAUSE_S, end_kind, fit_pause

RATE = 24000


def write_speech(wav: Path, before: float, voice: float, after: float) -> None:
    """A clip like Kokoro's: silence, a tone for the voice, silence; with its timings."""
    t = np.arange(round(voice * RATE)) / RATE
    tone = (np.sin(2 * np.pi * 220 * t) * 8000).astype("<i2")
    pcm = np.concatenate(
        [np.zeros(round(before * RATE), "<i2"), tone, np.zeros(round(after * RATE), "<i2")]
    )
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    end = before + voice
    timings = {
        "seconds": before + voice + after,
        "words": [{"word": "Hello", "start": before, "end": end}],
        "sounds": [],
        "shapes": [
            {"shape": "rest", "start": 0.0, "end": before},
            {"shape": "open", "start": before, "end": end},
            {"shape": "rest", "start": end, "end": end + after},
        ],
    }
    wav.with_suffix(".json").write_text(json.dumps(timings))


def length(wav: Path) -> float:
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / w.getframerate()


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("It is a fine day.", "sentence"),
        ('He said "yes!"', "sentence"),
        ("Is it?**", "sentence"),
        ("- a list item", "sentence"),
        ("## A heading", "sentence"),
        ("It is a fine day,", "clause"),
        ("first; then", "none"),
        ("as follows:", "clause"),
        ("a leader —", "clause"),
        ("where the staff can watch", "none"),
    ],
)
def test_a_clips_end_is_read_from_its_text(text: str, kind: str) -> None:
    assert end_kind(text) == kind


def test_the_silence_is_cut_to_the_pause_its_text_calls_for(tmp_path: Path) -> None:
    """R129: Kokoro starts each clip with about 315 ms of silence and ends it with about 470."""
    wav = tmp_path / "1.wav"
    write_speech(wav, 0.315, 1.0, 0.47)
    cut = fit_pause(wav, "It is a fine day.")
    assert cut is not None
    assert cut[0] == pytest.approx(0.315 - LEAD_S, abs=0.01)
    assert cut[1] == pytest.approx(0.47 - PAUSE_S["sentence"], abs=0.01)
    assert length(wav) == pytest.approx(LEAD_S + 1.0 + PAUSE_S["sentence"], abs=0.01)
    # The timings move with the speech, so the mouth still opens with the voice (R128).
    data = json.loads(wav.with_suffix(".json").read_text())
    assert data["seconds"] == pytest.approx(length(wav), abs=0.001)
    assert data["words"][0]["start"] == pytest.approx(LEAD_S, abs=0.01)
    assert [s["shape"] for s in data["shapes"]] == ["rest", "open", "rest"]
    assert data["shapes"][1]["start"] == pytest.approx(LEAD_S, abs=0.01)
    assert data["shapes"][-1]["end"] <= data["seconds"]


def test_mid_clause_there_is_no_pause_and_too_little_silence_is_padded(tmp_path: Path) -> None:
    wav = tmp_path / "1.wav"
    write_speech(wav, 0.0, 1.0, 0.4)
    assert fit_pause(wav, "where the staff can watch") is not None
    assert length(wav) == pytest.approx(1.0, abs=0.01)
    write_speech(wav, 0.02, 1.0, 0.05)  # less silence at the end than a full stop's pause
    cut = fit_pause(wav, "Done.")
    assert cut is not None and cut[0] == 0 and cut[1] < 0
    assert length(wav) == pytest.approx(0.02 + 1.0 + PAUSE_S["sentence"], abs=0.01)


def test_speech_without_timings_or_voice_is_left_as_it_is(tmp_path: Path) -> None:
    text = tmp_path / "text.wav"
    text.write_text("Hello.")  # an engine that keeps the text in the voice step
    assert fit_pause(text, "Hello.") is None
    silent = tmp_path / "silent.wav"
    write_speech(silent, 0.5, 0.0, 0.5)
    before = silent.read_bytes()
    assert fit_pause(silent, "Hello.") is None
    assert silent.read_bytes() == before


def test_a_clip_whose_pause_cant_be_fitted_is_still_made(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from imageskin.prepare_job import ClipSteps
    from imageskin.reply_video import ReplyVideos, VoiceReady

    def speak(text: str, wav: Path) -> None:
        wav.write_bytes(b"not a wav")
        wav.with_suffix(".json").write_text("{}")

    def render(photo: Path, wav: Path, output: Path) -> None:
        output.write_bytes(b"clip")

    videos = ReplyVideos(
        tmp_path, lambda *a: None, VoiceReady(lambda: None, lambda: "v"), ClipSteps(speak, render)
    )
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    caplog.set_level(logging.INFO)
    clips("Hello there.")
    clips.close()
    clips.wait(10)
    assert clips.done and clips.error is None and clips.rendered == 1
    assert "Could not fit a clip's pause" in caplog.messages
