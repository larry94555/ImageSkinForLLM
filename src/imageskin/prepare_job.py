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
import os
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from imageskin.accent import OWN, Accent, AccentEngine
from imageskin.download import sha256_of
from imageskin.kokoro_engine import DEFAULT_VOICE, KokoroEngine
from imageskin.sample import SAMPLE_SCRIPT
from imageskin.uploads import UploadStore
from imageskin.video import INSTALL_HINT, VideoError, find_ffmpeg
from imageskin.voice import VoiceEngine, VoiceError, write_speech

if TYPE_CHECKING:
    from imageskin.chatterbox_engine import ChatterboxEngine
    from imageskin.speaker_checks import SpeakerChecker

logger = logging.getLogger(__name__)

State = Literal["idle", "running", "done", "failed"]
Progress = Callable[[str, int, int], None]  # step key, done, total
PrepareVoice = Callable[[], None]
PrepareFace = Callable[[Path, Progress], None]
RenderClip = Callable[[Path, str, Path], None]  # photo, what to say, MP4 to write
SpeakClip = Callable[[str, Path], None]  # what to say, WAV to write (its timings JSON beside it)
RenderVideo = Callable[[Path, Path, Path], None]  # photo, the WAV spoken, MP4 to write


@dataclass(frozen=True)
class ClipSteps:
    """A clip's two steps apart, so one clip's video is rendered while the next is spoken
    (roadmap R22b)."""

    speak: SpeakClip
    render: RenderVideo


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
# 4-core CPU, which weights it in the overall percentage. The idle loop is most of the work. The
# voice and clips weights are for the cloned voice, which loads for about 30 seconds and takes
# about 2.5 seconds per second of speech; Kokoro is quicker.
STEPS = (
    ("voice", "Get the voice ready", 40),
    ("models", "Load the face model", 30),
    ("shapes", "Render the 10 mouth shapes and the blinking eyes", 70),
    ("loop", "Render the idle video (head movement)", 250),
    ("align", "Line up the mouth with the head", 20),
    ("clips", "Render the sample video and the fixed lines", 100),
)
NO_PHOTO = "Add a photo that passes the checks first."


class PrepareError(Exception):
    """The job can't start yet; the message says what is missing."""


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    done: int = 0
    total: int = 1
    seconds: float | None = None  # how long it took, once finished in this run
    left_s: int | None = None  # while it runs: about how many seconds are left


@dataclass(frozen=True)
class PrepareStatus:
    state: State
    photo_id: str | None = None  # the photo being, or last, prepared
    # The voice the clips are spoken in: "<kind>:<voice_fingerprint>", with "-<accent>" after the
    # kind when the clone speaks with another accent than the person's own.
    voice_id: str | None = None
    percent: int = 0
    steps: list[Step] | None = None
    error: str | None = None  # why it failed
    started_at: str | None = None  # ISO 8601, UTC
    finished_at: str | None = None


def fresh_steps() -> list[Step]:
    return [Step(key, label) for key, label, _ in STEPS]


def percent(steps: list[Step]) -> int:
    weights = {key: weight for key, _, weight in STEPS}
    done = sum(weights[s.key] * s.done / s.total for s in steps if s.total)
    return int(100 * done / sum(weights.values()))


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
        voice_kind: str = "kokoro",  # what speaks the clips: "clone" or "kokoro"
        accent: Callable[[], Accent] = lambda: OWN,  # the accent chosen in setup
    ) -> None:
        self._file = home / "prepare.json"
        self.clips_folder = home / "clips"
        self._store = store
        self._prepare_voice = prepare_voice
        self._prepare_face = prepare_face
        self._render_clip = render_clip
        self._voice_kind = voice_kind
        self._accent = accent
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        # Per running step: when it started and how much was done then, for the time left.
        self._clock: dict[str, tuple[float, int]] = {}
        self._status = self._load()

    def _load(self) -> PrepareStatus:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            steps = [Step(**s) for s in data.pop("steps") or []]
            status = PrepareStatus(**data, steps=steps)
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
        learned from them) or another accent is chosen."""
        with self._lock:
            status = self._status
        return self._current(status)

    def _current(self, status: PrepareStatus) -> PrepareStatus:
        if status.state in ("done", "failed"):
            if status.photo_id != self._store.photo_choice().id:
                return PrepareStatus("idle")
            if self._store.voice_sample().problem:
                return PrepareStatus("idle")
            if status.voice_id != self.voice_id():
                return PrepareStatus("idle")
        return status

    def change_accent(self, change: Callable[[], None]) -> bool:
        """Change the accent with `change`, unless a job is running: it would
        finish in the voice from before. When the clips were ready, prepare again at once (the
        face is kept, so only the voice and the clips are redone). Whether it was changed.

        Done under the job's lock, so a Prepare started at the same time either runs with the
        change or makes it wait: never a job that finishes in a voice the page no longer shows."""
        with self._lock:
            if self._status.state == "running":
                return False
            prepared = self._current(self._status).state == "done"
            change()
            if prepared and self._current(self._status).state == "idle":
                logger.info("Accent changed; preparing the sample again")
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

    def start(self) -> PrepareStatus:
        """Start preparing the chosen photo and the voice; while it runs, just report on it."""
        with self._lock:
            return self._start()

    def _start(self) -> PrepareStatus:
        if self._status.state == "running":
            return self._status
        photo_id = self._store.photo_choice().id
        if photo_id is None:
            raise PrepareError(NO_PHOTO)
        problem = self._store.voice_sample().problem
        if problem:
            raise PrepareError(problem)
        # Clips from before were made from other uploads; the face's frames are kept per
        # photo by the library, so only the clips are removed.
        self._remove_clips()
        self._status = PrepareStatus("running", photo_id, steps=fresh_steps(), started_at=now_iso())
        self._save()
        self._run_in_background()
        return self._status

    def voice_id(self) -> str | None:
        """The voice clips are spoken in now: who speaks them, with which accent, and the sample
        they learned from. Installing Chatterbox after a Kokoro prepare changes it too. Kokoro
        speaks with its own accent, whichever is chosen."""
        fingerprint = voice_fingerprint(self._store.voice_sample_file)
        if not fingerprint:
            return None
        accent = self._accent()
        kind = self._voice_kind
        if kind == "clone" and accent != OWN:
            kind = f"clone-{accent}"
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
            # The steps keep showing how far it had got until each one reports again.
            logger.info("Resuming prepare job", extra={"photo_id": self._status.photo_id})
            self._run_in_background()

    def _run_in_background(self) -> None:
        self._thread = threading.Thread(target=self._run, name="prepare", daemon=True)
        self._thread.start()

    def wait(self, timeout: float | None = None) -> None:
        """For tests: wait for the background thread to finish."""
        if self._thread is not None:
            self._thread.join(timeout)

    def _progress(self, key: str, done: int, total: int) -> None:
        now = time.perf_counter()
        with self._lock:
            steps = self._status.steps or []
            old = next(s for s in steps if s.key == key)
            if old.done >= old.total and done >= total:
                return  # told twice that it is finished
            started, done_at_start = self._clock.setdefault(key, (now, done))
            elapsed = now - started
            seconds, left = None, None
            if done >= total and done_at_start >= total:
                logger.info("Prepare step already done", extra={"step": key})  # kept from before
            elif done >= total:
                seconds = round(elapsed, 1)
                logger.info("Prepare step finished", extra={"step": key, "duration_s": seconds})
            elif done > done_at_start:
                left = round(elapsed / (done - done_at_start) * (total - done))
            new = replace(old, done=done, total=total, seconds=seconds, left_s=left)
            steps = [new if s.key == key else s for s in steps]
            self._status = replace(self._status, steps=steps, percent=percent(steps))
            self._save()  # a small file, and a frame takes seconds

    def _run(self) -> None:
        start = time.perf_counter()
        photo_id = self._status.photo_id or ""
        self._clock = {}
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
        try:
            photo = self._store.path("photos", photo_id)
            if photo is None:
                raise PrepareError("The photo to prepare was removed. Choose another one.")
            self._progress("voice", 0, 1)
            self._prepare_voice()
            self._progress("voice", 1, 1)
            self._prepare_face(photo, self._progress)
            self._render_clips(photo)
        except (VoiceError, VideoError, PrepareError) as e:  # these say what to do
            logger.error("Prepare job failed", extra={"error": str(e)})
            self._finish("failed", str(e))
            return
        except Exception as e:
            logger.exception("Prepare job failed")
            self._finish("failed", f"Something went wrong: {e}. The server log has the details.")
            return
        self._finish("done", None)
        logger.info(
            "Prepare job finished",
            extra={"photo_id": photo_id, "duration_s": round(time.perf_counter() - start, 1)},
        )

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

    def _finish(self, state: State, error: str | None) -> None:
        with self._lock:
            steps = self._status.steps or []
            if state == "done":
                # Steps with nothing to do (a library made before) are complete too.
                steps = [replace(s, done=s.total, left_s=None) for s in steps]
            else:
                steps = [replace(s, left_s=None) for s in steps]
            self._status = replace(
                self._status,
                state=state,
                steps=steps,
                percent=100 if state == "done" else percent(steps),
                error=error,
                finished_at=now_iso(),
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
    """The voice step, the engine, the voice the clips are spoken in and its kind ("clone" or
    "kokoro"): the person's own, cloned from the voice sample with the chosen accent, when
    Chatterbox is installed (see the README); otherwise Kokoro's."""
    from imageskin.chatterbox_engine import ChatterboxEngine, check_installed

    try:
        check_installed()
    except VoiceError as e:
        message = "Prepare speaks in a ready-made Kokoro voice, not the person's"
        logger.warning(message, extra={"reason": str(e)})
        kokoro = KokoroEngine()
        return kokoro_voice(kokoro), kokoro, DEFAULT_VOICE, "kokoro"
    logger.info("Prepare speaks in the person's own voice, cloned with Chatterbox Turbo")
    engine = accent_engine(ChatterboxEngine(), speakers)
    return cloned_voice(engine, voice_sample, accent), engine, str(voice_sample), "clone"


def accent_engine(clone: "ChatterboxEngine", speakers: "SpeakerChecker") -> AccentEngine:
    """The clone, with Kokoro, Chatterbox's converter and the app's speaker model (shared with the
    one-speaker check) for other accents. Each is loaded only when another accent is first used."""
    from imageskin.chatterbox_engine import SAMPLE_RATE, TurboConverter
    from imageskin.kokoro_engine import kokoro_for

    return AccentEngine(
        clone,
        kokoro_for,
        lambda: TurboConverter(clone.cloner().tts.s3gen),  # type: ignore[attr-defined]
        lambda samples: speakers.voice_print(samples, SAMPLE_RATE),
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
) -> ClipSteps:
    """Speak the text in the voice; render the speech from the photo's photoreal library."""
    # The video engine and the loaded library, made on first use and kept for the next clip.
    kept: dict[str, Any] = {}

    def speak(text: str, wav: Path) -> None:
        write_speech(voice_engine.speak(voice, text), wav, wav.with_suffix(".json"))

    def render(photo: Path, wav: Path, output: Path) -> None:
        from imageskin.photoreal import PhotorealEngine
        from imageskin.photoreal_library import scaled

        if kept.get("photo") != photo:
            video = PhotorealEngine(home)
            # Already rendered by the face step, so this only loads it.
            lib = video.prepare(photo)
            if max_side is not None:
                lib = scaled(lib, max_side)
            kept.update(photo=photo, video=video, lib=lib)
        kept["video"].render(kept["lib"], wav, output, progressive=progressive)

    return ClipSteps(speak, render)


def photoreal_clip(home: Path, voice_engine: VoiceEngine, voice: str = DEFAULT_VOICE) -> RenderClip:
    """Speak the text in the voice and render it from the photo's photoreal library."""
    return steps_clip(photoreal_steps(home, voice_engine, voice))
