"""Video engine interface: prepare a photo once, then render it speaking a WAV file."""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
import wave
from array import array
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

FPS = 25
SMOOTH_S = 0.05  # spread of the mouth smoothing, in seconds (a Gaussian sigma)
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


FaceT = TypeVar("FaceT")


class VideoEngine(Protocol[FaceT]):
    """`prepare` does the per-photo work once; `render` makes each video from its result."""

    def prepare(self, photo: Path) -> FaceT:
        """Find the face in the photo."""
        ...

    def render(self, face: FaceT, wav: Path, output: Path) -> float:
        """Write an MP4 of the face speaking the WAV; return its length in seconds.

        The timings JSON from `write_speech` sits next to the WAV, with the same name.
        """
        ...


def find_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise VideoError(
            "ffmpeg not found; install it (Windows: winget install Gyan.FFmpeg), "
            "open a new terminal and check with: ffmpeg -version"
        )
    return ffmpeg


PROGRESSIVE_FRAGMENT_US = 500_000  # a progressive MP4's fragments, in microseconds


def write_mp4(
    frames: Iterable[bytes],
    size: tuple[int, int],
    wav: Path | None,
    output: Path,
    timeout_s: float,
    pix_fmt: str = "bgr24",
    progressive: bool = False,
) -> None:
    """Pipe raw frames (width x height, `pix_fmt`) to ffmpeg, which adds the WAV as AAC
    (when given) and writes an H.264 MP4 at FPS frames per second. A `progressive` MP4 is
    fragmented and written as the frames come, half a second at a time, so a browser can play
    it while it is still being written (roadmap R22d); the others are written whole, with the
    index first."""
    width, height = size
    cmd = [find_ffmpeg(), "-nostdin", "-y", "-v", "error"]
    cmd += ["-f", "rawvideo", "-pix_fmt", pix_fmt, "-s", f"{width}x{height}"]
    cmd += ["-r", str(FPS), "-i", "-"]
    if wav is not None:
        cmd += ["-i", str(wav), "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    if progressive:
        # No look-ahead in the encoder, so each fragment is out as soon as its frames are in.
        cmd += ["-tune", "zerolatency", "-movflags", "frag_keyframe+empty_moov+default_base_moof"]
        cmd += ["-frag_duration", str(PROGRESSIVE_FRAGMENT_US), "-flush_packets", "1", str(output)]
    else:
        cmd += ["-movflags", "+faststart", str(output)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for frame in frames:
            proc.stdin.write(frame)
        _, err = proc.communicate(timeout=timeout_s)
    except BrokenPipeError:
        _, err = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        proc.kill()
        proc.communicate()  # reap the process and close its pipes
        output.unlink(missing_ok=True)  # a partial MP4 must not look like a result
        raise VideoError(f"ffmpeg took longer than {timeout_s:g} seconds") from e
    if proc.returncode != 0:
        output.unlink(missing_ok=True)
        detail = err.decode(errors="replace").strip().splitlines()[-1:] or ["no error output"]
        raise VideoError(f"ffmpeg could not write {output.name} ({detail[0]})")


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
    (pauses, breaths) close the mouth. The result is smoothed over about a fifth of a second, so
    the mouth eases open and shut over several frames instead of jumping between two positions.
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
    return [round(v, 3) for v in smooth(raw, SMOOTH_S * fps)]


def smooth(values: list[float], sigma: float) -> list[float]:
    """Gaussian smoothing with `sigma` in frames; the ends are padded with the end values."""
    radius = max(1, math.ceil(3 * sigma))
    kernel = [math.exp(-0.5 * (k / sigma) ** 2) for k in range(-radius, radius + 1)]
    total = sum(kernel)
    n = len(values)
    return [
        sum(w * values[min(n - 1, max(0, i + k - radius))] for k, w in enumerate(kernel)) / total
        for i in range(n)
    ]
