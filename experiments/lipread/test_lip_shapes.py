import pytest
from lip_shapes import (
    CONTACT,
    SHAPES,
    VISEME_OF,
    Segment,
    frame_weights,
    mix,
    segments,
    top_two,
)


def test_every_mapped_sound_has_a_shape() -> None:
    assert set(VISEME_OF.values()) <= set(SHAPES)
    assert all(SHAPES[name].ratio is not None for name in CONTACT)


def test_key_sounds_map_to_readable_shapes() -> None:
    assert [VISEME_OF[c] for c in "mbp"] == ["MBP"] * 3
    assert [VISEME_OF[c] for c in "fv"] == ["FV"] * 2
    assert VISEME_OF["u"] == VISEME_OF["w"] == "OO"
    assert VISEME_OF["i"] == "EE"
    assert VISEME_OF["ɑ"] == "AA"


def test_segments_merge_holds_and_mark_pauses() -> None:
    # "mˈɑː." : stress and length marks extend the sound before them; "." rests.
    segs = segments("mˈɑː.", [0.1, 0.05, 0.1, 0.05, 0.2])
    assert segs == [
        Segment("MBP", 0.0, pytest.approx(0.15)),
        Segment("AA", pytest.approx(0.15), pytest.approx(0.3)),
        Segment("rest", pytest.approx(0.3), pytest.approx(0.5)),
    ]


def test_segments_join_repeats_and_default_unknown_sounds() -> None:
    segs = segments("mm?Q", [0.1, 0.1, 0.1, 0.1])
    assert [s.shape for s in segs] == ["MBP", "rest", "IH"]
    assert segs[0].end == pytest.approx(0.2)


def test_segments_reject_length_mismatch() -> None:
    with pytest.raises(ValueError):
        segments("ab", [0.1])


def test_leading_hold_rests() -> None:
    assert segments(" a", [0.1, 0.1])[0].shape == "rest"


def test_frame_weights_sum_to_one_and_blend_between_shapes() -> None:
    segs = [Segment("AA", 0.0, 0.5), Segment("OO", 0.5, 1.0)]
    weights = frame_weights(segs, 30, 30.0)
    assert all(sum(w.values()) == pytest.approx(1.0) for w in weights)
    assert weights[3] == {"AA": pytest.approx(1.0)}
    assert top_two(weights[25])[0] == "OO"
    middle = weights[15]
    assert 0.2 < middle["AA"] < 0.8 and 0.2 < middle["OO"] < 0.8


def test_short_lip_closure_still_gets_a_full_frame() -> None:
    # A 20 ms "m" is shorter than one 33 ms frame and would blur away without the rule.
    segs = [Segment("AA", 0.0, 0.5), Segment("MBP", 0.5, 0.52), Segment("AA", 0.52, 1.0)]
    weights = frame_weights(segs, 30, 30.0)
    assert {"MBP": 1.0} in weights


def test_mix_uses_photo_ratio_for_rest() -> None:
    controls, ratio = mix({"rest": 0.5, "OO": 0.5}, photo_ratio=0.2)
    assert ratio == pytest.approx(0.5 * 0.2 + 0.5 * SHAPES["OO"].ratio)  # type: ignore[operator]
    assert controls == {"purse": pytest.approx(12.0)}


def test_top_two() -> None:
    assert top_two({"AA": 1.0}) == ("AA", "AA", 0.0)
    a, b, t = top_two({"AA": 0.6, "OO": 0.3, "EE": 0.1})
    assert (a, b) == ("AA", "OO")
    assert t == pytest.approx(1 / 3)
