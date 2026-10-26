"""Unit tests for the R127 mouth lead experiment, with made-up speech (no models)."""

import json
import logging
import shutil
from pathlib import Path

import numpy as np
import pytest
from mouth_lead import (
    CLIPS,
    FPS,
    MARKS_S,
    BrowserClip,
    ClipResult,
    Onset,
    audio_delay_ms,
    browser_clips,
    browser_markdown,
    browser_table,
    first_sound,
    frame_times,
    level_db,
    markdown,
    measure_clip,
    mouth_opens,
    sync_media,
    total_ms,
    video_shift_ms,
    voice_onsets,
    word_near,
    write_results,
)

from imageskin.visemes import SoundTiming
from imageskin.voice import Speech, WordTiming

RATE = 24000
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def tone(seconds: float, start: float, end: float, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return np.where((t >= start) & (t < end), amp * np.sin(2 * np.pi * 220 * t), 0.0)


def speech(seconds: float, voiced: list[tuple[float, float]], sounds: list[SoundTiming]) -> Speech:
    audio = sum(tone(seconds, a, b) for a, b in voiced)
    pcm = (np.asarray(audio) * 32767).astype("<i2").tobytes()
    words = [WordTiming(f"w{i}", a, b) for i, (a, b) in enumerate(voiced)]
    return Speech(pcm, RATE, words, sounds)


def test_level_is_measured_against_the_loud_part() -> None:
    db = level_db(tone(1.0, 0.5, 1.0), RATE)
    assert len(db) == 200
    assert db[-1] == pytest.approx(0.0, abs=1.0)
    assert db[0] < -100
    assert len(level_db(np.zeros(10), RATE)) == 0


def test_voice_onsets_are_the_start_and_each_start_after_a_pause() -> None:
    audio = tone(2.0, 0.3, 0.8) + tone(2.0, 0.85, 1.0) + tone(2.0, 1.4, 1.8)
    onsets = voice_onsets(audio, RATE)
    # The 50 ms gap is too short to count; the 400 ms one counts.
    assert onsets == [(0.0, 0.3), (1.0, 1.4)]


def test_mouth_opens_on_the_first_open_frame_after_a_closed_one() -> None:
    track = [0.0] * 5 + [0.05, 0.2, 0.5] + [0.0] * 4
    assert mouth_opens(track, FPS, 0.0, 0.3) == pytest.approx(6 / FPS)
    # It must have closed in the pause: open from the start, it never "opens".
    assert mouth_opens([0.5] * 20, FPS, 0.0, 0.2) is None


def test_first_sound_is_the_one_nearest_the_voice_after_the_pause() -> None:
    sounds = [
        SoundTiming("ɪ", 0.9, 1.05),  # the word before, running into the pause
        SoundTiming(",", 1.05, 1.35),
        SoundTiming("h", 1.35, 1.4),
        SoundTiming("ɛ", 1.4, 1.5),
    ]
    s = first_sound(sounds, 1.0, 1.36)
    assert s is not None and s.sound == "h"
    assert first_sound(sounds[:2], 1.0, 1.3) is None


def test_word_near_picks_the_closest_start() -> None:
    words = [WordTiming("one", 0.1, 0.4), WordTiming("two", 0.6, 0.9)]
    assert word_near(words, 0.55) == "two"
    assert word_near([], 0.5) == ""


def test_onset_splits_its_lead_into_timings_and_frames() -> None:
    o = Onset("hi", heard=0.30, sound=0.35, opens=0.24)
    assert o.lead_ms == 60
    assert o.timings_ms == -50  # the timings start the sound after it is heard
    assert o.frames_ms == 110  # the frames open the mouth before the sound's start
    assert Onset("hi", 0.3, None, None).lead_ms is None
    assert Onset("hi", 0.3, None, 0.2).frames_ms is None
    assert total_ms(o, 40.0) == 100
    assert total_ms(Onset("hi", 0.3, None, None), 40.0) is None


def test_audio_delay_finds_a_shift_either_way() -> None:
    ref = tone(1.0, 0.2, 0.25) + tone(1.0, 0.5, 0.6, 0.3)
    later = np.concatenate([np.zeros(int(0.043 * RATE)), ref])
    earlier = ref[int(0.02 * RATE) :]
    assert audio_delay_ms(ref, later, RATE) == pytest.approx(43, abs=0.5)
    assert audio_delay_ms(ref, earlier, RATE) == pytest.approx(-20, abs=0.5)


def test_video_shift_skips_the_first_frame() -> None:
    assert video_shift_ms([0.0, 0.04, 0.08]) == 0.0
    assert video_shift_ms([0.0, 0.0827, 0.1227, 0.1627]) == pytest.approx(42.7)
    assert video_shift_ms([0.0]) == 0.0


def test_measure_clip_finds_the_lead_at_the_start(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sounds = [SoundTiming(".", 0.0, 0.4), SoundTiming("ɑ", 0.4, 0.9), SoundTiming(".", 0.9, 1.2)]
    made = speech(1.2, [(0.4, 0.9)], sounds)
    with caplog.at_level(logging.INFO, logger="mouth_lead"):
        r = measure_clip("reply 1", "ah", lambda text: made, tmp_path, mp4=False)
    assert r.seconds == 1.2
    assert r.start is not None
    assert r.start.heard == pytest.approx(0.4, abs=0.006)
    assert r.start.sound == 0.4
    # Since R128 the mouth opens on the first frame that starts with the voice, not before it.
    assert r.start.opens == pytest.approx(0.4)
    assert r.start.lead_ms is not None and -40 < r.start.lead_ms <= 0
    assert "Measured clip" in caplog.text


def test_measure_clip_compares_the_aligner(tmp_path: Path) -> None:
    sounds = [SoundTiming(".", 0.0, 0.4), SoundTiming("ɑ", 0.4, 0.9)]
    made = speech(1.0, [(0.4, 0.9)], sounds)

    def align(samples: np.ndarray, rate: int, text: str) -> list[WordTiming]:
        return [WordTiming("w0", 0.47, 0.9)]

    r = measure_clip("goodbye", "ah", lambda text: made, tmp_path, align=align, mp4=False)
    assert r.aligner_ms == [("w0", 70)]


def test_aligner_words_are_paired_by_their_letters(tmp_path: Path) -> None:
    sounds = [SoundTiming(".", 0.0, 0.2), SoundTiming("ɑ", 0.2, 0.9)]
    made = speech(1.0, [(0.2, 0.5), (0.55, 0.9)], sounds)  # words w0 and w1

    def align(samples: np.ndarray, rate: int, text: str) -> list[WordTiming]:
        return [WordTiming("x", 0.1, 0.2), WordTiming("W1", 0.6, 0.9)]

    r = measure_clip("goodbye", "ah", lambda text: made, tmp_path, align=align, mp4=False)
    assert r.aligner_ms == [("w1", 50)]


@needs_ffmpeg
def test_measure_clip_measures_the_mp4s(tmp_path: Path) -> None:
    sounds = [SoundTiming(".", 0.0, 0.3), SoundTiming("ɑ", 0.3, 0.8), SoundTiming(".", 0.8, 1.0)]
    made = speech(1.0, [(0.3, 0.8)], sounds)
    r = measure_clip("reply 1", "ah", lambda text: made, tmp_path)
    # In both kinds of MP4 the sound stays with the picture (the AAC encoder's delay moves both).
    assert r.whole_mp4_ms is not None and abs(r.whole_mp4_ms) < 5
    assert r.progressive_mp4_ms is not None and abs(r.progressive_mp4_ms) < 5


@needs_ffmpeg
def test_sync_media_writes_the_browser_test(tmp_path: Path) -> None:
    paths = sync_media(tmp_path)
    assert [p.name for p in paths] == ["marks-whole.mp4", "marks-progressive.mp4", "idle.mp4"]
    whites = json.loads((tmp_path / "marks.json").read_text())
    assert whites["marks-whole.mp4"] == pytest.approx(list(MARKS_S))
    assert len(frame_times(paths[0])) == 75


def results() -> list[ClipResult]:
    return [
        ClipResult(
            "reply 1",
            "Hi.",
            1.0,
            [Onset("Hi", 0.3, 0.35, 0.2), Onset("there", 1.0, 1.02, 0.98)],
            0.0,
            0.0,
            [("Hi", 50)],
        ),
        ClipResult("goodbye", "Bye.", 1.0, [Onset("Bye", 0.3, 0.3, None)], 0.0, 0.0),
        ClipResult("sample", "", 0.0, []),
    ]


def test_markdown_has_each_table_and_counts_leads_over_the_limit() -> None:
    md = markdown("af_heart", results())
    assert "| reply 1 | 0.300 s | 0.2 s | 100 ms | -50 ms | 150 ms | 0 ms | 0 ms | 100 ms |" in md
    assert "| goodbye | 0.300 s | – s | – ms |" in md
    assert "| sample | no voice |" in md
    assert "| reply 1 | there | 1.000 s | 0.98 s | 20 ms |" in md
    assert "1 words: the aligner's start is +50 ms" in md
    assert "Leads over 80 ms in the file: 1 of 3." in md


def test_write_results_writes_markdown_and_json(tmp_path: Path) -> None:
    md = write_results(tmp_path, "/x/donor.wav", results())
    assert md.name == "mouth-lead-donor.md"
    data = json.loads(md.with_suffix(".json").read_text())
    assert data[0]["onsets"][0]["lead_ms"] == 100
    assert data[0]["aligner_ms"] == [["Hi", 50]]


def test_clips_cover_replies_the_fixed_lines_and_the_sample() -> None:
    names = [n for n, _ in CLIPS]
    assert names[:3] == ["reply 1", "reply 2", "reply 3"]
    assert {"goodbye", "welcome back", "sample"} <= set(names)


def browser_raw() -> dict:
    """Two clips: the first fades in after it plays; the second is shown before it plays."""
    frames = [{"clip": 0, "media": 0.0, "shown": 500.0}]  # loaded out of sight, before playing
    frames += [{"clip": 0, "media": t / 1000, "shown": 1000.0 + t} for t in (0, 40, 600, 640)]
    frames += [{"clip": 1, "media": t / 1000, "shown": 4100.0 + t} for t in (0, 40, 600)]
    return {
        "clips": ["a.mp4", "b.mp4"],
        "frames": frames,
        # First sound 30 ms after the first frame in clip 1; in clip 2, 90 ms after it was shown.
        "sounds": [
            {"clip": 0, "played": 1030.0},
            {"clip": 0, "played": 1640.0},
            {"clip": 1, "played": 4140.0},
            {"clip": 1, "played": 4740.0},
        ],
        "playing": [{"clip": 0, "at": 995.0}, {"clip": 1, "at": 4095.0}],
        "shown": [{"clip": 1, "at": 4050.0}],
        "visible": [{"clip": 0, "at": 1100.0}, {"clip": 1, "at": 4050.0}],
        "browser": "Chromium 1",
        "latency": 0.042,
    }


WHITES = {"a.mp4": [0.0, 0.6], "b.mp4": [0.0, 0.6]}


def test_browser_clips_measures_the_switch_and_each_mark() -> None:
    a, b = browser_clips(browser_raw(), WHITES)
    # The frame shown before clip 1 played is out of sight and doesn't count.
    assert a == BrowserClip(1, "a.mp4", 30, -70, [30, 40])
    # Clip 2's player was shown before its first frame came: that is its first picture.
    assert b == BrowserClip(2, "b.mp4", 90, 90, [40, 40])


def test_browser_clips_keep_the_switch_apart_from_later_marks() -> None:
    raw = browser_raw()
    raw["sounds"] = [s for s in raw["sounds"] if s["played"] != 1640.0]  # a beep not heard
    a, _ = browser_clips(raw, WHITES)
    assert a.first_picture_ms == 30
    assert a.marks_ms == [30, None]


def test_browser_clips_without_frames_or_sounds() -> None:
    raw = browser_raw()
    raw["frames"] = [f for f in raw["frames"] if f["clip"] == 0]
    raw["sounds"] = [s for s in raw["sounds"] if s["clip"] == 1]
    a, b = browser_clips(raw, WHITES)
    assert (a.first_picture_ms, a.half_visible_ms, a.marks_ms) == (None, None, [None, None])
    assert (b.first_picture_ms, b.marks_ms) == (None, [])


def test_browser_table_writes_markdown(tmp_path: Path) -> None:
    (tmp_path / "browser-raw.json").write_text(json.dumps(browser_raw()))
    (tmp_path / "marks.json").write_text(json.dumps(WHITES))
    md = browser_table(tmp_path).read_text()
    assert "Chromium 1; Web Audio's output delay 42 ms" in md
    assert "| 1 (a.mp4) | idle video to the reply | 30 ms | -70 ms | 30 ms | 40 ms |" in md
    assert "| 2 (b.mp4) | from the clip before | 90 ms | 90 ms |" in md
    assert "| 1 (" not in browser_markdown(browser_raw(), [])
