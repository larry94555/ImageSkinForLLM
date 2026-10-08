"""Unit tests for the expressive-face experiment, on synthetic sounds and a fake library."""

import json
import logging
import sys
import wave
from pathlib import Path

import cv2
import numpy as np
import pytest
from expressive import (
    ExpressiveCompositor,
    brow_field,
    head_weight,
    jaw_field,
    openness,
    render,
)
from prosody import Motion, _f0, accents, loudness, motion, pitch

from imageskin.photoreal import Compositor
from imageskin.photoreal_library import build_library, load_library

sys.path.insert(0, str(Path(__file__).parents[2] / "tests"))
from photoreal_fakes import FakePortrait, landmarks, short_loop  # noqa: E402

__all__ = ["short_loop"]  # a fixture, used by name

RATE = 24000
FPS = 25


def tone(hz: float | np.ndarray, seconds: float, level: float = 0.3) -> np.ndarray:
    """A voice-like buzz: a fundamental with falling harmonics, at a fixed or gliding pitch."""
    n = int(seconds * RATE)
    f = np.broadcast_to(np.asarray(hz, np.float64), (n,)) if np.ndim(hz) else np.full(n, hz)
    phase = 2 * np.pi * np.cumsum(f) / RATE
    wave_ = sum(np.sin(k * phase) / k for k in range(1, 6))
    return np.asarray(level * wave_ / 2, np.float32)


def test_loudness_is_zero_in_silence_and_one_at_the_loudest() -> None:
    audio = np.concatenate([np.zeros(RATE // 2, np.float32), tone(120, 0.5)])
    loud = loudness(audio, RATE, 25, FPS)
    assert loud[:10].max() == 0.0
    assert loud[15:23].min() > 0.9


def test_loudness_of_silence_is_zero() -> None:
    assert not loudness(np.zeros(RATE, np.float32), RATE, 25, FPS).any()


def test_f0_finds_the_fundamental_not_a_harmonic() -> None:
    w = tone(120, 0.04).astype(np.float64)
    assert _f0(w, RATE) == pytest.approx(120, rel=0.03)


def test_f0_is_zero_for_noise_and_silence() -> None:
    noise = np.random.default_rng(0).normal(size=960)
    assert _f0(noise, RATE) == 0.0
    assert _f0(np.zeros(960), RATE) == 0.0


def test_pitch_rises_with_the_voice() -> None:
    glide = np.linspace(100, 160, 2 * RATE)
    audio = tone(glide, 2.0)
    pitch_st = pitch(audio, RATE, 50, FPS, np.ones(50))
    assert pitch_st[40] - pitch_st[10] > 4  # 100 to 160 Hz is about 8 semitones
    assert abs(float(np.median(pitch_st))) < 1.5


def test_pitch_is_flat_without_voice() -> None:
    assert not pitch(np.zeros(RATE, np.float32), RATE, 25, FPS, np.zeros(25)).any()


def test_accents_are_the_loudness_peaks_and_kept_apart() -> None:
    loud = np.full(100, 0.4)
    for f in (20, 24, 60):  # 20 and 24 are closer than 0.3 s: one beat
        loud[f - 2 : f + 3] = 1.0
    beats = accents(loud, FPS)
    assert [f for f, _ in beats] == [pytest.approx(22, abs=3), pytest.approx(60, abs=1)]
    assert max(s for _, s in beats) == 1.0


def test_motion_opens_wider_when_loud_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    audio = np.concatenate([tone(110, 1.0, 0.05), tone(150, 1.0, 0.6)])
    with caplog.at_level(logging.INFO):
        m = motion(audio, RATE, 50, FPS)
    assert m.jaw[40] > 5 and m.jaw[15] < 0  # loud opens wider, quiet a little less
    assert m.brow[40] > m.brow[15]  # higher pitch lifts the brows
    assert m.tilt[45] > 0
    assert "Measured voice expression" in caplog.text


def test_openness_keeps_the_lips_closed_for_m_b_p_f_v() -> None:
    assert openness({"AA": 1.0}) == pytest.approx(1.0)
    assert openness({"MBP": 1.0}) == 0.0 and openness({"FV": 1.0}) == 0.0
    assert openness({"rest": 1.0}) == 0.0
    assert 0 < openness({"AA": 0.5, "MBP": 0.5}) < 1


def test_fields_move_the_right_parts_and_fade_out_at_the_edges() -> None:
    lm = landmarks()
    jaw = jaw_field(lm, (150, 300, 360, 470))
    assert jaw[370 + 15 - 300, 256 - 150] == pytest.approx(1.0)  # below the lower lip
    assert jaw[370 - 8 - 300, 256 - 150] < 0  # the upper lip goes up
    assert not jaw[0].any() and not jaw[-1].any() and not jaw[:, 0].any()
    brow = brow_field(lm, (120, 160, 380, 300))
    assert brow[205 - 160, 256 - 120] == pytest.approx(1.0)
    assert not brow[-1].any() and not brow[:, 0].any()
    head = head_weight(lm)
    assert head[256, 256] == 1.0 and head[0, 0] == 0.0 and head[511, 0] == 0.0


def still(n: int) -> Motion:
    zero = np.zeros(n)
    return Motion(zero, zero, zero, zero)


def test_no_motion_gives_todays_face(tmp_path: Path, short_loop: object) -> None:
    build_library(tmp_path / "me.png", tmp_path / "lib", lambda _: FakePortrait())
    lib = load_library(tmp_path / "lib")
    plain, expressive = Compositor(lib), ExpressiveCompositor(lib)
    for w in ({"rest": 1.0}, {"AA": 1.0}):
        assert np.array_equal(plain.face(w, 3), expressive.expressive_face(w, 3, 1.0, still(1), 0))


def test_jaw_brows_and_nod_change_the_face(tmp_path: Path, short_loop: object) -> None:
    build_library(tmp_path / "me.png", tmp_path / "lib", lambda _: FakePortrait())
    comp = ExpressiveCompositor(load_library(tmp_path / "lib"))
    base = comp.expressive_face({"AA": 1.0}, 0, 1.0, still(1), 0)
    one = np.ones(1)
    zero = np.zeros(1)
    for m, rows in (
        (Motion(12 * one, zero, zero, zero), slice(360, 420)),  # the jaw
        (Motion(zero, 8 * one, zero, zero), slice(190, 230)),  # the brows
        (Motion(zero, zero, 6 * one, 2 * one), slice(100, 450)),  # the whole head
    ):
        moved = comp.expressive_face({"AA": 1.0}, 0, 1.0, m, 0)
        assert np.abs(moved[rows].astype(int) - base[rows]).mean() > 1
        assert np.array_equal(moved[:8], base[:8])  # the crop's edge stays put for the paste


def write_voice(wav: Path) -> None:
    audio = np.concatenate([tone(110, 0.2, 0.05), tone(150, 0.2, 0.6)])
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((audio * 32767).astype(np.int16).tobytes())
    shapes = [{"shape": "AA", "start": 0.0, "end": 0.4}]
    wav.with_suffix(".json").write_text(json.dumps({"shapes": shapes}))


def test_render_writes_the_video_and_motion(
    tmp_path: Path, short_loop: object, caplog: pytest.LogCaptureFixture
) -> None:
    build_library(tmp_path / "me.png", tmp_path / "lib", lambda _: FakePortrait())
    wav = tmp_path / "speech.wav"
    write_voice(wav)
    out = tmp_path / "after.mp4"
    with caplog.at_level(logging.INFO):
        render(load_library(tmp_path / "lib"), wav, out)
    video = cv2.VideoCapture(str(out))
    assert int(video.get(cv2.CAP_PROP_FRAME_COUNT)) == 10
    video.release()
    assert np.load(out.with_suffix(".motion.npz"))["jaw"].shape == (10,)
    assert "Rendered expressive video" in caplog.text
