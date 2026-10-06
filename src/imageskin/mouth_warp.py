"""Video engine that animates the mouth in a single photo, on the CPU, with OpenCV.

`prepare` finds the face with OpenCV's built-in face detector (no model download) and the line
where the lips meet. `render` opens the mouth in each frame as loud as the speech is at that
moment: the lower lip and chin are stretched down a little and the gap is filled with a soft,
dark-red mouth opening, with a hint of upper teeth on the louder sounds. These are the "softer"
settings Larry picked from the side-by-side test in GitHub PR #9.
Frames are piped to ffmpeg, which adds the audio and writes an H.264 MP4.

It runs much faster than real time on a laptop CPU. The rest of the face stays still; head motion
and blinking come later (R23).
"""

import logging
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from imageskin.video import (
    Face,
    VideoError,
    find_ffmpeg,
    mouth_openness,
    read_pcm16,
    write_mp4,
)

logger = logging.getLogger(__name__)

MAX_SIDE = 720  # longest side of the video, in pixels
MAX_DROP = 0.1  # how far the lower lip drops at full volume, as a share of lips-to-chin
TEETH_FROM = 0.53  # openness above which the upper teeth start to show
DEFAULT_TIMEOUT_S = 300.0

CASCADE = "haarcascade_frontalface_default.xml"  # bundled with opencv-python 4.x

Box = tuple[int, int, int, int]  # x, y, width, height
Image = NDArray[np.uint8]


def detect_faces(gray: Image) -> list[Box]:
    """Find frontal faces with the Haar cascade that ships with OpenCV."""
    path = Path(cv2.__file__).parent / "data" / CASCADE
    cascade = cv2.CascadeClassifier(str(path))
    if cascade.empty():  # missing file, or a non-ASCII path OpenCV can't open on Windows
        raise VideoError(f"could not load OpenCV's face detector from {path}")
    side = min(gray.shape[:2]) // 6
    found = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(side, side))
    return [(int(x), int(y), int(w), int(h)) for x, y, w, h in found]


def load_photo(photo: Path) -> Image:
    """Read a photo and shrink it so the longest side is at most MAX_SIDE, with even sides."""
    if not photo.is_file():
        raise VideoError(f"{photo}: file not found")
    # imdecode rather than imread: imread can't open non-ASCII paths on Windows.
    data = np.fromfile(photo, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if image is None:
        raise VideoError(f"could not read {photo} as an image (use JPEG or PNG)")
    h, w = image.shape[:2]
    scale = min(1.0, MAX_SIDE / max(h, w))
    size = (max(2, int(w * scale) // 2 * 2), max(2, int(h * scale) // 2 * 2))
    if size != (w, h):
        image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(image, dtype=np.uint8)


def find_lip_line(image: Image, face: Box) -> int:
    """Find the row where the lips meet, from how red each row is in the lower part of the face.

    Lips are redder than the skin around them, so the middle of the reddest rows is where the lips
    meet (or the middle of the mouth, if it is open). This is not fooled by the dark shadow under
    the nose the way looking for the darkest row is.
    """
    x, y, w, h = face
    top, bottom = y + int(0.66 * h), min(image.shape[0], y + int(0.98 * h))
    left, right = x + int(0.38 * w), x + int(0.62 * w)
    band = cv2.cvtColor(image[top:bottom, left:right], cv2.COLOR_BGR2LAB)
    if band.size == 0:
        return y + int(0.8 * h)
    redness = band[..., 1].astype(np.float64).mean(axis=1)
    weight = np.clip(redness - np.median(redness), 0, None) ** 2
    if weight.sum() == 0:
        return y + int(0.8 * h)
    return top + round(float((weight * np.arange(len(weight))).sum() / weight.sum()))


def refine_lip_line(image: Image, mouth_x: int, mouth_y: int, mouth_w: int, jaw_h: int) -> int:
    """Move the lip line onto the darkest row near it: the seam between closed lips.

    The redness centre can land a few pixels off on pale lips. Only a short way up is searched,
    since the shadow under the nose is dark too.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float64)
    reach = max(3, jaw_h // 3)
    top = max(0, mouth_y - reach // 2)
    half = max(2, mouth_w // 4)
    band = gray[top : mouth_y + reach + 1, max(0, mouth_x - half) : mouth_x + half]
    if band.shape[0] < 3 or band.shape[1] == 0:
        return mouth_y
    rows = np.convolve(band.mean(axis=1), np.ones(3) / 3, mode="same")
    rows[0] = rows[-1] = np.inf  # the ends average in rows outside the band
    return top + int(np.argmin(rows))


def frame_weights(face: Face) -> tuple[Box, NDArray[np.float32]]:
    """The region that moves and, per pixel, how much of the full drop it gets (0 to 1)."""
    half_w = face.mouth_w // 2 + face.mouth_w // 4
    x0, x1 = max(0, face.mouth_x - half_w), min(face.width, face.mouth_x + half_w)
    y0 = max(0, face.mouth_y - 2)
    y1 = min(face.height, face.mouth_y + int(1.4 * face.jaw_h))
    xs = (np.arange(x0, x1, dtype=np.float32) - face.mouth_x) / half_w
    wx = np.clip(1 - xs**2, 0, 1) ** 2
    ys = np.arange(y0, y1, dtype=np.float32) - face.mouth_y
    # Nothing above the lips moves; the lower lip and chin move fully; below the chin fades out.
    wy = np.clip(ys / 2, 0, 1) * np.clip((1.4 * face.jaw_h - ys) / (0.4 * face.jaw_h), 0, 1)
    return (x0, y0, x1 - x0, y1 - y0), np.outer(wy, wx).astype(np.float32)


def draw_frame(
    image: Image, face: Face, region: Box, weights: NDArray[np.float32], o: float
) -> Image:
    """Return a copy of the photo with the mouth opened by `o` (0 closed, 1 fully open)."""
    frame = image.copy()
    drop = o * MAX_DROP * face.jaw_h
    if drop < 0.5:
        return frame
    x, y, w, h = region
    roi = image[y : y + h, x : x + w]
    grid_x, grid_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    # Each moved pixel takes its colour from `drop` pixels higher up, so the jaw slides down.
    moved = cv2.remap(
        roi, grid_x, grid_y - drop * weights, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )
    frame[y : y + h, x : x + w] = moved
    # Fill the gap between the lips with a soft-edged, partly see-through opening. It is
    # almond-shaped, tallest in the middle and closing towards the corners of the lips, rather
    # than a slot of even height. Only a patch around the mouth is blended, to keep frames fast.
    half_w = max(1, round(0.45 * face.mouth_w))  # about the corners of the lips
    sigma = max(0.7, drop / 6)
    pad = int(3 * sigma) + 2
    px0, px1 = max(0, face.mouth_x - half_w - pad), min(face.width, face.mouth_x + half_w + pad)
    py0, py1 = max(0, face.mouth_y - pad), min(face.height, face.mouth_y + int(drop) + pad)
    patch = frame[py0:py1, px0:px1].astype(np.float32)
    dx = np.arange(px0, px1, dtype=np.float32) - face.mouth_x
    gap = drop * np.clip(1 - (dx / half_w) ** 2, 0, 1) ** 1.5  # height of the opening per column
    dy = np.arange(py0, py1, dtype=np.float32)[:, None] - face.mouth_y
    # Share of each pixel inside the opening, which runs from the lip line down `gap` pixels.
    inside_gap = np.minimum(dy + 0.5, gap[None, :] - dy + 0.5)
    # Columns that open less than a pixel only get a faint shadow, not a line.
    mask = (np.clip(inside_gap, 0, 1) * np.clip(gap, 0, 1)[None, :]).astype(np.float32)
    alpha = 0.75 * cv2.GaussianBlur(mask, (0, 0), sigma)[..., None]
    cx, cy = face.mouth_x - px0, face.mouth_y - py0
    inside = np.array([45, 40, 70], dtype=np.float32)  # BGR, a dark warm red
    patch = patch * (1 - alpha) + inside * alpha
    if o > TEETH_FROM:
        # A faint band of upper teeth just under the upper lip.
        teeth = np.zeros(patch.shape[:2], dtype=np.float32)
        th = max(1, int(drop * 0.18))
        cv2.ellipse(teeth, (cx, cy + th), (int(half_w * 0.3), th), 0, 0, 180, 1.0, -1)
        strength = 0.2 * (o - TEETH_FROM) / (1 - TEETH_FROM)
        t_alpha = strength * cv2.GaussianBlur(teeth, (0, 0), 1.0)[..., None]
        patch = patch * (1 - t_alpha) + np.array([200, 205, 215], dtype=np.float32) * t_alpha
    frame[py0:py1, px0:px1] = patch.astype(np.uint8)
    return frame


class MouthWarpEngine:
    def __init__(
        self,
        detect: Callable[[Image], list[Box]] = detect_faces,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._detect = detect
        self._timeout_s = timeout_s

    def prepare(self, photo: Path) -> Face:
        start = time.perf_counter()
        find_ffmpeg()  # fail now, not after the slower speech step
        image = load_photo(photo)
        gray = np.asarray(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), dtype=np.uint8)
        faces = self._detect(gray)
        if not faces:
            raise VideoError(
                f"no face found in {photo.name}; "
                "use a front-facing photo with the whole face visible"
            )
        if len(faces) > 1:
            raise VideoError(
                f"found {len(faces)} faces in {photo.name}; use a photo with exactly one face"
            )
        box = faces[0]
        x, y, w, h = box
        chin_y = min(image.shape[0] - 1, y + int(1.02 * h))
        mouth_x, mouth_w = x + w // 2, max(4, int(0.42 * w))
        red_y = find_lip_line(image, box)
        mouth_y = refine_lip_line(image, mouth_x, red_y, mouth_w, max(4, chin_y - red_y))
        face = Face(
            photo=photo,
            width=image.shape[1],
            height=image.shape[0],
            mouth_x=mouth_x,
            mouth_y=mouth_y,
            mouth_w=mouth_w,
            jaw_h=max(4, chin_y - mouth_y),
        )
        logger.info(
            "Prepared face",
            extra={
                "photo": str(photo),
                "faces_found": len(faces),
                "face_box": box,
                "mouth": [face.mouth_x, face.mouth_y, face.mouth_w, face.jaw_h],
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return face

    def render(self, face: Face, wav: Path, output: Path) -> float:
        start = time.perf_counter()
        samples, rate = read_pcm16(wav)
        openness = mouth_openness(samples, rate)
        if not openness:
            raise VideoError(f"{wav.name} has no audio")
        image = load_photo(face.photo)
        if image.shape[:2] != (face.height, face.width):
            raise VideoError(f"{face.photo.name} changed since it was prepared; prepare it again")
        region, weights = frame_weights(face)
        frames = (draw_frame(image, face, region, weights, o).tobytes() for o in openness)
        write_mp4(frames, (face.width, face.height), wav, output, self._timeout_s)
        seconds = len(samples) / rate
        elapsed = time.perf_counter() - start
        logger.info(
            "Rendered video",
            extra={
                "output": str(output),
                "frames": len(openness),
                "video_s": round(seconds, 2),
                "duration_ms": round(elapsed * 1000, 1),
                # Below 1.0 means faster than real time.
                "real_time_factor": round(elapsed / seconds, 2) if seconds else None,
            },
        )
        return seconds
