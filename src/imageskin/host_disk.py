"""The disk space a host has used (roadmap R192, item 152; R65b).

A host's disk space is the whole of their site's folder (R61), every file counted once, in one of
six lines: images and voice recordings, PDFs, guidelines, conversations and history, preferences,
and other, so the total always matches the folder (R65b, in place of Larry's choice of 2026-10-30
that only the uploaded files count). At the main address, whose folder is also the service's
home, what serves every site counts for no host.

Each photo, recording and PDF stored is still recorded with the host signed in when it was added,
in `owners.json`, so R61e and R61f could move each host's files to their own site.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

FILENAME = "owners.json"
Kind = Literal["photos", "sounds", "pdfs"]


class OwnersUnreadable(Exception):
    """owners.json is there but can't be read, or isn't a record of who added what."""


# Said when a photo, recording or PDF can't be added, as it couldn't be recorded with its host.
NOT_RECORDED = "The file could not be added just now. Please tell whoever runs this site."


class Owners:
    """Who added each photo, recording and PDF, kept in owners.json."""

    def __init__(self, home: Path) -> None:
        self.path = home / FILENAME
        self._lock = threading.Lock()

    def read(self) -> dict[str, dict[str, str]]:
        """The record, or OwnersUnreadable when the file is there but not readable as one; it
        is then left as it is, never written over (Codex's review of PR #236)."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.error("Could not read who added each file", extra={"error": str(e)})
            raise OwnersUnreadable(str(e)) from e
        if not (
            isinstance(data, dict)
            and all(
                isinstance(items, dict)
                and all(isinstance(k, str) and isinstance(v, str) for k, v in items.items())
                for items in data.values()
            )
        ):
            logger.error("Could not read who added each file", extra={"error": "not a record"})
            raise OwnersUnreadable("not a record of who added each file")
        return data

    def check(self) -> None:
        """Raise OwnersUnreadable when a file added now couldn't be recorded, so it is refused
        rather than stored with no host."""
        with self._lock:
            self.read()

    def record(self, kind: Kind, item: str, email: str) -> None:
        with self._lock:
            data = self.read()
            data.setdefault(kind, {})[item] = email
            writing = self.path.with_suffix(".writing")
            writing.write_text(json.dumps(data, indent=1), encoding="utf-8")
            writing.replace(self.path)
        logger.info("File owner recorded", extra={"kind": kind, "id": item, "email": email})

    def rename(self, email: str, new_email: str) -> int:
        """Give the host's files their new email (R62c): how many."""
        with self._lock:
            data = self.read()
            moved = sum(v == email for items in data.values() for v in items.values())
            if not moved:
                return 0
            data = {
                kind: {k: new_email if v == email else v for k, v in items.items()}
                for kind, items in data.items()
            }
            writing = self.path.with_suffix(".writing")
            writing.write_text(json.dumps(data, indent=1), encoding="utf-8")
            writing.replace(self.path)
        logger.info("File owners renamed", extra={"email": new_email, "files": moved})
        return moved


# Each line of the Resources page, by the first part of a path in the site's folder; anything
# else is "other" (R65b).
LINES: dict[str, str] = {
    # The photos and recordings, with what is made from them: the voice sample and converted
    # copies (uploads), the prepared faces, the sample video, Goodbye and Welcome back, and the
    # reply and idle videos.
    "uploads": "images_and_recordings",
    "photoreal": "images_and_recordings",
    "clips": "images_and_recordings",
    "replies": "images_and_recordings",
    # The PDFs, what was read from them, the wiki and the lessons written ahead.
    "content": "pdfs",
    # Customization's identity, goals and guidelines, with their saved versions and draft.
    "customization.json": "guidelines",
    "customization.history.json": "guidelines",
    "customization.generated": "guidelines",
    # The site's own conversation and each visitor's (R65a).
    "conversation.json": "conversations",
    "conversation.saving.json": "conversations",
    "conversations": "conversations",
    # The site's settings, its LLM choice and its ChatGPT sign-in.
    "ui-settings.json": "preferences",
    "llm.json": "preferences",
    "chatgpt.json": "preferences",
}
AMOUNTS = ("images_and_recordings", "pdfs", "guidelines", "conversations", "preferences", "other")
# At the main address, whose folder is the service's home: what serves every site, counted for no
# host (R61). Every other site's folder holds only its own.
SERVICE = frozenset(
    {
        "sites",
        "hosts",  # each host's PDFs, kept once for all their sites, counted as theirs (R258)
        "sites.json",
        "hosts.json",
        "admin.toml",
        "admin-laptops.toml",
        "admin-settings.json",
        "admin-guidelines.json",
        "admin-guidelines.history.json",
        "network-month.json",
        "outbox",
        "models",
        "default-people",
        "default-person-times.json",
        "config.toml",
        "speed",
    }
)


def line_of(relative: Path) -> str:
    first = relative.parts[0]
    if first.startswith("customization."):  # a saved or written-aside copy of it
        return "guidelines"
    return LINES.get(first, "other")


def count(folder: Path, email: str, leave_out: frozenset[str] = frozenset()) -> dict[str, int]:
    """The bytes in each line and the total for the site whose folder this is, leaving out the
    names at its top in `leave_out`. A file linked twice counts once, and a link to another
    folder is not followed. A file that can't be read is logged and left out."""
    started = time.perf_counter()
    amounts = dict.fromkeys(AMOUNTS, 0)
    seen: set[tuple[int, int]] = set()

    def failed(e: OSError) -> None:
        logger.error(
            "Could not count a file of the site", extra={"path": e.filename, "error": str(e)}
        )

    for top, dirs, names in os.walk(folder, onerror=failed):
        here = Path(top)
        if here == folder:
            dirs[:] = [d for d in dirs if d not in leave_out]
            names = [n for n in names if n not in leave_out]
        for name in names:
            path = here / name
            try:
                stat = path.lstat()
            except OSError as e:
                failed(e)
                continue
            if (stat.st_dev, stat.st_ino) in seen:
                continue
            seen.add((stat.st_dev, stat.st_ino))
            amounts[line_of(path.relative_to(folder))] += stat.st_size
    amounts["total"] = sum(amounts[k] for k in AMOUNTS)
    logger.info(
        "Host disk space counted",
        extra={
            "email": email,
            **amounts,
            "took_ms": round((time.perf_counter() - started) * 1000, 1),
        },
    )
    return amounts
