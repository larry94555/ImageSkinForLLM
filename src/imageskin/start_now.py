"""Start now with a default person (roadmap R24c, features.md items 56 to 58).

The user picks a gender, an accent, photoreal or animated, and a role, and chats at once with that
made-up person: no consent, uploads, prepare or review. Only the chosen person's pack is
downloaded, the first time they are chosen, from the GitHub release that holds the 60 packs; it
is unpacked into the app's home and kept, so choosing them again starts at once. Goodbye and
Welcome back are then rendered in the person's ready-made Kokoro voice.

The choice is saved as default-person.json in the home. While it is there, the chat uses the
default person's picture and voice instead of the person's own (see `PresetVoice`).
"""

import json
import logging
import os
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
    VOICES,
    PackError,
    check_pack,
    people,
    unpack,
)
from imageskin.download import DownloadError, download
from imageskin.voice import Speech, VoiceEngine

logger = logging.getLogger(__name__)

# Where the packs are kept: assets of a GitHub release of this repository (picked in R24b).
RELEASE_URL = "https://github.com/larry94555/ImageSkinForLLM/releases/download/default-people-v1"
# Set to download the packs from somewhere else, such as a local folder served with
# `python -m http.server`, to try Start now before the packs are uploaded.
URL_VARIABLE = "IMAGESKIN_DEFAULT_PEOPLE_URL"
# Each pack's size and SHA-256, so a download is checked before it is unpacked.
PACKS_FILE = Path(__file__).with_name("default_people_packs.json")
CHOICE_FILE = "default-person.json"
FOLDER = "default-people"
ACCENTS = ("American", "British")
# The fixed lines said on exit and on return (roadmap R29), as Prepare renders them.
LINES = (("goodbye", "Goodbye."), ("welcome-back", "Welcome back."))

State = Literal["idle", "downloading", "unpacking", "getting-ready", "ready", "failed"]
Fetch = Callable[..., None]  # download()'s signature
Unpack = Callable[[Path, Path], Path]  # pack, home: the picture
RenderClip = Callable[[Path, str, Path], None]  # picture, what to say, MP4 to write

DOWNLOAD_FAILED = (
    "The person couldn't be downloaded. Check the internet connection and click Try again."
)
DAMAGED = "The person's download was damaged. Click Try again."
# The release doesn't have the person's pack: retrying won't help until it is uploaded.
NOT_PUBLISHED = (
    "This person isn't available to download yet. Pick another, or use your own photos and voice."
)
NOT_READY = "Something went wrong getting the person ready. Click Try again."


@dataclass(frozen=True)
class Choice:
    gender: str
    accent: str
    realism: str
    role: str

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
        return None

    @property
    def name(self) -> str:
        """The person's name, such as animated_female_professor (the first face; R24c2 adds
        picking the second)."""
        return next(
            p.name
            for p in people()
            if p.face == 1
            and (p.gender, p.realism, p.role) == (self.gender, self.realism, self.role)
        )

    @property
    def voice(self) -> tuple[str, str]:
        """Kokoro's language code and voice for the gender and accent."""
        return VOICES[(self.gender, self.accent)]


@dataclass(frozen=True)
class StartStatus:
    state: State
    person: str | None = None
    percent: int = 0  # of the download
    error: str | None = None  # in plain words, for the user


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
        base_url: str | None = None,  # RELEASE_URL
        fetch: Fetch = download,
        unpack_pack: Unpack = unpack,
        on_ready: Callable[[], None] = lambda: None,  # the chat opens: warm up the replies
    ) -> None:
        self._home = home
        self._folder = home / FOLDER
        self._render_clip = render_clip
        self._packs = load_packs() if packs is None else packs
        self._base_url = (base_url or os.environ.get(URL_VARIABLE) or RELEASE_URL).rstrip("/")
        self._fetch = fetch
        self._unpack = unpack_pack
        self._on_ready = on_ready
        self._lock = threading.Lock()
        self._status = StartStatus("idle")
        self._thread: threading.Thread | None = None

    # The choice

    def chosen(self) -> Choice | None:
        """The default person chosen now, or None when the person is the user's own."""
        path = self._home / CHOICE_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            choice = Choice(data["gender"], data["accent"], data["realism"], data["role"])
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.error("Could not read the default person", extra={"error": str(e)})
            return None
        return None if choice.problem() else choice

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

    def _picture(self, name: str) -> Path:
        return self._folder / f"{name}.png"

    def _lines(self, choice: Choice) -> Path:
        return self._folder / "lines" / f"{choice.name}_{choice.accent.lower()}"

    def _save(self, choice: Choice) -> None:
        self._home.mkdir(parents=True, exist_ok=True)
        path = self._home / CHOICE_FILE
        tmp = path.with_name(CHOICE_FILE + ".saving")
        data = {**asdict(choice), "chosen_at": datetime.now(UTC).isoformat(timespec="seconds")}
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
            if self._status.state in ("downloading", "unpacking", "getting-ready"):
                return self._status
            logger.info(
                "Start now with a default person", extra={"person": choice.name, **asdict(choice)}
            )
            if self._ready(choice):
                self._save(choice)
                self._status = StartStatus("ready", choice.name, 100)
                logger.info("Default person already downloaded", extra={"person": choice.name})
                self._on_ready()
                return self._status
            self._status = StartStatus("downloading", choice.name)
            self._thread = threading.Thread(
                target=self._run, args=(choice,), name="start-now", daemon=True
            )
            self._thread.start()
            return self._status

    def wait(self, timeout: float | None = None) -> None:
        """For tests: wait for the background thread to finish."""
        if self._thread is not None:
            self._thread.join(timeout)

    def _ready(self, choice: Choice) -> bool:
        return self._picture(choice.name).is_file() and all(
            (self._lines(choice) / f"{n}.mp4").is_file() for n, _ in LINES
        )

    def _set(self, state: State, percent: int = 0, error: str | None = None) -> None:
        with self._lock:
            self._status = StartStatus(state, self._status.person, percent, error)

    def _run(self, choice: Choice) -> None:
        start = time.perf_counter()
        name = choice.name
        try:
            if not self._picture(name).is_file():
                pack = self._download(name)
                self._set("unpacking", 100)
                self._unpack(pack, self._home)
                pack.unlink(missing_ok=True)  # unpacked, it is no longer needed
            self._save(choice)
            self._set("getting-ready", 100)
            self._render_lines(choice)
        except DownloadError as e:
            logger.error(
                "Could not download the default person", extra={"person": name, "error": str(e)}
            )
            missing = isinstance(e.__cause__, urllib.error.HTTPError) and e.__cause__.code == 404
            self._set("failed", error=NOT_PUBLISHED if missing else DOWNLOAD_FAILED)
            return
        except PackError as e:
            logger.error(
                "Default person's pack is not usable", extra={"person": name, "error": str(e)}
            )
            self._set("failed", error=DAMAGED)
            return
        except Exception:
            logger.exception("Could not get the default person ready", extra={"person": name})
            self._set("failed", error=NOT_READY)
            return
        self._set("ready", 100)
        self._on_ready()
        logger.info(
            "Default person ready",
            extra={"person": name, "duration_s": round(time.perf_counter() - start, 1)},
        )

    def _download(self, name: str) -> Path:
        info = self._packs.get(name)
        if info is None:
            raise PackError(f"{name} has no pack")
        pack = self._folder / "downloads" / f"{name}.zip"
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


class PresetVoice:
    """The voice engine the clips and replies speak with: the chosen default person's
    ready-made Kokoro voice while there is one (item 58), otherwise the engine set up for the
    person's own voice, with the voice it was asked for."""

    def __init__(
        self,
        own: VoiceEngine,
        preset: Callable[[], tuple[str, str] | None],
        kokoro: Callable[[str], VoiceEngine] | None = None,
    ) -> None:
        self._own = own
        self._preset = preset
        self._kokoro = kokoro
        self._engines: dict[str, VoiceEngine] = {}  # by language code, each loaded once
        self._lock = threading.Lock()

    def speak(self, voice: str, text: str) -> Speech:
        preset = self._preset()
        if preset is None:
            return self._own.speak(voice, text)
        lang, name = preset
        with self._lock:
            engine = self._engines.get(lang)
            if engine is None:
                if self._kokoro is None:
                    from imageskin.kokoro_engine import kokoro_for

                    self._kokoro = kokoro_for
                engine = self._engines[lang] = self._kokoro(lang)
        return engine.speak(name, text)

    def __getattr__(self, name: str) -> Any:
        # Anything else (such as forget_voice) is the own engine's.
        return getattr(self._own, name)
