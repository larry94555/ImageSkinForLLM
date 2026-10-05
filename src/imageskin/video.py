"""Video engine interface: prepare a photo once, then render it speaking a WAV file."""

from __future__ import annotations

import math
import sys
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

FPS = 25
INSTALL_HINT = 'OpenCV is not installed; run: pip install -e ".[video]"'


class VideoError(Exception):
    """A photo could not be prepared or a video could not be rendered."""


@dataclass(frozen=True)
class Face:
    """Where the mouth is in a photo, found once by `prepare` and reused for every render."""

    photo: Path
    width: int  # size the photo is rendered at, in pixels (even, for H.264)
    height: int
    mouth_x: int  # middle of the line where the lips meet
    mouth_y: int
    mouth_w: int  # mouth width
    jaw_h: int  # distance from the lips to the chin


class VideoEngine(Protocol):
    def prepare(self, photo: Path) -> Face:
        """Find the face in the photo."""
        ...

    def render(self, face: Face, wav: Path, output: Path) -> float:
        """Write an MP4 of the face speaking the WAV; return its length in seconds."""
        ...


def read_pcm16(wav: Path) -> tuple[array[int], int]:
    """Read a mono 16-bit WAV; return its samples and sample rate."""
    try:
        with wave.open(str(wav), "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise VideoError(f"{wav.name}: expected mono 16-bit WAV")
            rate = w.getframerate()
            data = w.readframes(w.getnframes())
    except (OSError, EOFError, wave.Error) as e:
        raise VideoError(f"could not read {wav}: {e}") from e
    samples = array("h", data)
    if sys.byteorder == "big":
        samples.byteswap()
    return samples, rate


def mouth_openness(samples: array[int], sample_rate: int, fps: int = FPS) -> list[float]:
    """How open the mouth is in each video frame, from 0 (closed) to 1, from the audio's loudness.

    Loudness is measured per frame and scaled so the loud parts of speech reach 1; quiet frames
    (pauses, breaths) close the mouth. A light smoothing keeps the mouth from flickering.
    """
    per_frame = sample_rate / fps
    frames = math.ceil(len(samples) / per_frame)
    rms = []
    for i in range(frames):
        chunk = samples[round(i * per_frame) : round((i + 1) * per_frame)]
        rms.append(math.sqrt(sum(s * s for s in chunk) / len(chunk)) if chunk else 0.0)
    if not rms:
        return []
    loud = sorted(rms)[int(0.95 * (len(rms) - 1))]  # ignore the few loudest peaks
    if loud < 100:  # silence (16-bit samples peak at 32767)
        return [0.0] * frames
    gate = 0.1
    raw = [min(1.0, max(0.0, (r / loud - gate) / (1 - gate))) for r in rms]
    padded = [raw[0], *raw, raw[-1]]
    return [
        round(0.25 * padded[i] + 0.5 * padded[i + 1] + 0.25 * padded[i + 2], 3)
        for i in range(frames)
    ]
