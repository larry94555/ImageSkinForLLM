import pytest
from face_points import (
    CONTROLS,
    MOODS,
    MP_TO_68,
    NUM_KP,
    VISEMES,
    expression_delta,
    loop_motion,
    viseme_frames,
)


def test_mapping_has_68_distinct_mediapipe_points() -> None:
    assert len(MP_TO_68) == 68
    assert len(set(MP_TO_68)) == 68
    assert all(0 <= i < 478 for i in MP_TO_68)


def test_expression_delta_scales_and_sums_controls() -> None:
    delta = expression_delta({"open": 10.0, "pout": 0.05})
    assert len(delta) == NUM_KP and all(len(row) == 3 for row in delta)
    assert delta[19][1] == pytest.approx(0.01)
    assert delta[19][0] == pytest.approx(0.05)
    assert delta[17][1] == pytest.approx(-0.001)
    assert delta[0] == [0.0, 0.0, 0.0]


def test_expression_delta_empty_is_zero_and_unknown_raises() -> None:
    assert all(v == 0.0 for row in expression_delta({}) for v in row)
    with pytest.raises(KeyError):
        expression_delta({"frown": 1.0})


def test_presets_only_use_known_controls() -> None:
    for preset in [*VISEMES.values(), *MOODS.values()]:
        assert set(preset) <= set(CONTROLS)
    assert "rest" in VISEMES and "neutral" in MOODS


def test_loop_motion_is_seamless_and_blinks_once() -> None:
    n, fps = 50, 25.0
    first = loop_motion(0, n, fps)
    after_last = loop_motion(n, n, fps)
    assert first[:3] == pytest.approx(after_last[:3], abs=1e-9)
    eyes = [loop_motion(i, n, fps)[3] for i in range(n)]
    assert min(eyes) < 0.5
    closed = [i for i, e in enumerate(eyes) if e < 1.0]
    assert closed == list(range(closed[0], closed[-1] + 1))  # one contiguous blink
    assert all(abs(p) <= 3.0 for i in range(n) for p in loop_motion(i, n, fps)[:3])


def test_viseme_frames_holds_then_crossfades() -> None:
    frames = viseme_frames([("AA", 0.0, 0.2), ("OO", 0.2, 0.4)], fps=25.0, blend_s=0.08)
    assert len(frames) == 10
    assert frames[0] == ("AA", "OO", 0.0)
    assert frames[4][0] == "AA" and frames[4][1] == "OO" and 0.0 < frames[4][2] < 1.0
    assert frames[5][0] == "OO"
    assert frames[-1][1] == "rest"  # fades back to rest at the end


def test_viseme_frames_fills_gaps_with_rest() -> None:
    frames = viseme_frames([("AA", 0.0, 0.1), ("EE", 0.3, 0.4)], fps=10.0, blend_s=0.05)
    assert [f[0] for f in frames] == ["AA", "rest", "rest", "EE"]
    assert frames[1][1] == "EE"


def test_viseme_frames_empty() -> None:
    assert viseme_frames([], fps=25.0) == []
