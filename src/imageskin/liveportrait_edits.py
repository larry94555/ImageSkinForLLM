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
import random
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
    # Lowers the brows (found by rendering each keypoint): in a real blink the muscle around
    # the eye pulls them down a little, and lids moving alone look like a doll's.
    "brow": ((2, 1, -0.001),),
}

BLINK_CLOSED = 15.0  # "blink" amount that fully closes the eyes (checked on real weights)

# Larry's accepted settings (2026-10-06): the lip spread and rounding move 45% of the way
# from rest, and the upper lip moves 30% as far as the rest of the mouth. In R13 the opening
# barely moved at 45% and opened too far at 100% of the wider shapes below; Larry asked for
# halfway between, which is 60% of the way to the wider shapes.
STRENGTH = 0.45
OPENING = 0.6
UPPER_LIP = 0.3


@dataclass(frozen=True)
class MouthShape:
    ratio: float | None  # lip opening for the retargeting model; None keeps the photo's
    controls: dict[str, float]


# Tuned by eye on two portraits (a painting turned slightly sideways and a frontal photo).
# The vowel openings were widened 1.7 times in R13, when Larry found the mouth barely moved
# in the sample video.
MOUTH_SHAPES: dict[str, MouthShape] = {
    "rest": MouthShape(None, {}),
    "MBP": MouthShape(0.0, {"open": -15.0}),  # lips pressed: m, b, p
    "FV": MouthShape(0.08, {"grin": 8.0, "open": -8.0}),  # upper teeth on lower lip: f, v
    "AA": MouthShape(0.60, {"grin": 3.0}),  # father, cup
    "EH": MouthShape(0.43, {"grin": 5.0}),  # bed, cat
    "EE": MouthShape(0.20, {"grin": 7.0}),  # see, it
    "IH": MouthShape(0.31, {"grin": 3.0}),  # small opening: t, d, n, s, k, l, the
    # Rounding halved after Larry saw a kiss-like pucker (2026-10-06).
    "OH": MouthShape(0.51, {"purse": 7.0}),  # go, more
    "OO": MouthShape(0.20, {"purse": 12.0}),  # you, would, boat's w
    "SH": MouthShape(0.26, {"purse": 5.0}),  # she, chair, judge
}
assert tuple(MOUTH_SHAPES) == SHAPES

# The idle loop the face moves through while it speaks: whole cycles, so it repeats smoothly.
LOOP_SECONDS = 8.0

# Blinks are added when a video is made, not baked into the idle loop, so they never repeat
# on the loop's cycle. The eyes are rendered on the still head at these openness levels
# (1 open, 0 closed), with the brows dipping by up to BLINK_BROW.
EYE_STAGES = (0.7, 0.4, 0.15, 0.0)
BLINK_BROW = 6.0


def expression_delta(controls: dict[str, float]) -> list[list[float]]:
    """Sum the control offsets into a NUM_KP x 3 matrix. Unknown names raise KeyError."""
    delta = [[0.0, 0.0, 0.0] for _ in range(NUM_KP)]
    for name, amount in controls.items():
        for kp, axis, coef in CONTROLS[name]:
            delta[kp][axis] += coef * amount
    return delta


def soften(name: str, strength: float, photo_ratio: float) -> tuple[dict[str, float], float]:
    """A shape's controls moved only `strength` (0..1) of the way from rest, and its lip
    ratio moved OPENING of the way from the photo's.

    Lip-contact shapes (m, b, p, f, v) keep their lip ratio so the lips still touch; only
    their press and spread soften.
    """
    if not 0.0 <= strength <= 1.0:
        raise ValueError(f"strength must be between 0 and 1, got {strength}")
    shape = MOUTH_SHAPES[name]
    target = photo_ratio if shape.ratio is None else shape.ratio
    ratio = target if name in CONTACT else photo_ratio + OPENING * (target - photo_ratio)
    return {k: strength * v for k, v in shape.controls.items()}, ratio


def top_two(weights: dict[str, float]) -> tuple[str, str, float]:
    """The two strongest shapes and how far to morph from the first toward the second."""
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])
    if len(ranked) == 1:
        return ranked[0][0], ranked[0][0], 0.0
    (a, wa), (b, wb) = ranked[0], ranked[1]
    return a, b, wb / (wa + wb)


@dataclass(frozen=True)
class Blink:
    start: float  # seconds
    close_s: float  # the lids come down fast...
    hold_s: float
    open_s: float  # ...and go back up more slowly
    depth: float = 0.0  # how open the eyes get at the bottom: 0 is fully closed

    def openness(self, t: float) -> float:
        t -= self.start
        if t <= 0.0 or t >= self.close_s + self.hold_s + self.open_s:
            return 1.0
        if t < self.close_s:
            s = t / self.close_s
            return 1.0 - (1.0 - self.depth) * s * s  # the lids speed up as they close
        t -= self.close_s
        if t < self.hold_s:
            return self.depth
        s = (t - self.hold_s) / self.open_s
        return self.depth + (1.0 - self.depth) * (1.0 - (1.0 - s) ** 2)  # and slow to a stop


def blink_times(seconds: float, seed: int) -> list[Blink]:
    """When the person blinks in a video `seconds` long: about every 3 seconds but never on a
    beat (2 to 8 s apart), each blink a little different, now and then a half blink or two
    blinks in a row, as people do while talking. The same seed gives the same blinks.

    Every blink ends before the video does: one cut off would leave the eyes half shut on
    the last frame, which a player keeps on screen."""
    rng = random.Random(seed)
    blinks: list[Blink] = []
    t = rng.uniform(0.5, 2.5)
    double = False
    while True:
        depth = rng.uniform(0.2, 0.5) if rng.random() < 0.15 else 0.0
        blink = Blink(
            t, rng.uniform(0.07, 0.1), rng.uniform(0.0, 0.05), rng.uniform(0.14, 0.24), depth
        )
        end = t + blink.close_s + blink.hold_s + blink.open_s
        if end > seconds:
            return blinks
        blinks.append(blink)
        double = not double and rng.random() < 0.1  # a second blink after it, never a third
        if double:
            t = end + rng.uniform(0.08, 0.2)
        else:
            t = end + min(8.0, max(2.0, rng.lognormvariate(math.log(3.0), 0.5)))


def eye_track(n_frames: int, fps: float, seed: int) -> list[float]:
    """How open the eyes are in each video frame, averaged over the frame's time as a camera
    would see it, so a blink shorter than a frame still shows."""
    blinks = blink_times(n_frames / fps, seed)
    track = []
    for f in range(n_frames):
        times = [(f + (k + 0.5) / 4) / fps for k in range(4)]
        track.append(sum(min((b.openness(t) for b in blinks), default=1.0) for t in times) / 4)
    return track


def idle_motion(frame: int, n_frames: int) -> tuple[float, float, float]:
    """Head (pitch, yaw, roll) in degrees for one frame of the idle loop.

    The head drifts by a degree or two: a slow turn with a faster, smaller one on top, a
    slight nod and tilt, all in whole cycles so the last frame flows back into the first.
    """
    phase = 2 * math.pi * frame / n_frames
    pitch = 0.8 * math.sin(2 * phase + 0.5)
    yaw = 1.5 * math.sin(phase) + 0.5 * math.sin(3 * phase + 1.0)
    roll = 0.6 * math.sin(phase + 2.0)
    return pitch, yaw, roll
