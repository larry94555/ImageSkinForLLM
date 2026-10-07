import logging
import math
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from imageskin import face_checks
from imageskin.download import DownloadError
from imageskin.face_checks import (
    COVERED,
    EYEBROWS,
    FACE_OVAL,
    MANY_FACES,
    NO_FACE,
    TOO_SMALL,
    TURNED,
    FaceChecker,
    FaceCheckError,
    FaceMeasure,
    covered_share,
    head_angles,
    problems,
    read_rgb,
)

GOOD = FaceMeasure(faces=1, height_px=600, yaw_deg=5, pitch_deg=-3, covered=0.02)


@pytest.mark.parametrize(
    ("measure", "expected"),
    [
        (GOOD, []),
        (FaceMeasure(faces=0), [NO_FACE]),
        (FaceMeasure(faces=3), [MANY_FACES]),
        (FaceMeasure(faces=1, height_px=300), [TOO_SMALL]),
        (FaceMeasure(faces=1, height_px=600, yaw_deg=-40), [TURNED]),
        (FaceMeasure(faces=1, height_px=600, pitch_deg=30), [TURNED]),
        (FaceMeasure(faces=1, height_px=600, covered=0.3), [COVERED]),
        (
            FaceMeasure(faces=1, height_px=100, yaw_deg=40, covered=0.5),
            [TOO_SMALL, TURNED, COVERED],
        ),
    ],
)
def test_each_failed_check_gives_its_message(measure: FaceMeasure, expected: list[str]) -> None:
    assert problems(measure) == expected


def test_messages_are_plain_sentences() -> None:
    for message in (NO_FACE, MANY_FACES, TOO_SMALL, TURNED, COVERED):
        assert message.endswith(".") and len(message) < 120


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


def photo(tmp_path: Path, size: int) -> Path:
    path = tmp_path / "me.png"
    path.write_bytes(cv2.imencode(".png", np.zeros((size, size, 3), np.uint8))[1].tobytes())
    return path


MODELS = (Path("face.task"), Path("segment.tflite"))


def checker(tmp_path: Path) -> FaceChecker:
    face_checker = FaceChecker(tmp_path / "models")
    face_checker._paths = MODELS
    return face_checker


def test_checker_passes_a_large_straight_uncovered_face(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with patch.dict(sys.modules, fake_mediapipe()), caplog.at_level(logging.INFO):
        assert checker(tmp_path).check(photo(tmp_path, 600)) == []
    record = next(r for r in caplog.records if r.message == "Face checks done")
    assert record.faces == 1 and record.problems == 0  # type: ignore[attr-defined]
    assert record.face_px > 500  # type: ignore[attr-defined]
    face_options, segment_options = FakeModel.opened
    assert face_options["base_options"] == str(MODELS[0]) and face_options["num_faces"] == 3
    assert segment_options["base_options"] == str(MODELS[1])
    assert FakeModel.closed == 2  # both models closed after use


def test_checker_reports_each_problem(tmp_path: Path) -> None:
    with patch.dict(sys.modules, fake_mediapipe(yaw=40, label=5)):
        assert checker(tmp_path).check(photo(tmp_path, 200)) == [TOO_SMALL, TURNED, COVERED]
    with patch.dict(sys.modules, fake_mediapipe(faces=2)):
        assert checker(tmp_path).check(photo(tmp_path, 600)) == [MANY_FACES]
        assert len(FakeModel.opened) == 1  # no need to segment
    with patch.dict(sys.modules, fake_mediapipe(faces=0)):
        assert checker(tmp_path).check(photo(tmp_path, 600)) == [NO_FACE]


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
