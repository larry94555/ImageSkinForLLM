"""Photoreal video engine: each reply is mixed from the frame library, with no model run.

`prepare` builds the photo's frame library once (see `photoreal_library`) and loads it.
`render` turns the sound timings into mouth-shape weights per frame (`imageskin.visemes`),
morphs between the two strongest shapes along the optical flow between them, places that
mouth on the matching idle-loop frame, adds the blinks (at natural, irregular times from
`liveportrait_edits.eye_track`), moves the jaw, brows and head with the voice's loudness and
pitch (`imageskin.expression`), pastes the face back into the photo and encodes the MP4 with
the voice.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from array import array
from collections.abc import Callable, Iterator
from itertools import pairwise
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from imageskin.config import default_home
from imageskin.expression import (
    STILL,
    FrameMotion,
    brow_field,
    head_weight,
    jaw_field,
    motion,
    openness,
    push,
)
from imageskin.liveportrait_edits import EYE_STAGES, eye_track, top_two
from imageskin.photoreal_library import (
    CROP,
    Image,
    Library,
    Mask,
    Paster,
    PortraitLike,
    Window,
    liveportrait_factory,
    morph,
    optical_flow,
    pixel_grid,
    prepare_library,
    to_gray,
)
from imageskin.video import FPS, VideoError, find_ffmpeg, read_pcm16, write_mp4
from imageskin.visemes import ShapeTiming, frame_weights

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 300.0


class ShapeMorph:
    """In-between shapes: two shapes warped toward each other along their optical flow and
    blended, which keeps one set of lips (or lids) instead of the double ones of a plain
    cross-fade."""

    def __init__(self, shapes: dict[str, Image], window: Window) -> None:
        x0, y0, x1, y1 = window
        self.faces = {k: np.ascontiguousarray(v[y0:y1, x0:x1]) for k, v in shapes.items()}
        gray = {k: to_gray(v) for k, v in self.faces.items()}
        self.flows = {(a, b): optical_flow(gray[a], gray[b]) for a in gray for b in gray if a != b}
        self.grid = pixel_grid(next(iter(self.faces.values())))  # made once, used every frame

    def __call__(self, a: str, b: str, t: float) -> Image:
        """The mouth t of the way (0..1) from shape a to shape b."""
        if a == b:
            return self.faces[a]
        flow_ab, flow_ba = self.flows[(a, b)], self.flows[(b, a)]
        return morph(self.faces[a], self.faces[b], flow_ab, flow_ba, t, self.grid)


def reach(window: Window, moves: NDArray[np.float64]) -> Window:
    """The part of the crop that `window` can land on in any loop frame, given each frame's
    move from the still head (2x3 affines), with a pixel to spare."""
    x0, y0, x1, y1 = window
    corners = np.array([[x0, y0, 1], [x1, y0, 1], [x0, y1, 1], [x1, y1, 1]], np.float64)
    shift = int(np.ceil(np.abs(corners @ moves.transpose(0, 2, 1) - corners[:, :2]).max())) + 1
    return (
        max(0, x0 - shift),
        max(0, y0 - shift),
        min(CROP, x1 + shift),
        min(CROP, y1 + shift),
    )


class EyeMorph:
    """The eyes at any openness, morphed between the two nearest rendered stages."""

    def __init__(self, lib: Library) -> None:
        self.levels = (1.0, *EYE_STAGES)
        stages = [lib.shapes["rest"], *lib.eyes]
        self.morph = ShapeMorph({str(i): face for i, face in enumerate(stages)}, lib.eye_window)

    def __call__(self, eye_open: float) -> Image:
        """The eyes `eye_open` open (1 as in the photo, 0 closed)."""
        for i, (high, low) in enumerate(pairwise(self.levels)):
            if eye_open >= low:
                return self.morph(str(i), str(i + 1), (high - min(eye_open, high)) / (high - low))
        return self.morph.faces[str(len(self.levels) - 1)]


class Compositor:
    """Builds whole video frames from a library: mouth on the idle loop, face on the photo."""

    def __init__(self, lib: Library) -> None:
        self.lib = lib
        self.morph = ShapeMorph(lib.shapes, lib.window)
        self.eyes = EyeMorph(lib)
        self.paste = Paster(lib)
        self.boxes = (reach(lib.window, lib.align), reach(lib.eye_window, lib.eye_align))
        # Where the voice's expression moves the face (imageskin.expression), made once.
        lm = np.load(lib.folder / "crop_landmarks.npy")
        self.jaw = jaw_field(lm, lib.window)
        self.brow = brow_field(lm, lib.eye_window)
        self.head = head_weight(lm)
        self.crop_grid = pixel_grid(lib.shapes["rest"])
        self.pivot = (float(lm[8, 0]), float(lm[8, 1]) + 40)  # below the chin, at the neck
        # The head's move is a turn about the pivot plus a shift, faded by `head`: the parts
        # that don't change from frame to frame are made once (roadmap R22c).
        px, py = self.pivot
        self._x = np.ascontiguousarray(self.crop_grid[..., 0])
        self._y = np.ascontiguousarray(self.crop_grid[..., 1])
        self._hx = np.ascontiguousarray((self._x - px) * self.head, np.float32)
        self._hy = np.ascontiguousarray((self._y - py) * self.head, np.float32)
        self._map_x = np.empty_like(self._x)
        self._map_y = np.empty_like(self._y)
        # The still head around each window, which only the window's part changes in.
        self._stills = {
            box: self.lib.shapes["rest"][box[1] : box[3], box[0] : box[2]].copy()
            for box in self.boxes
        }

    def face(
        self,
        weights: dict[str, float],
        frame: int,
        eye_open: float = 1.0,
        move: FrameMotion = STILL,
    ) -> Image:
        """The face crop for one video frame: idle-loop frame `frame`, mouth from `weights`,
        eyes `eye_open` open, jaw, brows and head moved by `move`.

        The mouth and the eyes are made on the still head, then moved with the head (a shift
        and a slight turn, from `Library.align` and `Library.eye_align`) and blended in
        through their soft masks. The head's nod, tilt and sway are added last, fading out
        before the crop's edge so the paste into the photo stays seamless.
        """
        lib = self.lib
        j = frame % len(lib.loop)
        face = lib.loop[j].copy()
        mouth_box, eye_box = self.boxes
        mouth = self.morph(*top_two(weights))
        jaw = move.jaw * openness(weights)
        if abs(jaw) > 0.05:
            mouth = push(mouth, self.morph.grid, 0.0, jaw * self.jaw)
        self._put(face, mouth, lib.window, mouth_box, lib.align[j], lib.mouth)
        eyes = self.eyes(eye_open)
        if move.brow > 0.05:
            eyes = push(eyes, self.eyes.morph.grid, 0.0, -move.brow * self.brow)
        self._put(face, eyes, lib.eye_window, eye_box, lib.eye_align[j], lib.eye_mask)
        if move.nod or move.tilt or move.sway:
            face = self._move_head(face, move)
        return face

    def _move_head(self, face: Image, move: FrameMotion) -> Image:
        """Turn the head about the neck by `move.tilt` and shift it by the nod and sway: each
        output pixel takes the colour from where it came, as `expression.push` does, with the
        maps made in place by OpenCV."""
        a = math.radians(move.tilt)
        turn, lean = math.cos(a) - 1.0, math.sin(a)
        # map_x = x - head * ((cos a - 1) * gx - sin a * gy + sway), and likewise for y.
        map_x, map_y = self._map_x, self._map_y
        cv2.addWeighted(self._hx, -turn, self._hy, lean, 0.0, dst=map_x)
        cv2.scaleAdd(self.head, -move.sway, map_x, dst=map_x)
        cv2.add(map_x, self._x, dst=map_x)
        cv2.addWeighted(self._hx, -lean, self._hy, -turn, 0.0, dst=map_y)
        cv2.scaleAdd(self.head, -move.nod, map_y, dst=map_y)
        cv2.add(map_y, self._y, dst=map_y)
        out = cv2.remap(face, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        return np.asarray(out, np.uint8)

    def _put(
        self,
        face: Image,
        part: Image,
        window: Window,
        box: Window,
        to_loop: NDArray[np.float64],
        mask: Mask,
    ) -> None:
        """Blend `part`, the still head inside `window`, into `face`: moved by `to_loop` and
        through the moved `mask`. Only `box`, where the moved window can land, is touched."""
        (x0, y0, x1, y1), (bx0, by0, bx1, by1) = window, box
        still = self._stills[box]  # kept from the last frame: only the window's part changes
        still[y0 - by0 : y1 - by0, x0 - bx0 : x1 - bx0] = part
        origin = np.array([bx0, by0], np.float64)
        move = to_loop.copy()
        move[:, 2] += to_loop[:, :2] @ origin - origin  # the same move, in the box's pixels
        size = (bx1 - bx0, by1 - by0)
        soft = cv2.warpAffine(mask[by0:by1, bx0:bx1], move, size)
        moved = cv2.warpAffine(still, move, size, borderMode=cv2.BORDER_REFLECT)
        # Blended in 8-bit by OpenCV in one pass (roadmap R22c).
        face[by0:by1, bx0:bx1] = cv2.blendLinear(face[by0:by1, bx0:bx1], moved, 1.0 - soft, soft)

    def frame(
        self,
        weights: dict[str, float],
        frame: int,
        eye_open: float = 1.0,
        move: FrameMotion = STILL,
    ) -> Image:
        """One whole RGB video frame."""
        return self.paste(self.face(weights, frame, eye_open, move))


def audio_seed(samples: array[int]) -> int:
    """A seed taken from the speech itself: each video gets its own blinks, and the same
    speech always gets the same ones."""
    return int.from_bytes(hashlib.sha256(samples.tobytes()).digest()[:8], "big")


def read_shapes(timings: Path) -> list[ShapeTiming]:
    """The mouth shapes over time from the timings JSON that `write_speech` writes."""
    try:
        data = json.loads(timings.read_text(encoding="utf-8"))
        return [ShapeTiming(s["shape"], s["start"], s["end"]) for s in data["shapes"]]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise VideoError(f"could not read mouth shapes from {timings}: {e}") from e


class PhotorealEngine:
    def __init__(
        self,
        home: Path | None = None,
        make_portrait: Callable[[Path], PortraitLike] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._home = home or default_home()
        self._make_portrait = make_portrait or liveportrait_factory(self._home)
        self._timeout_s = timeout_s
        self._compositors: dict[Path, Compositor] = {}

    def prepare(self, photo: Path) -> Library:
        find_ffmpeg()  # fail now, not after a long setup
        return prepare_library(photo, self._home, self._make_portrait)

    def render(self, lib: Library, wav: Path, output: Path) -> float:
        start = time.perf_counter()
        samples, rate = read_pcm16(wav)
        seconds = len(samples) / rate
        n_frames = max(1, round(seconds * FPS))
        weights = frame_weights(read_shapes(wav.with_suffix(".json")), n_frames, FPS)
        eyes = eye_track(n_frames, FPS, seed=audio_seed(samples))
        moves = motion(np.asarray(samples, np.float32) / 32768.0, rate, n_frames, FPS)
        compositor = self._compositors.get(lib.folder) or Compositor(lib)
        self._compositors[lib.folder] = compositor

        def frames() -> Iterator[bytes]:
            for i, w in enumerate(weights):
                yield compositor.frame(w, i, eyes[i], moves.at(i)).tobytes()

        h, w = lib.photo.shape[:2]
        write_mp4(frames(), (w, h), wav, output, self._timeout_s, pix_fmt="rgb24")
        elapsed = time.perf_counter() - start
        logger.info(
            "Rendered video",
            extra={
                "engine": "photoreal",
                "output": str(output),
                "frames": n_frames,
                "video_s": round(seconds, 2),
                "duration_ms": round(elapsed * 1000, 1),
                # Below 1.0 means faster than real time.
                "real_time_factor": round(elapsed / seconds, 2) if seconds else None,
            },
        )
        return seconds
