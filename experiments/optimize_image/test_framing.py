"""Unit tests for the R233 framing functions, on made-up face points and labels (no models)."""

import cv2
import numpy as np
import pytest
from framing import (
    BODY_SKIN,
    CHIN,
    FACE_SKIN,
    FOREHEAD,
    HAIR,
    HAIR_ABOVE_FOREHEAD,
    MAX_GROW,
    Box,
    Framing,
    box_from_landmarks,
    box_from_segments,
    crop_square,
    enlarge,
    face_height,
    face_search_box,
    hair_cut,
    head_mask,
    head_top_and_centre,
    lanczos,
    measure_framing,
    median_framing,
    neck_cut,
    psnr,
)

TARGET = Framing(margin_above_hair=0.1, face_share=0.4, chin_to_bottom=0.6, centre_offset=0.0)


def face(cx: float, forehead: float, chin: float, n: int = 478) -> np.ndarray:
    """Face points on an oval from forehead to chin, with points 10 and 152 at the two ends."""
    half = (chin - forehead) * 0.4
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    middle = (forehead + chin) / 2
    pts = np.stack(
        [cx + half * np.sin(angles), middle - (chin - forehead) / 2 * np.cos(angles)], axis=1
    ).astype(np.float32)
    pts[FOREHEAD] = (cx, forehead)
    pts[CHIN] = (cx, chin)
    return pts


def labels_for(shape: tuple[int, int], pts: np.ndarray, hair_top: int, hair_shift: int = 0):
    """Face skin inside the points, and hair from hair_top down to the forehead, as wide as the
    face, shifted sideways by hair_shift."""
    labels = np.zeros(shape, np.uint8)
    cx = float(pts[:, 0].mean())
    half = float(pts[:, 0].max() - pts[:, 0].min()) / 2
    forehead = int(pts[FOREHEAD, 1])
    left, right = int(cx - half + hair_shift), int(cx + half + hair_shift)
    labels[hair_top : forehead + 5, max(0, left) : right] = HAIR
    cv2.fillPoly(labels, [np.round(pts).astype(np.int32)], FACE_SKIN)
    return labels


def test_face_height_is_forehead_to_chin():
    assert face_height(face(100, 50, 150)) == 100


def test_head_mask_keeps_only_hair_joined_to_the_face():
    pts = face(200, 100, 200)
    labels = labels_for((400, 400), pts, hair_top=60)
    labels[10:30, 10:30] = HAIR  # someone else's hair, not touching the face
    head = head_mask(labels, pts)
    assert head[70, 200] and head[150, 200]
    assert not head[20, 20]


def test_head_mask_is_empty_without_hair_or_skin():
    assert not head_mask(np.zeros((50, 50), np.uint8), face(25, 10, 40)).any()


def test_head_top_and_centre_from_the_mask():
    pts = face(200, 100, 200)
    head = head_mask(labels_for((400, 400), pts, hair_top=60, hair_shift=10), pts)
    top, centre = head_top_and_centre(head, pts)
    assert top == 60
    assert 200 < centre <= 206  # the hair pulls the middle a little to the right


def test_head_top_without_a_mask_is_guessed_from_the_landmarks():
    pts = face(200, 100, 200)
    top, centre = head_top_and_centre(np.zeros((400, 400), bool), pts)
    assert top == pytest.approx(100 - HAIR_ABOVE_FOREHEAD * 100)
    assert centre == pytest.approx(200, abs=1)


def test_measure_framing_of_a_square_picture():
    pts = face(500, 300, 700)  # face 400 px in a 1000 px square
    labels = labels_for((1000, 1000), pts, hair_top=150)
    f = measure_framing(pts, labels)
    assert f.face_share == pytest.approx(0.4)
    assert f.margin_above_hair == pytest.approx(150 / 400)
    assert f.chin_to_bottom == pytest.approx(300 / 400)
    assert f.centre_offset == pytest.approx(0, abs=0.01)


def test_median_framing_takes_each_number_on_its_own():
    a = Framing(0.1, 0.3, 0.5, -0.1)
    b = Framing(0.3, 0.5, 0.7, 0.1)
    c = Framing(0.2, 0.4, 0.9, 0.0)
    assert median_framing([a, b, c]) == Framing(0.2, 0.4, 0.7, 0.0)


def test_box_from_landmarks_matches_the_target():
    pts = face(1000, 800, 900)  # face 100 px
    box = box_from_landmarks(pts, TARGET)
    assert box.size == 250  # 100 / 0.4
    assert box.bottom == 960  # chin 900 + 0.6 * 100
    assert box.left + box.size / 2 == pytest.approx(1000, abs=1)


def test_box_from_segments_is_the_landmark_box_when_the_hair_fits():
    pts = face(1000, 800, 900)
    labels = labels_for((2000, 2000), pts, hair_top=760)
    seg = box_from_segments(pts, labels, TARGET)
    land = box_from_landmarks(pts, TARGET)
    assert (seg.top, seg.size) == (land.top, land.size)


def test_box_from_segments_grows_to_keep_tall_hair_in():
    pts = face(1000, 800, 900)
    labels = labels_for((2000, 2000), pts, hair_top=690)  # the landmark box starts at 710
    land = box_from_landmarks(pts, TARGET)
    seg = box_from_segments(pts, labels, TARGET)
    assert seg.top == 680  # 690 minus the 0.1 face-height margin
    assert seg.bottom == land.bottom
    head = head_mask(labels, pts)
    assert hair_cut(head, land, 900) > 0
    assert hair_cut(head, seg, 900) == 0


def test_box_from_segments_grows_no_more_than_max_grow_then_moves_up():
    pts = face(1000, 800, 900)
    labels = labels_for((2000, 2000), pts, hair_top=400)  # very tall hair
    land = box_from_landmarks(pts, TARGET)
    seg = box_from_segments(pts, labels, TARGET)
    assert seg.size == round(land.size * MAX_GROW)
    assert seg.top == 390
    assert seg.bottom < land.bottom


def test_box_from_segments_centres_on_the_head():
    pts = face(1000, 800, 900)
    labels = labels_for((2000, 2000), pts, hair_top=760, hair_shift=30)
    seg = box_from_segments(pts, labels, TARGET)
    land = box_from_landmarks(pts, TARGET)
    assert seg.left > land.left


def test_hair_cut_counts_only_above_the_chin():
    head = np.zeros((100, 100), bool)
    head[10:90, 40:60] = True  # hair from row 10 to 90; chin at row 50
    assert hair_cut(head, Box(0, 0, 100), 50) == 0
    assert hair_cut(head, Box(0, 30, 100), 50) == pytest.approx(0.5)
    assert hair_cut(np.zeros((10, 10), bool), Box(0, 0, 10), 5) == 0


def test_neck_cut_counts_the_skin_below_the_chin():
    pts = face(100, 100, 200)  # face 100 px tall, 80 px wide
    labels = np.zeros((400, 200), np.uint8)
    labels[200:250, 80:120] = BODY_SKIN  # the neck, half a face height below the chin
    labels[250:300, 80:120] = BODY_SKIN  # the chest, not counted
    labels[350:, :] = BODY_SKIN  # arms far below are not the neck
    assert neck_cut(labels, pts, Box(0, 0, 300)) == 0
    assert neck_cut(labels, pts, Box(-50, -50, 275)) == pytest.approx(0.5)
    assert neck_cut(np.zeros((400, 200), np.uint8), pts, Box(0, 0, 10)) == 0


def test_crop_square_inside_the_photo_is_a_plain_cut():
    rgb = np.arange(100 * 100 * 3, dtype=np.uint32).reshape(100, 100, 3).astype(np.uint8)
    out, filled = crop_square(rgb, Box(10, 20, 50))
    assert filled == 0
    assert np.array_equal(out, rgb[20:70, 10:60])


def test_crop_square_past_the_edge_is_filled_softly():
    rgb = np.zeros((100, 100, 3), np.uint8)
    rgb[:, :50] = 200  # left half light, right half dark
    out, filled = crop_square(rgb, Box(-50, 0, 100))
    assert out.shape == (100, 100, 3)
    assert filled == pytest.approx(0.5)
    # The photo's own pixels next to the edge are kept, and the fill carries the edge's colour
    # outward with no hard line: neighbouring columns differ little.
    assert out[50, 60, 0] == 200
    steps = np.abs(np.diff(out[50, :50, 0].astype(int)))
    assert steps.max() < 30
    assert out[50, 0, 0] > 100  # the light edge, stretched


def test_crop_square_fills_every_side():
    rgb = np.full((40, 40, 3), 90, np.uint8)
    out, filled = crop_square(rgb, Box(-10, -10, 60))
    assert out.shape == (60, 60, 3)
    assert np.all(np.abs(out.astype(int) - 90) <= 1)
    assert filled == pytest.approx(1 - 1600 / 3600)


def test_enlarge_shrinks_a_big_square():
    out = enlarge(np.full((2000, 2000, 3), 7, np.uint8), 1024, None)
    assert out.shape == (1024, 1024, 3) and out[0, 0, 0] == 7


def test_enlarge_with_resizing_only():
    rgb = np.random.default_rng(0).integers(0, 255, (300, 300, 3), dtype=np.uint8)
    assert np.array_equal(enlarge(rgb, 1024, None), lanczos(rgb, 1024))


def test_enlarge_runs_the_model_until_big_enough_then_fits():
    calls = []

    def double(rgb):
        calls.append(rgb.shape[0])
        return cv2.resize(rgb, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)

    out = enlarge(np.zeros((300, 300, 3), np.uint8), 1024, double)
    assert calls == [300, 600]  # 1200 is past 1024, then shrunk
    assert out.shape == (1024, 1024, 3)
    calls.clear()
    enlarge(np.zeros((100, 100, 3), np.uint8), 1024, double, max_passes=2)
    assert calls == [100, 200]  # stops at max_passes, then resized up


def test_enlarge_exact_size_is_returned_as_is():
    def four(rgb):
        return np.zeros((rgb.shape[0] * 4, rgb.shape[1] * 4, 3), np.uint8)

    assert enlarge(np.zeros((256, 256, 3), np.uint8), 1024, four).shape == (1024, 1024, 3)


def test_psnr():
    a = np.zeros((4, 4, 3), np.uint8)
    assert psnr(a, a) == 99.0
    b = np.full((4, 4, 3), 255, np.uint8)
    assert psnr(a, b) == pytest.approx(0)


def test_face_search_box_around_the_largest_face_skin():
    labels = np.zeros((1000, 600), np.uint8)
    labels[100:140, 300:330] = FACE_SKIN  # 30 x 40 face
    labels[500:505, 10:15] = FACE_SKIN  # a speck elsewhere
    box = face_search_box(labels)
    assert box == Box(255, 60, 120)
    assert face_search_box(np.zeros((10, 10), np.uint8)) is None
