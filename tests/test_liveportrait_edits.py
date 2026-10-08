import pytest

from imageskin.liveportrait_edits import (
    BLINK_CLOSED,
    CONTROLS,
    MOUTH_SHAPES,
    MP_TO_68,
    NUM_KP,
    Blink,
    blink_times,
    expression_delta,
    eye_track,
    idle_motion,
    soften,
    top_two,
)
from imageskin.visemes import CONTACT, SHAPES


def test_every_mouth_shape_has_a_liveportrait_edit() -> None:
    assert tuple(MOUTH_SHAPES) == SHAPES
    assert all(MOUTH_SHAPES[name].ratio is not None for name in CONTACT)
    assert all(set(s.controls) <= set(CONTROLS) for s in MOUTH_SHAPES.values())


def test_mapping_has_68_distinct_mediapipe_points() -> None:
    assert len(MP_TO_68) == 68
    assert len(set(MP_TO_68)) == 68
    assert all(0 <= i < 478 for i in MP_TO_68)


def test_expression_delta_scales_and_sums_controls() -> None:
    delta = expression_delta({"open": 10.0, "grin": 2.0})
    assert len(delta) == NUM_KP and all(len(row) == 3 for row in delta)
    assert delta[19][1] == pytest.approx(0.01)
    assert delta[14][1] == pytest.approx(-0.002)
    assert delta[0] == [0.0, 0.0, 0.0]
    with pytest.raises(KeyError):
        expression_delta({"frown": 1.0})


def test_blink_closes_both_eyes_evenly() -> None:
    delta = expression_delta({"blink": BLINK_CLOSED})
    assert delta[11][1] == pytest.approx(delta[15][1]) and delta[11][1] > 0


def test_top_two() -> None:
    assert top_two({"AA": 1.0}) == ("AA", "AA", 0.0)
    a, b, t = top_two({"AA": 0.6, "OO": 0.3, "EE": 0.1})
    assert (a, b) == ("AA", "OO")
    assert t == pytest.approx(1 / 3)


def test_soften_moves_part_way_from_rest() -> None:
    controls, ratio = soften("OH", 0.5, photo_ratio=0.1)
    assert controls == {"purse": pytest.approx(3.5)}
    assert ratio == pytest.approx(0.1 + 0.6 * (0.51 - 0.1))  # opening 60% of the way
    controls, ratio = soften("rest", 0.4, 0.2)
    assert controls == {} and ratio == pytest.approx(0.2)


def test_soften_keeps_lip_contact() -> None:
    controls, ratio = soften("MBP", 0.4, photo_ratio=0.2)
    assert ratio == 0.0
    assert controls == {"open": pytest.approx(-6.0)}


def test_soften_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        soften("AA", 1.5, 0.0)


def test_brows_lower_without_moving_the_lids() -> None:
    delta = expression_delta({"brow": 6.0})
    assert delta[2][1] < 0
    assert delta[11] == delta[15] == [0.0, 0.0, 0.0]


def test_a_blink_closes_fast_holds_and_opens_slower() -> None:
    blink = Blink(start=1.0, close_s=0.08, hold_s=0.02, open_s=0.2)
    assert blink.openness(0.9) == blink.openness(1.31) == 1.0
    assert blink.openness(1.04) == pytest.approx(0.75)  # a quarter shut halfway down
    assert blink.openness(1.09) == 0.0
    assert blink.openness(1.2) == pytest.approx(0.75)  # three quarters back halfway up
    half = Blink(start=0.0, close_s=0.1, hold_s=0.0, open_s=0.2, depth=0.4)
    assert min(half.openness(t / 100) for t in range(30)) == pytest.approx(0.4)


def test_blinks_come_at_irregular_natural_times() -> None:
    blinks = blink_times(600.0, seed=1)
    starts = [b.start for b in blinks]
    gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)]
    per_minute = len(blinks) / 10
    assert 12 <= per_minute <= 30  # people blink 15 to 20 times a minute when they talk
    assert all(g > 0.15 for g in gaps) and max(gaps) <= 9.0
    assert len({round(g, 1) for g in gaps}) > 30  # not on a beat
    assert any(b.depth > 0 for b in blinks) and any(g < 0.6 for g in gaps)  # half and double
    assert len({b.close_s for b in blinks}) == len(blinks)  # each a little different
    assert blink_times(600.0, seed=1) == blinks
    assert blink_times(600.0, seed=2) != blinks


def test_eye_track_follows_the_blinks_frame_by_frame() -> None:
    fps = 25.0
    track = eye_track(250, fps, seed=3)
    assert len(track) == 250 and all(0.0 <= v <= 1.0 for v in track)
    first = blink_times(10.0, seed=3)[0]
    shut = round((first.start + first.close_s) * fps)
    assert track[shut] < 0.6 and track[0] == 1.0
    assert eye_track(250, fps, seed=3) == track


def test_idle_motion_is_subtle_and_seamless() -> None:
    n = 200
    assert idle_motion(0, n) == pytest.approx(idle_motion(n, n), abs=1e-9)
    frames = [idle_motion(i, n) for i in range(n)]
    assert all(abs(angle) <= 2.0 for f in frames for angle in f)


def test_rounding_does_not_push_the_lips_forward() -> None:
    delta = expression_delta({"purse": MOUTH_SHAPES["OO"].controls["purse"]})
    assert all(row[2] == 0.0 for row in delta)  # no depth: no kiss-like pucker
