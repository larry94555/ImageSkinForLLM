import logging
import math
import sys
import types
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from imageskin import face_checks
from imageskin.download import DownloadError
from imageskin.face_checks import (
    BLURRY,
    COVERED,
    EYEBROWS,
    FACE_OVAL,
    MANY_FACES,
    NO_FACE,
    TOO_BRIGHT,
    TOO_DARK,
    TOO_SMALL,
    TURNED,
    UNEVEN,
    FaceChecker,
    FaceCheckError,
    FaceMeasure,
    covered_share,
    head_angles,
    light_and_sharpness,
    problems,
    read_rgb,
    score,
)
from imageskin.liveportrait import MAX_SIDE
from imageskin.uploads import PhotoResult

GOOD = FaceMeasure(faces=1, height_px=600, yaw_deg=5, pitch_deg=-3, covered=0.02)


@pytest.mark.parametrize(
    ("measure", "expected"),
    [
        (GOOD, []),
        (FaceMeasure(faces=0), [NO_FACE]),
        (FaceMeasure(faces=3), [MANY_FACES]),
        (FaceMeasure(faces=1, height_px=150), [TOO_SMALL]),
        (FaceMeasure(faces=1, height_px=600, yaw_deg=-40), [TURNED]),
        (FaceMeasure(faces=1, height_px=600, pitch_deg=30), [TURNED]),
        (FaceMeasure(faces=1, height_px=600, covered=0.3), [COVERED]),
        (
            FaceMeasure(faces=1, height_px=100, yaw_deg=40, covered=0.5),
            [TOO_SMALL, TURNED, COVERED],
        ),
        (FaceMeasure(faces=1, height_px=600, sharpness=0.03), [BLURRY]),
        (FaceMeasure(faces=1, height_px=600, brightness=60), [TOO_DARK]),
        (FaceMeasure(faces=1, height_px=600, washed_out=0.4), [TOO_BRIGHT]),
        (FaceMeasure(faces=1, height_px=600, evenness=0.3), [UNEVEN]),
        (
            FaceMeasure(faces=1, height_px=600, sharpness=0.03, brightness=40, evenness=0.2),
            [BLURRY, TOO_DARK, UNEVEN],
        ),
    ],
)
def test_each_failed_check_gives_its_message(measure: FaceMeasure, expected: list[str]) -> None:
    assert problems(measure) == expected


def test_messages_are_plain_sentences() -> None:
    for message in (NO_FACE, MANY_FACES, TOO_SMALL, TURNED, COVERED):
        assert message.endswith(".") and len(message) < 120
    for message in (BLURRY, TOO_DARK, TOO_BRIGHT, UNEVEN):
        assert message.endswith(".") and len(message) < 120


def test_score_rises_with_each_quality_up_to_what_the_video_needs() -> None:
    best = FaceMeasure(faces=1, height_px=300, sharpness=0.15, brightness=180, evenness=0.9)
    assert score(best) == 100
    assert score(replace(best, height_px=1000, sharpness=2.0)) == 100  # more doesn't count
    assert score(replace(best, sharpness=0.06)) == 92
    assert score(replace(best, yaw_deg=-20, covered=0.06)) < score(replace(best, yaw_deg=5))
    worst = FaceMeasure(faces=1, yaw_deg=90, covered=1, sharpness=0, brightness=0, evenness=0)
    assert score(worst) == 0


def rotation(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    """A 4x4 matrix turning the head by yaw (about y), then tilting it by pitch (about x)."""
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    m = np.eye(4)
    m[:3, :3] = ry @ rx
    return m


def test_head_angles_measure_turn_and_tilt_from_level() -> None:
    yaw, pitch = head_angles(rotation(30, 10 + 15))
    assert yaw == pytest.approx(30)
    assert pitch == pytest.approx(15)
    assert head_angles(rotation(0, 10)) == pytest.approx((0, 0))


def face_points(size: int = 200) -> np.ndarray:
    """478 points with the face edge on a circle filling the image and the brows mid-way."""
    points = np.full((478, 2), size / 2, np.float32)
    for i, index in enumerate(FACE_OVAL):
        angle = 2 * math.pi * i / len(FACE_OVAL)
        points[index] = (
            size / 2 + size * 0.45 * math.sin(angle),
            size / 2 - size * 0.45 * math.cos(angle),
        )
    points[EYEBROWS, 1] = size / 2
    return points


def test_covered_share_counts_hands_masks_and_glasses_below_the_brows() -> None:
    labels = np.full((200, 200), 3, np.uint8)  # all face skin
    assert covered_share(labels, face_points()) == 0.0

    labels[150:, :] = 4  # a mask over the lower face
    assert 0.2 < covered_share(labels, face_points()) < 0.5

    labels[:] = 3
    labels[:100, :] = 5  # sunglasses above the brows don't count
    assert covered_share(labels, face_points()) == 0.0

    labels[:] = 1  # hair (a beard or a fringe) is allowed
    assert covered_share(labels, face_points()) == 0.0


def test_covered_share_of_a_face_with_nothing_below_the_brows_is_zero() -> None:
    points = np.full((478, 2), 9, np.float32)  # brows on the bottom row
    points[EYEBROWS, 1] = 10
    assert covered_share(np.full((10, 10), 5, np.uint8), points) == 0.0


def test_read_rgb_returns_rgb(tmp_path: Path) -> None:
    bgr = np.zeros((4, 6, 3), np.uint8)
    bgr[..., 0] = 255  # blue
    path = tmp_path / "blue é.png"  # non-ASCII names work too
    path.write_bytes(cv2.imencode(".png", bgr)[1].tobytes())
    rgb = read_rgb(path)
    assert rgb.shape == (4, 6, 3) and rgb[0, 0].tolist() == [0, 0, 255]


@pytest.mark.parametrize("data", [b"", b"not an image"])
def test_read_rgb_refuses_unreadable_files(tmp_path: Path, data: bytes) -> None:
    path = tmp_path / "bad.jpg"
    path.write_bytes(data)
    with pytest.raises(FaceCheckError, match="could not read bad.jpg"):
        read_rgb(path)


def test_ensure_models_downloads_both_models(tmp_path: Path) -> None:
    with patch.object(face_checks, "download") as download:
        face, segment = face_checks.ensure_models(tmp_path)
    assert face == tmp_path / "face_landmarker.task"
    assert segment == tmp_path / "selfie_multiclass_256x256.tflite"
    assert [c.args[1] for c in download.call_args_list] == [face, segment]


# A stand-in for MediaPipe, so the checker runs without it installed.
class Point:
    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y


class FakeModel:
    """Both models: finds `faces` faces turned by `yaw`, and labels every pixel `label`."""

    opened: list[dict[str, Any]] = []
    closed = 0

    def __init__(self, faces: int, yaw: float, label: int) -> None:
        self.faces, self.yaw, self.label = faces, yaw, label

    def __enter__(self) -> "FakeModel":
        return self

    def __exit__(self, *exc: object) -> None:
        FakeModel.closed += 1

    def detect(self, image: Any) -> Any:
        h, w = image.data.shape[:2]
        points = [Point(x / w, y / h) for x, y in face_points(h)]
        return types.SimpleNamespace(
            face_landmarks=[points] * self.faces,
            facial_transformation_matrixes=[rotation(self.yaw, 10)] * self.faces,
        )

    def segment(self, image: Any) -> Any:
        labels = np.full(image.data.shape[:2], self.label, np.uint8)
        return types.SimpleNamespace(category_mask=types.SimpleNamespace(numpy_view=lambda: labels))


def fake_mediapipe(faces: int = 1, yaw: float = 0.0, label: int = 3) -> dict[str, Any]:
    """sys.modules entries for mediapipe and mediapipe.tasks.python."""
    FakeModel.opened, FakeModel.closed = [], 0

    def create(options: dict[str, Any]) -> FakeModel:
        FakeModel.opened.append(options)
        return FakeModel(faces, yaw, label)

    model = types.SimpleNamespace(create_from_options=create)
    python = types.ModuleType("mediapipe.tasks.python")
    python.BaseOptions = lambda model_asset_path: model_asset_path  # type: ignore[attr-defined]
    python.vision = types.SimpleNamespace(  # type: ignore[attr-defined]
        FaceLandmarker=model,
        FaceLandmarkerOptions=lambda **kw: kw,
        ImageSegmenter=model,
        ImageSegmenterOptions=lambda **kw: kw,
    )
    mp = types.ModuleType("mediapipe")
    mp.ImageFormat = types.SimpleNamespace(SRGB="srgb")  # type: ignore[attr-defined]
    mp.Image = lambda image_format, data: types.SimpleNamespace(data=data)  # type: ignore[attr-defined]
    return {
        "mediapipe": mp,
        "mediapipe.tasks": types.ModuleType("t"),
        "mediapipe.tasks.python": python,
    }


def textured(size: int, low: int = 90, high: int = 210) -> np.ndarray:
    """A sharp, evenly lit stand-in for a face: smooth shading from high in the middle to low
    at the corners, like a face's shape, with fine grain on top, like skin's pores."""
    y, x = np.mgrid[0:size, 0:size] / size
    shade = low + (high - low - 20) * (1 - np.hypot(x - 0.5, y - 0.4))
    # Grain about a pixel wide at the face's size in the video, whatever the photo's size.
    grain = np.random.default_rng(1).integers(0, 30, (240, 240)).astype(np.float32)
    grain = cv2.resize(grain, (size, size), interpolation=cv2.INTER_NEAREST)
    grey = np.clip(shade + grain, 0, 255).astype(np.uint8)
    return np.repeat(grey[..., None], 3, axis=2)


def photo(tmp_path: Path, size: int) -> Path:
    path = tmp_path / "me.png"
    path.write_bytes(cv2.imencode(".png", textured(size))[1].tobytes())
    return path


def test_a_sharp_evenly_lit_face_passes_the_quality_checks() -> None:
    m = FaceMeasure(faces=1, height_px=600, **light_and_sharpness(textured(400), face_points(400)))
    assert problems(m) == []
    assert m.sharpness > 0.08 and 150 < m.brightness < 220 and m.evenness > 0.95
    big = light_and_sharpness(textured(1600), face_points(1600))  # shrunk to the video's size
    assert big["sharpness"] > 0.08
    assert m.washed_out == 0


def test_a_blurred_face_is_blurry_whatever_the_photo_size() -> None:
    for size in (400, 1600):  # the face is scaled to its size in the video first
        blurred = cv2.GaussianBlur(textured(size), (0, 0), 1.5 * size / 222).astype(np.uint8)
        found = light_and_sharpness(blurred, face_points(size))
        assert found["sharpness"] < 0.05, size


def test_a_dark_face_is_too_dark_but_not_blurry() -> None:
    found = light_and_sharpness(textured(400) // 4, face_points(400))
    assert found["brightness"] < 75
    assert found["sharpness"] > 0.08  # judged against the face's own grey level


def test_a_white_face_is_washed_out() -> None:
    found = light_and_sharpness(textured(400, 250, 280), face_points(400))
    assert found["washed_out"] > 0.25


def test_a_face_lit_from_one_side_is_uneven() -> None:
    image = textured(400)
    image[:, :200] //= 4  # the left half in shadow
    assert light_and_sharpness(image, face_points(400))["evenness"] < 0.4


def test_a_face_with_nothing_below_the_brows_measures_no_light() -> None:
    points = face_points(200)
    points[EYEBROWS, 1] = 199
    found = light_and_sharpness(textured(200), points)
    assert found["brightness"] == 0 and found["evenness"] == 0


MODELS = (Path("face.task"), Path("segment.tflite"))


def checker(tmp_path: Path) -> FaceChecker:
    face_checker = FaceChecker(tmp_path / "models")
    face_checker._paths = MODELS
    return face_checker


def test_checker_passes_a_large_straight_uncovered_face(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with patch.dict(sys.modules, fake_mediapipe()), caplog.at_level(logging.INFO):
        result = checker(tmp_path).check(photo(tmp_path, 600))
    assert result.problems == [] and result.score is not None and result.score > 90
    record = next(r for r in caplog.records if r.message == "Face checks done")
    assert record.faces == 1 and record.problems == 0  # type: ignore[attr-defined]
    assert record.score == result.score  # type: ignore[attr-defined]
    assert record.face_px > 500  # type: ignore[attr-defined]
    face_options, segment_options = FakeModel.opened
    assert face_options["base_options"] == str(MODELS[0]) and face_options["num_faces"] == 3
    assert segment_options["base_options"] == str(MODELS[1])
    assert FakeModel.closed == 2  # both models closed after use


def test_checker_reports_each_problem(tmp_path: Path) -> None:
    with patch.dict(sys.modules, fake_mediapipe(yaw=40, label=5)):
        found = checker(tmp_path).check(photo(tmp_path, 150))
        assert found == PhotoResult([TOO_SMALL, TURNED, COVERED])
    with patch.dict(sys.modules, fake_mediapipe(faces=2)):
        assert checker(tmp_path).check(photo(tmp_path, 600)) == PhotoResult([MANY_FACES])
        assert len(FakeModel.opened) == 1  # no need to segment
    with patch.dict(sys.modules, fake_mediapipe(faces=0)):
        assert checker(tmp_path).check(photo(tmp_path, 600)) == PhotoResult([NO_FACE])


def test_models_are_downloaded_once(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    face_checker = FaceChecker(tmp_path / "models")
    with (
        patch.dict(sys.modules, fake_mediapipe()),
        patch.object(face_checks, "ensure_models", return_value=MODELS) as ensure,
        caplog.at_level(logging.INFO),
    ):
        face_checker.check(photo(tmp_path, 600))
        face_checker.check(photo(tmp_path, 600))
    ensure.assert_called_once_with(tmp_path / "models")
    assert "Face check models ready" in caplog.text


def test_failed_model_download_turns_checks_off_until_restart(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    face_checker = FaceChecker(tmp_path / "models")
    failing = patch.object(face_checks, "ensure_models", side_effect=DownloadError("offline"))
    with (
        patch.dict(sys.modules, fake_mediapipe()),
        failing as ensure,
        caplog.at_level(logging.ERROR),
    ):
        for _ in range(2):
            with pytest.raises(FaceCheckError, match="offline"):
                face_checker.check(photo(tmp_path, 600))
    assert ensure.call_count == 1  # not retried on every photo
    assert "Face checks are off until restart" in caplog.text


def test_prepare_downloads_the_models_and_logs_a_failure_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    face_checker = FaceChecker(tmp_path / "models")
    with (
        patch.dict(sys.modules, fake_mediapipe(faces=0)),
        patch.object(face_checks, "ensure_models", return_value=MODELS) as ensure,
        caplog.at_level(logging.INFO),
    ):
        face_checker.prepare()
    ensure.assert_called_once()
    assert len(FakeModel.opened) == 1  # MediaPipe loaded once, ahead of the first photo
    assert "Face checks ready" in caplog.text
    broken = FaceChecker(tmp_path / "models")
    failing = patch.object(face_checks, "ensure_models", side_effect=DownloadError("offline"))
    with failing, caplog.at_level(logging.ERROR):
        broken.prepare()  # doesn't raise
    assert "Face checks are off until restart" in caplog.text


def test_a_big_photo_is_measured_as_the_engine_will_shrink_it(tmp_path: Path) -> None:
    # face_points fills 90% of the height; the engine shrinks the photo to MAX_SIDE first.
    with patch.dict(sys.modules, fake_mediapipe()):
        measure = checker(tmp_path).measure(photo(tmp_path, 2 * MAX_SIDE))
    assert measure.height_px == pytest.approx(MAX_SIDE * 0.9, rel=0.02)
