"""Unit tests for the cheeks and face that move with the mouth (roadmap R128a)."""

import logging
from pathlib import Path

import numpy as np
import pytest
from photoreal_fakes import MOUTH, FakePortrait, landmarks, photo_file, short_loop, write_speech

from imageskin.cheeks import (
    MAX_PX,
    STRENGTHS,
    CheekGains,
    fields,
    limit,
    log_added,
    strength_of,
    tracks,
)
from imageskin.expression import STILL, FrameMotion
from imageskin.photoreal import Compositor, PhotorealEngine
from imageskin.photoreal_library import CROP, build_library, load_library

__all__ = ["short_loop"]  # a fixture, used by name

FPS = 25


def word(shape: str, n: int = 50, start: int = 15, length: int = 10) -> list[dict[str, float]]:
    """`n` frames at rest with `shape` held from frame `start` for `length` frames."""
    return [{shape: 1.0} if start <= i < start + length else {"rest": 1.0} for i in range(n)]


def test_each_kind_of_shape_moves_its_own_part() -> None:
    jaw = np.zeros(50)
    spread = tracks(word("EE"), jaw, FPS)
    rounded = tracks(word("OO"), jaw, FPS)
    opened = tracks(word("AA"), jaw, FPS)
    assert spread.lift.max() > 8.0 and spread.draw.max() == 0.0
    assert rounded.draw.max() > 4.0 and rounded.lift.max() == 0.0
    assert opened.stretch.max() > rounded.stretch.max() > 0.0  # wider open, more stretch
    assert opened.stretch.max() > spread.stretch.max()


def test_lips_pressed_and_rest_leave_the_cheeks_still() -> None:
    cheeks = tracks(word("MBP"), np.zeros(50), FPS)
    assert cheeks.lift.max() == 0.0 and cheeks.draw.max() == 0.0 and cheeks.stretch.max() == 0.0
    rest = tracks([{"rest": 1.0}] * 20, np.zeros(20), FPS)
    assert not rest.lift.any() and not rest.stretch.any()


def test_the_cheeks_follow_a_little_behind_the_lips_and_ease_back_to_rest() -> None:
    cheeks = tracks(word("EE", start=15, length=10), np.zeros(50), FPS)
    peak = int(np.argmax(cheeks.lift))
    assert 20 <= peak <= 22  # the shape's middle is frame 19.5; the cheeks come 40 ms later
    top = cheeks.lift[peak]
    assert cheeks.lift[12] < 0.05 * top < cheeks.lift[15] < 0.6 * top  # eased in
    assert cheeks.lift[40:].max() < 0.01  # back at rest between words
    assert np.abs(np.diff(cheeks.lift)).max() < 0.4 * top  # no jumps


def test_a_louder_syllable_stretches_the_face_further() -> None:
    weights = word("AA")
    quiet = tracks(weights, np.full(50, -4.0), FPS)
    loud = tracks(weights, np.full(50, 12.0), FPS)
    assert loud.stretch.max() > quiet.stretch.max()


def test_the_strength_scales_the_movement_and_off_stops_it() -> None:
    weights, jaw = word("EH"), np.zeros(50)
    normal = tracks(weights, jaw, FPS, STRENGTHS["normal"])
    slight = tracks(weights, jaw, FPS, STRENGTHS["slight"])
    off = tracks(weights, jaw, FPS, STRENGTHS["off"])
    assert slight.lift.max() == pytest.approx(0.6 * normal.lift.max())
    assert "more" not in STRENGTHS  # taken out: it looked strange (Larry, 2026-10-26)
    assert not off.lift.any() and not off.stretch.any()
    custom = tracks(weights, jaw, FPS, gains=CheekGains(lift_px=1.0))
    assert custom.lift.max() < normal.lift.max()
    assert len(tracks([], np.zeros(0), FPS).lift) == 0


def test_the_fields_move_the_cheeks_and_chin_but_not_the_lips() -> None:
    lm = landmarks()
    f = fields(lm)
    mx, my = MOUTH
    for dx, dy in (f.lift, f.draw, f.stretch):
        assert dx[my, mx] == 0.0 and dy[my, mx] == 0.0  # the lips are left as tuned
        assert float(np.hypot(dx, dy).max()) <= 1.0
        for edge in (dx[0], dx[-1], dx[:, 0], dx[:, -1], dy[0], dy[-1], dy[:, 0], dy[:, -1]):
            assert not edge.any()  # seamless paste: the crop's edge never moves
    apple_y = int(lm[33, 1] - 0.25 * (lm[33, 1] - lm[36:48, 1].mean()))
    half = float(np.ptp(lm[48:60, 0])) / 2
    left, right = round(mx - 1.5 * half), round(mx + 1.5 * half)
    assert f.lift[1][apple_y, left] < -0.5 and f.lift[1][apple_y, right] < -0.5  # cheeks up
    assert f.lift[0][apple_y, left] < 0 < f.lift[0][apple_y, right]  # and a little outward
    assert f.draw[0][apple_y, left] > 0 > f.draw[0][apple_y, right]  # drawn in
    chin_y = int(lm[8, 1])
    assert f.stretch[1][chin_y - 10, round(mx + 1.5 * half)] > 0.3  # lower cheek down
    above_nose = int(lm[33, 1]) - 10
    assert f.stretch[1][above_nose, round(mx + 1.5 * half)] == 0.0  # none above the nose tip


def test_limit_keeps_every_pixel_within_max_px() -> None:
    assert limit(4.0, 2.0, 8.0) == (4.0, 2.0, 8.0)
    capped = limit(20.0, 10.0, 30.0)
    assert sum(abs(v) for v in capped) == pytest.approx(MAX_PX)
    assert capped[0] / capped[2] == pytest.approx(20.0 / 30.0)
    assert limit(0.0, 0.0, 0.0) == (0.0, 0.0, 0.0)


def test_an_unknown_strength_is_logged_and_taken_as_normal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert strength_of("slight") == 0.6
    with caplog.at_level(logging.ERROR):
        assert strength_of("wild") == 1.0
    assert "Unknown face movement strength; using normal" in caplog.messages


def test_the_log_says_how_far_and_how_long(caplog: pytest.LogCaptureFixture) -> None:
    cheeks = tracks(word("EE"), np.zeros(50), FPS)
    with caplog.at_level(logging.INFO):
        log_added(cheeks, "normal", 0.0123, 50)
    record = next(r for r in caplog.records if r.message == "Face movement added")
    assert record.__dict__["duration_ms"] == 12.3 and record.__dict__["frames"] == 50
    assert 8.0 < record.__dict__["peak_px"] <= MAX_PX and record.__dict__["strength"] == "normal"


def test_the_compositor_moves_the_cheeks_and_leaves_the_rest(
    tmp_path: Path, short_loop: object
) -> None:
    build_library(tmp_path / "me.png", tmp_path / "lib", lambda _: FakePortrait())
    comp = Compositor(load_library(tmp_path / "lib"))
    still = comp.face({"rest": 1.0}, 0, move=STILL)
    lifted = comp.face({"rest": 1.0}, 0, move=FrameMotion(lift=3.0))
    stretched = comp.face({"rest": 1.0}, 0, move=FrameMotion(stretch=3.0))
    mx, my = MOUTH
    cheek = (slice(290, 316), slice(mx - 40, mx - 22))  # see the fields test
    chin = (slice(405, 425), slice(mx + 15, mx + 45))
    diff = np.abs(lifted.astype(int) - still.astype(int))
    assert diff[cheek].mean() > 3  # the cheek moved
    assert diff[my - 2 : my + 3, mx - 5 : mx + 5].max() == 0  # the lips did not
    assert diff[:40].max() == 0 and diff[:, :40].max() == 0  # nor the crop's edges
    assert np.abs(stretched.astype(int) - still.astype(int))[chin].mean() > 3
    assert comp.cheek_s > 0
    assert still.shape == (CROP, CROP, 3)


@pytest.mark.parametrize(("setting", "moves"), [("normal", True), ("off", False)])
def test_render_follows_the_setting_and_logs(
    tmp_path: Path,
    short_loop: object,
    caplog: pytest.LogCaptureFixture,
    setting: str,
    moves: bool,
) -> None:
    engine = PhotorealEngine(home=tmp_path / "home", make_portrait=lambda _: FakePortrait())
    lib = engine.prepare(photo_file(tmp_path))
    wav = tmp_path / "speech.wav"
    write_speech(wav, seconds=0.8)
    with caplog.at_level(logging.INFO):
        engine.render(lib, wav, tmp_path / "reply.mp4", face_movement=setting)
    record = next(r for r in caplog.records if r.message == "Face movement added")
    assert record.__dict__["strength"] == setting
    assert (record.__dict__["peak_px"] > 0) is moves
