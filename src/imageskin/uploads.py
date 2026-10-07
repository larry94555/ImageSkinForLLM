"""Uploaded photos and sound files, stored safely in the app's home folder (roadmap R6).

The type is read from the file's first bytes, never from its name. Each file is stored under a
generated id: photos as JPG or PNG (HEIC is converted to JPG), sounds as 24 kHz mono WAV via
audio.to_wav. A small JSON file next to each one keeps the name it was uploaded with, for display,
and the problems the photo checks (roadmap R8, R9) or sound checks (roadmap R10) found. The best
photo is used for the video unless the user chose another. The recordings that pass the sound
checks are joined, in the order they were uploaded, into the voice sample.
"""

import contextlib
import importlib.util
import json
import logging
import shutil
import subprocess
import sys
import threading
import time
import uuid
import wave
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal

from imageskin import sound_checks
from imageskin.audio import AudioError, join_wavs, to_wav
from imageskin.sound_checks import MIN_SAMPLE_SPEECH_S, SoundResult

logger = logging.getLogger(__name__)

Kind = Literal["photos", "sounds"]
KINDS: tuple[Kind, ...] = ("photos", "sounds")

MAX_BYTES: dict[Kind, int] = {"photos": 25 * 1024 * 1024, "sounds": 100 * 1024 * 1024}
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_SOUND_SECONDS = 10 * 60
CONVERT_TIMEOUT_S = 60.0
CHUNK = 1024 * 1024

# ISO media files (HEIC photos, M4A sound) start with an "ftyp" box naming a brand.
HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
M4A_BRANDS = {b"M4A ", b"M4B ", b"mp41", b"mp42", b"isom", b"iso2", b"3gp4", b"3gp5"}

SUFFIX = {"jpg": ".jpg", "png": ".png", "heic": ".jpg", "wav": ".wav", "mp3": ".wav", "m4a": ".wav"}
MEDIA_TYPE = {".jpg": "image/jpeg", ".png": "image/png", ".wav": "audio/wav"}
ALLOWED = {"photos": ("jpg", "png", "heic"), "sounds": ("wav", "mp3", "m4a")}
DESCRIPTION = {"photos": "a JPG, PNG or HEIC photo", "sounds": "a WAV, M4A or MP3 recording"}


class UploadError(Exception):
    """An upload was refused; the message is meant for the person who sent it."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Upload:
    id: str
    kind: Kind
    name: str  # the name it was uploaded with, for display only
    format: str  # the format it arrived in: jpg, png, heic, wav, mp3 or m4a
    size: int  # bytes as stored
    uploaded_at: str  # ISO 8601, UTC
    seconds: float | None = None  # sounds only
    # What the photo or sound checks found ([] when it passed), or None when not checked.
    problems: list[str] | None = None
    checks: int | None = None  # the FACE_CHECKS or SOUND_CHECKS version that found `problems`
    score: int | None = None  # photos that passed the checks: 0 to 100, higher is better
    speech: float | None = None  # checked sounds: seconds of speech, pauses not counted


@dataclass(frozen=True)
class PhotoResult:
    """What the photo checks found: the problems, and the score when there are none."""

    problems: list[str]
    score: int | None = None


@dataclass(frozen=True)
class PhotoChoice:
    """The photo the video will be made from: id None when no photo has passed the checks."""

    id: str | None
    chosen_by: Literal["app", "you"] = "app"


@dataclass(frozen=True)
class VoiceSample:
    """The recordings that passed the sound checks, joined into one; problem says what is
    missing while there is not enough speech for the voice."""

    recordings: int
    seconds: float
    speech: float
    problem: str | None


def detect_format(head: bytes) -> str | None:
    """The file's format from its first bytes, or None when it is none of the supported ones."""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[4:8] == b"ftyp":
        if head[8:12] in HEIC_BRANDS:
            return "heic"
        if head[8:12] in M4A_BRANDS:
            return "m4a"
        return None
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "mp3"
    return None


def display_name(name: str | None) -> str:
    """The last part of an uploaded file name, shortened; it is never used as a path."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return "".join(c for c in base if c.isprintable())[:100] or "unnamed"


def heic_supported() -> bool:
    return importlib.util.find_spec("pillow_heif") is not None


def convert_heic(src: Path, dst: Path, timeout_s: float = CONVERT_TIMEOUT_S) -> None:
    """HEIC to JPG in a separate process, so a slow or broken file can be stopped."""
    cmd = [sys.executable, "-m", "imageskin.heic", str(src), str(dst)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        raise UploadError(f"Converting the HEIC photo took over {timeout_s:g} seconds.") from e
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1:] or ["no error output"]
        logger.error("HEIC conversion failed", extra={"src": str(src), "error": detail[0]})
        raise UploadError("The HEIC photo could not be read. Try saving it as JPG.")


PhotoCheck = Callable[[Path], PhotoResult]
SoundCheck = Callable[[Path], SoundResult]
# Raise these when the checks' limits change: uploads checked by an older version are then
# listed as not checked, and the browser checks them again.
FACE_CHECKS = 3
SOUND_CHECKS = 1

NO_VOICE = "No recording has passed the checks yet."
JOIN_FAILED = (
    "The recordings could not be joined into the voice sample. Remove the newest recording and"
    " add it again."
)
SHORT_VOICE = (
    "The recordings that passed the checks have {speech:.0f} seconds of speech. The voice needs"
    f" at least {MIN_SAMPLE_SPEECH_S:.0f}: add another recording."
)


def checks_version(kind: Kind) -> int:
    return FACE_CHECKS if kind == "photos" else SOUND_CHECKS


class UploadStore:
    """Uploads kept in <home>/uploads/photos and <home>/uploads/sounds.

    check_photo and check_sound, when given, return the problems found in a stored upload;
    uploads are checked as they arrive, and check() checks one stored before the checks were
    available. The photo the user chose for the video is kept in <home>/uploads/chosen-photo.json
    and the voice sample in <home>/uploads/voice-sample.wav.
    """

    def __init__(
        self,
        home: Path,
        check_photo: PhotoCheck | None = None,
        check_sound: SoundCheck | None = sound_checks.check,
    ) -> None:
        self.root = home / "uploads"
        self.check_photo = check_photo
        self.check_sound = check_sound
        self._choice_file = self.root / "chosen-photo.json"
        self.voice_sample_file = self.root / "voice-sample.wav"
        # Held while sounds are removed and while the voice sample is joined from them.
        self._sounds_lock = threading.Lock()

    def _dir(self, kind: Kind) -> Path:
        return self.root / kind

    def _total_bytes(self) -> int:
        """Bytes in stored uploads; files still being received or converted don't count."""
        folders = [self._dir(kind) for kind in KINDS if self._dir(kind).is_dir()]
        return sum(p.stat().st_size for folder in folders for p in folder.iterdir() if p.is_file())

    def save(self, kind: Kind, name: str | None, data: BinaryIO) -> Upload:
        """Check, convert and store one upload, or raise UploadError saying why not."""
        start = time.perf_counter()
        shown = display_name(name)
        try:
            upload = self._save(kind, shown, data)
        except UploadError as e:
            logger.warning(
                "Upload refused", extra={"kind": kind, "upload_name": shown, "reason": str(e)}
            )
            raise
        logger.info(
            "Upload stored",
            extra={
                "kind": kind,
                "id": upload.id,
                "upload_name": shown,
                "format": upload.format,
                "size": upload.size,
                "seconds": upload.seconds,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        if kind == "sounds" and upload.problems == []:
            self._update_voice_sample()
        return upload

    def _save(self, kind: Kind, name: str, data: BinaryIO) -> Upload:
        tmp_dir = self.root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        upload_id = uuid.uuid4().hex
        # Every working file for this upload starts with its id, so one glob removes them all.
        received = tmp_dir / f"{upload_id}.upload"
        converted = tmp_dir / f"{upload_id}.converted"
        try:
            size = copy_limited(data, received, MAX_BYTES[kind])
            if size == 0:
                raise UploadError("The file is empty.")
            with received.open("rb") as f:
                fmt = detect_format(f.read(16))
            if fmt not in ALLOWED[kind]:
                raise UploadError(
                    f"This is not {DESCRIPTION[kind]}. The file's contents were checked,"
                    " not its name.",
                    status=415,
                )
            seconds = self._convert(fmt, received, converted)
            # Checked on the converted file: that is what is stored, and a compressed
            # recording grows when it becomes WAV.
            if self._total_bytes() + converted.stat().st_size > MAX_TOTAL_BYTES:
                raise UploadError(
                    f"Uploads are limited to {MAX_TOTAL_BYTES // 2**20} MB in total."
                    " Remove some files first.",
                    status=413,
                )
            final = self._dir(kind) / f"{upload_id}{SUFFIX[fmt]}"
            final.parent.mkdir(parents=True, exist_ok=True)
            converted.replace(final)
            try:
                upload = Upload(
                    id=upload_id,
                    kind=kind,
                    name=name,
                    format=fmt,
                    size=final.stat().st_size,
                    # To the microsecond, so files sent together keep their order.
                    uploaded_at=datetime.now(UTC).isoformat(timespec="microseconds"),
                    seconds=seconds,
                )
                upload = self._with_checks(upload, final)
                self._write_info(final, upload)
            except BaseException:
                # Without its info file the upload could not be listed or removed.
                final.unlink(missing_ok=True)
                final.with_suffix(".json").unlink(missing_ok=True)
                raise
            return upload
        finally:
            for leftover in tmp_dir.glob(f"{upload_id}*"):
                leftover.unlink(missing_ok=True)

    def _convert(self, fmt: str, src: Path, dst: Path) -> float | None:
        """Make the stored file from the received one; return a sound's length in seconds."""
        if fmt in ("jpg", "png"):
            shutil.copyfile(src, dst)
            return None
        if fmt == "heic":
            if not heic_supported():
                raise UploadError(
                    "HEIC photos need the optional HEIC support"
                    ' (pip install -e ".[heic]"). Or save the photo as JPG.',
                    status=415,
                )
            convert_heic(src, dst)
            return None
        # ffmpeg picks the format from the name, so give it a matching one.
        named = src.with_name(f"{src.stem}-in.{fmt}")
        src.replace(named)
        wav_out = dst.with_name(f"{dst.stem}-out.wav")
        try:
            to_wav(named, wav_out, CONVERT_TIMEOUT_S)
            with wave.open(str(wav_out), "rb") as w:
                seconds = w.getnframes() / w.getframerate()
        except AudioError as e:
            logger.error("Sound conversion failed", extra={"src": str(named), "error": str(e)})
            raise UploadError(
                "The recording could not be read. Try exporting it again as WAV or MP3."
            ) from e
        if seconds > MAX_SOUND_SECONDS:
            raise UploadError(
                f"Recordings are limited to {MAX_SOUND_SECONDS // 60} minutes each;"
                f" this one is {seconds / 60:.1f} minutes.",
                status=413,
            )
        wav_out.replace(dst)
        return round(seconds, 2)

    def _check(self, kind: Kind, stored: Path) -> PhotoResult | SoundResult | None:
        """What the checks found, or None when they are off or could not run."""
        check = self.check_photo if kind == "photos" else self.check_sound
        if check is None:
            return None
        try:
            return check(stored)
        except Exception as e:
            # An upload that can't be checked is still kept; it shows as not checked.
            what = "Face" if kind == "photos" else "Sound"
            logger.error(f"{what} checks failed", extra={"upload": stored.name, "error": str(e)})
            return None

    @staticmethod
    def _write_info(stored: Path, upload: Upload) -> None:
        stored.with_suffix(".json").write_text(json.dumps(asdict(upload)), encoding="utf-8")

    def list(self, kind: Kind) -> list[Upload]:
        """Stored uploads of one kind, oldest first. Never runs the checks, so it is quick."""
        folder = self._dir(kind)
        if not folder.is_dir():
            return []
        uploads = [u for p in folder.glob("*.json") if (u := self._read(p)) is not None]
        return sorted(map(self._current, uploads), key=lambda u: u.uploaded_at)

    @staticmethod
    def _current(upload: Upload) -> Upload:
        """Results from older checks count as not checked, so they are redone."""
        if upload.checks == checks_version(upload.kind):
            return upload
        return replace(upload, problems=None, score=None, speech=None)

    def check(self, kind: Kind, upload_id: str) -> Upload | None:
        """Run the checks on a stored upload, such as one uploaded before they were on, and
        save the result. None when there is no such upload."""
        stored = self.path(kind, upload_id)
        upload = self._read(stored.with_suffix(".json")) if stored else None
        if stored is None or upload is None:
            return None
        checked = self._with_checks(upload, stored)
        if checked.problems is None or not stored.exists():  # removed while it was being checked
            return self._current(upload)
        self._write_info(stored, checked)
        if not stored.exists():
            # Removed between the test above and the write: drop the info file written back.
            stored.with_suffix(".json").unlink(missing_ok=True)
        if kind == "sounds":
            self._update_voice_sample()
        return checked

    def _with_checks(self, upload: Upload, stored: Path) -> Upload:
        result = self._check(upload.kind, stored)
        unchecked = replace(upload, problems=None, checks=None, score=None, speech=None)
        if isinstance(result, PhotoResult):
            return replace(
                unchecked, problems=result.problems, checks=FACE_CHECKS, score=result.score
            )
        if isinstance(result, SoundResult):
            return replace(
                unchecked, problems=result.problems, checks=SOUND_CHECKS, speech=result.speech_s
            )
        return unchecked

    def voice_sample(self) -> VoiceSample:
        """What the voice sample is made of, and what it still needs."""
        passed = [s for s in self.list("sounds") if s.problems == []]
        if passed and not self.voice_sample_file.is_file():
            # Joining them failed (see the server log): there is no sample to play.
            return VoiceSample(recordings=0, seconds=0, speech=0, problem=JOIN_FAILED)
        speech = round(sum(s.speech or 0 for s in passed), 2)
        problem = None
        if not passed:
            problem = NO_VOICE
        elif speech < MIN_SAMPLE_SPEECH_S:
            problem = SHORT_VOICE.format(speech=speech)
        seconds = round(sum(s.seconds or 0 for s in passed), 2)
        return VoiceSample(recordings=len(passed), seconds=seconds, speech=speech, problem=problem)

    def _update_voice_sample(self) -> None:
        """Join the recordings that passed the checks into the voice sample, or remove it when
        there are none. A failure is logged; the recordings themselves are kept."""
        start = time.perf_counter()
        with self._sounds_lock:
            passed = [s for s in self.list("sounds") if s.problems == []]
            parts = [p for s in passed if (p := self.path("sounds", s.id))]
            joining = self.voice_sample_file.with_name("voice-sample.joining.wav")
            try:
                if not parts:
                    self.voice_sample_file.unlink(missing_ok=True)
                    seconds = 0.0
                else:
                    seconds = join_wavs(parts, joining)
                    joining.replace(self.voice_sample_file)
            except (AudioError, OSError, wave.Error) as e:
                logger.error("Could not make the voice sample", extra={"error": str(e)})
                joining.unlink(missing_ok=True)
                # The old sample no longer matches the recordings, so it must not be served.
                self.voice_sample_file.unlink(missing_ok=True)
                return
        logger.info(
            "Voice sample updated",
            extra={
                "recordings": len(parts),
                "seconds": round(seconds, 2),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )

    def photo_choice(self) -> PhotoChoice:
        """The photo the user chose, while it is there and passes the checks; otherwise the
        best scoring photo, picked by the app."""
        passed = [p for p in self.list("photos") if p.problems == [] and p.score is not None]
        try:
            chosen = json.loads(self._choice_file.read_text(encoding="utf-8")).get("id")
        except FileNotFoundError:
            chosen = None
        except (OSError, ValueError, AttributeError) as e:
            logger.error("Could not read the chosen photo", extra={"error": str(e)})
            chosen = None
        if any(p.id == chosen for p in passed):
            return PhotoChoice(chosen, "you")
        best = max(passed, key=lambda p: p.score or 0, default=None)
        return PhotoChoice(best.id if best else None)

    def choose_photo(self, upload_id: str) -> PhotoChoice:
        """Use this photo for the video, or raise UploadError saying why not."""
        photo = next((p for p in self.list("photos") if p.id == upload_id), None)
        if photo is None:
            raise UploadError("No such photo.", status=404)
        if photo.problems != []:
            raise UploadError("Only a photo that passed the checks can be used for the video.")
        self.root.mkdir(parents=True, exist_ok=True)
        self._choice_file.write_text(json.dumps({"id": upload_id}), encoding="utf-8")
        logger.info("Photo chosen for the video", extra={"id": upload_id, "score": photo.score})
        return PhotoChoice(upload_id, "you")

    def _read(self, info: Path) -> Upload | None:
        try:
            return Upload(**json.loads(info.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as e:
            logger.error("Could not read upload info", extra={"path": str(info), "error": str(e)})
            return None

    def path(self, kind: Kind, upload_id: str) -> Path | None:
        """The stored file for an id from list(), or None. Ids are 32 hex digits."""
        if len(upload_id) != 32 or any(c not in "0123456789abcdef" for c in upload_id):
            return None
        found = [p for p in self._dir(kind).glob(f"{upload_id}.*") if p.suffix in MEDIA_TYPE]
        return found[0] if found else None

    def remove(self, kind: Kind, upload_id: str) -> bool:
        """Delete an upload; False when there is none with that id."""
        # A sound is not removed while the voice sample is being joined from the sounds.
        lock = self._sounds_lock if kind == "sounds" else contextlib.nullcontext()
        with lock:
            stored = self.path(kind, upload_id)
            if stored is None:
                return False
            stored.unlink()
            stored.with_suffix(".json").unlink(missing_ok=True)
        logger.info("Upload removed", extra={"kind": kind, "id": upload_id})
        if kind == "sounds":
            self._update_voice_sample()
        return True


def copy_limited(src: BinaryIO, dst: Path, limit: int) -> int:
    """Copy src to dst in chunks, stopping with UploadError once it passes limit bytes."""
    size = 0
    with dst.open("wb") as out:
        while chunk := src.read(CHUNK):
            size += len(chunk)
            if size > limit:
                raise UploadError(
                    f"The file is larger than the {limit // 2**20} MB limit.", status=413
                )
            out.write(chunk)
    return size
