"""Audio conversion with ffmpeg, and joining recordings into one voice sample."""

import logging
import shutil
import subprocess
import tempfile
import time
import wave
from collections.abc import Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = (".m4a", ".mp3", ".wav")
# Every converted file has the same format, so the WAVs can be joined frame by frame.
SAMPLE_RATE = 24000
CHANNELS = 1
DEFAULT_TIMEOUT_S = 60.0


class AudioError(Exception):
    """A recording could not be read, converted or joined."""


def to_wav(src: Path, dst: Path, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
    """Convert an M4A, MP3 or WAV file to 24 kHz mono 16-bit WAV."""
    if src.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise AudioError(f"{src.name}: unsupported file type, use one of {SUPPORTED_SUFFIXES}")
    if not src.is_file():
        raise AudioError(f"{src}: file not found")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AudioError("ffmpeg not found; install it and make sure it is on PATH")

    cmd = [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(src)]
    cmd += ["-vn", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(dst)]
    start = time.perf_counter()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        raise AudioError(f"{src.name}: conversion took longer than {timeout_s:g} seconds") from e
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1:] or ["no error output"]
        raise AudioError(f"{src.name}: ffmpeg could not convert it ({detail[0]})")
    logger.info(
        "Converted to WAV",
        extra={"src": str(src), "duration_ms": round((time.perf_counter() - start) * 1000, 1)},
    )


def join_wavs(parts: Sequence[Path], output: Path) -> float:
    """Join WAV files of the same format into one; return its length in seconds."""
    if not parts:
        raise AudioError("no recordings to join")
    with wave.open(str(parts[0]), "rb") as first:
        params = first.getparams()
    frames = 0
    with wave.open(str(output), "wb") as out:
        out.setparams(params)
        for part in parts:
            with wave.open(str(part), "rb") as w:
                if w.getparams()[:3] != params[:3]:
                    raise AudioError(f"{part.name}: format differs from {parts[0].name}")
                data = w.readframes(w.getnframes())
                frames += w.getnframes()
            out.writeframes(data)
    return frames / params.framerate


def make_voice_sample(
    recordings: Sequence[Path], output: Path, timeout_s: float = DEFAULT_TIMEOUT_S
) -> float:
    """Convert each recording to WAV and join them, in order; return the length in seconds."""
    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        parts = [Path(tmp) / f"{i}.wav" for i in range(len(recordings))]
        for src, part in zip(recordings, parts, strict=True):
            to_wav(src, part, timeout_s)
        try:
            seconds = join_wavs(parts, output)
        except (OSError, wave.Error) as e:
            raise AudioError(f"could not write {output}: {e}") from e
    logger.info(
        "Wrote voice sample",
        extra={
            "output": str(output),
            "recordings": len(recordings),
            "seconds": round(seconds, 2),
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return seconds
