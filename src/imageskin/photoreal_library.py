"""The photoreal engine's frame library: rendered once per photo with LivePortrait.

`prepare_library` (once per photo, minutes to tens of minutes on a laptop CPU) renders and
saves to a folder:
  - the 10 mouth shapes on the still head, with Larry's accepted softness (R4a);
  - an idle loop of the face with a slight head drift and two blinks (LOOP_SECONDS long).
    Only every KEY_EVERY-th frame and the frames around the blinks are rendered; the head
    moves less than a tenth of a degree per frame, so the ones between are filled in along
    the optical flow (45 to 55 dB PSNR against fully rendered frames, about 3x faster);
  - how the lower face moves in each loop frame, so the mouth can follow the head.
An interrupted run picks up where it stopped; a finished library is reused. Making videos
from a library needs only NumPy and OpenCV, no model.
"""

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from imageskin.liveportrait_edits import (
    CONTROLS,
    LOOP_SECONDS,
    MOUTH_SHAPES,
    STRENGTH,
    UPPER_LIP,
    eye_openness,
    idle_motion,
    soften,
)
from imageskin.video import FPS, VideoError, write_mp4
from imageskin.visemes import SHAPES

logger = logging.getLogger(__name__)

# Bump when the frames a library holds would change, so old libraries are rebuilt.
LIBRARY_VERSION = 1
CROP = 512  # LivePortrait's face crop is CROP x CROP pixels
KEY_EVERY = 4  # idle-loop frames rendered by the model; the rest are filled in between

Image = NDArray[np.uint8]
Mask = NDArray[np.float32]
Window = tuple[int, int, int, int]  # x0, y0, x1, y1
# Told how far a step has got: the step ("models", "shapes", "loop" or "align"), done, total.
Progress = Callable[[str, int, int], None]


def no_progress(step: str, done: int, total: int) -> None:
    pass


class PortraitLike(Protocol):
    photo: Image  # RGB, the size of the video
    lip_ratio: float
    crop_to_photo: NDArray[np.float64]  # 2x3 affine from the face crop to the photo
    crop_landmarks: NDArray[np.float32]  # 68 face points in the crop
    paste_template: Image  # CROP x CROP, how much of the crop to paste over the photo

    def render(
        self,
        controls: dict[str, float],
        ratio: float | None = None,
        upper: float = 1.0,
        pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
        eye_open: float = 1.0,
    ) -> Image: ...


@dataclass(frozen=True)
class Library:
    folder: Path
    photo: Image
    crop_to_photo: NDArray[np.float64]
    paste_template: Image
    shapes: dict[str, Image]  # each mouth shape on the still head
    loop: list[Image]  # the idle loop, with the photo's own mouth
    align: NDArray[np.float64]  # per loop frame, 2x3 affine from the still head to that frame
    mouth: Mask  # where the mouth and jaw are, soft-edged, in the still head's crop
    window: Window  # the part of the crop that holds the mouth mask


def optical_flow(a: NDArray[np.uint8], b: NDArray[np.uint8]) -> NDArray[np.float32]:
    """Dense optical flow between two grey images: where each pixel of `a` is in `b`."""
    dis: Any = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)  # type: ignore[attr-defined]
    return np.asarray(dis.calc(a, b, None), np.float32)


def to_gray(image: Image) -> NDArray[np.uint8]:
    return np.asarray(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), np.uint8)


def library_key(photo: Path) -> str:
    digest = hashlib.sha256(photo.read_bytes())
    digest.update(f"v{LIBRARY_VERSION} l{LOOP_SECONDS} f{FPS}".encode())
    return digest.hexdigest()[:16]


def mouth_key() -> str:
    """Changes whenever the mouth-shape settings do, so only the shapes are rendered again."""
    settings = repr((sorted(MOUTH_SHAPES.items()), sorted(CONTROLS.items()), STRENGTH, UPPER_LIP))
    return hashlib.sha256(settings.encode()).hexdigest()[:12]


def mouth_mask(landmarks: NDArray[np.float32], size: int = CROP) -> tuple[Mask, Window]:
    """A soft oval over the mouth and jaw, from below the nose to the chin, and its bounds.

    Inside it the mouth comes from the mouth shapes; outside, from the idle loop.
    """
    mouth, chin, nose = landmarks[48:68], landmarks[8], landmarks[33]
    width = max(4.0, float(np.ptp(mouth[:, 0])))
    height = max(4.0, float(chin[1] - nose[1]))
    centre = (round(float(mouth[:, 0].mean())), round(float(nose[1] + 0.6 * height)))
    mask = np.zeros((size, size), np.float32)
    axes = (round(0.95 * width), round(0.55 * height))
    cv2.ellipse(mask, centre, axes, 0, 0, 360, 1.0, -1)
    mask = np.asarray(cv2.GaussianBlur(mask, (0, 0), 0.12 * width), np.float32)
    ys, xs = np.nonzero(mask > 0.01)
    if not len(xs):
        raise VideoError("could not find the mouth in the face crop")
    return mask, (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def align_loop(rest: Image, loop: list[Image], mask: Mask, window: Window) -> NDArray[np.float64]:
    """For each loop frame, the shift, turn and scale that carries the still head's lower
    face onto that frame's, from the optical flow between them.

    The head moves by a degree or two, so this keeps the mouth in place to within a pixel.
    """
    x0, y0, x1, y1 = window
    gy, gx = np.mgrid[y0:y1:4, x0:x1:4]
    inside = mask[gy, gx] > 0.3
    src = np.stack([gx[inside], gy[inside]], axis=1).astype(np.float32)
    still = to_gray(rest)
    out = np.zeros((len(loop), 2, 3))
    for i, frame in enumerate(loop):
        flow = optical_flow(still, to_gray(frame))
        dst = src + flow[src[:, 1].astype(int), src[:, 0].astype(int)]
        matrix, _ = cv2.estimateAffinePartial2D(src, dst) if len(src) >= 3 else (None, None)
        out[i] = matrix if matrix is not None else np.eye(2, 3)
    return out


def key_frames(n_loop: int) -> list[int]:
    """The idle-loop frames the model renders: every KEY_EVERY-th one, and each frame in or
    next to a blink, since eyelids move too fast to fill in."""
    blinking = {i for i in range(n_loop) if eye_openness(i / FPS) < 1.0}
    near = {j for i in blinking for j in (i - 1, i, i + 1) if 0 <= j < n_loop}
    return sorted({i for i in range(n_loop) if i % KEY_EVERY == 0} | near)


def in_between(a: Image, b: Image, t: float) -> Image:
    """The face t of the way (0..1) from frame a to frame b: both warped toward each other
    along their optical flow and blended, so nothing is doubled as in a plain cross-fade."""
    h, w = a.shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    grid = np.dstack([gx, gy])
    to_a = grid + t * optical_flow(to_gray(b), to_gray(a))
    to_b = grid + (1.0 - t) * optical_flow(to_gray(a), to_gray(b))
    from_a = cv2.remap(a, to_a, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)  # type: ignore[call-overload]
    from_b = cv2.remap(b, to_b, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)  # type: ignore[call-overload]
    return np.asarray(cv2.addWeighted(from_a, 1.0 - t, from_b, t, 0.0), np.uint8)


def fill_loop(loop: Path, n_loop: int, keys: list[int]) -> int:
    """Fill in the idle-loop frames between the rendered ones; return how many were made.
    The last frames are filled toward frame 0, since the loop wraps around."""
    made = 0
    for k, a in enumerate(keys):
        b = keys[k + 1] if k + 1 < len(keys) else n_loop
        todo = [i for i in range(a + 1, b) if not (loop / f"{i:04d}.npy").exists()]
        if not todo:
            continue
        first = np.load(loop / f"{a:04d}.npy")
        last = np.load(loop / f"{b % n_loop:04d}.npy")
        for i in todo:
            _save(loop / f"{i:04d}.npy", in_between(first, last, (i - a) / (b - a)))
            made += 1
    return made


def _save(path: Path, array: NDArray[np.generic]) -> None:
    """Save an array so that an interrupted write never leaves a file that looks complete."""
    tmp = path.with_name(path.stem + ".tmp.npy")
    np.save(tmp, array)
    os.replace(tmp, path)


def build_library(
    photo: Path,
    folder: Path,
    make_portrait: Callable[[Path], PortraitLike],
    progress: Progress = no_progress,
) -> None:
    """Render the frames for one photo into `folder`, skipping frames already there."""
    start = time.perf_counter()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "loop").mkdir(exist_ok=True)
    n_loop = round(LOOP_SECONDS * FPS)
    logger.info(
        "Preparing photoreal library",
        extra={"photo": str(photo), "folder": str(folder), "loop_frames": n_loop},
    )
    progress("models", 0, 1)
    portrait = make_portrait(photo)
    progress("models", 1, 1)
    _save(folder / "photo.npy", portrait.photo)
    _save(folder / "paste_template.npy", portrait.paste_template)
    _save(folder / "crop_landmarks.npy", portrait.crop_landmarks)
    _save(folder / "crop_to_photo.npy", portrait.crop_to_photo)

    shapes_meta = folder / "shapes.json"
    old_mouth = json.loads(shapes_meta.read_text()).get("mouth") if shapes_meta.exists() else None
    if old_mouth != mouth_key() or not (folder / "shapes.npy").exists():
        faces = []
        progress("shapes", 0, len(SHAPES))
        for name in SHAPES:
            controls, ratio = soften(name, STRENGTH, portrait.lip_ratio)
            faces.append(portrait.render(controls, None if name == "rest" else ratio, UPPER_LIP))
            progress("shapes", len(faces), len(SHAPES))
        _save(folder / "shapes.npy", np.stack(faces))
        shapes_meta.write_text(json.dumps({"mouth": mouth_key()}), encoding="utf-8")
        logger.info("Rendered mouth shapes", extra={"shapes": len(SHAPES), "mouth": mouth_key()})

    keys = key_frames(n_loop)
    todo = [i for i in keys if not (folder / "loop" / f"{i:04d}.npy").exists()]
    if 0 < len(todo) < len(keys):
        logger.info("Resuming idle loop", extra={"done": len(keys) - len(todo), "of": len(keys)})
    progress("shapes", len(SHAPES), len(SHAPES))
    progress("loop", len(keys) - len(todo), len(keys))
    loop_start = time.perf_counter()
    for k, i in enumerate(todo, 1):
        pitch, yaw, roll, eye_open = idle_motion(i, n_loop, FPS)
        face = portrait.render({}, None, 1.0, (pitch, yaw, roll), eye_open)
        _save(folder / "loop" / f"{i:04d}.npy", face)
        progress("loop", len(keys) - len(todo) + k, len(keys))
        if k % 10 == 0 or k == len(todo):
            per_frame = (time.perf_counter() - loop_start) / k
            logger.info(
                "Rendered idle loop frame %d of %d",
                len(keys) - len(todo) + k,
                len(keys),
                extra={
                    "s_per_frame": round(per_frame, 2),
                    "s_left": round(per_frame * (len(todo) - k)),
                },
            )

    fill_start = time.perf_counter()
    filled = fill_loop(folder / "loop", n_loop, keys)
    if filled:
        logger.info(
            "Filled in idle loop frames",
            extra={"frames": filled, "duration_s": round(time.perf_counter() - fill_start, 1)},
        )

    shapes = np.load(folder / "shapes.npy")
    mask, window = mouth_mask(portrait.crop_landmarks)
    loop = [np.load(folder / "loop" / f"{i:04d}.npy") for i in range(n_loop)]
    progress("align", 0, 1)
    _save(folder / "align.npy", align_loop(shapes[0], loop, mask, window))
    progress("align", 1, 1)
    (folder / "library.json").write_text(
        json.dumps(
            {
                "version": LIBRARY_VERSION,
                "photo": str(photo),
                "loop_frames": n_loop,
                "mouth": mouth_key(),
            }
        ),
        encoding="utf-8",
    )
    logger.info(
        "Photoreal library ready",
        extra={"folder": str(folder), "duration_s": round(time.perf_counter() - start, 1)},
    )


def load_library(folder: Path) -> Library:
    meta = json.loads((folder / "library.json").read_text(encoding="utf-8"))
    shapes = np.load(folder / "shapes.npy")
    landmarks = np.load(folder / "crop_landmarks.npy")
    mask, window = mouth_mask(landmarks)
    return Library(
        folder=folder,
        photo=np.load(folder / "photo.npy"),
        crop_to_photo=np.load(folder / "crop_to_photo.npy"),
        paste_template=np.load(folder / "paste_template.npy"),
        shapes=dict(zip(SHAPES, shapes, strict=True)),
        loop=[np.load(folder / "loop" / f"{i:04d}.npy") for i in range(meta["loop_frames"])],
        align=np.load(folder / "align.npy"),
        mouth=mask,
        window=window,
    )


def liveportrait_factory(home: Path) -> Callable[[Path], PortraitLike]:
    def make(photo: Path) -> PortraitLike:
        try:
            from imageskin.liveportrait import Portrait, ensure_models
        except ImportError as e:
            if e.name in ("torch", "mediapipe", "cv2", "numpy"):
                from imageskin.liveportrait import INSTALL_HINT

                raise VideoError(INSTALL_HINT) from e
            raise
        lp_dir = home / "models" / "LivePortrait"
        ensure_models(lp_dir)
        return Portrait(lp_dir, photo)

    return make


def prepare_library(
    photo: Path,
    home: Path,
    make_portrait: Callable[[Path], PortraitLike] | None = None,
    progress: Progress = no_progress,
) -> Library:
    """Build the photo's library under `home` unless it is already there, then load it."""
    start = time.perf_counter()
    if not photo.is_file():
        raise VideoError(f"{photo}: file not found")
    folder = home / "photoreal" / library_key(photo)
    meta = folder / "library.json"
    if not meta.exists() or json.loads(meta.read_text()).get("mouth") != mouth_key():
        # A new photo, an unfinished one, or new mouth settings (then only the 10 mouth
        # shapes are rendered again, about a minute; the idle loop is kept).
        build_library(photo, folder, make_portrait or liveportrait_factory(home), progress)
    lib = load_library(folder)
    logger.info(
        "Loaded photoreal library",
        extra={
            "photo": str(photo),
            "folder": str(folder),
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return lib


class Paster:
    """Puts a face crop back into the photo, blending its edges as LivePortrait does."""

    def __init__(self, lib: Library) -> None:
        self.photo = lib.photo
        h, w = lib.photo.shape[:2]
        paste = cv2.warpAffine(lib.paste_template, lib.crop_to_photo, (w, h))
        ys, xs = np.nonzero(paste)
        if not len(xs):
            raise VideoError("the face crop falls outside the photo")
        self.box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        x0, y0, x1, y1 = self.box
        self.weight = (paste[y0:y1, x0:x1].astype(np.float32) / 255.0)[..., None]
        # The crop-to-photo transform, shifted so the crop lands in the box. Only the box is
        # warped and blended, which keeps each frame fast.
        self.to_box = lib.crop_to_photo - np.array([[0, 0, x0], [0, 0, y0]], np.float64)

    def __call__(self, face: Image) -> Image:
        """One whole RGB video frame with `face` in place."""
        x0, y0, x1, y1 = self.box
        moved = cv2.warpAffine(face, self.to_box, (x1 - x0, y1 - y0))
        out = self.photo.copy()
        region = out[y0:y1, x0:x1]
        out[y0:y1, x0:x1] = (region * (1.0 - self.weight) + moved * self.weight).astype(np.uint8)
        return out


def write_idle_preview(lib: Library, output: Path, timeout_s: float = 300.0) -> float:
    """Write the idle loop, pasted into the photo, as a silent MP4; return its length."""
    paste = Paster(lib)
    h, w = lib.photo.shape[:2]
    frames = (paste(face).tobytes() for face in lib.loop)
    write_mp4(frames, (w, h), None, output, timeout_s, pix_fmt="rgb24")
    return len(lib.loop) / FPS
