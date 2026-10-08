"""Expression from the voice itself: loudness and pitch drive the jaw, brows and head.

Larry, after R25 (2026-10-08): the cloned voice rises, falls and gets louder, but the face moved
the same way whether a word was whispered or shouted. Tried in experiments/expressive (GitHub
PR #32) and kept. Nothing here runs a model; everything comes from the WAV the voice engine
wrote, and the motion is drawn as small smooth warps on the photoreal engine's frames:
  - jaw: louder syllables open wider and quiet ones a little less, scaled by how open the
    mouth shape already is, so m, b, p, f and v still close;
  - brows: lift on high or stressed words;
  - head: a gentle nod on the strongest beat of a phrase, a tilt and slight lift with the
    pitch, and a slow side-to-side drift while speaking.
Pixels are in LivePortrait's 512 px face crop.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, NamedTuple

import cv2
import numpy as np
from numpy.typing import NDArray

from imageskin.liveportrait_edits import MOUTH_SHAPES
from imageskin.photoreal_library import CROP, Image
from imageskin.visemes import CONTACT

logger = logging.getLogger(__name__)

Track = NDArray[np.float64]
Field = NDArray[np.float32]
Shift = NDArray[np.floating[Any]] | float  # pixels to move, per pixel or for all of them

LEAD_S = 0.03  # the face moves just ahead of the sound, like the mouth (visemes.frame_weights)


def _smooth(x: Track, fps: float, sigma_s: float) -> Track:
    """A Gaussian blur over time."""
    sigma = sigma_s * fps
    radius = max(1, int(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    k /= k.sum()
    return np.convolve(np.pad(x, radius, mode="edge"), k, mode="valid")


def loudness(samples: NDArray[np.float32], rate: int, n_frames: int, fps: float) -> Track:
    """Loudness per frame, scaled to this speech: 0.05 at its quiet end, 1 at its loudest.

    Speech loudness is measured in dB over a 40 ms window; silence (more than 35 dB below the
    loudest part) is 0.
    """
    half = int(0.02 * rate)
    db = np.full(n_frames, -120.0)
    for f in range(n_frames):
        c = int(((f + 0.5) / fps + LEAD_S) * rate)
        w = samples[max(0, c - half) : c + half]
        if len(w):
            db[f] = 10 * math.log10(float(np.mean(w.astype(np.float64) ** 2)) + 1e-12)
    top = float(np.percentile(db, 98))
    if top < -70:  # no speech at all
        return np.zeros(n_frames)
    speech = db > top - 35
    if not speech.any():
        return np.zeros(n_frames)
    low = min(float(np.percentile(db[speech], 15)), top - 12)  # even steady speech has a range
    level = np.clip((db - low) / (top - low), 0.0, 1.0)
    return np.where(speech, 0.05 + 0.95 * level, 0.0)  # any speech is above 0, silence is 0


def _f0(window: NDArray[np.float64], rate: int) -> float:
    """The voice's pitch in one window by autocorrelation, or 0 where it is not voiced. The
    earliest strong peak wins, which avoids landing an octave low."""
    w = (window - window.mean()) * np.hanning(len(window))
    spec = np.fft.rfft(w, n=2 * len(w))
    ac = np.fft.irfft(np.abs(spec) ** 2)[: len(w)]
    if ac[0] <= 0:
        return 0.0
    ac = ac / ac[0]
    lo, hi = int(rate / 400), min(len(ac) - 1, int(rate / 65))
    if hi <= lo:
        return 0.0
    seg = ac[lo:hi]
    best = float(seg.max())
    if best < 0.5:
        return 0.0
    i = int(np.argmax(seg >= 0.9 * best))
    while i + 1 < len(seg) and seg[i + 1] > seg[i]:  # climb to the top of that peak
        i += 1
    shift = 0.0
    if 0 < i < len(seg) - 1:  # and place it between samples
        a, b, c = seg[i - 1], seg[i], seg[i + 1]
        shift = 0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c else 0.0
    return rate / (lo + i + shift)


def pitch(
    samples: NDArray[np.float32], rate: int, n_frames: int, fps: float, voiced: Track
) -> Track:
    """Pitch per frame in semitones from the speaker's own median, 0 where there is no voice.

    Unvoiced frames hold the last voiced value and ease back to 0, so the motion it drives
    does not jump between syllables.
    """
    half = int(0.02 * rate)
    f0 = np.zeros(n_frames)
    for f in range(n_frames):
        c = int(((f + 0.5) / fps + LEAD_S) * rate)
        w = samples[max(0, c - half) : c + half].astype(np.float64)
        if voiced[f] > 0.25 and len(w) == 2 * half:
            f0[f] = _f0(w, rate)
    good = f0 > 0
    if good.sum() < 5:
        return np.zeros(n_frames)
    mid = float(np.median(f0[good]))
    f0 = np.where(f0 > 1.7 * mid, f0 / 2, np.where(good & (f0 < mid / 1.7), f0 * 2, f0))  # octaves
    st = np.zeros(n_frames)
    st[good] = 12 * np.log2(f0[good] / mid)
    # A median over 5 frames drops the odd wrong frame without blunting real rises.
    padded = np.pad(np.where(good, st, np.nan), 2, constant_values=np.nan)
    windows = np.lib.stride_tricks.sliding_window_view(padded, 5)
    st[good] = np.nanmedian(windows[good], axis=1)
    out = np.zeros(n_frames)
    last = 0.0
    for i in range(n_frames):
        last = float(st[i]) if good[i] else last * 0.9
        out[i] = last
    return _smooth(out, fps, 0.08)


def accents(loud: Track, fps: float, min_gap_s: float = 0.3) -> list[tuple[int, float]]:
    """The stressed beats: loudness peaks that stand out from the frames around them, as
    (frame, strength 0..1), at least `min_gap_s` apart."""
    smooth = _smooth(loud, fps, 0.04)
    base = _smooth(loud, fps, 0.4)
    rise = smooth - base
    out: list[tuple[int, float]] = []
    gap = int(min_gap_s * fps)
    for i in range(1, len(rise) - 1):
        if rise[i] >= rise[i - 1] and rise[i] > rise[i + 1] and rise[i] > 0.08 and smooth[i] > 0.5:
            if out and i - out[-1][0] < gap:
                if rise[i] > out[-1][1]:
                    out[-1] = (i, float(rise[i]))
                continue
            out.append((i, float(rise[i])))
    peak = max((s for _, s in out), default=1.0)
    return [(i, min(1.0, s / peak)) for i, s in out]


@dataclass(frozen=True)
class Gains:
    """How strongly the voice drives the face. Pixels are in LivePortrait's 512 px face crop."""

    jaw_px: float = 12.0  # extra opening at the loudest syllables, on the most open shape
    quiet: float = 0.35  # the quietest syllables open this share of jaw_px less
    brow_px: float = 8.0  # brow lift at a high or stressed note
    # The head: Larry found nodding on every stressed syllable bouncy (2026-10-08), so it nods
    # only on the strongest beat of a phrase, gently and slowly, and drifts side to side.
    nod_px: float = 2.5  # head dip on the strongest beat of a phrase
    nod_gap_s: float = 1.5  # at most one nod in this long
    tilt_deg: float = 1.5  # head tilt per 4 semitones of pitch
    lift_px: float = 1.0  # head lift per 4 semitones of pitch
    sway_px: float = 3.0  # slow side-to-side drift while speaking


@dataclass(frozen=True)
class Motion:
    """Per frame: extra jaw opening (px, negative closes a little), brow lift (px), head drop
    (px, positive is down), tilt (degrees) and sway (px, positive is to the right)."""

    jaw: Track
    brow: Track
    nod: Track
    tilt: Track
    sway: Track

    def at(self, i: int) -> FrameMotion:
        return FrameMotion(
            float(self.jaw[i]),
            float(self.brow[i]),
            float(self.nod[i]),
            float(self.tilt[i]),
            float(self.sway[i]),
        )


class FrameMotion(NamedTuple):
    """The motion in one frame, in the units of `Motion`."""

    jaw: float = 0.0
    brow: float = 0.0
    nod: float = 0.0
    tilt: float = 0.0
    sway: float = 0.0


STILL = FrameMotion()


def sway(loud: Track, fps: float, seed: int) -> Track:
    """A slow side-to-side drift, 1 at most: a few slow waves (3 to 8 seconds long) mixed at
    random, so it never repeats on a beat, and larger while the person speaks than in pauses.
    The same seed gives the same drift."""
    rng = np.random.default_rng(seed)
    t = np.arange(len(loud)) / fps
    wave = sum(
        rng.uniform(0.5, 1.0) * np.sin(2 * np.pi * rng.uniform(0.12, 0.33) * t + rng.uniform(0, 7))
        for _ in range(3)
    )
    wave = np.asarray(wave, np.float64)
    wave /= max(1e-6, float(np.abs(wave).max()))
    speaking = np.clip(1.5 * _smooth((loud > 0).astype(np.float64), fps, 0.8), 0.4, 1.0)
    return _smooth(wave * speaking, fps, 0.2)


DEFAULT_GAINS = Gains()


def motion(
    samples: NDArray[np.float32],
    rate: int,
    n_frames: int,
    fps: float,
    gains: Gains = DEFAULT_GAINS,
) -> Motion:
    start = time.perf_counter()
    loud = loudness(samples, rate, n_frames, fps)
    st = pitch(samples, rate, n_frames, fps, loud)
    beats = accents(loud, fps)
    phrase_beats = [(f, s) for f, s in accents(loud, fps, gains.nod_gap_s) if s >= 0.5]

    level = _smooth(loud, fps, 0.05)
    # Average syllables keep today's mouth; louder ones open wider, quieter ones a little less.
    centred = 2 * (level - 0.5)
    jaw = gains.jaw_px * np.where(centred > 0, centred, gains.quiet * centred) * (loud > 0)

    high = np.clip(_smooth(st, fps, 0.15) / 4.0, 0.0, 1.0)
    brow = np.zeros(n_frames)
    nod = np.zeros(n_frames)
    t = np.arange(n_frames) / fps
    for f, s in beats:
        u = (t - t[f] + 0.06) / 0.16  # peaks 0.1 s after the beat starts
        bump = np.where(u > 0, u * np.exp(1 - u), 0.0)
        brow += 0.5 * s * bump * (0.4 + high[f])  # brows go up most on high, stressed words
    for f, s in phrase_beats:
        u = (t - t[f] + 0.1) / 0.35  # a slow, gentle nod that peaks 0.25 s after the beat
        nod += gains.nod_px * s * np.where(u > 0, u * np.exp(1 - u), 0.0)
    brow = gains.brow_px * np.clip(0.6 * high + brow, 0.0, 1.0)

    slow = _smooth(st, fps, 0.45) / 4.0
    tilt = gains.tilt_deg * np.clip(slow, -1.0, 1.0)
    nod = nod - gains.lift_px * np.clip(slow, -1.0, 1.0)
    seed = int.from_bytes(hashlib.sha256(samples.tobytes()).digest()[:8], "big")
    logger.info(
        "Measured voice expression",
        extra={
            "frames": n_frames,
            "beats": len(beats),
            "nods": len(phrase_beats),
            "pitch_range_st": round(float(np.ptp(st)), 1),
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return Motion(
        jaw,
        brow,
        _smooth(nod, fps, 0.1),
        _smooth(tilt, fps, 0.15),
        gains.sway_px * sway(loud, fps, seed),
    )


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


def push(image: Image, grid: Field, dx: Shift, dy: Shift) -> Image:
    """Move pixels by (dx, dy): each output pixel takes the colour from where it came."""
    m = grid.copy()
    m[..., 0] -= dx
    m[..., 1] -= dy
    out = cv2.remap(image, m, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)  # type: ignore[call-overload]
    return np.asarray(out, np.uint8)
