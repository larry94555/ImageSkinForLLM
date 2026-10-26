"""Cheeks and face that move with the mouth (roadmap R128a).

Larry, 2026-10-25: only the lips and jaw moved when the person spoke, so the speech looked
mechanical. Each mouth shape now brings a small, matching movement of the cheeks and the
muscles around the mouth, drawn at video time as a smooth warp of the face crop, like the jaw
and brows of `imageskin.expression`, so no frame library or default person's pack is made
again:
  - lift: the cheeks rise a little on the spread shapes (EE, EH, IH: the "grin" of each
    shape in `liveportrait_edits.MOUTH_SHAPES`), and the lines from the nose to the mouth's
    corners rise and widen with them;
  - draw: they draw in slightly on the rounded ones (OO, OH, SH: their "purse");
  - stretch: the lower cheeks and chin move down as the jaw opens, with how far it opens
    (the shape's opening and the voice's extra jaw from `expression.motion`).
The lips themselves are left as they are, since their shapes were tuned for lip-reading.
Each track follows the mouth's weights from `visemes.frame_weights`, a little behind the lips
and eased in and out, so it goes back to rest between words. Pixels are in LivePortrait's
512 px face crop, and the whole movement is never more than MAX_PX.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from imageskin.expression import Field, Gains, Track, _smooth, _taper, head_weight, openness
from imageskin.liveportrait_edits import MOUTH_SHAPES
from imageskin.photoreal_library import CROP

logger = logging.getLogger(__name__)

# "Face movement while speaking" on the Setup page (UiSettings.face_movement): how much of
# CheekGains to use. "off" leaves only the lips and jaw moving, as before R128a.
STRENGTHS: dict[str, float] = {"off": 0.0, "slight": 0.5, "normal": 1.0, "more": 1.5}
MAX_PX = 5.0  # however strong, no pixel moves further than this

_GRIN = max(s.controls.get("grin", 0.0) for s in MOUTH_SHAPES.values())
_PURSE = max(s.controls.get("purse", 0.0) for s in MOUTH_SHAPES.values())


@dataclass(frozen=True)
class CheekGains:
    """How far the face moves at "normal", in pixels of the 512 px crop. Kept slight: where in
    doubt, smooth and small rather than sharp."""

    lift_px: float = 2.5  # cheeks up on the most spread shape
    draw_px: float = 1.5  # cheeks in on the most rounded shape
    stretch_px: float = 3.0  # lower cheeks and chin down on the most open shape
    lag_s: float = 0.04  # behind the lips
    ease_s: float = 0.07  # eased in and out over about this long


DEFAULT_CHEEK_GAINS = CheekGains()


@dataclass(frozen=True)
class CheekTracks:
    """Per frame, in pixels at the field's strongest point: lift, draw and stretch."""

    lift: Track
    draw: Track
    stretch: Track

    def at(self, i: int) -> tuple[float, float, float]:
        return float(self.lift[i]), float(self.draw[i]), float(self.stretch[i])


def _late(x: Track, fps: float, lag_s: float) -> Track:
    """`x` delayed by `lag_s`, holding its first value before it starts."""
    t = np.arange(len(x)) / fps
    return np.interp(t - lag_s, t, x)


def tracks(
    weights: list[dict[str, float]],
    jaw: Track,
    fps: float,
    strength: float = 1.0,
    gains: CheekGains = DEFAULT_CHEEK_GAINS,
    jaw_px: float = Gains().jaw_px,
) -> CheekTracks:
    """The cheeks' movement in each frame from the mouth's weights in it and the voice's extra
    jaw opening (`expression.Motion.jaw`, in pixels; `jaw_px` is its loudest)."""
    n = len(weights)
    spread, rounded, opened = np.zeros(n), np.zeros(n), np.zeros(n)
    for i, w in enumerate(weights):
        spread[i] = sum(v * MOUTH_SHAPES[k].controls.get("grin", 0.0) for k, v in w.items())
        rounded[i] = sum(v * MOUTH_SHAPES[k].controls.get("purse", 0.0) for k, v in w.items())
        opened[i] = openness(w)
    spread = np.clip(spread / _GRIN, 0.0, 1.0)
    rounded = np.clip(rounded / _PURSE, 0.0, 1.0)
    # A louder syllable opens the jaw further (expression.motion), and stretches the face more.
    jaw = np.asarray(jaw, np.float64)[:n] if len(jaw) else np.zeros(n)
    opened = np.clip(opened * (1.0 + 0.5 * jaw / jaw_px), 0.0, 1.5)

    def follow(x: Track, px: float) -> Track:
        if not n or not strength:
            return np.zeros(n)
        return strength * px * _smooth(_late(x, fps, gains.lag_s), fps, gains.ease_s)

    return CheekTracks(
        follow(spread, gains.lift_px),
        follow(rounded, gains.draw_px),
        follow(opened, gains.stretch_px),
    )


@dataclass(frozen=True)
class CheekFields:
    """How far each pixel of the face crop moves, (dx, dy) per pixel of each track."""

    lift: tuple[Field, Field]
    draw: tuple[Field, Field]
    stretch: tuple[Field, Field]


def _blob(
    gx: NDArray[np.float64], gy: NDArray[np.float64], x: float, y: float, r: float
) -> NDArray[np.float64]:
    """1 at (x, y), easing to 0 at `r` away."""
    return _taper(np.hypot(gx - x, gy - y), 0.0, r)


def fields(lm: NDArray[np.float32]) -> CheekFields:
    """Where the cheeks, the lines beside the mouth and the chin move, from the face crop's
    68 landmarks. Each field is 1 at its strongest point, 0 on the lips, and fades out before
    the crop's edge (`expression.head_weight`), so the paste into the photo stays seamless."""
    gy, gx = np.mgrid[0:CROP, 0:CROP].astype(np.float64)
    cx = float(lm[48:68, 0].mean())
    mouth_y = float(lm[48:68, 1].mean())
    half = max(8.0, float(np.ptp(lm[48:60, 0])) / 2)  # half the mouth's width
    nose_y = float(lm[33, 1])
    eye_y = float(lm[36:48, 1].mean())
    chin_y = max(float(lm[8, 1]), mouth_y + half)
    side = np.sign(gx - cx)  # -1 left of the mouth, 1 right
    # The lips are left as tuned: nothing moves inside them, easing in just outside.
    lips = np.hypot((gx - cx) / (1.1 * half), (gy - mouth_y) / (0.6 * half))
    keep = (1.0 - _taper(lips, 1.0, 1.7)) * head_weight(lm)

    # The apples of the cheeks, a little above the nose's tip and out past the mouth's corners,
    # and the lines from the nose to the corners, halfway down to the mouth.
    apple_y = nose_y - 0.25 * (nose_y - eye_y)
    r = 1.2 * half
    apples = _blob(gx, gy, cx - 1.5 * half, apple_y, r) + _blob(gx, gy, cx + 1.5 * half, apple_y, r)
    line_y = (nose_y + mouth_y) / 2
    lines = _blob(gx, gy, cx - 1.15 * half, line_y, 0.8 * r) + _blob(
        gx, gy, cx + 1.15 * half, line_y, 0.8 * r
    )
    lift_dx = side * (0.25 * apples + 0.35 * lines)
    lift_dy = -(apples + 0.6 * lines)
    draw_dx = -side * (apples + 0.6 * lines)
    draw_dy = np.zeros_like(gx)

    # Below the mouth: the lower cheeks and chin, most at the chin, none at the nose.
    v = np.interp(gy, [nose_y, mouth_y, chin_y, chin_y + 0.4 * (chin_y - mouth_y)], [0, 0.4, 1, 0])
    h = _taper(np.abs(gx - cx), 0.9 * half, 2.6 * half)
    stretch_dy = v * h
    stretch_dx = np.zeros_like(gx)

    def scaled(dx: NDArray[np.float64], dy: NDArray[np.float64]) -> tuple[Field, Field]:
        top = max(1e-6, float(np.hypot(dx, dy).max()))
        return np.asarray(dx * keep / top, np.float32), np.asarray(dy * keep / top, np.float32)

    return CheekFields(
        scaled(lift_dx, lift_dy), scaled(draw_dx, draw_dy), scaled(stretch_dx, stretch_dy)
    )


def limit(lift: float, draw: float, stretch: float) -> tuple[float, float, float]:
    """The three amounts scaled down together if they could move a pixel further than MAX_PX."""
    total = abs(lift) + abs(draw) + abs(stretch)
    k = min(1.0, MAX_PX / total) if total else 1.0
    return k * lift, k * draw, k * stretch


def log_added(cheeks: CheekTracks, strength: str, seconds: float, frames: int) -> None:
    """The log line R128a asks for, so its cost in a reply can be read beside R96's timings."""
    peak = max(
        (float(np.abs(t).max()) for t in (cheeks.lift, cheeks.draw, cheeks.stretch) if len(t)),
        default=0.0,
    )
    logger.info(
        "Face movement added",
        extra={
            "strength": strength,
            "frames": frames,
            "peak_px": round(min(peak, MAX_PX), 2),
            "duration_ms": round(seconds * 1000, 1),
        },
    )


def strength_of(name: str) -> float:
    """The setting's strength; an unknown name is logged and taken as "normal"."""
    if name in STRENGTHS:
        return STRENGTHS[name]
    logger.error("Unknown face movement strength; using normal", extra={"strength": name})
    return STRENGTHS["normal"]
