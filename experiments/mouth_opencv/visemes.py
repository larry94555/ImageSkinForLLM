"""Mouth shapes (visemes) over time, from Kokoro's phonemes and how long each one lasts.

Each phoneme maps to a mouth shape: how open the mouth is (0 closed, 1 fully open) and how wide
(1 normal, below 1 rounded as in "oo"). The timeline is sampled once per video frame. A lip
closure (m, b, p) is kept even when it is shorter than a frame, because a mouth that never closes
on those sounds is the most visible lip-sync error.
"""

from dataclasses import dataclass

# name: (open, width)
SHAPES: dict[str, tuple[float, float]] = {
    "rest": (0.0, 1.0),
    "closed": (0.0, 0.97),
    "fv": (0.1, 1.0),
    "small": (0.3, 1.0),
    "sh": (0.3, 0.85),
    "round": (0.45, 0.78),
    "mid": (0.6, 1.0),
    "wide": (0.9, 1.04),
}

_GROUPS = {
    "closed": "mbp",
    "fv": "fv",
    "sh": "ʃʒʧʤ",
    "round": "oʊuwɔOɒ",
    "wide": "aɑæʌIWɐ",
    "mid": "ɛeɪiəɜɝɚᵻAYE",
    "small": "tdnlszkgɡhθðɹrjŋɾʔxç",
}
VISEME_OF = {ch: name for name, chars in _GROUPS.items() for ch in chars}
PAUSES = set(",.!?;:—…")
MODIFIERS = set("ˈˌːʰ̃")  # stress and length marks: they belong to the sound next to them


@dataclass(frozen=True)
class Segment:
    shape: str
    start: float  # seconds
    end: float


def segments(phonemes: str, durations: list[float], offset: float = 0.0) -> list[Segment]:
    """Turn phonemes and their durations (seconds, one per character) into shape segments.

    Modifier marks extend the shape before them; spaces between words keep a small opening;
    punctuation is a pause with the mouth at rest.
    """
    out: list[Segment] = []
    t = offset
    for ch, d in zip(phonemes, durations, strict=True):
        if ch in MODIFIERS and out:
            last = out[-1]
            out[-1] = Segment(last.shape, last.start, t + d)
        elif ch in PAUSES:
            out.append(Segment("rest", t, t + d))
        elif ch == " ":
            out.append(Segment("small", t, t + d))
        else:
            out.append(Segment(VISEME_OF.get(ch, "small"), t, t + d))
        t += d
    return out


def frame_shapes(segs: list[Segment], frames: int, fps: int) -> list[tuple[float, float]]:
    """The (open, width) target for each frame, smoothed so the mouth moves between shapes."""
    targets: list[tuple[float, float]] = []
    closed: list[bool] = []
    i = 0
    for f in range(frames):
        a, b = f / fps, (f + 1) / fps
        while i < len(segs) and segs[i].end <= a:
            i += 1
        best, best_overlap, has_closure = "rest", 0.0, False
        j = i
        while j < len(segs) and segs[j].start < b:
            overlap = min(b, segs[j].end) - max(a, segs[j].start)
            if segs[j].shape == "closed" and overlap > 0:
                has_closure = True
            if overlap > best_overlap:
                best, best_overlap = segs[j].shape, overlap
            j += 1
        targets.append(SHAPES["closed" if has_closure else best])
        closed.append(has_closure)
    out: list[tuple[float, float]] = []
    prev = (0.0, 1.0)
    for (o, w), shut in zip(targets, closed, strict=True):
        # Closures snap shut; other shapes ease in, as real lips cannot jump between shapes.
        cur = (o, w) if shut else (0.6 * o + 0.4 * prev[0], 0.6 * w + 0.4 * prev[1])
        out.append((round(cur[0], 3), round(cur[1], 3)))
        prev = cur
    return out
