"""Unit tests for the R233 optimize image experiment, with fake models (no MediaPipe or models)."""

import json
import logging

import cv2
import numpy as np
import pytest
from framing import CHIN, FACE_SKIN, FOREHEAD, HAIR, Box, Framing
from make_photos import PHOTOS, near_edge, prompt
from optimize_image import (
    METHODS,
    MethodResult,
    PhotoResult,
    SmallFace,
    draw_box,
    find_small_face,
    frame_photo,
    grid,
    label,
    markdown,
    method_speed,
    small_faces,
    superres_model,
    thumb,
)
from PIL import Image as PILImage

TARGET = Framing(margin_above_hair=0.15, face_share=0.4, chin_to_bottom=0.6, centre_offset=0.0)


def fake_face(rgb):
    """Face points and labels for a face whose forehead is at a third of the height and chin
    at half, centred, with hair above."""
    h, w = rgb.shape[:2]
    forehead, chin, cx = h / 3, h / 2, w / 2
    half = (chin - forehead) * 0.4
    angles = np.linspace(0, 2 * np.pi, 478, endpoint=False)
    pts = np.stack(
        [
            cx + half * np.sin(angles),
            (forehead + chin) / 2 - (chin - forehead) / 2 * np.cos(angles),
        ],
        axis=1,
    ).astype(np.float32)
    pts[FOREHEAD] = (cx, forehead)
    pts[CHIN] = (cx, chin)
    labels = np.zeros((h, w), np.uint8)
    labels[
        int(forehead - 0.4 * (chin - forehead)) : int(forehead) + 3, int(cx - half) : int(cx + half)
    ] = HAIR
    cv2.fillPoly(labels, [np.round(pts).astype(np.int32)], FACE_SKIN)
    return pts, labels


def double(rgb):
    return cv2.resize(rgb, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


MODELS = {"lanczos": None, "fsrcnn": double, "espcn": double, "realesrgan": double}


def check(rgb):
    return [], 90, 300.0


def test_frame_photo_writes_every_picture(tmp_path, caplog):
    rgb = np.full((600, 400, 3), 120, np.uint8)
    with caplog.at_level(logging.INFO, logger="optimize_image"):
        r = frame_photo("waist.png", rgb, TARGET, fake_face, check, MODELS, tmp_path)
    assert r.error == ""
    assert r.face_px == 100
    assert set(r.boxes) == {"landmarks", "segments"}
    assert set(r.methods) == {"landmarks_lanczos"} | {f"segments_{m}" for m in METHODS}
    for key in r.methods:
        assert cv2.imread(str(tmp_path / "waist" / f"{key}.png")).shape == (1024, 1024, 3)
    assert r.methods["segments_lanczos"].score == 90
    assert r.framing["segments"]["face_share"] == pytest.approx(
        r.framing["landmarks"]["face_share"], abs=0.1
    )
    assert r.hair_cut["segments"] == 0
    assert "Head and neck framed" in caplog.text


def test_frame_photo_with_no_face(tmp_path, caplog):
    with caplog.at_level(logging.ERROR, logger="optimize_image"):
        r = frame_photo(
            "x.png",
            np.zeros((10, 10, 3), np.uint8),
            TARGET,
            lambda _: None,
            check,
            MODELS,
            tmp_path,
        )
    assert r.error == "no face found"
    assert "Head and neck framing failed" in caplog.text


def test_small_faces_compares_each_method_with_the_original():
    rng = np.random.default_rng(3)
    rgb = cv2.GaussianBlur(rng.integers(0, 255, (512, 512, 3), dtype=np.uint8), (0, 0), 3)
    pts, _ = fake_face(rgb)
    rows = small_faces("p", rgb, pts, (40, 80), MODELS, lambda big, p: 0.1)
    assert [r.face_px for r in rows] == [40, 80]
    for r in rows:
        assert set(r.psnr) == set(METHODS)
        assert all(v > 10 for v in r.psnr.values())
        assert r.sharpness["lanczos"] == 0.1
    # A bigger face comes back closer to the original.
    assert rows[1].psnr["lanczos"] > rows[0].psnr["lanczos"]


def test_superres_model_hands_opencv_bgr_and_returns_rgb():
    class SR:
        def upsample(self, bgr):
            self.seen = bgr[0, 0].tolist()
            return cv2.resize(bgr, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)

    sr = SR()
    out = superres_model(sr)(np.full((10, 12, 3), (200, 100, 50), np.uint8))
    assert sr.seen == [50, 100, 200]
    assert out.shape == (20, 24, 3) and out[0, 0].tolist() == [200, 100, 50]


def test_sheet_helpers():
    img = np.zeros((50, 100, 3), np.uint8)
    t = thumb(img, 80)
    assert t.shape == (80, 80, 3) and t[0, 0, 0] == 255  # fitted on white
    assert label(img, "hi")[5, 5, 0] == 255
    drawn = img.copy()
    draw_box(drawn, Box(10, 10, 20), (0, 255, 0))
    assert drawn[10, 15, 1] == 255
    sheet = grid([[img, img], [img]])
    assert sheet.shape == (100, 200, 3)


def test_markdown_has_every_table():
    photo = PhotoResult(
        photo="a.png",
        size=(640, 480),
        face_px=120,
        boxes={"landmarks": [0, 0, 300], "segments": [0, 0, 320]},
        hair_cut={"landmarks": 0.05, "segments": 0.0},
        neck_cut={"landmarks": 0.0, "segments": 0.0},
        filled={"landmarks": 0.1, "segments": 0.12},
        framing={"landmarks": {"face_share": 0.4}, "segments": {"face_share": 0.38}},
        methods={
            "segments_lanczos": MethodResult(5, [], 88, 300),
            "segments_fsrcnn": MethodResult(9, ["The photo is blurry. Hold still."], None, 300),
        },
    )
    failed = PhotoResult(photo="b.png", error="no face found")
    faces = [SmallFace("p", 80, {m: 30.0 for m in METHODS}, {m: 0.06 for m in METHODS})]
    speed = {m: {"model_kb": 1, "load_ms": 0, "memory_mb": 2, "ms": 3} for m in METHODS}
    text = markdown(TARGET, [("one", TARGET)], [photo, failed], faces, speed)
    assert "**Median (the target)** | 0.15 | 0.400" in text
    assert "| a.png | 640x480 | 120 | 5.0% / 0.0% | 0.0% / 0.0% |" in text
    assert "passes, score 88 (5 ms)" in text
    assert "fails: The photo is blurry" in text
    assert "| b.png | 0x0 | no face found | | | | |" in text
    assert "| 80 | 30.00 dB, 0.060" in text
    assert "| lanczos | 1 KB |" in text


def test_method_speed(tmp_path):
    for name in ("FSRCNN_x2.pb", "ESPCN_x2.pb", "realesr-general-x4v3.onnx"):
        (tmp_path / name).write_bytes(b"x" * 2048)
    speed = method_speed(tmp_path, MODELS, {"fsrcnn": (12.0, 3.5)})
    assert set(speed) == set(METHODS)
    assert speed["fsrcnn"]["model_kb"] == 2
    assert (speed["fsrcnn"]["load_ms"], speed["fsrcnn"]["memory_mb"]) == (12.0, 3.5)
    assert speed["lanczos"]["model_kb"] == 0
    assert all(s["ms"] >= 0 for s in speed.values())
    json.dumps(speed)


def test_test_photos():
    assert {p.name for p in PHOTOS} == {
        "waist_up",
        "full_length",
        "turned",
        "long_hair",
        "high_collar",
    }
    assert all(prompt(p).startswith(p.text) for p in PHOTOS)
    assert len({p.seed for p in PHOTOS}) == len(PHOTOS)


def test_near_edge_cuts_the_top_and_left():
    cut = near_edge(PILImage.new("RGB", (1000, 1000)))
    assert cut.size == (600, 880)


def test_find_small_face_looks_around_the_face_skin_and_maps_back():
    labels = np.zeros((1000, 600), np.uint8)
    labels[100:140, 300:330] = FACE_SKIN  # search box: left 255, top 60, 120 px
    seen = []

    def landmarks(square):
        seen.append(square.shape)
        return np.array([[256.0, 256.0]], np.float32)  # the middle of the 512 px square

    pts = find_small_face(np.zeros((1000, 600, 3), np.uint8), labels, landmarks)
    assert seen == [(512, 512, 3)]
    assert pts.tolist() == [[315.0, 120.0]]
    assert (
        find_small_face(np.zeros((10, 10, 3), np.uint8), np.zeros((10, 10), np.uint8), landmarks)
        is None
    )
    assert find_small_face(np.zeros((1000, 600, 3), np.uint8), labels, lambda _: None) is None
