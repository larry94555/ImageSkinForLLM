"""The prepare job (roadmaps R12, R13 and R25b): gets the voice and the face ready for the video,
renders the sample video and the fixed lines, in the background, and reports how far it has got.
The clips are spoken in the person's own voice, cloned from the voice sample, when Chatterbox is
installed (R25), with their own accent or the one chosen in setup (R26), and in a ready-made Kokoro
voice otherwise.

The face step renders the photoreal frame library (`photoreal_library`), which takes tens of
minutes or more on a laptop CPU. The job's state is saved in <data folder>/prepare.json, so
when the server stops mid-way, the next start carries on: frames and clips already rendered
are kept. The clips are saved in <data folder>/clips/<name>.mp4.
"""

import json
import logging
import math
import os
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeVar

from imageskin.accent import OWN, Accent, AccentEngine
from imageskin.download import sha256_of
from imageskin.failure import Failure, report
from imageskin.kokoro_engine import DEFAULT_VOICE, KokoroEngine
from imageskin.sample import SAMPLE_SCRIPT
from imageskin.ui_settings import DEFAULTS, load_ui_settings
from imageskin.uploads import UploadStore
from imageskin.video import INSTALL_HINT, VideoError, find_ffmpeg
from imageskin.voice import VoiceEngine, VoiceError, write_speech

if TYPE_CHECKING:
    from imageskin.chatterbox_engine import ChatterboxEngine
    from imageskin.speaker_checks import SpeakerChecker

logger = logging.getLogger(__name__)

State = Literal["idle", "running", "done", "failed"]
T = TypeVar("T")


class Progress(Protocol):
    """Told how far a step has got: the step's key, done, total, and what it is doing now in
    plain words, such as "Frame 12 of 40" (roadmap R134b)."""

    def __call__(
        self, step: str, done: int, total: int, activity: str | None = None, /
    ) -> None: ...


PrepareVoice = Callable[[], None]
PrepareFace = Callable[[Path, Progress], None]
RenderClip = Callable[[Path, str, Path], None]  # photo, what to say, MP4 to write
SpeakClip = Callable[[str, Path], None]  # what to say, WAV to write (its timings JSON beside it)
# photo, the WAV spoken, MP4 to write; returns how far the mouth opened before the voice in
# ms, when the engine measures it (roadmap R128)
RenderVideo = Callable[[Path, Path, Path], float | None]
RenderIdle = Callable[[Path, Path], None]  # photo, MP4 to write


@dataclass(frozen=True)
class ClipSteps:
    """A clip's two steps apart, so one clip's video is rendered while the next is spoken
    (roadmap R22b)."""

    speak: SpeakClip
    render: RenderVideo
    # The idle video shown between replies (roadmap R23), for an engine that can make one.
    idle: RenderIdle | None = None
    # Drops what the steps keep of the person, such as the loaded face (roadmap R31).
    forget: Callable[[], None] | None = None


def steps_clip(steps: ClipSteps) -> RenderClip:
    """The two steps as one clip, for the prepare job's clips and a reply spoken in one video."""

    def render(photo: Path, text: str, output: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "speech.wav"
            steps.speak(text, wav)
            steps.render(photo, wav, output)

    return render


ClipName = Literal["sample", "goodbye", "welcome-back"]

# The videos rendered after the face (features.md items 5 and 6): the sample video the user
# reviews, and the fixed lines said on exit and on return.
CLIPS: tuple[tuple[ClipName, str], ...] = (
    ("goodbye", "Goodbye."),
    ("welcome-back", "Welcome back."),
    ("sample", SAMPLE_SCRIPT),
)

# The steps in order: key, what the browser shows, and roughly how many seconds each takes on a
# 4-core CPU, which weights it in the overall percentage. The clips, the mouth shapes and the idle
# loop are most of the work (the loop renders a quarter as many frames since R96e). The voice and
# clips weights are for the cloned voice, which loads for about 30 seconds and takes
# about 2.5 seconds per second of speech; Kokoro is quicker.
STEPS = (
    ("voice", "Get the voice ready", 40),
    ("models", "Get ready to animate the face", 30),
    ("shapes", "Make the mouth shapes and the blinking eyes", 70),
    ("loop", "Make the video of the person listening", 70),
    ("align", "Line up the mouth with the head", 20),
    ("clips", "Make the sample video and the greetings", 100),
)
# How often the job tells the page it is still working, with the time so far (roadmap R134b).
BEAT_S = 1.0
# A step with nothing new for longer than this many times its usual time is slow.
SLOW_FACTOR = 2
# The range this run's pace against the usual times is kept in, for the time left.
PACE_MIN, PACE_MAX = 0.5, 5.0
# The last part of a step's expected time, as a share of it, over which its time left counts
# down ever more slowly instead of reaching 0 while the step still runs, and at least this many
# seconds of it, so the page keeps moving when a step takes longer than expected.
TAIL_SHARE, TAIL_MIN_S = 0.25, 10.0
# What each clip's activity line says while it is made.
CLIP_ACTIVITY: dict[str, str] = {
    "goodbye": "Making the video of “Goodbye.”",
    "welcome-back": "Making the video of “Welcome back.”",
    "sample": "Making the sample video",
}
NO_PHOTO = "Add a photo that passes the checks first."
# Run the video test again (roadmap R27b) needs the sample from a finished prepare.
NOT_PREPARED = "There is no sample video yet. Prepare it in setup first."
# Prepare started, or what it is made from changed, while the sample was rendered again.
CHANGED_MEANWHILE = "The setup changed while the video was made. Try again."
# Prepare and another accent wait for the sample being made again: they share its engines.
SAMPLE_BEING_MADE = "The sample video is being made again. Try again once it is ready."
# Delete my data (roadmap R31) waits for a prepare, which would write its files again.
WAIT_TO_DELETE = "Setup is preparing the video. Try again once it has finished."
# A default person (roadmap R24c) is got ready with the same engines and writes to the same
# folders, so nothing else that does runs meanwhile.
# Start now waits for a prepare, which uses the same engines.
WAIT_TO_START_NOW = "Setup is preparing your own video. Try again once it has finished."
DEFAULT_PERSON_BEING_READIED = "A default person is being got ready. Try again once they are ready."
# Prepare clicked while a cancelled job is still finishing the part it was on (roadmap R134c).
STOPPING = "Preparing is stopping. Try again in a moment."
# Before the avatar's name in a photo id, when the avatar is prepared in the user's voice (R24d).
AVATAR_PREFIX = "avatar-"
# The voice kinds that speak in the person's own voice: Pocket TTS or Chatterbox Turbo.
CLONES = ("pocket", "clone")


class PrepareError(Exception):
    """The job can't start yet; the message says what is missing."""


class PrepareCancelled(BaseException):
    """Raised in the job's thread at its next progress report once Cancel is confirmed (roadmap
    R134c). A BaseException, so an engine that catches Exception doesn't swallow it."""


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    done: int = 0
    total: int = 1
    seconds: float | None = None  # how long it took, once finished in this run
    left_s: int | None = None  # while it runs: about how many seconds are left
    activity: str | None = None  # while it runs: what it is doing now, in plain words (R134b)
    elapsed_s: int | None = None  # while it runs: how long it has taken so far
    slow: bool = False  # nothing new for longer than twice its usual time


# A job saved before R128a has no face movement: its clips were made with none, as with "off".
# So once the default Normal is chosen, it is prepared and reviewed again before replies move
# the cheeks (review on PR #174).
BEFORE_R128A = "off"


@dataclass(frozen=True)
class PrepareStatus:
    state: State
    photo_id: str | None = None  # the photo being, or last, prepared
    # The voice the clips are spoken in: "<kind>:<voice_fingerprint>", with "-<accent>" after the
    # kind when the clone speaks with another accent than the person's own.
    voice_id: str | None = None
    percent: int = 0
    steps: list[Step] | None = None
    error: str | None = None  # why it failed, in plain words
    failure: Failure | None = None  # with the step, the reference and the details (R134)
    started_at: str | None = None  # ISO 8601, UTC
    finished_at: str | None = None
    left_s: int | None = None  # while it runs: about how many seconds the whole prepare has left
    # How many seconds each step took the last time it ran on this machine (0: it had nothing
    # to do, as the face on Prepare again), for the time left of the next prepare.
    times: dict[str, float] | None = None
    # Running, but the app is no longer working on it (its thread has gone): Try again carries on.
    stopped: bool = False
    # The face movement while speaking the clips are made with (R128a), from the Setup page when
    # the job ran; None if saved before R128a.
    face_movement: str | None = None
    # Running, but Cancel was confirmed (R134c): it stops at the next progress report, once the
    # part it is on is finished, and is then idle.
    cancelling: bool = False


def fresh_steps() -> list[Step]:
    return [Step(key, label) for key, label, _ in STEPS]


def percent(steps: list[Step]) -> int:
    weights = {key: weight for key, _, weight in STEPS}
    done = sum(weights[s.key] * share(s, weights[s.key]) for s in steps if s.total)
    return int(100 * done / sum(weights.values()))


def share(step: Step, usual_s: float) -> float:
    """How much of the step is done. A step whose work can't be counted (one of one) moves with
    its time so far against its usual time, slower and slower, never quite reaching its end."""
    if step.total == 1 and step.done == 0 and step.elapsed_s:
        return 0.9 * (1 - math.exp(-step.elapsed_s / usual_s))
    return step.done / step.total


def remaining(expected: float, elapsed: float) -> float:
    """About how many seconds are left of a step expected to take `expected` seconds, `elapsed`
    seconds in. It counts down a second a second, then, over the last part (TAIL_SHARE, at least
    TAIL_MIN_S), ever more slowly, so it never stands at 0 while the step still runs."""
    tail = min(max(TAIL_SHARE * expected, TAIL_MIN_S), expected) if expected > 0 else 0.0
    if expected - elapsed >= tail:
        return expected - elapsed
    if tail <= 0:
        return 0.0
    return tail * math.exp((expected - tail - elapsed) / tail)


def voice_fingerprint(path: Path) -> str | None:
    """Tells voice samples apart: it changes whenever the recordings the sample is joined from
    change. None when there is no voice sample."""
    try:
        return sha256_of(path)[:16]
    except FileNotFoundError:
        return None


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class PrepareJob:
    """One prepare job at a time, run on a background thread."""

    def __init__(
        self,
        home: Path,
        store: UploadStore,
        prepare_voice: PrepareVoice,
        prepare_face: PrepareFace,
        render_clip: RenderClip,
        voice_kind: str = "kokoro",  # what speaks the clips: "pocket", "clone" or "kokoro"
        accent: Callable[[], Accent] = lambda: OWN,  # the accent chosen in setup
        # The ready-made Kokoro voice kept while the user's own photo replaces a default
        # person's picture (R24d), or None: then no recordings are needed or prepared.
        kept_voice: Callable[[], str | None] = lambda: None,
        # The ready-made avatar's picture while the avatar is to speak in the user's own voice
        # (R24d), or None: then the picture is prepared with the recordings, not the photo.
        avatar: Callable[[], Path | None] = lambda: None,
    ) -> None:
        self._file = home / "prepare.json"
        self.clips_folder = home / "clips"
        self._store = store
        self._prepare_voice = prepare_voice
        self._prepare_face = prepare_face
        self._render_clip = render_clip
        self._voice_kind = voice_kind
        self._accent = accent
        self._kept_voice = kept_voice
        self._avatar = avatar
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        # The sample is being rendered again (roadmap R27b): no prepare runs meanwhile, as it
        # would remove the clips and use the same voice and video engines.
        self._rendering_again = False
        # A default person is being got ready (roadmap R24c), see claim().
        self._claimed = False
        # Per running step: when it started and how much was done then, for the time left.
        self._clock: dict[str, tuple[float, int]] = {}
        # When the running step last reported something new, for the slow notice (R134b).
        self._changed = 0.0
        # When each running step's count last went up, for its time left between counts.
        self._counted: dict[str, float] = {}
        # Set by cancel() (R134c); the job's thread stops at its next progress report.
        self._cancel = threading.Event()
        self._status = self._load()

    def _load(self) -> PrepareStatus:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            steps = [Step(**s) for s in data.pop("steps") or []]
            failure = data.pop("failure", None)
            status = PrepareStatus(
                **data, steps=steps, failure=Failure(**failure) if failure else None
            )
            if [s.key for s in steps] != [key for key, _, _ in STEPS]:
                # Saved by a version with other steps: a running job starts its steps afresh
                # (frames already rendered are still kept); anything else needs preparing again.
                if status.state != "running":
                    return PrepareStatus("idle")
                status = replace(status, steps=fresh_steps(), percent=0)
            return status
        except FileNotFoundError:
            return PrepareStatus("idle")
        except (OSError, ValueError, TypeError, KeyError) as e:
            logger.error("Could not read the prepare job state", extra={"error": str(e)})
            return PrepareStatus("idle")

    def _save(self) -> None:
        """Write the state so that an interrupted write never leaves a broken file."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._file.with_name("prepare.saving.json")
        tmp.write_text(json.dumps(asdict(self._status), indent=2), encoding="utf-8")
        os.replace(tmp, self._file)

    def status(self) -> PrepareStatus:
        """How far the job has got. A finished job shows as idle once what it was made from
        changed: another photo is chosen, the recordings changed (the clips speak in the voice
        learned from them) or another accent is chosen. A running job no thread is working on
        shows as stopped."""
        with self._lock:
            status = self._status
            if status.state == "running" and not self._working():
                status = replace(status, stopped=True)
        return self._current(status)

    def _working(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _current(self, status: PrepareStatus) -> PrepareStatus:
        if status.state in ("done", "failed"):
            if status.photo_id != self._photo_id():
                return PrepareStatus("idle")
            if self._voice_problem():
                return PrepareStatus("idle")
            if status.voice_id != self.voice_id():
                return PrepareStatus("idle")
            # Another face movement chosen (R128a): the sample shows the old one, so it is
            # prepared and reviewed again before replies use the new one. A job saved before
            # R128a was made with none, as Off is (review on PR #174).
            if (status.face_movement or BEFORE_R128A) != self.face_movement():
                return PrepareStatus("idle")
        return status

    def face_movement(self) -> str:
        """The face movement chosen on the Setup page now."""
        return load_ui_settings(self._file.parent).face_movement

    def prepared_face_movement(self) -> str:
        """The face movement the clips of this job are made with: the one chosen when it ran,
        not a change made since, so a job's clips and the replies after them all move alike."""
        return self._status.face_movement or BEFORE_R128A

    def peek(self) -> PrepareStatus:
        """status() without the job's lock, for the replies' voice (R24d): a reply holds the
        voice engine, which Delete my data takes under this lock. One reference read is atomic."""
        return self._current(self._status)

    def change_voice(self, change: Callable[[], object], prepare_again: bool = True) -> bool:
        """Change the accent, or the ready-made voice used without recordings (item 59), or
        whether the ready-made avatar speaks in the user's voice (R24d), with `change`, unless a
        job is running: it would finish in the voice from before. While the sample is made
        again, PrepareError. When the clips were ready and `prepare_again`, prepare again at once
        (the face is kept, so only the voice and the clips are redone).
        Whether it was changed.

        Done under the job's lock, so a Prepare started at the same time either runs with the
        change or makes it wait: never a job that finishes in a voice the page no longer shows."""
        with self._lock:
            if self._status.state == "running":
                return False
            self._refuse_if_busy()
            prepared = self._current(self._status).state == "done"
            change()
            if prepare_again and prepared and self._current(self._status).state == "idle":
                logger.info("Voice changed; preparing the sample again")
                try:
                    self._start()
                except PrepareError as e:  # the uploads changed meanwhile; Prepare says what to do
                    logger.warning("Could not prepare again", extra={"error": str(e)})
            return True

    def clip(self, name: ClipName) -> Path | None:
        """The rendered clip, once the job has finished for what is uploaded now."""
        if self.status().state != "done":
            return None
        path = self.clips_folder / f"{name}.mp4"
        return path if path.is_file() else None

    def render_sample_again(self) -> float:
        """Render the sample video again from the prepared face and voice, replacing the one
        there (roadmap R27b), and return how many seconds it took. The caller keeps the replies
        off the engines meanwhile; Prepare and another accent are refused until it is done. The
        new video is kept only if nothing it is made from changed while it was rendered."""
        with self._lock:
            before = self._current(self._status)
            if before.state != "done" or before.photo_id is None:
                raise PrepareError(NOT_PREPARED)
            self._refuse_if_busy()
            photo = self._photo(before.photo_id)
            if photo is None:
                raise PrepareError(NOT_PREPARED)
            self._rendering_again = True
        start = time.perf_counter()
        logger.info("Rendering the sample video again", extra={"photo_id": before.photo_id})
        path = self.clips_folder / "sample.mp4"
        rendering = path.with_name("sample.again.mp4")
        try:
            self._render_clip(photo, SAMPLE_SCRIPT, rendering)
            with self._lock:
                if self._current(self._status) is not before:
                    raise PrepareError(CHANGED_MEANWHILE)
                os.replace(rendering, path)
        except Exception:
            rendering.unlink(missing_ok=True)
            raise
        finally:
            with self._lock:
                self._rendering_again = False
        seconds = round(time.perf_counter() - start, 1)
        logger.info("Rendered the sample video again", extra={"duration_s": seconds})
        return seconds

    def forget(self, delete: Callable[[], T]) -> T:
        """Delete my data (roadmap R31): run `delete`, which removes this job's files with the
        rest, and start again from nothing prepared. Refused with PrepareError while a job runs
        or the sample is made again, as they would write their files again. Done under the
        job's lock, so a Prepare started meanwhile waits for it."""
        with self._lock:
            if self._status.state == "running":
                raise PrepareError(WAIT_TO_DELETE)
            self._refuse_if_busy()
            done = delete()
            self._status = PrepareStatus("idle")
            return done

    def _refuse_if_busy(self) -> None:
        if self._rendering_again:
            raise PrepareError(SAMPLE_BEING_MADE)
        if self._claimed:
            raise PrepareError(DEFAULT_PERSON_BEING_READIED)

    def claim(self) -> None:
        """Start now (roadmap R24c) is about to get a default person ready: it renders with this
        job's engines and writes the photoreal library, so until release() no Prepare, accent
        change, sample rendered again or Delete my data runs (review on PR #113). PrepareError,
        saying why, while one of them is running."""
        with self._lock:
            if self._status.state == "running":
                raise PrepareError(WAIT_TO_START_NOW)
            self._refuse_if_busy()
            self._claimed = True

    def release(self) -> None:
        with self._lock:
            self._claimed = False

    def start(self) -> PrepareStatus:
        """Start preparing the chosen photo and the voice; while it runs, just report on it."""
        with self._lock:
            return self._start()

    def _start(self) -> PrepareStatus:
        if self._status.state == "running":
            if self._status.cancelling:
                raise PrepareError(STOPPING)
            if not self._working():  # stopped (R134b): carry on where it left off
                logger.warning(
                    "Prepare job had stopped; carrying on",
                    extra={"photo_id": self._status.photo_id},
                )
                self._run_in_background()
            return self._status
        self._refuse_if_busy()
        photo_id = self._photo_id()
        if photo_id is None:
            raise PrepareError(NO_PHOTO)
        problem = self._voice_problem()
        if problem:
            raise PrepareError(problem)
        # Clips from before were made from other uploads; the face's frames are kept per
        # photo by the library, so only the clips are removed.
        self._remove_clips()
        times = dict(self._status.times or {})
        if self._status.photo_id != photo_id:  # another face: its steps have work to do again
            times = {key: s for key, s in times.items() if s > 0}
        self._status = PrepareStatus(
            "running", photo_id, steps=fresh_steps(), started_at=now_iso(), times=times
        )
        self._save()
        self._run_in_background()
        return self._status

    def cancel(self) -> PrepareStatus:
        """Stop the running job (roadmap R134c). A job no thread is working on stops at once;
        otherwise it is marked cancelling and its thread stops at its next progress report, as
        an engine can't be stopped half-way through a frame or a clip. The face's frames already
        made are kept by the library, so preparing again later is quicker."""
        with self._lock:
            if self._status.state != "running":
                logger.info(
                    "Cancel asked with no prepare running", extra={"state": self._status.state}
                )
                return self._status
            if not self._working():
                self._to_idle("stopped")
                return self._status
            if not self._status.cancelling:
                logger.info("Prepare cancelling", extra={"photo_id": self._status.photo_id})
                self._cancel.set()
                self._status = replace(self._status, cancelling=True)
                self._save()
            return self._status

    def _to_idle(self, why: str) -> None:
        """The job cancelled, with the lock held: nothing prepared, but each step's time is
        kept for the next prepare's time left."""
        logger.info("Prepare cancelled", extra={"photo_id": self._status.photo_id, "when": why})
        self._status = PrepareStatus("idle", times=self._status.times)
        self._save()

    def _photo_id(self) -> str | None:
        """What is prepared: the chosen photo, or the avatar to speak in the user's voice."""
        avatar = self._avatar()
        if avatar is not None:
            return f"{AVATAR_PREFIX}{avatar.stem}"
        return self._store.photo_choice().id

    def _photo(self, photo_id: str) -> Path | None:
        if photo_id.startswith(AVATAR_PREFIX):
            avatar = self._avatar()
            return avatar if avatar is not None and photo_id == self._photo_id() else None
        return self._store.path("photos", photo_id)

    def _voice_problem(self) -> str | None:
        """Why the recordings can't make the voice, unless a ready-made one is kept (R24d)."""
        if self._kept_voice():
            return None
        return self._store.voice_sample().problem

    def voice_id(self) -> str | None:
        """The voice clips are spoken in now: who speaks them, with which accent, and the sample
        they learned from. Installing Chatterbox after a Kokoro prepare changes it too, and so does
        installing or removing Pocket TTS. Kokoro speaks with its own accent, whichever is
        chosen. A ready-made voice kept for the user's own photo (R24d) is "preset:<voice>"."""
        kept = self._kept_voice()
        if kept:
            return f"preset:{kept}"
        fingerprint = voice_fingerprint(self._store.voice_sample_file)
        if not fingerprint:
            return None
        accent = self._accent()
        kind = self._voice_kind
        # Chatterbox speaks another accent through Kokoro and its converter; Pocket TTS speaks it
        # itself, learned from converted speech.
        if kind in CLONES and accent != OWN:
            kind = f"{kind}-{accent}"
        return f"{kind}:{fingerprint}"

    def _remove_clips(self) -> int:
        old = list(self.clips_folder.glob("*.mp4"))
        for path in old:
            path.unlink()
        return len(old)

    def resume(self) -> None:
        """At server start: carry on with a job the last run of the server didn't finish."""
        with self._lock:
            if self._status.state != "running":
                return
            if self._status.cancelling:  # the server stopped before the cancel was done
                self._to_idle("at start")
                return
            # The steps keep showing how far it had got until each one reports again.
            logger.info("Resuming prepare job", extra={"photo_id": self._status.photo_id})
            self._run_in_background()

    def _run_in_background(self) -> None:
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, name="prepare", daemon=True)
        self._thread.start()

    def wait(self, timeout: float | None = None) -> None:
        """For tests: wait for the background thread to finish."""
        if self._thread is not None:
            self._thread.join(timeout)

    def _progress(self, key: str, done: int, total: int, activity: str | None = None) -> None:
        if self._cancel.is_set():
            raise PrepareCancelled()
        now = time.perf_counter()
        with self._lock:
            steps = self._status.steps or []
            old = next(s for s in steps if s.key == key)
            if old.done >= old.total and done >= total:
                return  # told twice that it is finished
            self._changed = now
            if (done, total) == (old.done, old.total) and key in self._clock:
                # Only what it is doing changed, such as another MB downloaded: kept in memory,
                # as it may change many times a second.
                if activity != old.activity:
                    logger.debug("Prepare activity", extra={"step": key, "activity": activity})
                new = replace(old, activity=activity, slow=False)
                self._status = replace(
                    self._status, steps=[new if s.key == key else s for s in steps]
                )
                return
            if activity is not None:
                logger.debug("Prepare activity", extra={"step": key, "activity": activity})
            started, done_at_start = self._clock.setdefault(key, (now, done))
            self._counted[key] = now
            elapsed = now - started
            seconds, left = None, None
            times = dict(self._status.times or {})
            if done >= total and done_at_start >= total:
                logger.info("Prepare step already done", extra={"step": key})  # kept from before
                times[key] = 0.0
            elif done >= total:
                seconds = round(elapsed, 1)
                logger.info("Prepare step finished", extra={"step": key, "duration_s": seconds})
                times[key] = seconds
            elif done > done_at_start:
                left = round(elapsed / (done - done_at_start) * (total - done))
            new = replace(
                old,
                done=done,
                total=total,
                seconds=seconds,
                left_s=left,
                activity=None if done >= total else activity,
                elapsed_s=None if done >= total else round(elapsed),
                slow=False,
            )
            steps = [new if s.key == key else s for s in steps]
            self._status = replace(self._status, steps=steps, times=times)
            self._estimate(now)
            self._save()  # a small file, and a frame takes seconds

    def _beat(self, now: float) -> None:
        """Tell the page the job is still working (roadmap R134b): about how long the running
        step and the whole prepare have left, and whether nothing new has come for longer than
        expected. Each step is expected to take as long as it did the last time it ran on this
        machine, or else its usual time at this run's pace. The time left counts down every
        second and the percentage, the time so far against the time so far and left, moves
        with it: never back, and never standing still while a step runs longer than expected."""
        with self._lock:
            if self._status.state == "running":
                self._estimate(now)

    def _estimate(self, now: float) -> None:
        """_beat()'s work, with the job's lock held."""
        usual = {key: weight for key, _, weight in STEPS}
        steps = self._status.steps or []
        pace = self._pace(steps)
        times = self._status.times or {}

        def expected(key: str) -> float:
            return times[key] if key in times else usual[key] * pace

        step = next((s for s in steps if s.done < s.total and s.key in self._clock), None)
        left = 0.0
        spent = sum(s.seconds or 0 for s in steps if s.done >= s.total)
        if step is not None:
            started, done_at_start = self._clock[step.key]
            elapsed = now - started
            spent += elapsed
            quiet = now - self._changed
            slow = quiet > SLOW_FACTOR * max(expected(step.key), usual[step.key])
            if slow and not step.slow:
                logger.warning(
                    "Prepare step slow",
                    extra={
                        "step": step.key,
                        "elapsed_s": round(elapsed),
                        "quiet_s": round(quiet),
                    },
                )
            if step.done > done_at_start and (step.key not in times or done_at_start):
                # From how fast it counts, when this machine's time for it isn't known.
                counted = self._counted[step.key]
                per = (counted - started) / (step.done - done_at_start)
                left = remaining(per * (step.total - step.done), now - counted)
            else:  # what was left of it when it started, at its expected time
                share_left = 1 - done_at_start / step.total
                left = remaining(expected(step.key) * share_left, elapsed)
            new = replace(step, elapsed_s=round(elapsed), slow=slow, left_s=round(left))
            steps = [new if s.key == step.key else s for s in steps]
        rest = sum(
            expected(s.key) * (1 - s.done / s.total)
            for s in steps
            if s.done < s.total and (step is None or s.key != step.key)
        )
        whole = spent + left + rest
        done_share = int(100 * spent / whole) if whole > 0 else 0
        self._status = replace(
            self._status,
            steps=steps,
            percent=min(max(done_share, self._status.percent), 99),
            left_s=round(left + rest),
        )

    @staticmethod
    def _pace(steps: list[Step]) -> float:
        """How long the steps finished in this run took against their usual times: 2.0 on a
        machine twice as slow as the one the usual times were measured on. 1.0 until one is.
        Kept between 0.5 and 5, as a quick step (models already downloaded, say) says little
        about the long ones."""
        usual = {key: weight for key, _, weight in STEPS}
        finished = [s for s in steps if s.done >= s.total and s.seconds is not None]
        expected = sum(usual[s.key] for s in finished)
        if not expected:
            return 1.0
        return min(max(sum(s.seconds or 0 for s in finished) / expected, PACE_MIN), PACE_MAX)

    def _beat_until(self, finished: threading.Event) -> None:
        while not finished.wait(BEAT_S):
            self._beat(time.perf_counter())

    def _run(self) -> None:
        finished = threading.Event()
        beats = threading.Thread(
            target=self._beat_until, args=(finished,), name="prepare-beat", daemon=True
        )
        beats.start()
        try:
            self._run_steps()
        finally:
            finished.set()

    def _run_steps(self) -> None:
        start = time.perf_counter()
        photo_id = self._status.photo_id or ""
        self._clock = {}
        self._counted = {}
        self._changed = start
        logger.info("Prepare job started", extra={"photo_id": photo_id})
        with self._lock:
            # The voice is learned from the sample as it is now. A job resumed after the
            # recordings changed, or saved before voices were tracked, may have clips in another
            # voice; they are rendered again rather than mixed with new ones.
            voice_id = self.voice_id()
            if self._status.voice_id != voice_id:
                removed = self._remove_clips()
                if removed:
                    message = "Voice changed; rendering the clips again"
                    logger.info(message, extra={"clips": removed})
                self._status = replace(self._status, voice_id=voice_id)
                self._save()
            # Likewise a job resumed after another face movement was chosen (R128a), or saved
            # before it was tracked: no clip set mixes two.
            movement = self.face_movement()
            if self._status.face_movement != movement:
                removed = self._remove_clips()
                if removed:
                    message = "Face movement changed; rendering the clips again"
                    logger.info(message, extra={"clips": removed, "face_movement": movement})
                self._status = replace(self._status, face_movement=movement)
                self._save()
        try:
            photo = self._photo(photo_id)
            if photo is None:
                raise PrepareError("The photo to prepare was removed. Choose another one.")
            if self._kept_voice():
                self._progress("voice", 0, 1, "Keeping the ready-made voice")
                logger.info("Keeping the ready-made voice", extra={"voice": self._kept_voice()})
            else:
                kokoro = self._voice_kind not in CLONES
                activity = (
                    "Loading the voice model"
                    if kokoro
                    else "Loading the voice models and learning the voice from your recordings"
                )
                self._progress("voice", 0, 1, activity)
                self._prepare_voice()
            self._progress("voice", 1, 1)
            self._prepare_face(photo, self._progress)
            self._render_clips(photo)  # its report after the last clip stops a late cancel
        except PrepareCancelled:
            with self._lock:
                self._to_idle("running")
            logger.info(
                "Prepare job stopped",
                extra={"photo_id": photo_id, "duration_s": round(time.perf_counter() - start, 1)},
            )
            return
        except Exception as e:
            if self._cancel.is_set():  # an engine failed while it was being stopped
                logger.warning("Prepare failed while cancelling", extra={"error": str(e)})
                with self._lock:
                    self._to_idle("running")
                return
            self._fail(e, photo_id)
            return
        self._finish("done", None)
        logger.info(
            "Prepare job finished",
            extra={"photo_id": photo_id, "duration_s": round(time.perf_counter() - start, 1)},
        )

    def _fail(self, e: Exception, photo_id: str) -> None:
        """Tell the customer which step failed, why and the reference to give support; the log
        has the full error under the reference (roadmap R134). A PrepareError already says what
        to do."""
        steps = self._status.steps or []
        step = next((s.label for s in steps if s.done < s.total), None)
        message = str(e) if isinstance(e, PrepareError) else None
        home = self._file.parent
        failure = report(e, logger, "Prepare job failed", home, step, message, photo_id=photo_id)
        self._finish("failed", failure.message, failure)

    def _render_clips(self, photo: Path) -> None:
        """Render each clip not already there. Progress counts words, so the long sample
        weighs more than "Goodbye." in the time left."""
        self.clips_folder.mkdir(parents=True, exist_ok=True)
        todo = [(n, t) for n, t in CLIPS if not (self.clips_folder / f"{n}.mp4").is_file()]
        total = sum(len(text.split()) for _, text in CLIPS)
        done = total - sum(len(text.split()) for _, text in todo)
        self._progress("clips", done, total)
        for name, text in todo:
            start = time.perf_counter()
            self._progress("clips", done, total, CLIP_ACTIVITY[name])
            path = self.clips_folder / f"{name}.mp4"
            # Written aside then moved, so a clip cut short by a restart is never used.
            rendering = path.with_name(f"{name}.rendering.mp4")
            self._render_clip(photo, text, rendering)
            os.replace(rendering, path)
            logger.info(
                "Rendered clip",
                extra={"clip": name, "duration_s": round(time.perf_counter() - start, 1)},
            )
            done += len(text.split())
            self._progress("clips", done, total)

    def _finish(self, state: State, error: str | None, failure: Failure | None = None) -> None:
        with self._lock:
            steps = self._status.steps or []
            if state == "done":
                # Steps with nothing to do (a library made before) are complete too.
                steps = [replace(s, done=s.total, left_s=None) for s in steps]
            else:
                steps = [replace(s, left_s=None) for s in steps]
            steps = [replace(s, activity=None, elapsed_s=None, slow=False) for s in steps]
            self._status = replace(
                self._status,
                state=state,
                steps=steps,
                percent=100 if state == "done" else percent(steps),
                error=error,
                failure=failure,
                finished_at=now_iso(),
                left_s=None,
            )
            self._save()


def kokoro_voice(engine: VoiceEngine) -> PrepareVoice:
    """Load the voice model (downloaded the first time, about 330 MB) by saying one word. The
    same engine then speaks the clips, so the model is loaded once."""

    def prepare() -> None:
        engine.speak(DEFAULT_VOICE, "Hello.")

    return prepare


def cloned_voice(
    engine: AccentEngine, voice_sample: Path, accent: Callable[[], Accent]
) -> PrepareVoice:
    """Load the clone's models (downloaded the first time, about 3 GB) and learn the person's
    voice from the voice sample, with the accent chosen now. The same engine then speaks the clips
    in that voice."""

    def prepare() -> None:
        start = time.perf_counter()
        chosen = accent()
        engine.prepare(str(voice_sample), chosen)
        logger.info(
            "Voice ready: the person's own",
            extra={
                "accent": chosen,
                "base": engine.base,
                "duration_s": round(time.perf_counter() - start, 1),
            },
        )

    return prepare


def clip_voice(
    voice_sample: Path, accent: Callable[[], Accent], speakers: "SpeakerChecker"
) -> tuple[PrepareVoice, VoiceEngine, str, str]:
    """The voice step, the engine, the voice the clips are spoken in and its kind ("pocket",
    "clone" or "kokoro"): the person's own, cloned from the voice sample with the chosen accent,
    when Chatterbox is installed (see the README); otherwise Kokoro's. With Pocket TTS installed
    too, Pocket speaks, about ten times faster than Chatterbox on 4 cores, so replies can start
    within 1 to 2 seconds (roadmap R22f), with every accent (see accent_engine)."""
    from imageskin import pocket_engine
    from imageskin.chatterbox_engine import ChatterboxEngine, check_installed

    try:
        check_installed()
    except VoiceError as e:
        message = "Prepare speaks in a ready-made Kokoro voice, not the person's"
        logger.warning(message, extra={"reason": str(e)})
        kokoro = KokoroEngine()
        return kokoro_voice(kokoro), kokoro, DEFAULT_VOICE, "kokoro"
    if pocket_engine.installed():
        logger.info("Prepare speaks in the person's own voice, cloned with Pocket TTS")
        clone, kind = pocket_engine.pocket_engine(), "pocket"
    else:
        logger.info("Prepare speaks in the person's own voice, cloned with Chatterbox Turbo")
        clone, kind = ChatterboxEngine(), "clone"
    engine = accent_engine(clone, kind, speakers)
    return cloned_voice(engine, voice_sample, accent), engine, str(voice_sample), kind


def accent_engine(clone: "ChatterboxEngine", kind: str, speakers: "SpeakerChecker") -> AccentEngine:
    """The clone, with Kokoro, Chatterbox's converter and the app's speaker model (shared with the
    one-speaker check) for other accents. Each is loaded only when another accent is first used.
    The converter shares Chatterbox's model with the clone, or loads it when Pocket TTS clones.
    Pocket keeps the accent it learns from, so it learns another accent from converted speech
    in prepare and speaks every line itself, as fast as the person's own accent. Both are decided
    by `kind`, the clone's kind in the voice id ("clone" for Chatterbox, "pocket"), not by its
    name in the logs."""
    from imageskin.chatterbox_engine import SAMPLE_RATE, TurboConverter, _load_cloner
    from imageskin.kokoro_engine import kokoro_for

    def converter() -> TurboConverter:
        model = clone.cloner() if kind == "clone" else _load_cloner()
        return TurboConverter(model.tts.s3gen)  # type: ignore[attr-defined]

    return AccentEngine(
        clone,
        kokoro_for,
        converter,
        lambda samples: speakers.voice_print(samples, SAMPLE_RATE),
        clone_keeps_accent=kind == "pocket",
    )


def photoreal_face(home: Path) -> PrepareFace:
    """Render the photo's photoreal frame library (models downloaded the first time)."""

    def prepare(photo: Path, progress: Progress) -> None:
        try:
            from imageskin.photoreal_library import prepare_library
        except ImportError as e:
            if e.name in ("cv2", "numpy"):
                raise VideoError(INSTALL_HINT.replace(".[video]", ".[photoreal]")) from e
            raise
        find_ffmpeg()  # the sample video will need it; say so now, not after the long part
        prepare_library(photo, home, progress=progress)

    return prepare


# The longest side of a reply clip, in pixels (roadmap R22c): the chat page shows it at most
# 640 pixels wide, and a frame of a 1280-pixel photo took about 6 times longer to paste and
# encode than a 512-pixel one. The sample video keeps the photo's own size.
REPLY_SIDE = 720


def photoreal_steps(
    home: Path,
    voice_engine: VoiceEngine,
    voice: str = DEFAULT_VOICE,
    max_side: int | None = None,  # the clip's longest side, when the photo is to be scaled down
    progressive: bool = False,  # an MP4 that can be played while it is written (roadmap R22d)
    # The face movement to render with (R128a): the prepare job's, so a change on the Setup
    # page shows only after preparing again.
    face_movement: Callable[[], str] = lambda: DEFAULTS.face_movement,
) -> ClipSteps:
    """Speak the text in the voice; render the speech from the photo's photoreal library.

    Each clip starts on the idle-loop frame the one before it ended on, so a reply's clips
    join without the head jumping back (roadmap R23)."""
    # The video engine and the loaded library, made on first use and kept for the next clip,
    # and the idle-loop frame the next clip starts on.
    kept: dict[str, Any] = {"frame": 0}

    def speak(text: str, wav: Path) -> None:
        write_speech(voice_engine.speak(voice, text), wav, wav.with_suffix(".json"))

    def load(photo: Path) -> tuple[Any, Any]:
        from imageskin.photoreal import PhotorealEngine
        from imageskin.photoreal_library import scaled

        if kept.get("photo") != photo:
            video = PhotorealEngine(home)
            # Already rendered by the face step, so this only loads it.
            lib = video.prepare(photo)
            if max_side is not None:
                lib = scaled(lib, max_side)
            kept.update(photo=photo, video=video, lib=lib, frame=0)
        return kept["video"], kept["lib"]

    def render(photo: Path, wav: Path, output: Path) -> float | None:
        from imageskin.video import FPS

        video, lib = load(photo)
        start = kept["frame"]
        seconds = video.render(
            lib,
            wav,
            output,
            progressive=progressive,
            start_frame=start,
            face_movement=face_movement(),
        )
        kept["frame"] = start + max(1, round(seconds * FPS))  # the loop wraps it
        lead: float | None = video.mouth_lead_ms
        return lead

    def idle(photo: Path, output: Path) -> None:
        video, lib = load(photo)
        video.render_idle(lib, output)

    def forget() -> None:
        # The loaded library holds the person's face; the next clip loads the new one.
        kept.clear()
        kept["frame"] = 0

    return ClipSteps(speak, render, idle, forget)


def photoreal_clip(home: Path, voice_engine: VoiceEngine, voice: str = DEFAULT_VOICE) -> RenderClip:
    """Speak the text in the voice and render it from the photo's photoreal library."""
    return steps_clip(photoreal_steps(home, voice_engine, voice))
