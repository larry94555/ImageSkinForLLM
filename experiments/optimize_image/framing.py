"""R233: finding, framing and enlarging the head and neck, as plain functions on landmarks and the
segmenter's labels, so they can be tested without the models. An experiment, not part of the app.

Every length is measured in face heights: mid-forehead to chin, MediaPipe points 10 and 152, as
the photo checks (R8) measure the face.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.uint8]
Points = NDArray[np.float32]
Labels = NDArray[np.uint8]

FOREHEAD = 10
CHIN = 152
# The segmenter's labels (R8): 0 background, 1 hair, 2 body skin, 3 face skin, 4 clothes.
HAIR, BODY_SKIN, FACE_SKIN = 1, 2, 3
# Where the segmenter finds no hair or face skin, the top of the hair is guessed this far above
# mid-forehead. On the twelve default people it is 0.36 to 0.59 face heights (median 0.49;
# three reach the picture's top edge, so theirs may be more).
HAIR_ABOVE_FOREHEAD = 0.5
# The segmenter box may grow this much over the landmark box to fit tall hair; past that the
# face would get too small, so the box moves up instead.
MAX_GROW = 1.35
NECK = 0.5  # face heights below the chin counted as the neck
# MediaPipe's face landmarker misses faces under about 50 px tall (a full-length photo). The
# segmenter still labels their skin, so the face is looked for again in a square this many
# times the face skin's size around it, enlarged to SEARCH_PX.
SEARCH_SCALE = 3.0
SEARCH_PX = 512


@dataclass(frozen=True)
class Box:
    """A square in photo pixels; it may reach past the photo's edges."""

    left: int
    top: int
    size: int

    @property
    def right(self) -> int:
        return self.left + self.size

    @property
    def bottom(self) -> int:
        return self.top + self.size


@dataclass(frozen=True)
class Framing:
    """Where the head sits in a square picture, in face heights (or a share of the side)."""

    margin_above_hair: float  # picture top to hair top
    face_share: float  # face height over the picture's side
    chin_to_bottom: float  # chin to picture bottom
    centre_offset: float  # head centre minus picture centre, left to right


def face_height(points: Points) -> float:
    return float(points[CHIN, 1] - points[FOREHEAD, 1])


def head_mask(labels: Labels, points: Points) -> NDArray[np.bool_]:
    """The hair and face skin joined to the face: other people's hair or a skin-coloured wall
    elsewhere in the picture is left out."""
    mask = np.isin(labels, (HAIR, FACE_SKIN)).astype(np.uint8)
    n, parts = cv2.connectedComponents(mask, connectivity=8)
    if n <= 1:
        return np.zeros(labels.shape, bool)
    h, w = labels.shape
    xs = np.clip(np.round(points[:, 0]).astype(int), 0, w - 1)
    ys = np.clip(np.round(points[:, 1]).astype(int), 0, h - 1)
    touched = np.unique(parts[ys, xs])
    touched = touched[touched > 0]
    return np.isin(parts, touched)


def head_top_and_centre(head: NDArray[np.bool_], points: Points) -> tuple[float, float]:
    """The top of the hair, and the middle of the head left to right, measured from the hair
    top down to the chin (long hair below the chin would pull the middle sideways)."""
    rows = np.flatnonzero(head.any(axis=1))
    if rows.size == 0:
        top = float(points[FOREHEAD, 1]) - HAIR_ABOVE_FOREHEAD * face_height(points)
        return top, float(points[:, 0].min() + points[:, 0].max()) / 2
    top = float(rows[0])
    chin = int(np.clip(points[CHIN, 1], rows[0], head.shape[0] - 1))
    cols = np.flatnonzero(head[rows[0] : chin + 1].any(axis=0))
    return top, float(cols[0] + cols[-1]) / 2


def measure_framing(points: Points, labels: Labels) -> Framing:
    """The framing of a square picture, such as a default person's."""
    side = labels.shape[0]
    fh = face_height(points)
    top, centre = head_top_and_centre(head_mask(labels, points), points)
    return Framing(
        margin_above_hair=top / fh,
        face_share=fh / side,
        chin_to_bottom=(side - float(points[CHIN, 1])) / fh,
        centre_offset=(centre - labels.shape[1] / 2) / fh,
    )


def median_framing(framings: list[Framing]) -> Framing:
    return Framing(
        *(
            float(np.median([getattr(f, name) for f in framings]))
            for name in ("margin_above_hair", "face_share", "chin_to_bottom", "centre_offset")
        )
    )


def box_from_landmarks(points: Points, target: Framing) -> Box:
    """The square from the face points alone: the face the target's share of the side, the
    chin the target's distance from the bottom, centred on the face."""
    fh = face_height(points)
    size = fh / target.face_share
    bottom = float(points[CHIN, 1]) + target.chin_to_bottom * fh
    centre = float(points[:, 0].min() + points[:, 0].max()) / 2
    return Box(round(centre - size / 2), round(bottom - size), round(size))


def box_from_segments(points: Points, labels: Labels, target: Framing) -> Box:
    """The landmark square, centred on the head (face and hair) instead of the face, and raised
    to keep the target's margin above the hair when the hair is taller than the face points
    suggest: the bottom stays put while the square can grow up to MAX_GROW, then it moves up."""
    fh = face_height(points)
    base = box_from_landmarks(points, target)
    hair_top, centre = head_top_and_centre(head_mask(labels, points), points)
    want_top = hair_top - target.margin_above_hair * fh
    size, top = float(base.size), float(base.top)
    if want_top < top:
        size = min(base.bottom - want_top, base.size * MAX_GROW)
        top = want_top
    return Box(round(centre - size / 2), round(top), round(size))


def hair_cut(head: NDArray[np.bool_], box: Box, chin_y: float) -> float:
    """Share of the head (hair and face, above the chin) left outside the square: 0 when the
    top of the hair and both sides are in."""
    h, w = head.shape
    above_chin = head.copy()
    above_chin[int(np.clip(math.ceil(chin_y), 0, h)) :] = False
    total = int(above_chin.sum())
    if total == 0:
        return 0.0
    inside = above_chin[
        max(0, box.top) : max(0, min(h, box.bottom)), max(0, box.left) : max(0, min(w, box.right))
    ]
    return 1.0 - int(inside.sum()) / total


def neck_cut(labels: Labels, points: Points, box: Box) -> float:
    """Share of the neck left outside the square: the body skin from the chin down half a face
    height (the default people's pictures end 0.5 to 0.76 below the chin, at the top of the
    shoulders), as wide as the face. 0 when there is none to see (a high collar)."""
    h, w = labels.shape
    fh = face_height(points)
    chin = int(np.clip(round(float(points[CHIN, 1])), 0, h))
    left = int(np.clip(round(float(points[:, 0].min())), 0, w))
    right = int(np.clip(round(float(points[:, 0].max())), 0, w))
    neck = np.zeros(labels.shape, bool)
    rows = slice(chin, int(np.clip(round(chin + NECK * fh), 0, h)))
    neck[rows, left:right] = labels[rows, left:right] == BODY_SKIN
    total = int(neck.sum())
    if total == 0:
        return 0.0
    inside = neck[
        max(0, box.top) : max(0, min(h, box.bottom)), max(0, box.left) : max(0, min(w, box.right))
    ]
    return 1.0 - int(inside.sum()) / total


def face_search_box(labels: Labels) -> Box | None:
    """The square to look for a small face in: around the largest patch of face skin, or None
    if the segmenter found no face skin."""
    n, parts, stats, _ = cv2.connectedComponentsWithStats((labels == FACE_SKIN).astype(np.uint8))
    if n <= 1:
        return None
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = (int(v) for v in stats[biggest, :4])
    size = round(max(w, h) * SEARCH_SCALE)
    return Box(round(x + w / 2 - size / 2), round(y + h / 2 - size / 2), size)


def crop_square(rgb: Image, box: Box) -> tuple[Image, float]:
    """The square cut from the photo. Where it reaches past an edge, the edge's pixels are
    stretched outward and blurred more the further they go, so there is no hard line. Returns
    the picture and the share of it that was filled."""
    h, w = rgb.shape[:2]
    pad_l, pad_t = max(0, -box.left), max(0, -box.top)
    pad_r, pad_b = max(0, box.right - w), max(0, box.bottom - h)
    inside = rgb[max(0, box.top) : min(h, box.bottom), max(0, box.left) : min(w, box.right)]
    if not (pad_l or pad_t or pad_r or pad_b):
        return np.ascontiguousarray(inside), 0.0
    stretched = cv2.copyMakeBorder(inside, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REPLICATE)
    # Stretched edge pixels make streaks; a wide blur (a twelfth of the side) smooths them into
    # a soft wash of the edge's colours.
    sigma = max(2.0, box.size / 12)
    blurred = cv2.GaussianBlur(stretched, (0, 0), sigma)
    # 0 inside the photo, rising to 1 one blur width past the edge.
    outside = np.ones(stretched.shape[:2], np.uint8)
    outside[pad_t : pad_t + inside.shape[0], pad_l : pad_l + inside.shape[1]] = 0
    distance = cv2.distanceTransform(outside, cv2.DIST_L2, 3)
    weight = np.clip(distance / sigma, 0, 1)[..., None]
    out = stretched * (1 - weight) + blurred * weight
    filled = float(outside.mean())
    return np.clip(out + 0.5, 0, 255).astype(np.uint8), filled


Upscale = Callable[[Image], Image]


def lanczos(rgb: Image, size: int) -> Image:
    return cv2.resize(rgb, (size, size), interpolation=cv2.INTER_LANCZOS4)


def enlarge(rgb: Image, size: int, model: Upscale | None, max_passes: int = 2) -> Image:
    """The square at size by size: shrunk with area averaging if it is bigger, otherwise run
    through the model (if any) until it reaches the size or max_passes, then resized to fit."""
    if rgb.shape[0] >= size:
        return cv2.resize(rgb, (size, size), interpolation=cv2.INTER_AREA)
    out = rgb
    passes = 0
    while model is not None and out.shape[0] < size and passes < max_passes:
        out = model(out)
        passes += 1
    if out.shape[0] == size:
        return out
    shrink = out.shape[0] > size
    return cv2.resize(
        out, (size, size), interpolation=cv2.INTER_AREA if shrink else cv2.INTER_LANCZOS4
    )


def psnr(a: Image, b: Image) -> float:
    """Peak signal to noise ratio in dB; higher is closer."""
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return 99.0 if mse == 0 else 10 * math.log10(255.0**2 / mse)
