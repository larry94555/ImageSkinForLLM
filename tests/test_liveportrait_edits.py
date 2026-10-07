import pytest

from imageskin.liveportrait_edits import (
    BLINK_CLOSE_S,
    BLINK_CLOSED,
    BLINK_OPEN_S,
    BLINKS_AT,
    CONTROLS,
    MOUTH_SHAPES,
    MP_TO_68,
    NUM_KP,
    expression_delta,
    eye_openness,
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


def test_soften_moves_the_controls_part_way_and_opens_in_full() -> None:
    controls, ratio = soften("OH", 0.5, photo_ratio=0.1)
    assert controls == {"purse": pytest.approx(3.5)}
    assert ratio == pytest.approx(0.51)  # the mouth opens fully, so speech is visible
    controls, ratio = soften("rest", 0.4, 0.2)
    assert controls == {} and ratio == pytest.approx(0.2)


def test_soften_keeps_lip_contact() -> None:
    controls, ratio = soften("MBP", 0.4, photo_ratio=0.2)
    assert ratio == 0.0
    assert controls == {"open": pytest.approx(-6.0)}


def test_soften_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        soften("AA", 1.5, 0.0)


def test_eyes_close_quickly_and_open_slowly() -> None:
    at = BLINKS_AT[0]
    assert eye_openness(0.0) == 1.0
    assert eye_openness(at) == pytest.approx(0.0)
    assert eye_openness(at - BLINK_CLOSE_S / 2) == pytest.approx(0.5)
    assert eye_openness(at + BLINK_OPEN_S / 2) == pytest.approx(0.5)
    assert eye_openness(at + BLINK_OPEN_S + 0.01) == 1.0


def test_idle_motion_is_subtle_seamless_and_blinks() -> None:
    n, fps = 200, 25.0
    assert idle_motion(0, n, fps)[:3] == pytest.approx(idle_motion(n, n, fps)[:3], abs=1e-9)
    frames = [idle_motion(i, n, fps) for i in range(n)]
    assert all(abs(angle) <= 2.0 for f in frames for angle in f[:3])
    closed = [i for i, f in enumerate(frames) if f[3] < 0.5]
    assert len(closed) >= 2 * len(BLINKS_AT)  # each blink lasts a few frames
    assert frames[0][3] == frames[-1][3] == 1.0  # no blink across the loop's seam


def test_rounding_does_not_push_the_lips_forward() -> None:
    delta = expression_delta({"purse": MOUTH_SHAPES["OO"].controls["purse"]})
    assert all(row[2] == 0.0 for row in delta)  # no depth: no kiss-like pucker
