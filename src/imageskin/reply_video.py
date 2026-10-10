"""Spoken video replies (roadmap R17, features.md items 11 and 20): each LLM reply is cleaned for
speech, spoken in the person's voice and rendered on their photo, with the same voice and video
engines as the sample video. Only the latest reply's video is kept, in <data folder>/replies.

A streamed reply is rendered sentence by sentence while the LLM is still writing (roadmap R21,
item 12), and the sentences' clips are then joined into the reply's video.
"""

import logging
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from imageskin.prepare_job import PrepareVoice, RenderClip
from imageskin.speech_text import spoken_text
from imageskin.video import VideoError, find_ffmpeg

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


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


class SentenceClips:
    """One reply's clips, rendered a sentence at a time on a background thread, in order, while
    the LLM writes the next ones. Give it to Conversation.send as `on_sentence`."""

    def __init__(self, videos: "ReplyVideos", photo: Path) -> None:
        self._videos = videos
        self._photo = photo
        self.folder = videos.folder / f"rendering-{uuid4().hex}"
        self.clips: list[Path] = []
        self.sentences = 0  # given so far
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._first_words: float | None = None
        self._error: Exception | None = None
        self._cancelled = False
        self._closed = False

    def __call__(self, sentence: str | None) -> None:
        if sentence is None:  # the LLM has started writing
            self._first_words = time.perf_counter()
            return
        self.sentences += 1
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="sentence-clips", daemon=True)
            self._thread.start()
        self._queue.put(sentence)

    def close(self) -> None:
        """The reply is complete: the clips' thread ends after the last sentence, so it never
        holds the engines while waiting for sentences that won't come."""
        if not self._closed:
            self._closed = True
            self._queue.put(None)

    def finish(self) -> list[Path]:
        """Wait for the last clip; the clips in order. The first engine error is passed on."""
        self.close()
        if self._thread is not None:
            self._thread.join()
        if self._error is not None:
            raise self._error
        return self.clips

    def cancel(self) -> None:
        """The reply failed: stop after the clip being rendered and remove the clips."""
        self._cancelled = True
        self.close()
        if self._thread is not None:
            self._thread.join()
        shutil.rmtree(self.folder, ignore_errors=True)

    def _run(self) -> None:
        with self._videos._lock:
            n = 0
            while (sentence := self._queue.get()) is not None:
                n += 1
                if self._error is not None or self._cancelled:
                    continue  # let the rest go by
                start = time.perf_counter()
                try:
                    rendered = self._render(sentence)
                except Exception as e:
                    self._error = e
                    logger.error("Sentence clip failed", extra={"sentence": n, "error": str(e)})
                    continue
                if rendered:
                    logger.info(
                        "Sentence clip ready",
                        extra={
                            "sentence": n,
                            "render_ms": ms_since(start),
                            # The roadmap's measure: from the LLM's first words to this clip.
                            "since_first_words_ms": (
                                None if self._first_words is None else ms_since(self._first_words)
                            ),
                        },
                    )

    def _render(self, sentence: str) -> bool:
        """Render the sentence's clip; False when there is nothing in it to say aloud."""
        text = spoken_text(sentence)
        if not text:
            return False
        self._videos._voice.ensure()
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{len(self.clips) + 1}.mp4"
        self._videos._render_clip(self._photo, text, path)
        self.clips.append(path)
        return True


class ReplyVideos:
    """Renders one reply at a time, as the voice and video engines are not shared safely."""

    def __init__(self, home: Path, render_clip: RenderClip, voice: VoiceReady) -> None:
        self.folder = home / "replies"
        # Left by a reply cut short when the server last stopped.
        for old in self.folder.glob("rendering-*"):
            shutil.rmtree(old, ignore_errors=True)
        for old in self.folder.glob("*.rendering.mp4"):
            old.unlink(missing_ok=True)
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

    def sentence_clips(self, photo: Path) -> SentenceClips:
        """Render a streamed reply sentence by sentence; see join()."""
        return SentenceClips(self, photo)

    def join(self, turn: int, clips: SentenceClips) -> Path | None:
        """Wait for the reply's clips and join them into its video. None when nothing in it was
        spoken. The engines' and ffmpeg's errors are passed on."""
        start = time.perf_counter()
        try:
            parts = clips.finish()
            if not parts:
                logger.info("Reply has nothing to speak", extra={"turn": turn})
                return None
            path = self.path(turn)
            rendering = path.with_name(f"{turn}.rendering.mp4")
            try:
                concat(parts, rendering)
                os.replace(rendering, path)
            finally:
                rendering.unlink(missing_ok=True)
            self._remove_old(keep=path)
        except Exception as e:
            logger.error(
                "Reply video failed",
                extra={"turn": turn, "error": str(e), "wait_ms": ms_since(start)},
            )
            raise
        finally:
            shutil.rmtree(clips.folder, ignore_errors=True)
        logger.info(
            "Joined reply video",
            extra={"turn": turn, "clips": len(parts), "wait_ms": ms_since(start)},
        )
        return path

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


def concat(clips: list[Path], output: Path) -> None:
    """Join MP4 clips made by the same engine into one, without encoding the video again."""
    listing = output.with_suffix(".txt")
    # Quoted for the concat list, where a ' in a path (as in /Users/O'Neil) is written '\''.
    quoted = (c.as_posix().replace("'", "'\\''") for c in clips)
    listing.write_text("".join(f"file '{q}'\n" for q in quoted), encoding="utf-8")
    cmd = [find_ffmpeg(), "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0"]
    cmd += ["-i", str(listing), "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart"]
    try:
        done = subprocess.run([*cmd, str(output)], capture_output=True, timeout=60)
    except subprocess.TimeoutExpired as e:
        output.unlink(missing_ok=True)
        raise VideoError("ffmpeg took longer than 60 seconds to join the clips") from e
    finally:
        listing.unlink(missing_ok=True)
    if done.returncode != 0:
        output.unlink(missing_ok=True)
        detail = done.stderr.decode(errors="replace").strip().splitlines()[-1:] or ["no output"]
        raise VideoError(f"ffmpeg could not join the clips ({detail[0]})")
