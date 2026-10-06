"""LivePortrait edits for the photoreal engine: mouth shapes, blinks and idle head motion.

Pure Python, so it runs in CI without the model stack. The mouth shapes and their softening
were tuned with Larry in the lip-reading test (roadmap R4a, GitHub PR #13); which sound gets
which shape, and how shapes blend over time, live in `imageskin.visemes`.

Each mouth shape is a LivePortrait edit:
  - `ratio`: how far apart the lips are, fed to LivePortrait's lip retargeting model, which
    moves the mouth keypoints together so the mouth opens straight down. None keeps the
    photo's lips.
  - `controls`: expression edits for the lip shape: "purse" rounds the lips, "grin" spreads
    them, "open" (kept small) presses or relaxes them.
"""

import math
from dataclasses import dataclass

from imageskin.visemes import CONTACT, SHAPES

NUM_KP = 21  # LivePortrait's implicit keypoints
UPPER_LIP_KP = 20  # the keypoint that lifts the upper lip (found by rendering each)

# MediaPipe Face Landmarker (478 points) to the classic 68-point layout that LivePortrait's
# cropper understands. Order: jaw 17, brows 5+5, nose 4+5, eyes 6+6, outer lips 12, inner 8.
MP_TO_68: tuple[int, ...] = (
    162, 234, 93, 58, 172, 136, 149, 148, 152, 377, 378, 365, 397, 288, 323, 454, 389,
    71, 63, 105, 66, 107, 336, 296, 334, 293, 301,
    168, 197, 5, 4, 75, 97, 2, 326, 305,
    33, 160, 158, 133, 153, 144, 362, 385, 387, 263, 373, 380,
    61, 39, 37, 0, 267, 269, 291, 405, 314, 17, 84, 181,
    78, 82, 13, 312, 308, 317, 14, 87,
)  # fmt: skip

# Expression controls as (keypoint, axis, coefficient) added to LivePortrait's expression
# offsets per unit of the control. Coefficients follow LivePortrait's image editor
# (src/gradio_pipeline.py, MIT); names follow its slider labels.
CONTROLS: dict[str, tuple[tuple[int, int, float], ...]] = {
    "open": ((19, 1, 0.001), (19, 2, 0.0001), (17, 1, -0.0001)),
    # LivePortrait's editor also pushes keypoint 17 forward here; that made the lips look
    # like a kiss (Larry, 2026-10-06), so rounding only draws the corners in.
    "purse": ((14, 1, 0.001), (3, 1, -0.0005), (7, 1, -0.0005)),
    "grin": ((20, 2, -0.001), (20, 1, -0.001), (14, 1, -0.001)),
    # Both eyelids, from the editor's eyeball-direction slider (sign flipped so positive
    # closes). LivePortrait's eye retargeting model closed only one eye on a turned head.
    "blink": ((11, 1, 0.001), (13, 1, -0.0003), (15, 1, 0.001), (16, 1, -0.0003)),
}

BLINK_CLOSED = 15.0  # "blink" amount that fully closes the eyes (checked on real weights)

# Larry's accepted settings (2026-10-06): shapes move 45% of the way from rest, and the
# upper lip moves 30% as far as the rest of the mouth.
STRENGTH = 0.45
UPPER_LIP = 0.3


@dataclass(frozen=True)
class MouthShape:
    ratio: float | None  # lip opening for the retargeting model; None keeps the photo's
    controls: dict[str, float]


# Tuned by eye on two portraits (a painting turned slightly sideways and a frontal photo),
# keeping the gap between the lips small.
MOUTH_SHAPES: dict[str, MouthShape] = {
    "rest": MouthShape(None, {}),
    "MBP": MouthShape(0.0, {"open": -15.0}),  # lips pressed: m, b, p
    "FV": MouthShape(0.08, {"grin": 8.0, "open": -8.0}),  # upper teeth on lower lip: f, v
    "AA": MouthShape(0.35, {"grin": 3.0}),  # father, cup
    "EH": MouthShape(0.25, {"grin": 5.0}),  # bed, cat
    "EE": MouthShape(0.12, {"grin": 7.0}),  # see, it
    "IH": MouthShape(0.18, {"grin": 3.0}),  # small opening: t, d, n, s, k, l, the
    # Rounding halved after Larry saw a kiss-like pucker (2026-10-06).
    "OH": MouthShape(0.30, {"purse": 7.0}),  # go, more
    "OO": MouthShape(0.12, {"purse": 12.0}),  # you, would, boat's w
    "SH": MouthShape(0.15, {"purse": 5.0}),  # she, chair, judge
}
assert tuple(MOUTH_SHAPES) == SHAPES

# The idle loop the face moves through while it speaks: whole cycles, so it repeats smoothly.
LOOP_SECONDS = 8.0
BLINKS_AT = (2.0, 5.6)  # seconds into the loop; uneven gaps look less mechanical
BLINK_CLOSE_S = 0.08  # eyelids close quickly and open more slowly, as in a real blink
BLINK_OPEN_S = 0.16


def expression_delta(controls: dict[str, float]) -> list[list[float]]:
    """Sum the control offsets into a NUM_KP x 3 matrix. Unknown names raise KeyError."""
    delta = [[0.0, 0.0, 0.0] for _ in range(NUM_KP)]
    for name, amount in controls.items():
        for kp, axis, coef in CONTROLS[name]:
            delta[kp][axis] += coef * amount
    return delta


def soften(name: str, strength: float, photo_ratio: float) -> tuple[dict[str, float], float]:
    """A shape's controls and lip ratio, moved only `strength` (0..1) of the way from rest.

    Lip-contact shapes (m, b, p, f, v) keep their lip ratio so the lips still touch; only
    their press and spread soften.
    """
    if not 0.0 <= strength <= 1.0:
        raise ValueError(f"strength must be between 0 and 1, got {strength}")
    shape = MOUTH_SHAPES[name]
    target = photo_ratio if shape.ratio is None else shape.ratio
    ratio = target if name in CONTACT else photo_ratio + strength * (target - photo_ratio)
    return {k: strength * v for k, v in shape.controls.items()}, ratio


def eye_openness(t: float) -> float:
    """How open the eyes are (1 open, 0 closed) `t` seconds into the idle loop."""
    for at in BLINKS_AT:
        if at - BLINK_CLOSE_S <= t <= at:
            x = (at - t) / BLINK_CLOSE_S
        elif at < t <= at + BLINK_OPEN_S:
            x = (t - at) / BLINK_OPEN_S
        else:
            continue
        return 0.5 - 0.5 * math.cos(math.pi * x)  # eased, so the lids don't snap
    return 1.0


def idle_motion(frame: int, n_frames: int, fps: float) -> tuple[float, float, float, float]:
    """Head (pitch, yaw, roll) in degrees and eye openness for one frame of the idle loop.

    The head drifts by a degree or two: a slow turn with a faster, smaller one on top, a
    slight nod and tilt, all in whole cycles so the last frame flows back into the first.
    """
    phase = 2 * math.pi * frame / n_frames
    pitch = 0.8 * math.sin(2 * phase + 0.5)
    yaw = 1.5 * math.sin(phase) + 0.5 * math.sin(3 * phase + 1.0)
    roll = 0.6 * math.sin(phase + 2.0)
    return pitch, yaw, roll, eye_openness(frame / fps)
