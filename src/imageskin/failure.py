"""A failure reported to the customer (roadmap R134): a plain reason sorted from the error,
whether trying again may help, and a short reference to give support. The log keeps the full
error, with its traceback, under the same reference, so `grep P-7K3F9Q` finds it."""

import errno
import logging
import re
import secrets
import subprocess
import urllib.error
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from imageskin import __version__
from imageskin.download import DownloadError

# Letters and digits that can't be read as one another (no 0/O or 1/I).
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# Each reason: what the customer is told, and whether Try again may help as it is.
REASONS: dict[str, tuple[str, bool]] = {
    "missing": ("A program or add-on the app needs is missing.", False),
    "memory": ("The computer ran out of memory. Close other programs first.", True),
    "disk": ("There isn't enough disk space left. Free some space first.", False),
    "download": ("A model couldn't be downloaded. Check the internet connection.", True),
    "unreadable": ("The photo or a recording couldn't be read. Upload it again.", False),
    "timeout": ("A step took too long.", True),
    "unexpected": ("Something unexpected went wrong.", True),
}

# Words in an error's message, for errors whose type doesn't say which reason it is: the
# engines raise VoiceError or VideoError for all of them.
_WORDS = (
    ("memory", ("out of memory", "cannot allocate memory", "not enough memory")),
    ("disk", ("no space left",)),
    ("missing", ("not installed", "no module named", "not found", "not on path")),
    ("unreadable", ("could not read", "unsupported file type", "is silent", "has no audio")),
    ("timeout", ("took longer than", "timed out")),
    ("download", ("download", "hugging face said", "connection")),
)


@dataclass(frozen=True)
class Failure:
    reference: str  # P- and 6 letters and digits
    step: str | None  # the step that failed, as the page names it
    reason: str  # a key of REASONS, or "setup" for a message that already says what to do
    message: str  # in plain words
    retry: bool  # whether Try again may help as it is
    details: str  # the error, without the data folder's paths and file names
    version: str  # the app's

    def summary(self) -> str:
        """One line for a page that shows only text."""
        again = " Click Try again." if self.retry else ""
        return f"{self.message}{again} Reference for support: {self.reference}."


def new_reference() -> str:
    return "P-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def _chain(e: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = e
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _by_type(e: BaseException) -> str | None:
    if isinstance(e, MemoryError):
        return "memory"
    if isinstance(e, OSError) and e.errno == errno.ENOSPC:
        return "disk"
    if isinstance(e, OSError) and e.errno == errno.ENOMEM:
        return "memory"
    if isinstance(e, ImportError | FileNotFoundError):
        return "missing"
    if isinstance(e, DownloadError | urllib.error.URLError | ConnectionError):
        return "download"
    if isinstance(e, TimeoutError | subprocess.TimeoutExpired):
        return "timeout"
    if type(e).__name__ == "UnidentifiedImageError":  # Pillow's, without importing it
        return "unreadable"
    return None


def classify(e: BaseException) -> str:
    """The reason for the error: from its type or its causes' first, then from its words."""
    chain = list(_chain(e))
    for link in chain:
        reason = _by_type(link)
        if reason:
            return reason
    text = " ".join(str(link) for link in chain).lower()
    for reason, words in _WORDS:
        if any(word in text for word in words):
            return reason
    return "unexpected"


def without_paths(text: str, home: Path) -> str:
    """The text with the data folder's paths and file names, and the user's home folder, taken
    out: the customer's page shows it, and they say nothing to the customer."""
    for folder in {str(home), str(home.resolve())}:
        text = re.sub(re.escape(folder) + r"[^\s'\":,)]*", "<data folder>", text)
    return text.replace(str(Path.home()), "~")


def report(
    e: BaseException,
    logger: logging.Logger,
    what: str,
    home: Path,
    step: str | None = None,
    message: str | None = None,  # instead of the reason's, when the error already says what to do
    **extra: Any,
) -> Failure:
    """Log `what` with the reference, the step, the reason and the full error with its
    traceback, and return what the customer is shown."""
    if message is None:
        reason = classify(e)
        message, retry = REASONS[reason]
    else:
        reason, retry = "setup", False
    detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
    failure = Failure(
        new_reference(), step, reason, message, retry, without_paths(detail, home), __version__
    )
    logger.error(
        what,
        exc_info=e,
        extra={
            "reference": failure.reference,
            "step": step,
            "reason": reason,
            "error": str(e),
            **extra,
        },
    )
    return failure
