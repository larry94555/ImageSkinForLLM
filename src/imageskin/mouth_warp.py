"""Video engine that animates the mouth in a single photo, on the CPU, with OpenCV.

`prepare` finds the face with OpenCV's built-in face detector (no model download) and the line
where the lips meet. `render` opens the mouth in each frame as loud as the speech is at that
moment: the lower lip and chin are stretched down and the gap is filled with a dark mouth opening.
Frames are piped to ffmpeg, which adds the audio and writes an H.264 MP4.

It runs much faster than real time on a laptop CPU. The rest of the face stays still; head motion
and blinking come later (R23).
"""

import logging
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from imageskin.video import FPS, Face, VideoError, mouth_openness, read_pcm16

logger = logging.getLogger(__name__)

MAX_SIDE = 720  # longest side of the video, in pixels
MAX_DROP = 0.35  # how far the lower lip drops at full volume, as a share of lips-to-chin
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
    # Fill the gap between the lips with a soft-edged dark opening.
    mask = np.zeros(frame.shape[:2], dtype=np.float32)
    center = (face.mouth_x, face.mouth_y + int(drop / 2))
    axes = (max(1, int(0.42 * face.mouth_w)), max(1, int(drop / 2)))
    cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, -1)
    alpha = cv2.GaussianBlur(mask, (0, 0), max(1.0, drop / 6))[..., None]
    dark = np.array([30, 25, 45], dtype=np.float32)  # BGR, a dark red-brown
    return (frame * (1 - alpha) + dark * alpha).astype(np.uint8)


def find_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise VideoError(
            "ffmpeg not found; install it (Windows: winget install Gyan.FFmpeg), "
            "open a new terminal and check with: ffmpeg -version"
        )
    return ffmpeg


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
        box = max(faces, key=lambda f: f[2] * f[3])
        x, y, w, h = box
        mouth_y = find_lip_line(image, box)
        chin_y = min(image.shape[0] - 1, y + int(1.02 * h))
        face = Face(
            photo=photo,
            width=image.shape[1],
            height=image.shape[0],
            mouth_x=x + w // 2,
            mouth_y=mouth_y,
            mouth_w=max(4, int(0.42 * w)),
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
        cmd = [find_ffmpeg(), "-nostdin", "-y", "-v", "error"]
        cmd += ["-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{face.width}x{face.height}"]
        cmd += ["-r", str(FPS), "-i", "-", "-i", str(wav)]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
        cmd += ["-c:a", "aac", "-shortest", "-movflags", "+faststart", str(output)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.stdin is not None
        try:
            for o in openness:
                proc.stdin.write(draw_frame(image, face, region, weights, o).tobytes())
            _, err = proc.communicate(timeout=self._timeout_s)
        except BrokenPipeError:
            _, err = proc.communicate(timeout=self._timeout_s)
        except subprocess.TimeoutExpired as e:
            proc.kill()
            raise VideoError(f"ffmpeg took longer than {self._timeout_s:g} seconds") from e
        if proc.returncode != 0:
            detail = err.decode(errors="replace").strip().splitlines()[-1:] or ["no error output"]
            raise VideoError(f"ffmpeg could not write {output.name} ({detail[0]})")
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
