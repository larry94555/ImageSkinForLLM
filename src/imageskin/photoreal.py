"""Photoreal video engine: each reply is mixed from the frame library, with no model run.

`prepare` builds the photo's frame library once (see `photoreal_library`) and loads it.
`render` turns the sound timings into mouth-shape weights per frame (`imageskin.visemes`),
morphs between the two strongest shapes along the optical flow between them, places that
mouth on the matching idle-loop frame, pastes the face back into the photo and encodes the
MP4 with the voice.
"""

import json
import logging
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from imageskin.config import default_home
from imageskin.liveportrait_edits import top_two
from imageskin.photoreal_library import (
    CROP,
    Image,
    Library,
    Paster,
    PortraitLike,
    Window,
    liveportrait_factory,
    optical_flow,
    prepare_library,
    to_gray,
)
from imageskin.video import FPS, VideoError, find_ffmpeg, read_pcm16, write_mp4
from imageskin.visemes import ShapeTiming, frame_weights

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 300.0


def _remap(image: Image, mapping: NDArray[np.float32]) -> Image:
    """Each output pixel (x, y) takes the colour of `image` at mapping[y, x]."""
    out = cv2.remap(image, mapping, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)  # type: ignore[call-overload]
    return np.asarray(out, np.uint8)


class MouthMorph:
    """In-between mouths: two shapes warped toward each other along their optical flow and
    blended, which keeps one set of lips instead of the double lips of a plain cross-fade."""

    def __init__(self, shapes: dict[str, Image], window: Window) -> None:
        x0, y0, x1, y1 = window
        self.faces = {k: np.ascontiguousarray(v[y0:y1, x0:x1]) for k, v in shapes.items()}
        gray = {k: to_gray(v) for k, v in self.faces.items()}
        self.flows = {(a, b): optical_flow(gray[a], gray[b]) for a in gray for b in gray if a != b}
        gx, gy = np.meshgrid(
            np.arange(x1 - x0, dtype=np.float32), np.arange(y1 - y0, dtype=np.float32)
        )
        self.grid = np.dstack([gx, gy])

    def __call__(self, a: str, b: str, t: float) -> Image:
        """The mouth t of the way (0..1) from shape a to shape b."""
        if a == b or t <= 0.0:
            return self.faces[a]
        if t >= 1.0:
            return self.faces[b]
        from_a = _remap(self.faces[a], self.grid + t * self.flows[(b, a)])
        from_b = _remap(self.faces[b], self.grid + (1.0 - t) * self.flows[(a, b)])
        return np.asarray(cv2.addWeighted(from_a, 1.0 - t, from_b, t, 0.0), np.uint8)


class Compositor:
    """Builds whole video frames from a library: mouth on the idle loop, face on the photo."""

    def __init__(self, lib: Library) -> None:
        self.lib = lib
        self.morph = MouthMorph(lib.shapes, lib.window)
        self.paste = Paster(lib)

    def face(self, weights: dict[str, float], frame: int) -> Image:
        """The face crop for one video frame: idle-loop frame `frame`, mouth from `weights`.

        The mouth is made on the still head, then moved with the head (a shift and a slight
        turn, from `Library.align`) and blended in through the soft mouth mask.
        """
        lib = self.lib
        j = frame % len(lib.loop)
        x0, y0, x1, y1 = lib.window
        still = lib.shapes["rest"].copy()
        still[y0:y1, x0:x1] = self.morph(*top_two(weights))
        to_loop = lib.align[j]
        mask = cv2.warpAffine(lib.mouth, to_loop, (CROP, CROP))[..., None]
        moved = cv2.warpAffine(still, to_loop, (CROP, CROP), borderMode=cv2.BORDER_REFLECT)
        return np.asarray(lib.loop[j] * (1.0 - mask) + moved * mask, np.uint8)

    def frame(self, weights: dict[str, float], frame: int) -> Image:
        """One whole RGB video frame."""
        return self.paste(self.face(weights, frame))


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
        compositor = self._compositors.get(lib.folder) or Compositor(lib)
        self._compositors[lib.folder] = compositor

        def frames() -> Iterator[bytes]:
            for i, w in enumerate(weights):
                yield compositor.frame(w, i).tobytes()

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
