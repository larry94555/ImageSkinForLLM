"""Face checks on an uploaded photo (roadmap R8): exactly one face, large enough, facing the
camera, nothing covering it. Each failed check gives a fixed message a nontechnical person can
act on.

Uses two MediaPipe models (Apache 2.0, about 20 MB, downloaded on first use): the face
landmarker finds the faces, their size and which way the head is turned, and the multiclass
selfie segmenter labels each pixel as face skin, hair, body skin, clothes or other things, which
shows hands, masks and sunglasses in front of the face. Needs the faces extra:
pip install -e ".[faces]" (the photoreal extra also has what it needs).
"""

import logging
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from imageskin.download import DownloadError, download

logger = logging.getLogger(__name__)

NO_FACE = (
    "No face was found. Use a photo where your face is clear and fills a good part of the picture."
)
MANY_FACES = "More than one face was found. Use a photo with only you in it."
TOO_SMALL = "Your face is too small. Move closer to the camera, or crop the photo around your face."
TURNED = "Your face is turned away. Look straight at the camera."
COVERED = (
    "Something is covering your face. Take off sunglasses or a mask, and keep hands and hair"
    " away from your face."
)

# Face height from mid-forehead to chin, as MediaPipe's face points measure it. The whole face
# up to the hairline is about a fifth taller, so this asks for a face about 500 px tall.
MIN_FACE_PX = 400
# How far the head may turn left or right, or tilt up or down, in degrees.
MAX_TURN_DEG = 25.0
# MediaPipe's face model reads about 10 degrees "up" on photos taken straight on, so
# up-and-down is measured from there.
LEVEL_PITCH_DEG = 10.0
# Share of the face below the eyebrows that may be hidden by something other than hair.
MAX_COVERED = 0.12

FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
FACE_MODEL_SIZE = 3758596
FACE_MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
SEGMENT_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
    "selfie_multiclass_256x256/float32/1/selfie_multiclass_256x256.tflite"
)
SEGMENT_MODEL_SIZE = 16371837
SEGMENT_MODEL_SHA256 = "c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0"

# The segmenter's labels: 0 background, 1 hair, 2 body skin, 3 face skin, 4 clothes, 5 other.
# Hair is allowed (beards, a fringe); hands, masks and sunglasses are not.
COVERING = (2, 4, 5)
# MediaPipe face points around the edge of the face, in order.
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400]
FACE_OVAL += [377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103]
FACE_OVAL += [67, 109]
EYEBROWS = [105, 334]  # the middle of each eyebrow

Points = NDArray[np.float32]


class FaceCheckError(Exception):
    """A photo could not be checked: unreadable, or the models could not be loaded."""


@dataclass(frozen=True)
class FaceMeasure:
    """What the checks look at, for the first face found."""

    faces: int
    height_px: float = 0.0
    yaw_deg: float = 0.0  # turned left or right
    pitch_deg: float = 0.0  # tilted up or down, from level
    covered: float = 0.0  # share of the face hidden, 0 to 1


def problems(m: FaceMeasure) -> list[str]:
    """The fixed message for each failed check, in the order they should be fixed."""
    if m.faces == 0:
        return [NO_FACE]
    if m.faces > 1:
        return [MANY_FACES]
    found = []
    if m.height_px < MIN_FACE_PX:
        found.append(TOO_SMALL)
    if abs(m.yaw_deg) > MAX_TURN_DEG or abs(m.pitch_deg) > MAX_TURN_DEG:
        found.append(TURNED)
    if m.covered > MAX_COVERED:
        found.append(COVERED)
    return found


def head_angles(matrix: NDArray[Any]) -> tuple[float, float]:
    """Yaw and pitch in degrees from MediaPipe's 4x4 face transformation matrix."""
    r = np.asarray(matrix, dtype=np.float64)[:3, :3]
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, -r[2, 0]))))
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    return yaw, pitch - LEVEL_PITCH_DEG


def covered_share(categories: NDArray[np.uint8], points: Points) -> float:
    """Share of the face, from the eyebrows down, labelled as something covering it."""
    area = np.zeros(categories.shape, np.uint8)
    cv2.fillPoly(area, [np.round(points[FACE_OVAL]).astype(np.int32)], 1)
    brows = int(round(float(points[EYEBROWS, 1].mean())))
    area[: max(0, brows)] = 0
    inside = categories[area > 0]
    if inside.size == 0:
        return 0.0
    return float(np.isin(inside, COVERING).mean())


def read_rgb(photo: Path) -> NDArray[np.uint8]:
    """The photo as RGB, turned upright as its EXIF data says (phones store it sideways)."""
    data = np.fromfile(photo, dtype=np.uint8)  # works with non-ASCII paths on Windows
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if bgr is None:
        raise FaceCheckError(f"could not read {photo.name} as an image")
    return np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def ensure_models(models_dir: Path) -> tuple[Path, Path]:
    """Download the two MediaPipe models once; return their paths."""
    face = models_dir / "face_landmarker.task"
    segment = models_dir / "selfie_multiclass_256x256.tflite"
    download(FACE_MODEL_URL, face, FACE_MODEL_SIZE, FACE_MODEL_SHA256)
    download(SEGMENT_MODEL_URL, segment, SEGMENT_MODEL_SIZE, SEGMENT_MODEL_SHA256)
    return face, segment


class FaceChecker:
    """Checks photos one at a time. Called from the upload request, so a photo is checked as
    it arrives. The models are opened for each photo (about 0.3 s) and closed again, since
    MediaPipe prints errors when models still open are closed as Python exits."""

    def __init__(self, models_dir: Path) -> None:
        self._models_dir = models_dir
        self._lock = threading.Lock()
        self._paths: tuple[Path, Path] | None = None
        self._broken: str | None = None

    def _model_paths(self) -> tuple[Path, Path]:
        if self._broken is not None:
            raise FaceCheckError(self._broken)
        if self._paths is None:
            start = time.perf_counter()
            try:
                self._paths = ensure_models(self._models_dir)
            except (DownloadError, OSError) as e:
                # Don't retry on every photo: a failed download retries for minutes.
                self._broken = f"face check models could not be downloaded: {e}"
                logger.error("Face checks are off until restart", extra={"error": str(e)})
                raise FaceCheckError(self._broken) from e
            logger.info(
                "Face check models ready",
                extra={
                    "path": str(self._models_dir),
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
        return self._paths

    def prepare(self) -> None:
        """Download the models if needed and load MediaPipe once, so the first photo is checked
        as fast as the rest. A failure is logged and leaves the checks off."""
        with self._lock:
            try:
                self._model_paths()
            except FaceCheckError:
                return  # already logged
            start = time.perf_counter()
            self.measure_rgb(np.zeros((64, 64, 3), np.uint8))
            logger.info(
                "Face checks ready",
                extra={"duration_ms": round((time.perf_counter() - start) * 1000, 1)},
            )

    def measure(self, photo: Path) -> FaceMeasure:
        return self.measure_rgb(read_rgb(photo))

    def measure_rgb(self, rgb: NDArray[np.uint8]) -> FaceMeasure:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        face_model, segment_model = self._model_paths()
        h, w = rgb.shape[:2]
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        face_options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(face_model)),
            num_faces=3,
            output_facial_transformation_matrixes=True,
        )
        with vision.FaceLandmarker.create_from_options(face_options) as landmarker:
            found = landmarker.detect(image)
        faces = len(found.face_landmarks)
        if faces != 1:
            return FaceMeasure(faces=faces)
        segment_options = vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(segment_model)),
            output_category_mask=True,
        )
        with vision.ImageSegmenter.create_from_options(segment_options) as segmenter:
            categories = segmenter.segment(image).category_mask.numpy_view().copy()
        points = np.array([[p.x * w, p.y * h] for p in found.face_landmarks[0]], np.float32)
        yaw, pitch = head_angles(found.facial_transformation_matrixes[0])
        return FaceMeasure(
            faces=1,
            height_px=float(points[:, 1].max() - points[:, 1].min()),
            yaw_deg=yaw,
            pitch_deg=pitch,
            covered=covered_share(categories, points),
        )

    def check(self, photo: Path) -> list[str]:
        """The problems found in the photo; an empty list when it passes every check."""
        start = time.perf_counter()
        with self._lock:  # one photo at a time keeps memory and CPU use down
            m = self.measure(photo)
        found = problems(m)
        logger.info(
            "Face checks done",
            extra={
                "photo": photo.name,
                "faces": m.faces,
                "face_px": round(m.height_px),
                "yaw_deg": round(m.yaw_deg, 1),
                "pitch_deg": round(m.pitch_deg, 1),
                "covered": round(m.covered, 3),
                "problems": len(found),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return found
