"""Spoken video replies (roadmap R17, features.md items 11 and 20): each LLM reply is cleaned for
speech, spoken in the person's voice and rendered on their photo, with the same voice and video
engines as the sample video. Only the latest reply's video is kept, in <data folder>/replies.

A streamed reply is rendered sentence by sentence while the LLM is still writing (roadmap R21,
item 12), and the browser plays each sentence's clip as soon as it is ready (roadmap R22). Each
clip is two steps, the voice and then the video (roadmap R22b), one after the other: on a 4-core
CPU, speaking one sentence while the one before it is rendered made both steps about twice as
slow, so nothing was gained.

Sentences that queue while the voice is busy are spoken as one clip, up to JOIN_WORDS (roadmap
R130): R129 measured a large fixed cost per clip on Larry's hosted machine (2 s of speech took
6 to 12 s to make, 9 s took 17 to 20 s), so fewer, longer clips are made faster per word, with
fewer joins. Each clip's silence is cut to the pause its text calls for (imageskin.pauses).
"""

import hashlib
import logging
import os
import queue
import re
import shutil
import tempfile
import threading
import time
import wave
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from imageskin import pace
from imageskin.pauses import fit_pause
from imageskin.prepare_job import ClipSteps, PrepareVoice, RenderClip
from imageskin.speech_text import CODE_FENCE, spoken_text
from imageskin.video import discard

logger = logging.getLogger(__name__)

HOLD_CHECK_S = 0.25  # how often a request waiting on held-back clips looks again

JOIN_WORDS = pace.JOIN_WORDS  # the most words a clip of sentences joined may have
_BLOCK = re.compile(r"[ \t]*(?:\d+[.)]|[-*+]|#{1,6})[ \t]")  # a list item or heading


def joins(batch: list[str], sentence: str, most: int = JOIN_WORDS) -> bool:
    """Whether `sentence` may be spoken in one clip with the sentences in `batch`: plain text
    only, as a code block, list item or heading is spoken on its own, and up to `most` words."""
    plain = all(not CODE_FENCE.search(t) and not _BLOCK.match(t) for t in [*batch, sentence])
    return plain and sum(len(t.split()) for t in [*batch, sentence]) <= most


class VoiceReady:
    """The voice step, done at most once per voice. Prepare does it as its first step; after the
    server restarts, the first reply does it, so the reply is spoken with the accent chosen in
    setup rather than the engine's default."""

    def __init__(
        self,
        prepare: PrepareVoice,
        voice_id: Callable[[], str | None],
        # True while replies speak in a voice that needs no preparing: a default person's
        # (roadmap R24c). Prepare still prepares the person's own voice meanwhile.
        ready_made: Callable[[], bool] = lambda: False,
    ) -> None:
        self._prepare = prepare
        self._voice_id = voice_id
        self._ready_made = ready_made
        # The voice prepared in this run of the server, in a tuple so that a voice with no id
        # (None) still counts as prepared.
        self._ready: tuple[str | None] | None = None

    def __call__(self) -> None:
        """Prepare the voice (the prepare job's voice step)."""
        voice = self._voice_id()
        self._prepare()
        self._ready = (voice,)

    def forget(self) -> None:
        """After Delete my data (roadmap R31), so the next reply prepares the voice again."""
        self._ready = None

    def ensure(self) -> None:
        """Prepare the voice unless it is ready already."""
        if self._ready_made():
            return
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
    """When a sentence arrived from the LLM and when its clip was listed for the browser, as its
    video began to be written (roadmap R22d), as time.perf_counter() seconds, for the chat
    page's timing readout (roadmap R22a). The clip plays once its first fragment is written;
    the page measures that itself, from when the video starts playing."""

    sentence_at: float
    ready_at: float
    started_at: float | None = None  # when its voice step began (roadmap R96)


@dataclass(frozen=True)
class Spoken:
    """A sentence spoken, waiting for its video."""

    n: int  # the sentence's number in the reply
    wav: Path
    sentence_at: float
    started_at: float | None = None  # when it began to be spoken
    seconds: float | None = None  # its speech's length, when it is a WAV (R130)
    words: int = 0


def speech_seconds(wav: Path) -> float | None:
    """The WAV's length, or None when it isn't one (`text_steps` keeps the text in it)."""
    try:
        with wave.open(str(wav), "rb") as w:
            return w.getnframes() / w.getframerate()
    except (OSError, EOFError, wave.Error):
        return None


def text_steps(render_clip: RenderClip) -> ClipSteps:
    """The steps for an engine given as one `render_clip`: the voice step keeps the text and
    the video step does the whole clip."""

    def speak(text: str, wav: Path) -> None:
        wav.write_text(text, encoding="utf-8")

    def render(photo: Path, wav: Path, output: Path) -> None:
        render_clip(photo, wav.read_text(encoding="utf-8"), output)

    return ClipSteps(speak, render)


class SentenceClips:
    """One reply's clips, spoken and rendered a sentence at a time on a background thread, in
    order, while the LLM writes the next ones. Give it to Conversation.send as `on_sentence`."""

    def __init__(self, videos: "ReplyVideos", photo: Path, reply_id: str) -> None:
        self._videos = videos
        self._photo = photo
        self.folder = videos.folder / f"clips-{reply_id}"
        self.clips: list[Path] = []  # listed as soon as each is being written (roadmap R22d)
        self.rendered = 0  # how many of them are whole
        self.times: list[ClipTime] = []  # one per clip
        self.whole_at: list[float] = []  # when each clip was whole, so far (roadmap R96)
        self.sentences = 0  # given so far
        self._handled = 0  # of them, made into clips (or let go by)
        self._queue: queue.Queue[tuple[str, float] | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._first_words: float | None = None
        self._error: Exception | None = None
        self._cancelled = False
        self._closed = False
        self.done = False  # every clip is rendered, or rendering stopped
        self._changed = threading.Condition()  # a clip was added, a clip failed or it is done
        self.join_words = JOIN_WORDS  # sentences queued are joined up to this many words
        # Playback is held back after the first clip is ready until the rest can play through,
        # by how fast this machine makes clips and the LLM writes (R130, R161).
        self.machine = videos.pace.machine()
        self.released_at: float | None = None  # when the clips were first listed to play
        self.gaps_foreseen_s: float | None = None  # at release
        self.words = 0  # the reply's words given so far
        self._words_begun = 0  # of them, in clips begun (or let go by)
        self._making: tuple[float, int] | None = None  # the clip being spoken: began, words
        self._last_sentence_at = 0.0
        self._ready_speech_s = 0.0  # the speech in clips listed so far
        self.plays: list[pace.ClipPlay] = []  # each whole clip's times, for the pace log
        # Given the clips once every one is rendered and none failed or was stopped, before they
        # can be removed (roadmap R130a). Set before close().
        self.on_complete: Callable[[list[Path]], None] | None = None

    def __call__(self, sentence: str | None) -> None:
        if sentence is None:  # the LLM has started writing
            self._first_words = time.perf_counter()
            return
        self.sentences += 1
        self.words += len(sentence.split())
        self._last_sentence_at = time.perf_counter()
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="sentence-clips", daemon=True)
            self._thread.start()
        self._queue.put((sentence, time.perf_counter()))

    def replay(self, kept: list[Path]) -> None:
        """Give the reply clips made before (roadmap R130a): copied in and listed whole at once,
        so the browser plays them as it would ones just rendered."""
        self.folder.mkdir(parents=True, exist_ok=True)
        now = time.perf_counter()
        with self._changed:
            for n, clip in enumerate(kept, 1):
                path = self.folder / f"{n}.mp4"
                shutil.copyfile(clip, path)
                self.clips.append(path)
                self.times.append(ClipTime(now, now, now))
                self.whole_at.append(now)
            self.rendered = self.sentences = self._handled = len(kept)
            self.released_at = now  # all made: nothing to wait for
            self._changed.notify_all()

    def whole(self) -> list[Path] | None:
        """Every clip, once all are rendered and none failed or was stopped, so the reply can be
        said again from them (roadmap R156); None otherwise."""
        with self._changed:
            if not self.done or self._stopped() or not self.clips:
                return None
            if self.rendered < len(self.clips) or not all(c.is_file() for c in self.clips):
                return None
            return list(self.clips)

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
            if self._stopped() or not self.plays:
                return
            self.listed()  # released now, if it was still held
            self._log_pace()
            self._learn()

    def _learn(self) -> None:
        """Keep how fast this machine made the clips and the LLM wrote, for the next reply."""
        clips = [
            (p.whole_at - p.started_at, p.speech_s, p.words)
            for p in self.plays
            if p.started_at is not None and p.speech_s > 0
        ]
        rate = self._llm_words_per_s() or 0.0
        self._videos.pace.add(clips, self.words, rate)

    def _log_pace(self) -> None:
        """Log the pace the reply is heard at, its wait and every gap over pace.GAP_S (R130)."""
        assert self.released_at is not None
        heard = pace.heard(self.plays, self.released_at)
        first = self.times[0].sentence_at
        logger.info(
            "Reply paced",
            extra={
                "clips": len(self.plays),
                "words": heard.words,
                "heard_s": heard.heard_s,
                "words_a_minute": heard.wpm,
                # From the first sentence arriving to the first clip playing, and of it, the
                # time held back so the rest keeps up.
                "wait_ms": round((self.released_at - first) * 1000),
                "held_ms": round((self.released_at - self.times[0].ready_at) * 1000),
                "gaps_foreseen_s": self.gaps_foreseen_s,
                "gaps": [
                    {"clip": g.clip, "seconds": g.seconds, "cause": g.cause} for g in heard.gaps
                ],
            },
        )

    def listed(self) -> int:
        """How many clips the browser may play: none while playback is held back (R130, R161),
        until the rest of the reply can play through, at most pace.MAX_HOLD_S after the first
        clip is ready, or until the reply is done; then every clip listed so far."""
        with self._changed:
            if self.released_at is None and self.clips:
                now = time.perf_counter()
                held_s = now - self.times[0].ready_at
                done = self.done or self._stopped()
                foreseen = None if done else self._gaps_ahead(now)
                through = foreseen is not None and foreseen <= pace.PLAY_THROUGH_GAP_S
                if done or held_s >= pace.MAX_HOLD_S or through:
                    self.released_at = now
                    self.gaps_foreseen_s = None if foreseen is None else round(foreseen, 2)
                    logger.info(
                        "Reply playback released",
                        extra={
                            "held_ms": round(held_s * 1000),
                            "gaps_foreseen_s": self.gaps_foreseen_s,
                            "clips_ready": self.rendered,
                            "words_given": self.words,
                            "reply_done": self._closed,
                            "make_fixed_s": round(self.machine.fixed_s, 2),
                            "make_per_speech_s": round(self.machine.per_speech_s, 2),
                        },
                    )
            return len(self.clips) if self.released_at is not None else 0

    def _llm_words_per_s(self) -> float | None:
        """How fast the LLM has written this reply, once it has written for a second."""
        if self._first_words is None or not self.times:
            return None
        start = self._first_words
        end = time.perf_counter() if not self._closed else self._last_sentence_at
        return self.words / (end - start) if end - start >= 1.0 else None

    def _gaps_ahead(self, now: float) -> float:
        """The gaps foreseen if playback started now (pace.gaps_ahead)."""
        making = None
        if self._making is not None:
            making = (now - self._making[0], self._making[1])
        begun = self._words_begun + (making[1] if making else 0)
        to_come = (
            0.0 if self._closed else max(self.machine.reply_words - self.words, pace.CLIP_WORDS)
        )
        return pace.gaps_ahead(
            self.machine,
            ahead_s=self._ready_speech_s,
            making=making,
            waiting_words=max(0, self.words - begun),
            words_to_come=to_come,
            llm_words_per_s=self._llm_words_per_s() or self.machine.llm_words_per_s,
        )

    def wait_for_change(self, known: int, timeout: float) -> None:
        """Wait, at most `timeout` seconds, until more than `known` clips may be played, a clip
        has failed or the reply is done, so the browser needn't ask again and again. While
        playback is held back, it looks again every HOLD_CHECK_S, as the hold ends in time."""
        end = time.perf_counter() + timeout
        with self._changed:
            while not (
                self.listed() > known or self.done or self._error is not None or self._cancelled
            ):
                left = end - time.perf_counter()
                if left <= 0:
                    return
                self._changed.wait(
                    left if self.released_at is not None else min(left, HOLD_CHECK_S)
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
        """The reply failed or was stopped: stop after the step being done and remove the
        clips. A request waiting for the next clip is answered at once (roadmap R19)."""
        with self._changed:
            self._cancelled = True
            self._changed.notify_all()
        self.close()
        self.wait()
        self._videos.remove_clips(self.folder)

    def _stopped(self) -> bool:
        return self._error is not None or self._cancelled

    def _fail(self, n: int, step: str, error: Exception) -> None:
        with self._changed:
            self._error = error
            self._changed.notify_all()
        logger.error(
            "Sentence clip failed", extra={"sentence": n, "step": step, "error": str(error)}
        )

    def _run(self) -> None:
        with self._videos._voice_lock, self._videos._video_lock:
            n = 0  # sentences taken so far
            held: list[tuple[str, float] | None] = []  # taken from the queue but not joined
            while (item := held.pop() if held else self._queue.get()) is not None:
                batch = [item]
                while n > 0:  # the first clip is kept short (R22b)
                    try:
                        more = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if more is None or not joins([t for t, _ in batch], more[0], self.join_words):
                        held.append(more)
                        break
                    batch.append(more)
                self._make(n + 1, " ".join(t for t, _ in batch), batch[0][1], len(batch))
                n += len(batch)
                self._handled += len(batch)
            if self.on_complete is not None and not self._stopped() and self.clips:
                try:
                    self.on_complete(list(self.clips))
                except Exception:
                    logger.exception("Could not hand on a reply's clips")
        self._finish()

    def voice_waiting(self) -> bool:
        """Whether every sentence given so far has been made into its clip, so the voice is
        waiting for the next (roadmap R100): the reply's text is then cut at the next clause
        rather than the next full stop. Asked on the LLM's thread, which gives the sentences."""
        return self._handled == self.sentences and not self._stopped()

    def _make(self, n: int, sentence: str, sentence_at: float, joined: int = 1) -> None:
        """Speak and render the clip of `joined` sentences from sentence `n` on."""
        if self._stopped():
            return  # let the rest go by
        start = time.perf_counter()
        with self._changed:
            self._making = (start, len(sentence.split()))
        try:
            spoken = self._speak(n, sentence, sentence_at)
        except Exception as e:
            self._begun()
            self._fail(n, "voice", e)
            return
        if spoken is None or self._stopped():  # nothing to say, or cancelled while spoken
            self._begun()
            if spoken is not None:
                spoken.wav.unlink(missing_ok=True)
                spoken.wav.with_suffix(".json").unlink(missing_ok=True)
            return
        # Still being made until _render lists it, under the same lock, so the hold never sees
        # it gone from the clips being made before it is among those ready (R161).
        try:
            listed_at, mouth_lead = self._render(spoken)
        except Exception as e:
            self._fail(n, "video", e)
            return
        logger.info(
            "Sentence clip ready",
            extra={
                "sentence": n,
                "sentences_joined": joined,
                "render_ms": ms_since(start),
                # How far the mouth opened before the voice, in ms, at most 80 (roadmap R128).
                "mouth_lead_ms": mouth_lead,
                # From the sentence arriving from the LLM to its clip being whole.
                "since_sentence_ms": ms_since(sentence_at),
                # From the sentence to the clip being listed for the browser, as its video
                # starts to be written (R22d); it plays once its first fragment is out, which
                # the chat page's readout measures.
                "listed_since_sentence_ms": round((listed_at - sentence_at) * 1000, 1),
                # The roadmap's measure: from the LLM's first words to this clip.
                "since_first_words_ms": (
                    None if self._first_words is None else ms_since(self._first_words)
                ),
            },
        )

    def _begun(self, speech_s: float = 0.0) -> None:
        """The clip being made is listed, or let go by: its words are no longer waited for."""
        with self._changed:
            if self._making is not None:
                self._words_begun += self._making[1]
                self._making = None
            self._ready_speech_s += speech_s

    def _speak(self, n: int, sentence: str, sentence_at: float) -> Spoken | None:
        """Speak the sentence to a WAV; None when there is nothing in it to say aloud."""
        text = spoken_text(sentence)
        if not text:
            return None
        start = time.perf_counter()
        self._videos._before_engines()
        self._videos._voice.ensure()
        self.folder.mkdir(parents=True, exist_ok=True)
        wav = self.folder / f"{n}.wav"
        self._videos._steps.speak(text, wav)
        try:
            fitted = fit_pause(wav, sentence)
        except Exception as e:  # the clip is still spoken, with the voice's own silence
            fitted = None
            logger.warning("Could not fit a clip's pause", extra={"sentence": n, "error": str(e)})
        logger.info(
            "Sentence spoken",
            extra={
                "sentence": n,
                "chars": len(text),
                "speak_ms": ms_since(start),
                "since_sentence_ms": ms_since(sentence_at),
                # The silence cut from its start and end to fit the pause (R130).
                "cut_start_ms": None if fitted is None else round(fitted[0] * 1000),
                "cut_end_ms": None if fitted is None else round(fitted[1] * 1000),
            },
        )
        return Spoken(n, wav, sentence_at, start, speech_seconds(wav), len(text.split()))

    def _render(self, spoken: Spoken) -> tuple[float, float | None]:
        """Render the spoken sentence's clip, listed as soon as the video step starts so the
        browser can play it while it is written, and remove the speech once it is in. Returns
        when the clip was listed and how far its mouth opened before the voice, if measured."""
        path = self.folder / f"{len(self.clips) + 1}.mp4"
        listed_at = time.perf_counter()
        with self._changed:
            self.times.append(ClipTime(spoken.sentence_at, listed_at, spoken.started_at))
            self.clips.append(path)
            self._begun(spoken.seconds or 0.0)
            self._changed.notify_all()
        try:
            mouth_lead = self._videos._steps.render(self._photo, spoken.wav, path)
        except Exception:
            with self._changed:  # a clip cut short is never played
                self.clips.pop()
                self.times.pop()
            discard(path)  # nor left behind, unless a browser still has it open
            raise
        finally:
            spoken.wav.unlink(missing_ok=True)
            spoken.wav.with_suffix(".json").unlink(missing_ok=True)
        whole_at = time.perf_counter()
        with self._changed:
            self.rendered += 1
            self.whole_at.append(whole_at)
            if spoken.seconds is not None:
                self.plays.append(
                    pace.ClipPlay(
                        spoken.sentence_at,
                        spoken.started_at,
                        listed_at,
                        whole_at,
                        spoken.seconds,
                        spoken.words,
                    )
                )
            self._changed.notify_all()
        return listed_at, mouth_lead

    def clip(self, n: int) -> tuple[Path, bool] | None:
        """Clip `n`'s file and whether it is whole, taken together; None when it isn't listed."""
        with self._changed:
            if not 1 <= n <= len(self.clips):
                return None
            return self.clips[n - 1], self.rendered >= n

    def follow(self, n: int, path: Path, every: float) -> Iterator[bytes]:
        """Clip `n`'s bytes from `path` (as `clip` gave it) as they are written, read every
        `every` seconds, until it is whole, or dropped: then what there was ends the stream,
        even when it was dropped before the stream began."""
        sent = 0
        while True:
            with self._changed:
                whole = self.rendered >= n
                dropped = n > len(self.clips) or self.clips[n - 1] != path
            if dropped:
                return
            try:
                with path.open("rb") as f:
                    f.seek(sent)
                    more = f.read()
            except FileNotFoundError:  # not begun yet, or dropped and removed since: see above
                more = b""
            if more:
                sent += len(more)
                yield more
            if whole:
                return
            time.sleep(every)


class ReplyVideos:
    """Renders one reply at a time, as the voice and video engines are not shared safely."""

    def __init__(
        self,
        home: Path,
        render_clip: RenderClip,
        voice: VoiceReady,
        steps: ClipSteps | None = None,  # the clip's two steps apart, for the sentence clips
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
        self._steps = steps or text_steps(render_clip)
        self._voice = voice
        # Each engine is used by one thread at a time; a reply holds both for its clips.
        self._voice_lock = threading.Lock()
        self._video_lock = threading.Lock()
        # Held while a reply video is published or the videos are cleared.
        self._publish_lock = threading.Lock()
        # Raised by each clear (roadmap R27b), and the turns whose videos were published since:
        # only those are served, even when a cleared one's file couldn't be removed.
        self.generation = 0
        self._published: set[int] = set()
        # How fast this machine makes clips and the LLM writes, kept across restarts, for when
        # to start playing each reply (R161).
        self.pace = pace.PaceStore(self.folder / "pace.json")
        # Each photo's SHA-256, by its path, change time and size, for its idle video's name.
        self._digests: dict[tuple[str, int, int], str] = {}

    def warm_up(self, photo: Path) -> None:
        """Load the voice and video models and make the voice ready, by rendering a word that is
        thrown away, so the first reply is as quick as the next ones. Run in the background when
        the server starts; a reply sent meanwhile waits for it. Failures are logged only: the
        reply that follows says what went wrong."""
        with self._voice_lock, self._video_lock:
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
            self._make_idle(photo)

    @contextmanager
    def engines(self) -> Iterator[None]:
        """Hold the voice and video engines for work other than a reply, such as rendering the
        sample video again (roadmap R27b), with the voice ready for the accent chosen."""
        with self._voice_lock, self._video_lock:
            self._before_engines()
            self._voice.ensure()
            yield

    @contextmanager
    def paused(self) -> Iterator[None]:
        """Hold the engines without readying the voice, so no clip or idle video is written
        meanwhile, as while Delete my data removes the videos (roadmap R31)."""
        with self._voice_lock, self._video_lock:
            yield

    def idle(self, photo: Path) -> Path | None:
        """The idle video for the photo (roadmap R23), once the warm-up has made it."""
        path = self.folder / "idle" / f"{self.idle_name(photo)}.mp4"
        return path if path.is_file() else None

    def idle_name(self, photo: Path) -> str:
        """The photo's name and the start of its SHA-256: a photo replaced under the same name,
        as a default person remade in R24b4, gets an idle video of its new face, even while
        the old one is open in a browser and can't be removed (Codex's review of PR #165)."""
        try:
            stat = photo.stat()
        except OSError:
            return photo.stem
        key = (str(photo), stat.st_mtime_ns, stat.st_size)
        if key not in self._digests:
            self._digests[key] = hashlib.sha256(photo.read_bytes()).hexdigest()[:12]
        return f"{photo.stem}-{self._digests[key]}"

    def _make_idle(self, photo: Path) -> None:
        """Make the photo's idle video, unless it is made already, and remove any other
        photo's. Failures are logged only: the chat then holds each reply's last frame."""
        render_idle = self._steps.idle
        if render_idle is None:
            return
        made = self.idle(photo)
        if made is not None:
            self._remove_other_idles(made)  # one that couldn't be removed before
            return
        start = time.perf_counter()
        folder = self.folder / "idle"
        name = self.idle_name(photo)
        path = folder / f"{name}.mp4"
        rendering = folder / f"{name}.rendering.mp4"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            render_idle(photo, rendering)
            os.replace(rendering, path)
        except Exception as e:
            discard(rendering)
            logger.error("Could not make the idle video", extra={"error": str(e)})
            return
        self._remove_other_idles(path)
        logger.info("Idle video ready", extra={"duration_ms": ms_since(start)})

    def _remove_other_idles(self, path: Path) -> None:
        for old in path.parent.glob("*.mp4"):
            if old != path:
                try:
                    old.unlink()
                except OSError as e:  # open in a browser, as on Windows: removed next time
                    logger.warning(
                        "Could not remove an old idle video",
                        extra={"video": old.name, "error": str(e)},
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

    def video(self, turn: int) -> Path | None:
        """The reply's video, if it was published since the conversation was last cleared."""
        path = self.path(turn)
        with self._publish_lock:
            published = turn in self._published
        return path if published and path.is_file() else None

    def render(
        self,
        photo: Path,
        turn: int,
        reply: str,
        stopped: Callable[[], bool] = lambda: False,
        generation: int | None = None,
    ) -> Path | None:
        """Speak the reply (turn is its place in the conversation) and render it on the photo.
        None when nothing in it is spoken, such as a reply of only emoji, or when `stopped`
        says so before the voice step or between it and the video step (roadmap R19). The
        voice and video engines' errors are passed on. `generation` is the one the reply was
        read in: if the conversation is cleared since, the video is dropped (R27b)."""
        if generation is None:
            generation = self.generation
        text = spoken_text(reply)
        if not text:
            logger.info("Reply has nothing to speak", extra={"turn": turn})
            return None
        with self._voice_lock, self._video_lock:
            start = time.perf_counter()
            if stopped():  # while it waited for the engines
                logger.info("Reply video stopped", extra={"turn": turn, "step": "before voice"})
                return None
            self._before_engines()
            self._voice.ensure()
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self.path(turn)

            def log_stop(step: str) -> None:
                logger.info(
                    "Reply video stopped",
                    extra={"turn": turn, "step": step, "duration_ms": ms_since(start)},
                )

            # Written aside then moved, so a video cut short is never played.
            rendering = path.with_name(f"{turn}.rendering.mp4")
            try:
                # The two steps apart, so a stop between them skips the video step.
                with tempfile.TemporaryDirectory() as tmp:
                    wav = Path(tmp) / "speech.wav"
                    self._steps.speak(text, wav)
                    if stopped():
                        log_stop("after voice")
                        return None
                    self._steps.render(photo, wav, rendering)
                # Checked and published under the lock clear() removes videos under, so a reply
                # cleared meanwhile is never published after it (roadmap R27b).
                with self._publish_lock:
                    if stopped() or generation != self.generation:  # dropped, not published
                        rendering.unlink(missing_ok=True)
                        log_stop("after video")
                        return None
                    os.replace(rendering, path)
                    self._published.add(turn)
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

    def clear(self) -> int:
        """Remove every reply video, as the conversation was cleared (roadmap R27b). None is
        served after this, and one being made for a reply read before it is never published.
        Returns how many files were removed; one that can't be (open in a browser, as on
        Windows) is left, but not served."""
        removed = 0
        with self._publish_lock:
            # At once, so none is served even if its file can't be removed.
            self.generation += 1
            self._published.clear()
            for video in self.folder.glob("*.mp4"):
                if not video.stem.isdigit():  # one being written, removed by its render
                    continue
                try:
                    video.unlink()
                    removed += 1
                except OSError as e:  # open in a browser, as on Windows
                    logger.warning(
                        "Could not remove a reply video",
                        extra={"video": video.name, "error": str(e)},
                    )
        return removed

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
