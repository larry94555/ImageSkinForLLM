"""Start now with a default person (roadmap R24c, features.md items 56 to 58).

The user picks an accent, photoreal or animated, and one of that look's faces (R24c2), and
chats at once with that made-up person: no consent, uploads, prepare or
review. Only the chosen person's pack is downloaded, the first time they are chosen, from the
hosted site that holds the 60 packs (R32a); it is unpacked into the app's home and kept, so
choosing them again starts at once. Goodbye and Welcome back are then rendered in the person's
ready-made Kokoro voice.

The page offers no role (Larry's test of PR #124) and no gender (Larry, 2026-10-21), but a
person is still named by the gender and role they were made for and their face number, which the
choice carries; the gender picks the voice. The choice is saved as
default-person.json in the home. While it is there, the chat uses the default person's picture
and voice instead of the person's own (see `PresetVoice`). With `own_voice` set in it (R24d), the
avatar is to speak in the user's own recorded voice instead, once its sample in that voice is
accepted; choosing an avatar again starts it in its ready-made voice.
"""

import json
import logging
import os
import shutil
import threading
import time
import urllib.error
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from imageskin.default_people import (
    GENDERS,
    REALISMS,
    ROLES,
    PackError,
    check_pack,
    people,
    unpack,
    voice_of,
)
from imageskin.download import DownloadError, download, sha256_of
from imageskin.failure import report
from imageskin.photoreal_library import library_key
from imageskin.ready_voice import save_ready_voice
from imageskin.sample import OPENER
from imageskin.voice import Speech, VoiceEngine

logger = logging.getLogger(__name__)

# Where the packs are kept: on the hosted site, which serves them without its password (R32a,
# deploy/Caddyfile).
HOSTED_URL = "https://app.me0.ai/default-people"
# Set to download the packs from somewhere else: the hosted app sets it to Caddy's own address
# inside Docker (deploy/compose.yaml), and a local folder served with `python -m http.server`
# tries Start now before the packs are uploaded.
URL_VARIABLE = "IMAGESKIN_DEFAULT_PEOPLE_URL"
# Each pack's size and SHA-256, so a download is checked before it is unpacked.
PACKS_FILE = Path(__file__).with_name("default_people_packs.json")
CHOICE_FILE = "default-person.json"
# Written first, then moved over CHOICE_FILE, so a save cut short never leaves a broken choice.
CHOICE_SAVING_FILE = "default-person.saving.json"
FOLDER = "default-people"
ACCENTS = ("American", "British")
# The fixed lines said on exit and on return (roadmap R29) and as a reply starts (R161), as
# Prepare renders them.
LINES = (("goodbye", "Goodbye."), ("welcome-back", "Welcome back."), ("opener", OPENER))

State = Literal["idle", "downloading", "unpacking", "getting-ready", "ready", "failed"]
# While a person is being got ready, on the background thread.
BUSY = ("downloading", "unpacking", "getting-ready")
Fetch = Callable[..., None]  # download()'s signature
Unpack = Callable[[Path, Path], Path]  # pack, home: the picture
RenderClip = Callable[[Path, str, Path], None]  # picture, what to say, MP4 to write

DOWNLOAD_FAILED = (
    "The person couldn't be downloaded. Check the internet connection and click Try again."
)
DAMAGED = "The person's download was damaged. Click Try again."
# The site doesn't have the person's pack: retrying won't help until it is uploaded.
NOT_PUBLISHED = (
    "This person isn't available to download yet. Pick another, or use your own photos and voice."
)
NOT_READY = "The person couldn't be got ready."


@dataclass(frozen=True)
class Choice:
    gender: str
    accent: str
    realism: str
    role: str
    face: int = 1  # R24c2: 2 picks the choice's second face, where it has one

    def problem(self) -> str | None:
        """What is wrong with the choice, or None."""
        for value, allowed in (
            (self.gender, GENDERS),
            (self.accent, ACCENTS),
            (self.realism, REALISMS),
            (self.role, ROLES),
        ):
            if value not in allowed:
                return f"{value!r} is not one of {', '.join(allowed)}."
        if self.face not in faces(self.gender, self.realism, self.role):
            return f"There is no face {self.face} for that choice."
        return None

    @property
    def name(self) -> str:
        """The person's name, such as animated_female_professor, with _2 for a second face."""
        return faces(self.gender, self.realism, self.role)[self.face]

    @property
    def voice(self) -> tuple[str, str]:
        """Kokoro's language code and the person's own voice for the accent (R24e)."""
        return voice_of(self.name, self.accent)


@dataclass(frozen=True)
class StartStatus:
    state: State
    person: str | None = None
    percent: int = 0  # of the download
    error: str | None = None  # in plain words, for the user


def faces(gender: str, realism: str, role: str) -> dict[int, str]:
    """The faces a choice has (R24c2), by number: each person's name."""
    return {
        p.face: p.name for p in people() if (p.gender, p.realism, p.role) == (gender, realism, role)
    }


def packs_url() -> str:
    """Where the packs are downloaded from."""
    return os.environ.get(URL_VARIABLE) or HOSTED_URL


def load_packs(path: Path = PACKS_FILE) -> dict[str, dict[str, Any]]:
    packs: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return packs


class StartNow:
    """One default person at a time, got ready on a background thread."""

    def __init__(
        self,
        home: Path,
        render_clip: RenderClip,
        packs: dict[str, dict[str, Any]] | None = None,
        base_url: str | None = None,  # packs_url()
        fetch: Fetch = download,
        unpack_pack: Unpack = unpack,
        on_ready: Callable[[], None] = lambda: None,  # the chat opens: warm up the replies
        # Taken before a person is got ready and given back once nothing more is written: the
        # prepare job's, so no Prepare or Delete my data runs meanwhile (review on PR #113).
        # `claim` raises to refuse.
        claim: Callable[[], None] = lambda: None,
        release: Callable[[], None] = lambda: None,
        # Makes the chosen person the one the chat uses: with the reply engines paused, so a
        # reply being rendered doesn't change voice or face partway (review on PR #113).
        activate: Callable[[Callable[[], None]], None] = lambda choose: choose(),
    ) -> None:
        self._home = home
        self._folder = home / FOLDER
        self._render_clip = render_clip
        self._packs = load_packs() if packs is None else packs
        self._base_url = (base_url or packs_url()).rstrip("/")
        self._fetch = fetch
        self._unpack = unpack_pack
        self._on_ready = on_ready
        self._claim = claim
        self._release = release
        self._activate = activate
        # The voice the lines are spoken in while they are rendered, for `rendering_voice`.
        self._rendering: tuple[str, str] | None = None
        self._lock = threading.Lock()
        self._status = StartStatus("idle")
        self._thread: threading.Thread | None = None

    # The choice

    def chosen(self) -> Choice | None:
        """The default person chosen now, or None when the person is the user's own."""
        path = self._home / CHOICE_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            choice = Choice(
                data["gender"], data["accent"], data["realism"], data["role"], data.get("face", 1)
            )
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.error("Could not read the default person", extra={"error": str(e)})
            return None
        return None if choice.problem() else choice

    def own_voice(self) -> bool:
        """Whether the chosen avatar is to speak in the user's own recorded voice (R24d)."""
        try:
            data = json.loads((self._home / CHOICE_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False  # none chosen; chosen() logs a file that can't be read
        return isinstance(data, dict) and data.get("own_voice") is True and bool(self.chosen())

    def set_own_voice(self, on: bool) -> None:
        """Make the chosen avatar speak in the user's own voice (R24d), or in its ready-made
        one again. ValueError when no avatar is chosen."""
        choice = self.chosen()
        if choice is None:
            raise ValueError("No ready-made avatar is chosen.")
        # With the replies paused: once its sample is accepted, the voice changes at once.
        self._activate(lambda: self._write(choice, own_voice=on))
        logger.info("Avatar's voice chosen", extra={"person": choice.name, "own_voice": on})

    def picture(self) -> Path | None:
        """The chosen default person's picture, the photo the videos are made from."""
        choice = self.chosen()
        if choice is None:
            return None
        path = self._picture(choice.name)
        return path if path.is_file() else None

    def voice(self) -> tuple[str, str] | None:
        """Kokoro's language code and voice while a default person is chosen."""
        choice = self.chosen()
        return None if choice is None else choice.voice

    def rendering_voice(self) -> tuple[str, str] | None:
        """Kokoro's language code and voice while the chosen person's lines are rendered, with
        the prepare job's engines; otherwise None, so Prepare speaks in the person's own voice
        even while a default person is chosen."""
        return self._rendering

    def clip(self, name: str) -> Path | None:
        """Goodbye or Welcome back, said by the chosen default person, once rendered."""
        choice = self.chosen()
        if choice is None:
            return None
        path = self._lines(choice) / f"{name}.mp4"
        return path if path.is_file() else None

    def forget(self) -> None:
        """The person is the user's own again: their sample was accepted. The downloaded people
        are kept, so choosing one again starts at once."""
        try:
            (self._home / CHOICE_FILE).unlink()
            logger.info("Default person no longer chosen")
        except FileNotFoundError:
            pass

    def forget_unless_busy(self) -> bool:
        """Forget the chosen person, as the user's own photo and voice are wanted again, unless
        a person is being got ready now: it would be chosen once ready, undoing this (review
        on PR #129). Whether it was forgotten. Under the lock `start` chooses with, so a person
        ready at once is either chosen before this or after it, never in between."""
        with self._lock:
            if self._status.state in BUSY:
                logger.warning(
                    "Own photo and voice asked for while a person is got ready",
                    extra={"person": self._status.person, "state": self._status.state},
                )
                return False
            self._activate(self.forget)
            return True

    def _picture(self, name: str) -> Path:
        return self._folder / f"{name}.png"

    def _lines(self, choice: Choice) -> Path:
        """Where the person's lines are, named for the voice too, so a person whose voice has
        changed (R24e) has them rendered again in the new one."""
        voice = choice.voice[1].replace(",", "+")
        return self._folder / "lines" / f"{choice.name}_{choice.accent.lower()}_{voice}"

    def _save(self, choice: Choice) -> None:
        self._write(choice)  # in its ready-made voice, even if chosen before in the user's own
        logger.info("Default voice chosen", extra={"person": choice.name, "voice": choice.voice[1]})
        # The user's own photo speaks in it until they add recordings (item 59).
        save_ready_voice(self._home, choice.voice[1])

    def _write(self, choice: Choice, own_voice: bool = False) -> None:
        self._home.mkdir(parents=True, exist_ok=True)
        path = self._home / CHOICE_FILE
        tmp = self._home / CHOICE_SAVING_FILE
        data = {
            **asdict(choice),
            "chosen_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "own_voice": own_voice,
        }
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)

    # Getting the person ready

    def status(self) -> StartStatus:
        with self._lock:
            return self._status

    def start(self, choice: Choice) -> StartStatus:
        """Get the chosen person ready, unless a person is being got ready now: then report on
        that one. A person downloaded before, with their lines rendered, is ready at once."""
        with self._lock:
            if self._status.state in BUSY:
                return self._status
            logger.info(
                "Start now with a default person", extra={"person": choice.name, **asdict(choice)}
            )
            if self._ready(choice):
                self._activate(lambda: self._save(choice))
                self._status = StartStatus("ready", choice.name, 100)
                logger.info("Default person already downloaded", extra={"person": choice.name})
                self._on_ready()
                return self._status
            self._claim()  # refused while Prepare runs or the sample is made again
            self._status = StartStatus("downloading", choice.name)
            self._thread = threading.Thread(
                target=self._run, args=(choice,), name="start-now", daemon=True
            )
            self._thread.start()
            return self._status

    def refresh(self) -> bool:
        """At start-up: the chosen person, unpacked before, whose lines aren't there in their
        voice, since it changed (R24e), gets them rendered again on the background thread. Only
        the lines: the choice, and whether the avatar speaks in the user's own voice (R24d), stay
        as they were (Codex's review of PR #142). A person whose pack has changed since it was
        unpacked (R24b4 remade four people under the same names) is downloaded and unpacked
        again first, keeping the choice in the same way. Whether that started. Raises as
        `start` does while Prepare runs."""
        with self._lock:
            choice = self.chosen()
            if choice is None or self._status.state in BUSY:
                return False
            if self._changed(choice.name):
                logger.info(
                    "Default person's pack changed: downloaded again", extra={"person": choice.name}
                )
                self._claim()  # refused while Prepare runs
                self._status = StartStatus("downloading", choice.name)
                self._thread = threading.Thread(
                    target=self._run, args=(choice, False), name="start-now", daemon=True
                )
                self._thread.start()
                return True
            if not self._unpacked(choice.name) or self._ready(choice):
                return False
            logger.info(
                "Default person's lines rendered again in their voice",
                extra={"person": choice.name, "voice": choice.voice[1]},
            )
            self._claim()  # refused while Prepare runs
            self._status = StartStatus("getting-ready", choice.name, 100)
            self._thread = threading.Thread(
                target=self._run_refresh, args=(choice,), name="start-now-lines", daemon=True
            )
            self._thread.start()
            return True

    def _run_refresh(self, choice: Choice) -> None:
        start = time.perf_counter()
        try:
            self._render_lines(choice)
        except Exception as e:
            what = "Could not render the lines again"
            failure = report(e, logger, what, self._home, person=choice.name)
            self._set("failed", error=f"{NOT_READY} {failure.summary()}")
            return
        finally:
            self._release()
        self._set("ready", 100)
        logger.info(
            "Default person's lines ready in their voice",
            extra={"person": choice.name, "duration_s": round(time.perf_counter() - start, 1)},
        )

    def wait(self, timeout: float | None = None) -> None:
        """For tests: wait for the background thread to finish."""
        if self._thread is not None:
            self._thread.join(timeout)

    def _ready(self, choice: Choice) -> bool:
        return self._unpacked(choice.name) and all(
            (self._lines(choice) / f"{n}.mp4").is_file() for n, _ in LINES
        )

    def _unpacked(self, name: str) -> bool:
        """The picture and its prepared library are there, from the pack the app names now.
        Delete my data removes the library with the person's own (it is under photoreal/), so
        it is unpacked again from the kept pack (review on PR #113)."""
        picture = self._picture(name)
        if not picture.is_file() or not self._current(name):
            return False
        return (self._home / "photoreal" / library_key(picture) / "library.json").is_file()

    def _changed(self, name: str) -> bool:
        """The person was unpacked from a pack the app no longer names (Codex's review of
        PR #165): their picture and lines are of the face they had before."""
        return self._picture(name).is_file() and not self._current(name)

    def _unpacked_from(self, name: str) -> Path:
        return self._folder / f"{name}.pack"

    def _current(self, name: str) -> bool:
        """Whether the person was unpacked from the pack the app names now."""
        info = self._packs.get(name)
        if info is None:
            return True  # no pack to compare with; choosing them says so
        try:
            return self._unpacked_from(name).read_text(encoding="utf-8") == str(info["sha256"])
        except FileNotFoundError:
            pass
        # Unpacked before the pack's SHA-256 was kept with it: the kept pack tells.
        if self._kept(name) is None:
            return False
        self._unpacked_from(name).write_text(info["sha256"], encoding="utf-8")
        return True

    def _forget_lines(self, name: str) -> None:
        """The person's lines in every accent and voice, said by the face they had before."""
        for folder in (self._folder / "lines").glob(f"{name}_*"):
            if not folder.name[len(name) + 1 :][:1].isdigit():  # not their second face's
                shutil.rmtree(folder)

    def _pack(self, name: str) -> Path:
        return self._folder / "downloads" / f"{name}.zip"

    def _kept(self, name: str) -> Path | None:
        """The person's pack, downloaded before and complete, or None."""
        info = self._packs.get(name)
        pack = self._pack(name)
        if info is None or not pack.is_file() or pack.stat().st_size != int(info["bytes"]):
            return None
        return pack if sha256_of(pack) == info["sha256"] else None

    def _set(self, state: State, percent: int = 0, error: str | None = None) -> None:
        with self._lock:
            self._status = StartStatus(state, self._status.person, percent, error)

    def _run(self, choice: Choice, save: bool = True) -> None:
        start = time.perf_counter()
        try:
            error = self._work(choice, save)
        finally:
            self._release()  # nothing more is written: Prepare and Delete my data may run now
        if error is not None:
            self._set("failed", error=error)
            return
        # The warm-up starts first, so whoever sees "ready" can also see it running and wait
        # for the new person's idle video before opening the chat (Larry's test of R32a).
        self._on_ready()
        self._set("ready", 100)
        logger.info(
            "Default person ready",
            extra={"person": choice.name, "duration_s": round(time.perf_counter() - start, 1)},
        )

    def _work(self, choice: Choice, save: bool = True) -> str | None:
        """Download, unpack and render the lines; what went wrong, in plain words, or None.
        Without save, the choice and its voice stay as they were (refresh)."""
        name = choice.name
        try:
            if not self._unpacked(name):
                changed = self._changed(name)
                # The pack is kept: unpacked again after Delete my data, it needs no download.
                pack = self._kept(name) or self._download(name)
                self._set("unpacking", 100)
                self._unpack(pack, self._home)
                self._unpacked_from(name).write_text(self._packs[name]["sha256"], encoding="utf-8")
                if changed:
                    self._forget_lines(name)
                    logger.info("Default person's pack changed", extra={"person": name})
            self._set("getting-ready", 100)
            self._render_lines(choice)
            if save:
                # Chosen only once everything is ready: until then the chat stays locked, and a
                # failure leaves the person chosen before (review on PR #113).
                self._activate(lambda: self._save(choice))
        except DownloadError as e:
            logger.error(
                "Could not download the default person", extra={"person": name, "error": str(e)}
            )
            missing = isinstance(e.__cause__, urllib.error.HTTPError) and e.__cause__.code == 404
            return NOT_PUBLISHED if missing else DOWNLOAD_FAILED
        except PackError as e:
            logger.error(
                "Default person's pack is not usable", extra={"person": name, "error": str(e)}
            )
            return DAMAGED
        except Exception as e:
            # A reason and a reference for support, the full error in the log (roadmap R134).
            what = "Could not get the default person ready"
            failure = report(e, logger, what, self._home, person=name)
            return f"{NOT_READY} {failure.summary()}"
        return None

    def _download(self, name: str) -> Path:
        info = self._packs.get(name)
        if info is None:
            raise PackError(f"{name} has no pack")
        pack = self._pack(name)
        size = int(info["bytes"])

        def progress(done: int, total: int) -> None:
            self._set("downloading", min(99, 100 * done // max(total, 1)))

        start = time.perf_counter()
        # Few tries, each given up on quickly: the user is waiting, and Try again resumes.
        url = f"{self._base_url}/{name}.zip"
        logger.info("Downloading default person", extra={"person": name, "url": url})
        self._fetch(
            url,
            pack,
            size,
            info["sha256"],
            timeout=15.0,
            retries=1,
            progress=progress,
        )
        check_pack(pack, name)
        logger.info(
            "Downloaded default person",
            extra={
                "person": name,
                "bytes": size,
                "duration_s": round(time.perf_counter() - start, 1),
            },
        )
        return pack

    def _render_lines(self, choice: Choice) -> None:
        folder = self._lines(choice)
        folder.mkdir(parents=True, exist_ok=True)
        self._rendering = choice.voice
        try:
            self._render_each(choice, folder)
        finally:
            self._rendering = None

    def _render_each(self, choice: Choice, folder: Path) -> None:
        for clip, text in LINES:
            path = folder / f"{clip}.mp4"
            if path.is_file():
                continue
            start = time.perf_counter()
            rendering = path.with_name(f"{clip}.rendering.mp4")
            self._render_clip(self._picture(choice.name), text, rendering)
            os.replace(rendering, path)
            logger.info(
                "Rendered default person's line",
                extra={
                    "person": choice.name,
                    "clip": clip,
                    "duration_s": round(time.perf_counter() - start, 1),
                },
            )


class KokoroVoices:
    """Kokoro's engines by language code, each loaded once and shared by the voices below. One
    speaks at a time: a reply and a default person's line can be spoken together."""

    def __init__(self, kokoro: Callable[[str], VoiceEngine] | None = None) -> None:
        self._kokoro = kokoro
        self._engines: dict[str, VoiceEngine] = {}
        self._lock = threading.Lock()  # guards _engines
        self._speaking = threading.Lock()

    def speak(self, lang: str, voice: str, text: str) -> Speech:
        with self._lock:
            engine = self._engines.get(lang)
            if engine is None:
                if self._kokoro is None:
                    from imageskin.kokoro_engine import kokoro_for

                    self._kokoro = kokoro_for
                engine = self._engines[lang] = self._kokoro(lang)
        with self._speaking:
            return engine.speak(voice, text)


class PresetVoice:
    """A voice engine that speaks in a default person's ready-made Kokoro voice (item 58) while
    `preset` gives one, otherwise with the engine set up for the person's own voice, in the
    voice it was asked for. The replies' follows the chosen person; Prepare's speaks the
    default person only while their lines are rendered."""

    def __init__(
        self,
        own: VoiceEngine,
        preset: Callable[[], tuple[str, str] | None],
        kokoro: "KokoroVoices | Callable[[str], VoiceEngine] | None" = None,
    ) -> None:
        self._own = own
        self._preset = preset
        self._kokoro = kokoro if isinstance(kokoro, KokoroVoices) else KokoroVoices(kokoro)

    def speak(self, voice: str, text: str) -> Speech:
        preset = self._preset()
        if preset is None:
            return self._own.speak(voice, text)
        lang, name = preset
        return self._kokoro.speak(lang, name, text)

    def __getattr__(self, name: str) -> Any:
        # Anything else (such as forget_voice) is the own engine's.
        return getattr(self._own, name)
