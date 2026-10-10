"""Spoken video replies (roadmap R17, features.md items 11 and 20): each LLM reply is cleaned for
speech, spoken in the person's voice and rendered on their photo, with the same voice and video
engines as the sample video. Only the latest reply's video is kept, in <data folder>/replies.

A streamed reply is rendered sentence by sentence while the LLM is still writing (roadmap R21,
item 12), and the browser plays each sentence's clip as soon as it is ready (roadmap R22).
"""

import logging
import os
import queue
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
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


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


@dataclass(frozen=True)
class ClipTime:
    """When a sentence arrived from the LLM and when its clip was ready, as time.perf_counter()
    seconds, for the chat page's timing readout (roadmap R22a)."""

    sentence_at: float
    ready_at: float


class SentenceClips:
    """One reply's clips, rendered a sentence at a time on a background thread, in order, while
    the LLM writes the next ones. Give it to Conversation.send as `on_sentence`."""

    def __init__(self, videos: "ReplyVideos", photo: Path, reply_id: str) -> None:
        self._videos = videos
        self._photo = photo
        self.folder = videos.folder / f"clips-{reply_id}"
        self.clips: list[Path] = []
        self.times: list[ClipTime] = []  # one per clip
        self.sentences = 0  # given so far
        self._queue: queue.Queue[tuple[str, float] | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._first_words: float | None = None
        self._error: Exception | None = None
        self._cancelled = False
        self._closed = False
        self.done = False  # every clip is rendered, or rendering stopped
        self._changed = threading.Condition()  # a clip was added, a clip failed or it is done

    def __call__(self, sentence: str | None) -> None:
        if sentence is None:  # the LLM has started writing
            self._first_words = time.perf_counter()
            return
        self.sentences += 1
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="sentence-clips", daemon=True)
            self._thread.start()
        self._queue.put((sentence, time.perf_counter()))

    def close(self) -> None:
        """The reply is complete: the clips' thread ends after the last sentence, so it never
        holds the engines while waiting for sentences that won't come."""
        if not self._closed:
            self._closed = True
            self._queue.put(None)
            if self._thread is None:
                self._finish()

    def _finish(self) -> None:
        with self._changed:
            self.done = True
            self._changed.notify_all()

    def wait_for_change(self, known: int, timeout: float) -> None:
        """Wait, at most `timeout` seconds, until there are more than `known` clips, a clip
        has failed or the reply is done, so the browser needn't ask again and again."""
        with self._changed:
            self._changed.wait_for(
                lambda: len(self.clips) > known or self.done or self._error is not None, timeout
            )

    @property
    def error(self) -> str | None:
        """Why a clip failed, if one did."""
        return None if self._error is None else str(self._error)

    def wait(self, timeout: float | None = None) -> None:
        """For tests: wait for the clips' thread to end (after close())."""
        if self._thread is not None:
            self._thread.join(timeout)

    def cancel(self) -> None:
        """The reply failed: stop after the clip being rendered and remove the clips."""
        self._cancelled = True
        self.close()
        if self._thread is not None:
            self._thread.join()
        self._videos.remove_clips(self.folder)

    def _run(self) -> None:
        with self._videos._lock:
            n = 0
            while (item := self._queue.get()) is not None:
                sentence, sentence_at = item
                n += 1
                if self._error is not None or self._cancelled:
                    continue  # let the rest go by
                start = time.perf_counter()
                try:
                    rendered = self._render(sentence, sentence_at)
                except Exception as e:
                    with self._changed:
                        self._error = e
                        self._changed.notify_all()
                    logger.error("Sentence clip failed", extra={"sentence": n, "error": str(e)})
                    continue
                if rendered:
                    logger.info(
                        "Sentence clip ready",
                        extra={
                            "sentence": n,
                            "render_ms": ms_since(start),
                            # The chat page's measure (roadmap R22a): from the sentence
                            # arriving from the LLM to its clip.
                            "since_sentence_ms": ms_since(sentence_at),
                            # The roadmap's measure: from the LLM's first words to this clip.
                            "since_first_words_ms": (
                                None if self._first_words is None else ms_since(self._first_words)
                            ),
                        },
                    )
        self._finish()

    def _render(self, sentence: str, sentence_at: float) -> bool:
        """Render the sentence's clip; False when there is nothing in it to say aloud."""
        text = spoken_text(sentence)
        if not text:
            return False
        self._videos._before_engines()
        self._videos._voice.ensure()
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{len(self.clips) + 1}.mp4"
        try:
            self._videos._render_clip(self._photo, text, path)
        except Exception:
            path.unlink(missing_ok=True)  # a clip cut short is never left behind
            raise
        with self._changed:
            self.times.append(ClipTime(sentence_at, time.perf_counter()))
            self.clips.append(path)
            self._changed.notify_all()
        return True


class ReplyVideos:
    """Renders one reply at a time, as the voice and video engines are not shared safely."""

    def __init__(
        self,
        home: Path,
        render_clip: RenderClip,
        voice: VoiceReady,
        # Called on the thread about to use the engines, before each clip: PyTorch's thread
        # count is per thread (roadmap R22a, imageskin.cores).
        before_engines: Callable[[], None] | None = None,
    ) -> None:
        self.folder = home / "replies"
        self._before_engines = before_engines or (lambda: None)
        # Left by a reply cut short when the server last stopped.
        for old in self.folder.glob("clips-*"):
            self.remove_clips(old)
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
                self._before_engines()
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

    def sentence_clips(self, photo: Path, reply_id: str) -> SentenceClips:
        """Render a streamed reply sentence by sentence into <folder>/clips-<reply_id>."""
        clips = SentenceClips(self, photo, reply_id)
        # Clips of an earlier reply that could not be removed are removed with this one.
        for old in self.folder.glob("clips-*"):
            if old != clips.folder:
                self.remove_clips(old)
        return clips

    def remove_clips(self, folder: Path) -> None:
        """Remove a reply's clips and their folder. A clip that can't be removed (as on Windows
        while the browser still has it open) is logged and left for the next reply to remove,
        like an old reply video."""
        left = 0
        for clip in folder.glob("*"):
            try:
                clip.unlink()
            except OSError as e:
                left += 1
                logger.warning(
                    "Could not remove a reply's clip",
                    extra={"clip": f"{folder.name}/{clip.name}", "error": str(e)},
                )
        if not left:
            try:
                folder.rmdir()
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.warning(
                    "Could not remove a reply's clips",
                    extra={"clips": folder.name, "error": str(e)},
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
            self._before_engines()
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
