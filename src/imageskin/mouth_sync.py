"""The mouth in step with the voice (roadmap R128).

R127 (experiments/mouth_sync/) found the mouth opening 60 to 160 ms before the voice after a
pause: the frames opened it early (fixed in `visemes.frame_weights`), and the sound timings
don't start where the voice is heard. Kokoro's start a median 55 ms after it (its first sound
is often a quiet breath or "h"), the forced aligner's for the cloned voice up to 71 ms before
it. So the first sound after each pause is moved to where the audio's voice starts, for every
voice, and each clip's lead is measured the way R127 measured it, for the log.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from imageskin.expression import openness
from imageskin.visemes import ShapeTiming, frame_weights, openings

Samples = NDArray[np.floating]

WINDOW_S = 0.005  # loudness is measured in windows this long
HEARD_DB = -35.0  # quieter than this below the clip's loud level is silence (as R127)
SILENT_DB = -70.0  # a clip whose loud level is below this has no voice (as expression.loudness)
LOOK_BACK_S = 0.2  # how far before its timing a sound may start (Kokoro: up to 190 ms late)
LOOK_AHEAD_S = 0.15  # and after it (the aligner: up to 71 ms early)
PAUSE_S = 0.15  # silence at least this long before a word means the mouth may close in it
OPEN_AT = 0.1  # openness at which the mouth counts as open (a tenth of the widest shape)


def heard(samples: Samples, rate: int) -> NDArray[np.bool_]:
    """Whether the voice is heard in each WINDOW_S window: no more than HEARD_DB below the
    clip's loud level (its 98th percentile, so a few peaks don't set it); nowhere in a silent
    clip."""
    n = max(1, int(rate * WINDOW_S))
    windows = len(samples) // n
    if windows == 0:
        return np.zeros(0, dtype=bool)
    x = np.asarray(samples[: windows * n], dtype=np.float64).reshape(windows, n)
    db = 10 * np.log10(np.mean(x**2, axis=1) + 1e-12)
    top = float(np.percentile(db, 98))
    if top < SILENT_DB:
        return np.zeros(windows, dtype=bool)
    return np.asarray(db - top > HEARD_DB)


def voice_start(loud: NDArray[np.bool_], at: float, earliest: float) -> float | None:
    """Where the voice that the timings start at `at` is first heard: back to the silence
    before it if it is already heard there, or on to where it is heard if not. None when
    there is no silence to find within LOOK_BACK_S (or `earliest`) or no voice within
    LOOK_AHEAD_S, so the timing is kept."""
    w = min(len(loud), round(at / WINDOW_S))
    if w < len(loud) and loud[w]:
        low = max(0, round(max(earliest, at - LOOK_BACK_S) / WINDOW_S))
        while w > low and loud[w - 1]:
            w -= 1
        return None if w == low and w > 0 and loud[w - 1] else w * WINDOW_S
    high = min(len(loud), w + round(LOOK_AHEAD_S / WINDOW_S))
    while w < high and not loud[w]:
        w += 1
    return w * WINDOW_S if w < high else None


def start_at_voice(shapes: list[ShapeTiming], samples: Samples, rate: int) -> list[ShapeTiming]:
    """The shapes with each one the mouth opens from rest for (`visemes.openings`) starting
    where its voice is first heard, and the rest before it ending there."""
    loud = heard(samples, rate)
    out = list(shapes)
    for i in openings(shapes):
        s = out[i]
        before = out[i - 1] if i > 0 else None
        earliest = 0.0
        for p in reversed(out[:i]):
            if p.shape != "rest":
                earliest = p.end
                break
        start = voice_start(loud, s.start, earliest)
        if start is None or start >= s.end or start == s.start:
            continue
        start = round(start, 3)
        out[i] = ShapeTiming(s.shape, start, s.end)
        if before is not None and before.shape == "rest" and before.end == s.start:
            out[i - 1] = ShapeTiming("rest", before.start, max(before.start, start))
    return out


def mouth_weights(
    shapes: list[ShapeTiming], samples: Samples, rate: int, n_frames: int, fps: float
) -> list[dict[str, float]]:
    """Each frame's mouth shapes, opening no earlier than the voice is heard. The sounds the
    mouth opens for are found before they move, as moving one can shorten the pause before it."""
    moved = start_at_voice(shapes, samples, rate)
    opens = [moved[i].start for i in openings(shapes)]
    return frame_weights(moved, n_frames, fps, opens=opens)


def voice_onsets(samples: Samples, rate: int) -> list[tuple[float, float]]:
    """Each time the voice starts after a silence of at least PAUSE_S, or at the clip's start:
    (when the silence before it began, when the voice is heard)."""
    out: list[tuple[float, float]] = []
    quiet_from = 0.0
    was = False
    for i, h in enumerate(heard(samples, rate)):
        t = i * WINDOW_S
        if h and not was and (not out or t - quiet_from >= PAUSE_S):
            out.append((quiet_from, t))
        if not h and was:
            quiet_from = t
        was = bool(h)
    return out


def mouth_opens(track: Sequence[float], fps: float, quiet_from: float, at: float) -> float | None:
    """When the mouth opens for a voice heard at `at` after silence from `quiet_from`: the
    start of the first frame at or over OPEN_AT after one under it. None if it doesn't close."""
    first = max(0, math.floor(quiet_from * fps))
    last = min(len(track), math.ceil((at + 0.5) * fps))
    closed = False
    for f in range(first, last):
        if track[f] < OPEN_AT:
            closed = True
        elif closed:
            return f / fps
    return None


def mouth_lead_ms(
    weights: Sequence[dict[str, float]], samples: Samples, rate: int, fps: float
) -> float | None:
    """The most the mouth opens before the voice in a clip, at its start and after each pause,
    in ms (negative: it opens after); None when the mouth never opens from closed."""
    track = [openness(w) for w in weights]
    leads = [
        at - opens
        for quiet_from, at in voice_onsets(samples, rate)
        if (opens := mouth_opens(track, fps, quiet_from, at)) is not None
    ]
    return round(max(leads) * 1000) if leads else None
