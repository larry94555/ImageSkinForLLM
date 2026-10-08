"""Render a photoreal video whose face follows the voice's loudness and pitch.

Usage (after `imageskin say ... -o mine.wav`, which also writes mine.json):

    python experiments/expressive/expressive.py LIBRARY_FOLDER mine.wav after.mp4

LIBRARY_FOLDER is the photo's frame library (~/.imageskin/photoreal/<key>). No model runs:
the extra motion is drawn with small smooth warps on top of today's engine (R4c), which
stays as it is:
  - jaw: louder syllables open wider and quiet ones a little less, scaled by how open the
    mouth shape already is, so m, b, p, f and v still close;
  - brows: lift on high or stressed words;
  - head: a gentle nod on the strongest beat of a phrase, a tilt with the pitch and a slow
    side-to-side drift while speaking.
"""

from __future__ import annotations

import logging
import math
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

sys.path.insert(0, str(Path(__file__).parent))

from prosody import DEFAULT_GAINS, Gains, Motion, motion  # noqa: E402

from imageskin.liveportrait_edits import MOUTH_SHAPES, eye_track, top_two  # noqa: E402
from imageskin.photoreal import Compositor, audio_seed, read_shapes  # noqa: E402
from imageskin.photoreal_library import CROP, Image, Library, load_library, pixel_grid  # noqa: E402
from imageskin.video import FPS, read_pcm16, write_mp4  # noqa: E402
from imageskin.visemes import CONTACT, frame_weights  # noqa: E402

logger = logging.getLogger(__name__)

Field = NDArray[np.float32]
MOST_OPEN = max(s.ratio or 0.0 for s in MOUTH_SHAPES.values())


def openness(weights: dict[str, float]) -> float:
    """How open the mouth shapes in this frame are, 0 (closed or lips touching) to 1."""
    return sum(
        w * (MOUTH_SHAPES[k].ratio or 0.0) / MOST_OPEN
        for k, w in weights.items()
        if k not in CONTACT
    )


def _taper(d: NDArray[np.float64], inner: float, outer: float) -> NDArray[np.float64]:
    """1 within `inner`, easing to 0 at `outer` (a raised cosine)."""
    s = np.clip((d - inner) / max(1e-6, outer - inner), 0.0, 1.0)
    return 0.5 * (1 + np.cos(math.pi * s))


def jaw_field(lm: NDArray[np.float32], window: tuple[int, int, int, int]) -> Field:
    """How far each pixel of the mouth patch moves down per pixel of extra opening: the lower
    lip and jaw the whole way, the chin less, the upper lip a quarter of the way up."""
    x0, y0, x1, y1 = window
    lip = float((lm[62, 1] + lm[66, 1]) / 2)
    chin = float(lm[8, 1])
    cx = float(lm[48:68, 0].mean())
    half = float(np.ptp(lm[48:60, 0])) / 2
    ys = np.arange(y0, y1, dtype=np.float64)
    xs = np.arange(x0, x1, dtype=np.float64)
    v = np.interp(
        ys,
        [y0, lip - 30, lip - 12, lip - 2, lip + 6, lip + 30, chin, y1 - 1],
        [0.0, 0.0, -0.25, -0.25, 1.0, 1.0, 0.6, 0.0],
    )
    h = _taper(np.abs(xs - cx), 0.6 * half, min(2.0 * half, cx - x0 - 2, x1 - cx - 2))
    return np.asarray(v[:, None] * h[None, :], np.float32)


def brow_field(lm: NDArray[np.float32], window: tuple[int, int, int, int]) -> Field:
    """How far each pixel of the eye patch moves up per pixel of brow lift."""
    x0, y0, x1, y1 = window
    brow = float(lm[17:27, 1].mean())
    eye = float(lm[36:48, 1].mean())
    ys = np.arange(y0, y1, dtype=np.float64)
    xs = np.arange(x0, x1, dtype=np.float64)
    v = np.interp(ys, [y0, brow - 25, brow - 8, brow + 6, eye - 6, y1 - 1], [0, 0.5, 1, 1, 0, 0])
    left, right = float(lm[17, 0]), float(lm[26, 0])
    cx, half = (left + right) / 2, (right - left) / 2
    h = _taper(np.abs(xs - cx), half - 5, min(half + 20, cx - x0 - 2, x1 - cx - 2))
    return np.asarray(v[:, None] * h[None, :], np.float32)


def head_weight(lm: NDArray[np.float32]) -> Field:
    """How much of the head's nod and tilt each pixel of the face crop takes: all of it over
    the head, easing to none well before the crop's edge, so the paste stays seamless."""
    gy, gx = np.mgrid[0:CROP, 0:CROP].astype(np.float64)
    cx, cy = float(lm[:, 0].mean()), float(lm[:, 1].mean()) - 20
    fade, margin = 1.6, 10.0  # the outermost 10 px never move
    rx = min(150.0, (min(cx, CROP - 1 - cx) - margin) / fade)
    up, down = (cy - margin) / fade, (CROP - 1 - cy - margin) / fade
    ry = np.where(gy < cy, min(180.0, up), min(140.0, down))
    r = np.sqrt(((gx - cx) / rx) ** 2 + ((gy - cy) / ry) ** 2)
    return np.asarray(_taper(r, 1.0, fade), np.float32)


def _push(image: Image, grid: Field, dx: Field | float, dy: Field) -> Image:
    """Move pixels by (dx, dy): each output pixel takes the colour from where it came."""
    m = grid.copy()
    m[..., 0] -= dx
    m[..., 1] -= dy
    out = cv2.remap(image, m, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return np.asarray(out, np.uint8)


class ExpressiveCompositor(Compositor):
    def __init__(self, lib: Library) -> None:
        super().__init__(lib)
        lm = np.load(lib.folder / "crop_landmarks.npy")
        self.jaw = jaw_field(lm, lib.window)
        self.brow = brow_field(lm, lib.eye_window)
        self.head = head_weight(lm)
        self.mouth_grid = pixel_grid(self.morph.faces["rest"])
        self.eye_grid = pixel_grid(self.eyes.morph.faces["0"])
        self.crop_grid = pixel_grid(lib.shapes["rest"])
        self.pivot = (float(lm[8, 0]), float(lm[8, 1]) + 40)  # below the chin, at the neck

    def expressive_face(
        self, weights: dict[str, float], frame: int, eye_open: float, m: Motion, i: int
    ) -> Image:
        lib = self.lib
        j = frame % len(lib.loop)
        face = lib.loop[j].copy()
        mouth_box, eye_box = self.boxes
        mouth = self.morph(*top_two(weights))
        jaw = float(m.jaw[i]) * openness(weights)
        if abs(jaw) > 0.05:
            mouth = _push(mouth, self.mouth_grid, 0.0, jaw * self.jaw)
        self._put(face, mouth, lib.window, mouth_box, lib.align[j], lib.mouth)
        eyes = self.eyes(eye_open)
        if m.brow[i] > 0.05:
            eyes = _push(eyes, self.eye_grid, 0.0, -float(m.brow[i]) * self.brow)
        self._put(face, eyes, lib.eye_window, eye_box, lib.eye_align[j], lib.eye_mask)

        # The whole head turns about the neck and drops, fading out toward the crop's edge.
        a = math.radians(float(m.tilt[i]))
        px, py = self.pivot
        gx = self.crop_grid[..., 0] - px
        gy = self.crop_grid[..., 1] - py
        dx = (math.cos(a) - 1) * gx - math.sin(a) * gy + float(m.sway[i])
        dy = math.sin(a) * gx + (math.cos(a) - 1) * gy + float(m.nod[i])
        return _push(face, self.crop_grid, dx * self.head, dy * self.head)


def render(lib: Library, wav: Path, output: Path, gains: Gains = DEFAULT_GAINS) -> float:
    start = time.perf_counter()
    samples, rate = read_pcm16(wav)
    audio = np.asarray(samples, np.float32) / 32768.0
    n_frames = max(1, round(len(samples) / rate * FPS))
    weights = frame_weights(read_shapes(wav.with_suffix(".json")), n_frames, FPS)
    eyes = eye_track(n_frames, FPS, seed=audio_seed(samples))
    m = motion(audio, rate, n_frames, FPS, gains)
    comp = ExpressiveCompositor(lib)

    def frames() -> Iterator[bytes]:
        for i, w in enumerate(weights):
            yield comp.paste(comp.expressive_face(w, i, eyes[i], m, i)).tobytes()

    h, w = lib.photo.shape[:2]
    write_mp4(frames(), (w, h), wav, output, 600.0, pix_fmt="rgb24")
    elapsed = time.perf_counter() - start
    logger.info(
        "Rendered expressive video",
        extra={
            "output": str(output),
            "frames": n_frames,
            "duration_ms": round(elapsed * 1000, 1),
            "real_time_factor": round(elapsed / (n_frames / FPS), 2),
        },
    )
    np.savez(
        output.with_suffix(".motion.npz"),
        jaw=m.jaw,
        brow=m.brow,
        nod=m.nod,
        tilt=m.tilt,
        sway=m.sway,
    )
    return elapsed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    folder, wav, out = (Path(a) for a in sys.argv[1:4])
    print(f"rendered in {render(load_library(folder), wav, out):.1f} s")
