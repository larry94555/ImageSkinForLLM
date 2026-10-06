"""The sample video (features.md item 6): the person in the photo speaks a fixed test script."""

import logging
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from imageskin.video import VideoEngine
from imageskin.voice import VoiceEngine, write_speech

logger = logging.getLogger(__name__)

SAMPLE_SCRIPT = (
    "This is a test. How do I sound? I'm speaking in my own voice, or as close to it as a "
    "computer can get. Let me try a few things. Numbers: one, two, three, forty-five, and nine "
    "hundred ninety-nine. A question: did you see that coming? And a little excitement: wow, "
    "that's great news! She sells seashells by the seashore. If anything looks or sounds wrong, "
    "tell me now so we can fix it."
)


@dataclass(frozen=True)
class SampleResult:
    seconds: float  # length of the video
    speak_ms: float  # time taken by each step
    prepare_ms: float
    render_ms: float


def _ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def make_sample(
    photo: Path,
    output: Path,
    voice_engine: VoiceEngine,
    video_engine: VideoEngine[Any],
    voice: str,
    script: str = SAMPLE_SCRIPT,
) -> SampleResult:
    """Prepare the photo, speak the script and render the MP4, timing each step."""
    with tempfile.TemporaryDirectory() as tmp:
        # The photo goes first, so a photo with no face fails before the slower speech step.
        start = time.perf_counter()
        face = video_engine.prepare(photo)
        prepare_ms = _ms_since(start)

        wav = Path(tmp) / "speech.wav"
        start = time.perf_counter()
        write_speech(voice_engine.speak(voice, script), wav, wav.with_suffix(".json"))
        speak_ms = _ms_since(start)

        start = time.perf_counter()
        seconds = video_engine.render(face, wav, output)
        render_ms = _ms_since(start)
    result = SampleResult(seconds, speak_ms, prepare_ms, render_ms)
    logger.info(
        "Wrote sample video",
        extra={
            "output": str(output),
            "video_s": round(seconds, 2),
            "speak_ms": speak_ms,
            "prepare_ms": prepare_ms,
            "render_ms": render_ms,
            "total_ms": round(speak_ms + prepare_ms + render_ms, 1),
        },
    )
    return result
