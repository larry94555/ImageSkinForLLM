"""The user's edits to the wiki (roadmap R38): an entry's title and summary, as the user wrote
them, kept apart from what the LLM built.

A PDF's edits are saved in <data folder>/content/wiki/<id>.edits.json, by entry id, so they are
there whenever the wiki is read again, after a restart too, and a rebuild never overwrites them.
After a rebuild (or a replaced PDF's rebuild) every edit is flagged for review: an entry the new
outline still has keeps the user's text, and an edit whose entry is gone is listed as lost until
the user discards it. Removing the PDF removes its edits.
"""

import contextlib
import json
import logging
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 200
MAX_SUMMARY_CHARS = 5000
UNREADABLE = "The saved edits could not be read, so nothing was changed. Try again."


class EditError(Exception):
    """An edit that can't be saved; the message says why, for the user."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


class WikiEdits:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._lock = threading.Lock()

    def get(self, pdf_id: str) -> dict[str, dict[str, Any]]:
        """A PDF's edits by entry id: title, summary, edited_at and review. Unreadable edits are
        logged and shown as none, for reading only: a change refuses them (see _load)."""
        try:
            return self._load(pdf_id)
        except EditError:
            return {}

    def _load(self, pdf_id: str) -> dict[str, dict[str, Any]]:
        """The edits to change. Raises EditError (500) when the file can't be read, so a change
        never replaces edits it couldn't read with fewer."""
        path = self._path(pdf_id)
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.error(
                "Could not read the wiki edits", extra={"path": str(path), "error": str(e)}
            )
            raise EditError(UNREADABLE, status=500) from e
        edits = saved.get("edits") if isinstance(saved, dict) else None
        if not isinstance(edits, dict):
            logger.error(
                "Could not read the wiki edits", extra={"path": str(path), "error": "not edits"}
            )
            raise EditError(UNREADABLE, status=500)
        return edits

    def save(self, pdf_id: str, entry_id: str, title: str, summary: str) -> dict[str, Any]:
        """Keeps the user's title and summary for an entry; saving it again marks it checked."""
        title, summary = " ".join(title.split()), summary.strip()
        if not title or not summary:
            raise EditError("A wiki entry needs a title and a summary.")
        if len(title) > MAX_TITLE_CHARS:
            raise EditError(f"A title can be at most {MAX_TITLE_CHARS} characters.")
        if len(summary) > MAX_SUMMARY_CHARS:
            raise EditError(f"A summary can be at most {MAX_SUMMARY_CHARS} characters.")
        edit = {
            "title": title,
            "summary": summary,
            "edited_at": datetime.now(UTC).isoformat(),
            "review": False,
        }
        with self._lock:
            edits = self._load(pdf_id)
            edits[entry_id] = edit
            self._write(pdf_id, edits)
        return edit

    def discard(self, pdf_id: str, entry_id: str) -> bool:
        """Back to what the LLM built; whether there was an edit."""
        with self._lock:
            edits = self._load(pdf_id)
            if edits.pop(entry_id, None) is None:
                return False
            self._write(pdf_id, edits)
        return True

    def reviewed(self, pdf_id: str, entry_id: str) -> bool:
        """The user has checked an edit after a rebuild; whether there was one."""
        with self._lock:
            edits = self._load(pdf_id)
            if entry_id not in edits:
                return False
            edits[entry_id] = {**edits[entry_id], "review": False}
            self._write(pdf_id, edits)
        return True

    def flag_all(self, pdf_id: str) -> int:
        """After a rebuild: every edit is to be checked against the new wiki. How many."""
        with self._lock:
            edits = self._load(pdf_id)
            if not edits:
                return 0
            for entry_id, edit in edits.items():
                edits[entry_id] = {**edit, "review": True}
            self._write(pdf_id, edits)
        return len(edits)

    def replace(self, pdf_id: str, edits: dict[str, dict[str, Any]]) -> None:
        """All of a PDF's edits at once: a restored or loaded wiki's (R38a)."""
        with self._lock:
            self._write(pdf_id, edits)

    def forget(self, pdf_id: str) -> None:
        with self._lock:
            self._path(pdf_id).unlink(missing_ok=True)

    def _path(self, pdf_id: str) -> Path:
        return self.folder / f"{pdf_id}.edits.json"

    def _write(self, pdf_id: str, edits: dict[str, dict[str, Any]]) -> None:
        """Called with the lock held. Raises EditError (500) when the file can't be written."""
        path = self._path(pdf_id)
        if not edits:
            path.unlink(missing_ok=True)
            return
        writing = path.with_suffix(".writing")
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            writing.write_text(json.dumps({"edits": edits}, ensure_ascii=False), encoding="utf-8")
            writing.replace(path)
        except OSError as e:
            with contextlib.suppress(OSError):
                writing.unlink(missing_ok=True)
            logger.error(
                "Could not save the wiki edits", extra={"path": str(path), "error": str(e)}
            )
            raise EditError("The edit could not be saved. Try again.", status=500) from e


def ids(entries: list[dict[str, Any]]) -> Iterator[str]:
    """Every entry id in an outline, at every level."""
    for entry in entries:
        yield entry["id"]
        yield from ids(entry["entries"])


def marked(entry: dict[str, Any], edits: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """An entry and its parts as the user sees them: with their edits, each marked `edited`,
    and `review` when it is to be checked after a rebuild, with what the rebuild `built`."""
    edit = edits.get(entry["id"])
    shown = {**entry, "edited": edit is not None, "review": bool(edit and edit["review"])}
    if edit is not None:
        shown |= {"title": edit["title"], "summary": edit["summary"]}
        if edit["review"]:  # what the rebuilt wiki says, to compare
            shown["built"] = {"title": entry["title"], "summary": entry["summary"]}
    if "entries" in entry:
        shown["entries"] = [marked(e, edits) for e in entry["entries"]]
    return shown


def lost(entries: list[dict[str, Any]], edits: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The edits whose entries the outline no longer has, after a rebuild."""
    found = set(ids(entries))
    return [
        {"id": entry_id, "title": edit["title"], "summary": edit["summary"]}
        for entry_id, edit in edits.items()
        if entry_id not in found
    ]
