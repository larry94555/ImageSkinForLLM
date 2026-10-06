"""LivePortrait edits for each mouth shape, and how to soften and blend them.

Which sound gets which shape, and how much of each shape to show per frame, live in the app
(`imageskin.visemes`, roadmap R4b); this file keeps only the LivePortrait-specific part.

Each mouth shape is a LivePortrait edit:
  - `ratio`: how far apart the lips are, fed to LivePortrait's lip retargeting model. That
    model moves several mouth keypoints together, so the mouth opens straight down. The old
    "open" edit moved one off-centre keypoint (19) alone, which made the lower lip drift
    sideways (roadmap R4a). None means "as in the photo".
  - `controls`: expression edits from experiments/photoreal/face_points.py for the lip shape:
    "purse" rounds the lips, "grin" spreads them, "open" (kept small) presses or relaxes.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

# The app's package, so this runs from a checkout without installing it.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from imageskin.visemes import CONTACT  # noqa: E402


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
