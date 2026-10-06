"""Mouth shapes for lip-reading: sounds to shapes, and shapes to per-frame weights.

Pure Python with no third-party imports, so these run in CI without the model stack.

Each mouth shape is a LivePortrait edit:
  - `ratio`: how far apart the lips are, fed to LivePortrait's lip retargeting model. That
    model moves several mouth keypoints together, so the mouth opens straight down. The old
    "open" edit moved one off-centre keypoint (19) alone, which made the lower lip drift
    sideways (roadmap R4a). None means "as in the photo".
  - `controls`: expression edits from experiments/photoreal/face_points.py for the lip shape:
    "purse" rounds the lips, "grin" spreads them, "open" (kept small) presses or relaxes.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Shape:
    ratio: float | None  # lip opening for the retargeting model; None keeps the photo's
    controls: dict[str, float]


# Tuned by eye on two portraits (a painting turned slightly sideways and a frontal photo),
# keeping the gap between the lips small, as Larry asked.
SHAPES: dict[str, Shape] = {
    "rest": Shape(None, {}),
    "MBP": Shape(0.0, {"open": -15.0}),  # lips pressed: m, b, p
    "FV": Shape(0.08, {"grin": 8.0, "open": -8.0}),  # upper teeth on lower lip: f, v
    "AA": Shape(0.35, {"grin": 3.0}),  # father, cup
    "EH": Shape(0.25, {"grin": 5.0}),  # bed, cat
    "EE": Shape(0.12, {"grin": 7.0}),  # see, it
    "IH": Shape(0.18, {"grin": 3.0}),  # small opening: t, d, n, s, k, l, the
    "OH": Shape(0.30, {"purse": 14.0}),  # go, more
    "OO": Shape(0.12, {"purse": 24.0}),  # you, would, boat's w
    "SH": Shape(0.15, {"purse": 10.0}),  # she, chair, judge
}

_GROUPS = {
    "MBP": "mbp",
    "FV": "fv",
    "OO": "uwʊ",
    "OH": "oɔɒ",
    "AA": "aɑʌɐ",
    "EH": "ɛeæ",
    "EE": "iɪj",
    "SH": "ʃʒʧʤ",
    # r stays neutral: rounding it made "three green trees" pulse the mouth corners in and
    # out between r and ee (Larry, 2026-10-06).
    "IH": "tdnlszkgɡhθðŋɾʔxçəᵻɹrɝɚ",
}
VISEME_OF: dict[str, str] = {ch: name for name, chars in _GROUPS.items() for ch in chars}
PAUSES = set(",.!?;:—…")
HOLDS = set(" ˈˌːʰ̃")  # spaces, stress and length marks keep the shape before them
CONTACT = ("MBP", "FV")  # sounds a lip-reader needs to see the lips touch


@dataclass(frozen=True)
class Segment:
    shape: str
    start: float  # seconds
    end: float


def segments(phonemes: str, durations: list[float]) -> list[Segment]:
    """Mouth-shape segments from phonemes and how long each lasts (seconds, one per char)."""
    if len(phonemes) != len(durations):
        raise ValueError(f"{len(phonemes)} phonemes but {len(durations)} durations")
    out: list[Segment] = []
    t = 0.0
    for ch, d in zip(phonemes, durations, strict=True):
        if ch in HOLDS and out:
            last = out[-1]
            out[-1] = Segment(last.shape, last.start, t + d)
        else:
            shape = "rest" if ch in PAUSES or ch in HOLDS else VISEME_OF.get(ch, "IH")
            if out and out[-1].shape == shape:
                out[-1] = Segment(shape, out[-1].start, t + d)
            else:
                out.append(Segment(shape, t, t + d))
        t += d
    return out


def frame_weights(
    segs: list[Segment],
    n_frames: int,
    fps: float,
    smooth_s: float = 0.06,
    lead_s: float = 0.03,
) -> list[dict[str, float]]:
    """How much of each mouth shape to show in each video frame.

    Shapes blend into each other over several frames (a Gaussian of `smooth_s` seconds),
    the way real lips start the next sound before the current one ends. Lip contact
    sounds (m, b, p, f, v) are often shorter than a frame and would blur away, so the
    frame nearest the middle of each one shows that shape fully.
    """
    step = 0.005
    end = n_frames / fps
    n_steps = int(math.ceil(end / step)) + 1
    names = list(SHAPES)
    grid = [[0.0] * n_steps for _ in names]
    index = {name: i for i, name in enumerate(names)}
    k = 0
    for s in range(n_steps):
        t = s * step
        while k < len(segs) and segs[k].end <= t:
            k += 1
        shape = segs[k].shape if k < len(segs) and segs[k].start <= t else "rest"
        grid[index[shape]][s] = 1.0

    radius = max(1, int(3 * smooth_s / step))
    kernel = [math.exp(-0.5 * (i * step / smooth_s) ** 2) for i in range(-radius, radius + 1)]
    out: list[dict[str, float]] = []
    for f in range(n_frames):
        centre = round(((f + 0.5) / fps + lead_s) / step)
        weights: dict[str, float] = {}
        total = 0.0
        for name, row in zip(names, grid, strict=True):
            acc = 0.0
            for j, kv in enumerate(kernel):
                s = min(n_steps - 1, max(0, centre + j - radius))
                acc += kv * row[s]
            if acc > 1e-6:
                weights[name] = acc
                total += acc
        out.append({name: w / total for name, w in weights.items()})

    for seg in segs:
        if seg.shape in CONTACT:
            f = min(n_frames - 1, max(0, int(((seg.start + seg.end) / 2 - lead_s) * fps)))
            out[f] = {seg.shape: 1.0}
    return out


def soften(name: str, strength: float, photo_ratio: float) -> tuple[dict[str, float], float]:
    """A shape's controls and lip ratio, moved only `strength` (0..1) of the way from rest.

    Lip-contact shapes (m, b, p, f, v) keep their lip ratio so the lips still touch; only
    their press and spread soften.
    """
    if not 0.0 <= strength <= 1.0:
        raise ValueError(f"strength must be between 0 and 1, got {strength}")
    shape = SHAPES[name]
    target = photo_ratio if shape.ratio is None else shape.ratio
    ratio = target if name in CONTACT else photo_ratio + strength * (target - photo_ratio)
    return {k: strength * v for k, v in shape.controls.items()}, ratio


def mix(
    weights: dict[str, float], photo_ratio: float, strength: float = 1.0
) -> tuple[dict[str, float], float]:
    """Blend softened shapes into one set of expression controls and one lip ratio."""
    controls: dict[str, float] = {}
    ratio = 0.0
    for name, w in weights.items():
        shape_controls, shape_ratio = soften(name, strength, photo_ratio)
        ratio += w * shape_ratio
        for key, value in shape_controls.items():
            controls[key] = controls.get(key, 0.0) + w * value
    return controls, ratio


def top_two(weights: dict[str, float]) -> tuple[str, str, float]:
    """The two strongest shapes and how far to morph from the first toward the second."""
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])
    if len(ranked) == 1:
        return ranked[0][0], ranked[0][0], 0.0
    (a, wa), (b, wb) = ranked[0], ranked[1]
    return a, b, wb / (wa + wb)
