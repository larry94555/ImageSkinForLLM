"""Face checks on an uploaded photo (roadmap R8): exactly one face, large enough, facing the
camera, nothing covering it. Then the quality checks (roadmap R9): sharp, and evenly lit, not too
dark or bright. Each failed check gives a fixed message a nontechnical person can act on, and a
photo that passes them all gets a score from 0 to 100 so the best one can be picked.

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
from imageskin.liveportrait import FACE_MODEL_SHA256, FACE_MODEL_SIZE, FACE_MODEL_URL, MAX_SIDE
from imageskin.uploads import PhotoResult

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
BLURRY = "The photo is blurry. Hold the camera still and let it focus on your face."
TOO_DARK = "The photo is too dark. Turn on more lights, or face a window."
TOO_BRIGHT = "The photo is too bright. Move out of direct sunlight or away from a bright lamp."
UNEVEN = "One side of your face is in shadow. Face the light so it falls evenly on your face."

# The photoreal engine first shrinks a photo so its longest side is liveportrait.MAX_SIDE, then
# cuts a 512 x 512 square around the face about 2.3 times the face's height. The face is
# measured at that size, from mid-forehead to chin as MediaPipe's face points place them.
# Below this the 512 px square is blown up from a smaller area and the video looks soft. A face
# filling about a third of the height of a 1080p webcam photo measures about 200.
MIN_FACE_PX = 180
# How far the head may turn left or right, or tilt up or down, in degrees.
MAX_TURN_DEG = 25.0
# MediaPipe's face model reads about 10 degrees "up" on photos taken straight on, so
# up-and-down is measured from there.
LEVEL_PITCH_DEG = 10.0
# Share of the face below the eyebrows that may be hidden by something other than hair.
MAX_COVERED = 0.12

# Sharpness and light are measured on the face as the video engine sees it: its 512 x 512 square
# is 2.3 face heights, so the face is about this tall in the video.
VIDEO_FACE_PX = 222
# Sharpness: fine detail (the spread of the Laplacian) over the face's average grey level, so a
# dark photo doesn't count as blurry. Sharp phone photos measure 0.1 to 0.23 and a 720p webcam
# photo 0.1; the same photos blurred by 1.5 px in the video measure 0.02 to 0.04.
MIN_SHARPNESS = 0.05
# Light, on the face below the eyebrows, in Lab lightness from 0 to 255. Brightness is the
# lightness 90% of the face is below, so dark skin in good light still passes; a face in a dim
# room measures about 60, a lit one 140 to 210.
MIN_BRIGHTNESS = 75
# Share of the face that is pure white (lightness 250 or more), washed out by the light.
MAX_WASHED_OUT = 0.25
# The darker side of the face over the lighter side. A face lit from one side by a window
# measures about 0.5 and still looks fine; below this one side is in deep shadow.
MIN_EVENNESS = 0.4
NOSE_TIP = 1

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
    height_px: float = 0.0  # mid-forehead to chin, at the video engine's size (MAX_SIDE)
    yaw_deg: float = 0.0  # turned left or right
    pitch_deg: float = 0.0  # tilted up or down, from level
    covered: float = 0.0  # share of the face hidden, 0 to 1
    sharpness: float = 1.0  # fine detail over the grey level, see MIN_SHARPNESS
    brightness: float = 200.0  # lightness 90% of the face is below, 0 to 255
    washed_out: float = 0.0  # share of the face that is pure white, 0 to 1
    evenness: float = 1.0  # darker side of the face over the lighter side, 0 to 1


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
    if m.sharpness < MIN_SHARPNESS:
        found.append(BLURRY)
    if m.brightness < MIN_BRIGHTNESS:
        found.append(TOO_DARK)
    elif m.washed_out > MAX_WASHED_OUT:
        found.append(TOO_BRIGHT)
    if m.evenness < MIN_EVENNESS:
        found.append(UNEVEN)
    return found


def score(m: FaceMeasure) -> int:
    """How good a photo that passes every check is, from 0 to 100: the average of how sharp,
    large, straight, uncovered, bright and evenly lit the face is, each counted up to the point
    where more no longer helps the video."""
    parts = [
        m.sharpness / 0.12,
        m.height_px / VIDEO_FACE_PX,
        1 - max(abs(m.yaw_deg), abs(m.pitch_deg)) / MAX_TURN_DEG,
        1 - m.covered / MAX_COVERED,
        m.brightness / 150,
        m.evenness / 0.8,
    ]
    return round(100 * sum(min(1.0, max(0.0, p)) for p in parts) / len(parts))


def head_angles(matrix: NDArray[Any]) -> tuple[float, float]:
    """Yaw and pitch in degrees from MediaPipe's 4x4 face transformation matrix."""
    r = np.asarray(matrix, dtype=np.float64)[:3, :3]
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, -r[2, 0]))))
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    return yaw, pitch - LEVEL_PITCH_DEG


def covered_share(categories: NDArray[np.uint8], points: Points) -> float:
    """Share of the face, from the eyebrows down, labelled as something covering it."""
    area = face_area(categories.shape, points)
    brows = int(round(float(points[EYEBROWS, 1].mean())))
    area[: max(0, brows)] = False
    inside = categories[area]
    if inside.size == 0:
        return 0.0
    return float(np.isin(inside, COVERING).mean())


def face_area(shape: tuple[int, ...], points: Points) -> NDArray[np.bool_]:
    """The pixels inside the face's edge."""
    area = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(area, [np.round(points[FACE_OVAL]).astype(np.int32)], 1)
    return area > 0


def light_and_sharpness(rgb: NDArray[np.uint8], points: Points) -> dict[str, float]:
    """Sharpness, brightness, washed_out and evenness of the face, as FaceMeasure has them.

    The face is cut out and scaled to its size in the video first, so a big photo isn't judged
    on detail the video never shows."""
    top_left = np.maximum(points.min(axis=0) - 2, 0).astype(int)
    bottom_right = np.ceil(points.max(axis=0) + 2).astype(int)
    scale = VIDEO_FACE_PX / max(1.0, float(points[:, 1].max() - points[:, 1].min()))
    shrink = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    crop = cv2.resize(
        rgb[top_left[1] : bottom_right[1], top_left[0] : bottom_right[0]],
        None,
        fx=scale,
        fy=scale,
        interpolation=shrink,
    )
    points = (points - top_left) * scale

    # Sharpness inside the face, away from its edge, where the background starts.
    inside = cv2.erode(face_area(crop.shape, points).astype(np.uint8), np.ones((9, 9), np.uint8))
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY).astype(np.float32)
    detail = cv2.Laplacian(gray, cv2.CV_32F)[inside > 0]
    grey_level = float(gray[inside > 0].mean()) if detail.size else 0.0
    sharpness = float(detail.std()) / max(grey_level, 1.0) if detail.size else 0.0

    # Light on the face below the eyebrows (hair and eye sockets would read as shadow).
    face = face_area(crop.shape, points)
    face[: max(0, int(round(float(points[EYEBROWS, 1].mean()))))] = False
    lightness = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)[..., 0].astype(np.float32)
    if not face.any():
        return {"sharpness": sharpness, "brightness": 0.0, "washed_out": 0.0, "evenness": 0.0}
    left = face & (np.arange(face.shape[1]) < points[NOSE_TIP, 0])
    sides = [float(lightness[side].mean()) for side in (left, face & ~left) if side.any()]
    return {
        "sharpness": sharpness,
        "brightness": float(np.percentile(lightness[face], 90)),
        "washed_out": float((lightness[face] >= 250).mean()),
        "evenness": min(sides) / max(max(sides), 1.0),
    }


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
            height_px=float(points[:, 1].max() - points[:, 1].min())
            * min(1.0, MAX_SIDE / max(h, w)),
            yaw_deg=yaw,
            pitch_deg=pitch,
            covered=covered_share(categories, points),
            **light_and_sharpness(rgb, points),
        )

    def check(self, photo: Path) -> PhotoResult:
        """The problems found in the photo, and its score when there are none."""
        start = time.perf_counter()
        with self._lock:  # one photo at a time keeps memory and CPU use down
            m = self.measure(photo)
        found = problems(m)
        result = PhotoResult(found, None if found else score(m))
        logger.info(
            "Face checks done",
            extra={
                "photo": photo.name,
                "faces": m.faces,
                "face_px": round(m.height_px),
                "yaw_deg": round(m.yaw_deg, 1),
                "pitch_deg": round(m.pitch_deg, 1),
                "covered": round(m.covered, 3),
                "sharpness": round(m.sharpness, 3),
                "brightness": round(m.brightness),
                "washed_out": round(m.washed_out, 3),
                "evenness": round(m.evenness, 2),
                "problems": len(found),
                "score": result.score,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return result
