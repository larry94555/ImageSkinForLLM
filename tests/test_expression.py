"""Unit tests for the voice-driven expression, on synthetic sounds and a fake library."""

import logging
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from photoreal_fakes import FakePortrait, landmarks, short_loop

from imageskin.expression import (
    STILL,
    FrameMotion,
    Gains,
    Motion,
    _f0,
    accents,
    brow_field,
    head_weight,
    jaw_field,
    loudness,
    motion,
    openness,
    pitch,
    sway,
)
from imageskin.photoreal import Compositor
from imageskin.photoreal_library import build_library, load_library

__all__ = ["short_loop"]  # a fixture, used by name

RATE = 24000
FPS = 25


def tone(
    hz: float | NDArray[np.float64], seconds: float, level: float = 0.3
) -> NDArray[np.float32]:
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


def test_head_nods_gently_and_only_on_the_strongest_beats() -> None:
    beats = np.concatenate([tone(150, 0.12, 0.6 if k % 2 else 0.1) for k in range(40)])  # 4.8 s
    m = motion(beats, RATE, 120, FPS, Gains(lift_px=0.0))
    every_beat = len(accents(loudness(beats, RATE, 120, FPS), FPS))
    dips = int((np.diff(np.sign(np.diff(m.nod))) < 0).sum())  # turning points of the head
    assert dips <= every_beat // 3
    assert m.nod.max() <= 2.5 + 1e-6 and m.nod.min() >= -1e-6


def test_sway_is_slow_bounded_and_seeded() -> None:
    loud = np.ones(250)
    a, b = sway(loud, FPS, 1), sway(loud, FPS, 2)
    assert np.abs(a).max() <= 1.0 and np.abs(a).max() > 0.5
    assert np.abs(np.diff(a)).max() < 0.1  # no jumps between frames
    assert np.array_equal(a, sway(loud, FPS, 1)) and not np.array_equal(a, b)
    assert np.abs(sway(np.zeros(250), FPS, 1)).max() < np.abs(a).max()  # calmer in pauses


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


def test_motion_at_a_frame() -> None:
    track = np.arange(3, dtype=np.float64)
    m = Motion(track, 2 * track, 3 * track, 4 * track, 5 * track)
    assert m.at(1) == FrameMotion(1.0, 2.0, 3.0, 4.0, 5.0)


def test_still_gives_the_face_without_expression(tmp_path: Path, short_loop: object) -> None:
    build_library(tmp_path / "me.png", tmp_path / "lib", lambda _: FakePortrait())
    comp = Compositor(load_library(tmp_path / "lib"))
    for w in ({"rest": 1.0}, {"AA": 1.0}):
        assert np.array_equal(comp.face(w, 3), comp.face(w, 3, 1.0, FrameMotion(0.01, 0.01)))


def test_jaw_brows_and_head_move_the_face(tmp_path: Path, short_loop: object) -> None:
    build_library(tmp_path / "me.png", tmp_path / "lib", lambda _: FakePortrait())
    comp = Compositor(load_library(tmp_path / "lib"))
    base = comp.face({"AA": 1.0}, 0, 1.0, STILL)
    for move, rows in (
        (FrameMotion(jaw=12), slice(360, 420)),
        (FrameMotion(brow=8), slice(190, 230)),
        (FrameMotion(nod=6, tilt=2), slice(100, 450)),
        (FrameMotion(sway=4), slice(100, 450)),
    ):
        moved = comp.face({"AA": 1.0}, 0, 1.0, move)
        assert np.abs(moved[rows].astype(int) - base[rows]).mean() > 1
        assert np.array_equal(moved[:8], base[:8])  # the crop's edge stays put for the paste


def test_jaw_leaves_closed_lips_alone(tmp_path: Path, short_loop: object) -> None:
    build_library(tmp_path / "me.png", tmp_path / "lib", lambda _: FakePortrait())
    comp = Compositor(load_library(tmp_path / "lib"))
    closed = comp.face({"MBP": 1.0}, 0)
    assert np.array_equal(closed, comp.face({"MBP": 1.0}, 0, 1.0, FrameMotion(jaw=12)))
