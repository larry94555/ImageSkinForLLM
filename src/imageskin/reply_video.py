"""Spoken video replies (roadmap R17, features.md items 11 and 20): each LLM reply is cleaned for
speech, spoken in the person's voice and rendered on their photo, with the same voice and video
engines as the sample video. Only the latest reply's video is kept, in <data folder>/replies.
"""

import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from imageskin.prepare_job import PrepareVoice, RenderClip
from imageskin.speech_text import spoken_text

logger = logging.getLogger(__name__)


class VoiceReady:
    """The voice step, done at most once per voice. Prepare does it as its first step; after the
    server restarts, the first reply does it, so the reply is spoken with the accent chosen in
    setup rather than the engine's default."""

    def __init__(self, prepare: PrepareVoice, voice_id: Callable[[], str | None]) -> None:
        self._prepare = prepare
        self._voice_id = voice_id
        # The voice prepared in this run of the server, in a tuple so that a voice with no id
        # (None) still counts as prepared.
        self._ready: tuple[str | None] | None = None

    def __call__(self) -> None:
        """Prepare the voice (the prepare job's voice step)."""
        voice = self._voice_id()
        self._prepare()
        self._ready = (voice,)

    def ensure(self) -> None:
        """Prepare the voice unless it is ready already."""
        if self._ready != (self._voice_id(),):
            start = time.perf_counter()
            self()
            logger.info(
                "Voice made ready for replies",
                extra={"duration_ms": round((time.perf_counter() - start) * 1000, 1)},
            )


class ReplyVideos:
    """Renders one reply at a time, as the voice and video engines are not shared safely."""

    def __init__(self, home: Path, render_clip: RenderClip, voice: VoiceReady) -> None:
        self.folder = home / "replies"
        self._render_clip = render_clip
        self._voice = voice
        self._lock = threading.Lock()

    def warm_up(self, photo: Path) -> None:
        """Load the voice and video models and make the voice ready, by rendering a word that is
        thrown away, so the first reply is as quick as the next ones. Run in the background when
        the server starts; a reply sent meanwhile waits for it. Failures are logged only: the
        reply that follows says what went wrong."""
        with self._lock:
            start = time.perf_counter()
            try:
                self._voice.ensure()
                with tempfile.TemporaryDirectory() as tmp:
                    self._render_clip(photo, "Hello.", Path(tmp) / "warm-up.mp4")
            except Exception as e:
                logger.error("Could not warm up replies", extra={"error": str(e)})
                return
            logger.info(
                "Replies warmed up",
                extra={"duration_ms": round((time.perf_counter() - start) * 1000, 1)},
            )

    def path(self, turn: int) -> Path:
        return self.folder / f"{turn}.mp4"

    def render(self, photo: Path, turn: int, reply: str) -> Path | None:
        """Speak the reply (turn is its place in the conversation) and render it on the photo.
        None when nothing in it is spoken, such as a reply of only emoji. The voice and video
        engines' errors are passed on."""
        text = spoken_text(reply)
        if not text:
            logger.info("Reply has nothing to speak", extra={"turn": turn})
            return None
        with self._lock:
            start = time.perf_counter()
            self._voice.ensure()
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self.path(turn)
            # Written aside then moved, so a video cut short is never played.
            rendering = path.with_name(f"{turn}.rendering.mp4")
            try:
                self._render_clip(photo, text, rendering)
                os.replace(rendering, path)
            except Exception as e:
                rendering.unlink(missing_ok=True)
                logger.error(
                    "Reply video failed",
                    extra={
                        "turn": turn,
                        "error": str(e),
                        "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    },
                )
                raise
            self._remove_old(keep=path)
            logger.info(
                "Rendered reply video",
                extra={
                    "turn": turn,
                    "reply_chars": len(reply),
                    "spoken_chars": len(text),
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
            return path

    def _remove_old(self, keep: Path) -> None:
        """Only the latest reply is played. Older videos are removed once the new one is in
        place; one the browser still has open may not be removable (on Windows), so it is left
        for the next reply to remove."""
        for old in self.folder.glob("*.mp4"):
            if old == keep:
                continue
            try:
                old.unlink()
            except OSError as e:
                logger.warning(
                    "Could not remove an old reply video",
                    extra={"video": old.name, "error": str(e)},
                )
