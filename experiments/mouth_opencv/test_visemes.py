import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from visemes import SHAPES, Segment, frame_shapes, segments  # noqa: E402


def test_segments_map_phonemes_to_shapes() -> None:
    segs = segments("mˈɑː b,", [0.1, 0.02, 0.1, 0.03, 0.05, 0.08, 0.2])
    assert [s.shape for s in segs] == ["closed", "wide", "small", "closed", "rest"]
    # Stress and length marks extend the sound before them.
    assert (segs[1].shape, segs[1].start, segs[1].end) == (
        "wide",
        pytest.approx(0.12),
        pytest.approx(0.25),
    )
    assert segs[-1].end == pytest.approx(0.58)


def test_segments_need_one_duration_per_phoneme() -> None:
    with pytest.raises(ValueError):
        segments("ab", [0.1])


def test_short_closure_still_closes_the_mouth() -> None:
    # A 20 ms "b" in the middle of an open vowel, shorter than a 40 ms frame.
    segs = [Segment("wide", 0, 0.1), Segment("closed", 0.1, 0.12), Segment("wide", 0.12, 0.3)]
    shapes = frame_shapes(segs, 7, 25)
    assert shapes[2][0] == SHAPES["closed"][0]
    assert shapes[1][0] > 0.5 and shapes[4][0] > 0.5


def test_shapes_ease_in_and_rest_after_speech() -> None:
    shapes = frame_shapes([Segment("round", 0, 0.2)], 10, 25)
    assert 0 < shapes[0][0] < SHAPES["round"][0]  # eases toward the shape
    assert shapes[4][0] == pytest.approx(SHAPES["round"][0], abs=0.01)
    assert shapes[4][1] < 1  # rounded lips are narrower
    assert shapes[9][0] < 0.05  # back to rest


def test_soft_frame_is_unchanged_when_closed() -> None:
    from compare import soft_frame

    from imageskin.mouth_warp import frame_weights
    from imageskin.video import Face

    image = np.full((160, 200, 3), 180, dtype=np.uint8)
    face = Face(Path("f.png"), 200, 160, 100, 100, 42, 40)
    region, weights = frame_weights(face)
    assert np.array_equal(soft_frame(image, face, region, weights, 0.0), image)
    opened = soft_frame(image, face, region, weights, 1.0, 0.8)
    assert opened[103, 100].sum() < image[103, 100].sum()  # dark opening below the lip line
    assert np.array_equal(opened[:85], image[:85])  # nothing high above the mouth changes


def test_refine_lip_line_finds_the_seam_below_the_nose_shadow() -> None:
    from compare import refine_lip_line

    from imageskin.video import Face

    image = np.full((160, 200, 3), 180, dtype=np.uint8)
    image[88:91, 80:120] = 90  # shadow under the nose
    image[104:106, 80:120] = 60  # seam between the lips
    face = Face(Path("f.png"), 200, 160, 100, 100, 42, 30)
    refined = refine_lip_line(image, face)
    assert refined.mouth_y in (104, 105)
    assert refined.mouth_y + refined.jaw_h == face.mouth_y + face.jaw_h  # chin unchanged
