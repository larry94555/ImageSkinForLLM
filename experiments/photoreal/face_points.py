"""Pure helpers for the LivePortrait CPU test: landmark mapping, mouth shapes, timing.

No third-party imports, so these run in CI without the heavy model stack.
"""

import math

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

NUM_KP = 21  # LivePortrait implicit keypoints

# Expression controls as (keypoint, axis, coefficient) added to LivePortrait's expression
# offsets per unit of the control. Coefficients follow LivePortrait's image editor
# (src/gradio_pipeline.py, MIT); names follow its slider labels.
CONTROLS: dict[str, tuple[tuple[int, int, float], ...]] = {
    "open": ((19, 1, 0.001), (19, 2, 0.0001), (17, 1, -0.0001)),
    "pout": ((19, 0, 1.0),),
    "purse": ((14, 1, 0.001), (3, 1, -0.0005), (7, 1, -0.0005), (17, 2, -0.0005)),
    "grin": ((20, 2, -0.001), (20, 1, -0.001), (14, 1, -0.001)),
    "smile": (
        (20, 1, -0.01), (14, 1, -0.02), (17, 1, 0.0065), (17, 2, 0.003),
        (13, 1, -0.00275), (16, 1, -0.00275), (3, 1, -0.0035), (7, 1, -0.0035),
    ),
}  # fmt: skip

# A first set of mouth shapes (visemes). The full plan needs about 12 to 15; these cover the
# most distinct ones so the test shows whether the edits look photoreal.
VISEMES: dict[str, dict[str, float]] = {
    "rest": {},
    "AA": {"open": 70.0},  # father, hot
    "EH": {"open": 35.0, "grin": 4.0},  # bed, cat
    "EE": {"open": 15.0, "grin": 10.0},  # see, it
    "OH": {"open": 45.0, "purse": 8.0},  # go, law
    "OO": {"open": 10.0, "purse": 12.0, "pout": 0.05},  # you, wood
    "MBP": {"open": -40.0},  # lips pressed: m, b, p
    "FV": {"open": 5.0, "purse": -10.0},  # lower lip to teeth: f, v
}

# Moods are expression offsets held for a whole base loop.
MOODS: dict[str, dict[str, float]] = {
    "neutral": {},
    "happy": {"smile": 0.6},
}


def expression_delta(controls: dict[str, float]) -> list[list[float]]:
    """Sum the control offsets into a NUM_KP x 3 matrix. Unknown names raise KeyError."""
    delta = [[0.0, 0.0, 0.0] for _ in range(NUM_KP)]
    for name, amount in controls.items():
        for kp, axis, coef in CONTROLS[name]:
            delta[kp][axis] += coef * amount
    return delta


def loop_motion(frame: int, n_frames: int, fps: float) -> tuple[float, float, float, float]:
    """Head (pitch, yaw, roll) in degrees and eye openness (0..1) for one frame of a base loop.

    Motion is sinusoidal with whole cycles, so the last frame flows back into the first.
    One blink of about 0.2 s sits a third of the way through.
    """
    phase = 2 * math.pi * frame / n_frames
    pitch = 1.5 * math.sin(2 * phase)
    yaw = 3.0 * math.sin(phase)
    roll = 1.0 * math.sin(phase + math.pi / 3)
    blink_center = n_frames / 3
    half_width = max(1.0, 0.1 * fps)
    distance = abs(frame - blink_center) / half_width
    eye_open = min(1.0, distance)
    return pitch, yaw, roll, eye_open


def viseme_frames(
    segments: list[tuple[str, float, float]], fps: float, blend_s: float = 0.04
) -> list[tuple[str, str, float]]:
    """Turn timed mouth shapes into one (from, to, weight) entry per video frame.

    segments: (viseme, start_s, end_s) in time order; gaps are filled with "rest".
    Each frame shows `from` blended toward `to` by `weight` (0..1), so shapes cross-fade
    over `blend_s` seconds before each change instead of popping.
    """
    if not segments:
        return []
    end = segments[-1][2]
    n = max(1, round(end * fps))
    frames: list[tuple[str, str, float]] = []
    for i in range(n):
        t = (i + 0.5) / fps
        current, next_shape, next_start = "rest", "rest", end
        for j, (name, start, stop) in enumerate(segments):
            if start <= t < stop:
                current = name
                if j + 1 < len(segments):
                    next_shape, next_start = segments[j + 1][0], segments[j + 1][1]
                else:
                    next_start = stop
                break
            if t < start:
                next_shape, next_start = name, start
                break
        remaining = next_start - t
        weight = 0.0 if remaining >= blend_s else 1.0 - remaining / blend_s
        frames.append((current, next_shape, max(0.0, min(1.0, weight))))
    return frames
