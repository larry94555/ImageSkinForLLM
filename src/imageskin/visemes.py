"""Sounds to mouth shapes (visemes), and mouth shapes to per-frame weights for the video.

Pure Python, so it runs anywhere without the model stack. Moved from experiments/lipread/,
where the shapes were tuned until Larry could follow the test sentences with the sound off.

Sounds are Kokoro's phonemes: IPA letters plus a few capitals for diphthongs (A in "say",
I in "my", W in "now", O in "go", Y in "boy").
"""

import math
from dataclasses import dataclass

# Mouth shapes; "rest" is the mouth as in the photo.
SHAPES = ("rest", "MBP", "FV", "AA", "EH", "EE", "IH", "OH", "OO", "SH")

_GROUPS = {
    "MBP": "mbp",  # lips pressed
    "FV": "fv",  # upper teeth on lower lip
    "OO": "uwʊ",  # you, would, boat's w
    "OH": "oɔɒOYQ",  # go, more, boy
    "AA": "aɑʌɐIW",  # father, cup, my, now
    "EH": "ɛeæA",  # bed, cat, say
    "EE": "iɪj",  # see, it
    "SH": "ʃʒʧʤ",  # she, chair, judge
    # Small opening. r stays here: rounding it made "three green trees" pulse the mouth
    # corners between r and ee (Larry, 2026-10-06).
    "IH": "tdnlszkgɡhθðŋɾʔxçəᵊᵻɹrɜɝɚ",
}
SHAPE_OF: dict[str, str] = {ch: name for name, chars in _GROUPS.items() for ch in chars}
PAUSES = set(",.!?;:—…")
HOLDS = set(" ˈˌːʰ̃")  # spaces, stress and length marks keep the sound before them
CONTACT = ("MBP", "FV")  # sounds a lip-reader needs to see the lips touch


@dataclass(frozen=True)
class SoundTiming:
    sound: str  # one phoneme, or punctuation for a pause
    start: float  # seconds from the start of the audio
    end: float

    @property
    def shape(self) -> str:
        if self.sound in PAUSES:
            return "rest"
        return SHAPE_OF.get(self.sound, "IH")


@dataclass(frozen=True)
class ShapeTiming:
    shape: str
    start: float
    end: float


def sound_timings(phonemes: str, seconds: list[float], offset: float = 0.0) -> list[SoundTiming]:
    """One timing per sound, from phonemes and how long each character lasts.

    Spaces, stress and length marks have a duration too; it is added to the sound before them.
    """
    if len(phonemes) != len(seconds):
        raise ValueError(f"{len(phonemes)} phonemes but {len(seconds)} durations")
    out: list[SoundTiming] = []
    t = offset
    for ch, d in zip(phonemes, seconds, strict=True):
        if ch in HOLDS and out:
            out[-1] = SoundTiming(out[-1].sound, out[-1].start, round(t + d, 3))
        elif ch not in HOLDS:
            out.append(SoundTiming(ch, round(t, 3), round(t + d, 3)))
        t += d
    return out


def shape_timings(sounds: list[SoundTiming]) -> list[ShapeTiming]:
    """Mouth shapes over time, joining neighbouring sounds that share a shape."""
    out: list[ShapeTiming] = []
    for s in sounds:
        if out and out[-1].shape == s.shape and out[-1].end == s.start:
            out[-1] = ShapeTiming(s.shape, out[-1].start, s.end)
        else:
            out.append(ShapeTiming(s.shape, s.start, s.end))
    return out


def frame_weights(
    shapes: list[ShapeTiming],
    n_frames: int,
    fps: float,
    smooth_s: float = 0.06,
    lead_s: float = 0.03,
) -> list[dict[str, float]]:
    """How much of each mouth shape to show in each video frame (weights add up to 1).

    Shapes blend into each other over a Gaussian of `smooth_s` seconds, the way real lips
    start the next sound before the current one ends, and the lips move `lead_s` ahead of
    the sound. Lip contact sounds (m, b, p, f, v) are often shorter than a frame and would
    blur away, so the frame nearest the middle of each one shows that shape fully.
    The defaults are the 60 ms blend and 30 ms lead Larry accepted (2026-10-06).
    """
    step = 0.005
    n_steps = int(math.ceil(n_frames / fps / step)) + 1
    grid = {name: [0.0] * n_steps for name in SHAPES}
    k = 0
    for i in range(n_steps):
        t = i * step
        while k < len(shapes) and shapes[k].end <= t:
            k += 1
        shape = shapes[k].shape if k < len(shapes) and shapes[k].start <= t else "rest"
        grid[shape][i] = 1.0

    radius = max(1, int(3 * smooth_s / step))
    kernel = [math.exp(-0.5 * (j * step / smooth_s) ** 2) for j in range(-radius, radius + 1)]
    out: list[dict[str, float]] = []
    for f in range(n_frames):
        centre = round(((f + 0.5) / fps + lead_s) / step)
        weights: dict[str, float] = {}
        for name, row in grid.items():
            acc = sum(
                kv * row[min(n_steps - 1, max(0, centre + j - radius))]
                for j, kv in enumerate(kernel)
            )
            if acc > 1e-6:
                weights[name] = acc
        total = sum(weights.values())
        out.append({name: w / total for name, w in weights.items()})

    for s in shapes:
        if s.shape in CONTACT and n_frames:
            f = min(n_frames - 1, max(0, int(((s.start + s.end) / 2 - lead_s) * fps)))
            out[f] = {s.shape: 1.0}
    return out
