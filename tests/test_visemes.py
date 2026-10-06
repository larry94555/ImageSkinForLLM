import pytest

from imageskin.visemes import (
    SHAPE_OF,
    SHAPES,
    ShapeTiming,
    SoundTiming,
    frame_weights,
    shape_timings,
    sound_timings,
)


def test_every_shape_is_known_and_lip_sounds_map_as_expected() -> None:
    assert set(SHAPE_OF.values()) <= set(SHAPES)
    assert [SoundTiming(ch, 0, 1).shape for ch in "mfuOAiʃɹ,"] == [
        "MBP", "FV", "OO", "OH", "EH", "EE", "SH", "IH", "rest",
    ]  # fmt: skip
    assert SoundTiming("@", 0, 1).shape == "IH"  # unknown sounds get a small opening


def test_sound_timings_adds_spaces_and_stress_to_the_sound_before() -> None:
    sounds = sound_timings("ˈhi m", [0.1, 0.1, 0.1, 0.05, 0.1], offset=1.0)
    assert sounds == [
        SoundTiming("h", 1.1, 1.2),  # a leading stress mark has nothing to hold, so it is skipped
        SoundTiming("i", 1.2, 1.35),
        SoundTiming("m", 1.35, 1.45),
    ]


def test_sound_timings_needs_one_duration_per_phoneme() -> None:
    with pytest.raises(ValueError, match="2 phonemes but 1 durations"):
        sound_timings("hi", [0.1])


def test_shape_timings_joins_touching_sounds_with_the_same_shape() -> None:
    sounds = [
        SoundTiming("m", 0.0, 0.1),
        SoundTiming("p", 0.1, 0.2),
        SoundTiming("i", 0.2, 0.3),
        SoundTiming("i", 0.5, 0.6),  # a gap keeps it separate
    ]
    assert shape_timings(sounds) == [
        ShapeTiming("MBP", 0.0, 0.2),
        ShapeTiming("EE", 0.2, 0.3),
        ShapeTiming("EE", 0.5, 0.6),
    ]


def test_frame_weights_add_up_to_one_and_follow_the_sound() -> None:
    shapes = [ShapeTiming("AA", 0.0, 0.5), ShapeTiming("OO", 0.5, 1.0)]
    frames = frame_weights(shapes, n_frames=25, fps=25)
    assert len(frames) == 25
    for w in frames:
        assert sum(w.values()) == pytest.approx(1.0)
    assert max(frames[5], key=frames[5].__getitem__) == "AA"
    assert max(frames[20], key=frames[20].__getitem__) == "OO"
    assert frames[24].get("rest", 0) > 0  # after the speech ends the mouth heads to rest


def test_a_closed_lip_sound_shorter_than_a_frame_still_gets_one() -> None:
    shapes = [
        ShapeTiming("AA", 0.0, 0.5),
        ShapeTiming("MBP", 0.5, 0.52),  # 20 ms, half a frame at 25 fps
        ShapeTiming("AA", 0.52, 1.0),
    ]
    frames = frame_weights(shapes, n_frames=25, fps=25)
    assert frames[12] == {"MBP": 1.0}  # middle of the sound, 30 ms early: 0.48 s
    assert all(f.get("MBP", 0) < 0.5 for i, f in enumerate(frames) if i != 12)


def test_frame_weights_with_no_frames() -> None:
    assert frame_weights([ShapeTiming("MBP", 0.0, 0.1)], n_frames=0, fps=25) == []
