"""The photoreal engine's frame library: rendered once per photo with LivePortrait.

`prepare_library` (once per photo, minutes to tens of minutes on a laptop CPU) renders and
saves to a folder:
  - the 10 mouth shapes on the still head, with Larry's accepted softness (R4a), and the eyes
    part-way and fully closed for blinks, which are added when a video is made;
  - an idle loop of the face with a slight head drift and open eyes (LOOP_SECONDS long).
    Only every KEY_EVERY-th frame is rendered; the head
    moves less than a tenth of a degree per frame, so the ones between are filled in along
    the optical flow (45 to 55 dB PSNR against fully rendered frames, about 3x faster);
  - how the lower face and the eyes move in each loop frame, so they follow the head.
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
    BLINK_BROW,
    CONTROLS,
    EYE_STAGES,
    LOOP_SECONDS,
    MOUTH_SHAPES,
    OPENING,
    STRENGTH,
    UPPER_LIP,
    idle_motion,
    soften,
)
from imageskin.video import FPS, VideoError, write_mp4
from imageskin.visemes import SHAPES

logger = logging.getLogger(__name__)

# Bump when existing libraries become unusable or must be made again, so they are rebuilt. A
# change that only makes new frames differently (such as filling in idle-loop frames) keeps
# the version: libraries made before stay valid.
LIBRARY_VERSION = 2  # 2: blinks taken out of the idle loop
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
    eyes: list[Image]  # the still head with its eyes at each of EYE_STAGES
    eye_align: NDArray[np.float64]  # like align, for the eyes and brows
    eye_mask: Mask
    eye_window: Window


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
    """Changes whenever the mouth-shape or blink settings do, so only the shapes and eyes are
    rendered again."""
    settings = repr(
        (sorted(MOUTH_SHAPES.items()), sorted(CONTROLS.items()), STRENGTH, OPENING, UPPER_LIP)
    )
    settings += repr((EYE_STAGES, BLINK_BROW))
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


def eye_mask(landmarks: NDArray[np.float32], size: int = CROP) -> tuple[Mask, Window]:
    """A soft patch over both eyes and brows, and its bounds. Inside it the blinks come from
    the eye stages; outside, from the idle loop."""
    points = np.concatenate([landmarks[17:27], landmarks[36:48]]).astype(np.int32)
    width = max(4.0, float(np.ptp(points[:, 0])))
    mask = np.zeros((size, size), np.float32)
    cv2.fillConvexPoly(mask, cv2.convexHull(points), 1.0)
    grow = max(1, round(0.12 * width))  # so the lids close well inside the soft edge
    disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    mask = np.asarray(cv2.dilate(mask, disc), np.float32)
    mask = np.asarray(cv2.GaussianBlur(mask, (0, 0), 0.05 * width), np.float32)
    ys, xs = np.nonzero(mask > 0.01)
    if not len(xs):
        raise VideoError("could not find the eyes in the face crop")
    return mask, (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def align_loop(rest: Image, loop: list[Image], mask: Mask, window: Window) -> NDArray[np.float64]:
    """For each loop frame, the shift, turn and scale that carries the part of the still head
    under `mask` (the lower face, or the eyes) onto that frame's, from the optical flow.

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
    """The idle-loop frames the model renders: every KEY_EVERY-th one."""
    return list(range(0, n_loop, KEY_EVERY))


def pixel_grid(image: Image) -> NDArray[np.float32]:
    """Each pixel's own (x, y), the starting point of a warp. Make it once per picture size."""
    h, w = image.shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return np.dstack([gx, gy])


def morph(
    a: Image,
    b: Image,
    flow_ab: NDArray[np.float32],
    flow_ba: NDArray[np.float32],
    t: float,
    grid: NDArray[np.float32] | None = None,
) -> Image:
    """The picture t of the way (0..1) from a to b: both warped toward each other along their
    optical flows (`optical_flow(a, b)` and `(b, a)` of their grey images) and blended, which
    keeps one set of edges instead of the doubled ones of a plain cross-fade. Callers that morph
    many times pass `pixel_grid(a)` so it is not made again each time."""
    if t <= 0.0:
        return a
    if t >= 1.0:
        return b
    if grid is None:
        grid = pixel_grid(a)
    from_a = _remap(a, grid + t * flow_ba)
    from_b = _remap(b, grid + (1.0 - t) * flow_ab)
    return np.asarray(cv2.addWeighted(from_a, 1.0 - t, from_b, t, 0.0), np.uint8)


def _remap(image: Image, mapping: NDArray[np.float32]) -> Image:
    """Each output pixel (x, y) takes the colour of `image` at mapping[y, x]."""
    out = cv2.remap(image, mapping, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)  # type: ignore[call-overload]
    return np.asarray(out, np.uint8)


def fill_loop(loop: Path, n_loop: int, keys: list[int]) -> int:
    """Fill in the idle-loop frames between the rendered ones; return how many were made.
    The last frames are filled toward frame 0, since the loop wraps around."""
    made = 0
    grid: NDArray[np.float32] | None = None  # all frames are the same size
    for k, a in enumerate(keys):
        b = keys[k + 1] if k + 1 < len(keys) else n_loop
        todo = [i for i in range(a + 1, b) if not (loop / f"{i:04d}.npy").exists()]
        if not todo:
            continue
        first = np.load(loop / f"{a:04d}.npy")
        last = np.load(loop / f"{b % n_loop:04d}.npy")
        there = optical_flow(to_gray(first), to_gray(last))  # once per pair of rendered frames
        back = optical_flow(to_gray(last), to_gray(first))
        if grid is None:
            grid = pixel_grid(first)
        for i in todo:
            t = (i - a) / (b - a)
            _save(loop / f"{i:04d}.npy", morph(first, last, there, back, t, grid))
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
        total = len(SHAPES) + len(EYE_STAGES)
        progress("shapes", 0, total)
        for name in SHAPES:
            controls, ratio = soften(name, STRENGTH, portrait.lip_ratio)
            faces.append(portrait.render(controls, None if name == "rest" else ratio, UPPER_LIP))
            progress("shapes", len(faces), total)
        eyes = []
        for level in EYE_STAGES:
            brow = {"brow": BLINK_BROW * (1.0 - level)}
            eyes.append(portrait.render(brow, None, UPPER_LIP, (0.0, 0.0, 0.0), level))
            progress("shapes", len(faces) + len(eyes), total)
        _save(folder / "shapes.npy", np.stack(faces))
        _save(folder / "eyes.npy", np.stack(eyes))
        shapes_meta.write_text(json.dumps({"mouth": mouth_key()}), encoding="utf-8")
        logger.info(
            "Rendered mouth and eye shapes",
            extra={"shapes": len(SHAPES), "eyes": len(EYE_STAGES), "mouth": mouth_key()},
        )

    keys = key_frames(n_loop)
    todo = [i for i in keys if not (folder / "loop" / f"{i:04d}.npy").exists()]
    if 0 < len(todo) < len(keys):
        logger.info("Resuming idle loop", extra={"done": len(keys) - len(todo), "of": len(keys)})
    progress("shapes", len(SHAPES) + len(EYE_STAGES), len(SHAPES) + len(EYE_STAGES))
    progress("loop", len(keys) - len(todo), len(keys))
    loop_start = time.perf_counter()
    for k, i in enumerate(todo, 1):
        face = portrait.render({}, None, 1.0, idle_motion(i, n_loop))
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
    emask, ewindow = eye_mask(portrait.crop_landmarks)
    _save(folder / "eye_align.npy", align_loop(shapes[0], loop, emask, ewindow))
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
    emask, ewindow = eye_mask(landmarks)
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
        eyes=list(np.load(folder / "eyes.npy")),
        eye_align=np.load(folder / "eye_align.npy"),
        eye_mask=emask,
        eye_window=ewindow,
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
        # The blend's weights, for the face and for the photo under it, made once.
        self.weight = np.ascontiguousarray(paste[y0:y1, x0:x1].astype(np.float32) / 255.0)
        self.under = np.ascontiguousarray(1.0 - self.weight)
        # The crop-to-photo transform, shifted so the crop lands in the box. Only the box is
        # warped and blended, which keeps each frame fast.
        self.to_box = lib.crop_to_photo - np.array([[0, 0, x0], [0, 0, y0]], np.float64)

    def __call__(self, face: Image) -> Image:
        """One whole RGB video frame with `face` in place."""
        x0, y0, x1, y1 = self.box
        moved = cv2.warpAffine(face, self.to_box, (x1 - x0, y1 - y0))
        out = self.photo.copy()
        # Blended in 8-bit by OpenCV in one pass: in floating point over the box, as before, the
        # blend was most of a frame's time (roadmap R22c).
        out[y0:y1, x0:x1] = cv2.blendLinear(out[y0:y1, x0:x1], moved, self.under, self.weight)
        return out


def write_idle_preview(lib: Library, output: Path, timeout_s: float = 300.0) -> float:
    """Write the idle loop, pasted into the photo, as a silent MP4; return its length. It has
    no blinks: those are added when a video is made."""
    paste = Paster(lib)
    h, w = lib.photo.shape[:2]
    frames = (paste(face).tobytes() for face in lib.loop)
    write_mp4(frames, (w, h), None, output, timeout_s, pix_fmt="rgb24")
    return len(lib.loop) / FPS
