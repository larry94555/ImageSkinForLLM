"""The history of each PDF's wiki (roadmap R38a): every change saves a version of the whole wiki
as it then reads, the built pages with the user's edits, so an earlier state can be restored,
and the wiki and its history can be saved to a file and loaded back.

A PDF's versions are kept in <data folder>/content/wiki/<id>.history/, one file per version,
all of them. Each has an id of its own, so versions loaded from a file join the history without
replacing any. Removing the PDF removes its history.
"""

import contextlib
import json
import logging
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

# What changed. "start": the wiki as it was before its history began (built before R38a).
Kind = Literal[
    "start", "built", "rebuilt", "edited", "undone", "kept", "discarded", "restored", "loaded"
]
FILE_KIND = "imageskin-wiki"
FILE_FORMAT = 1


class HistoryError(Exception):
    """A version that can't be kept, restored or loaded; the message says why, for the user."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def _strings(d: dict[str, Any], *keys: str) -> bool:
    return all(isinstance(d.get(k), str) for k in keys)


def _page_numbers(pages: Any) -> bool:
    return isinstance(pages, list) and all(
        isinstance(p, int) and not isinstance(p, bool) for p in pages
    )


def _is_page(page: Any) -> bool:
    return (
        isinstance(page, dict)
        and _strings(page, "id", "title", "text")
        and _page_numbers(page.get("pages"))
    )


def _is_entry(entry: Any) -> bool:
    """An outline entry as saved, with every level below it."""
    return (
        isinstance(entry, dict)
        and _strings(entry, "id", "title", "summary")
        and _page_numbers(entry.get("pages"))
        and isinstance(entry.get("detail"), bool)
        and isinstance(entry.get("entries"), list)
        and all(_is_entry(e) for e in entry["entries"])
    )


def is_edits(edits: Any) -> bool:
    """A PDF's edits by entry id, as wiki_edits.py saves them."""
    return isinstance(edits, dict) and all(
        isinstance(entry_id, str)
        and isinstance(edit, dict)
        and _strings(edit, "title", "summary")
        and isinstance(edit.get("review"), bool)
        for entry_id, edit in edits.items()
    )


def is_wiki(wiki: Any, wiki_format: int) -> bool:
    """Whether this is a PDF's saved wiki, in the form it is saved in now, down to every page
    and entry, so whatever reads it can rely on it."""
    return (
        isinstance(wiki, dict)
        and wiki.get("format") == wiki_format
        and _strings(wiki, "version", "name")
        and isinstance(wiki.get("parts"), int)
        and isinstance(wiki.get("skipped_parts"), list)
        and isinstance(wiki.get("pages"), list)
        and all(_is_page(p) for p in wiki["pages"])
        and isinstance(wiki.get("outline"), list)
        and all(_is_entry(e) for e in wiki["outline"])
    )


def is_version(version: Any, wiki_format: int) -> bool:
    return (
        isinstance(version, dict)
        and isinstance(version.get("id"), str)
        and isinstance(version.get("at"), str)
        and isinstance(version.get("change"), dict)
        and is_wiki(version.get("wiki"), wiki_format)
        and is_edits(version.get("edits"))
    )


class WikiHistory:
    def __init__(self, folder: Path, wiki_format: int) -> None:
        self.folder = folder
        self.wiki_format = wiki_format
        self._lock = threading.Lock()

    def record(
        self,
        pdf_id: str,
        wiki: dict[str, Any],
        edits: dict[str, Any],
        kind: Kind,
        **about: str,  # what it is about: the entry's title, or when the restored version was
    ) -> dict[str, Any]:
        """Keeps a new version; raises HistoryError (500) when it can't be written."""
        version = {
            "id": uuid.uuid4().hex,
            "at": datetime.now(UTC).isoformat(),
            "change": {"kind": kind, **about},
            "wiki": wiki,
            "edits": edits,
        }
        with self._lock:
            self._write(pdf_id, version)
        logger.info(
            "Wiki version kept", extra={"id": pdf_id, "kind": kind, "version": version["id"]}
        )
        return version

    def started(self, pdf_id: str) -> bool:
        """Whether the PDF's wiki has any history yet."""
        folder = self._folder(pdf_id)
        return folder.is_dir() and any(folder.glob("*.json"))

    def versions(self, pdf_id: str) -> list[dict[str, Any]]:
        """Every version, newest first, without its wiki: id, at and change."""
        return [
            {"id": v["id"], "at": v["at"], "change": v["change"]}
            for v in reversed(self._all(pdf_id))
        ]

    def get(self, pdf_id: str, version_id: str) -> dict[str, Any] | None:
        for version in self._all(pdf_id):
            if version["id"] == version_id:
                return version
        return None

    def everything(self, pdf_id: str) -> list[dict[str, Any]]:
        """Every version with its wiki, oldest first, for saving to a file."""
        return self._all(pdf_id)

    def add(self, pdf_id: str, versions: list[dict[str, Any]]) -> int:
        """Versions from a file that the history doesn't have yet; how many were added. One that
        can't be written is logged and left out, as a change's own version is (see record)."""
        known = {v["id"] for v in self._all(pdf_id)}
        added = 0
        with self._lock:
            for version in versions:
                if version["id"] in known:
                    continue
                try:
                    self._write(pdf_id, version)
                except HistoryError:
                    continue  # logged
                known.add(version["id"])
                added += 1
        return added

    def forget(self, pdf_id: str) -> None:
        with self._lock:
            folder = self._folder(pdf_id)
            for path in folder.glob("*"):
                path.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                folder.rmdir()

    def _folder(self, pdf_id: str) -> Path:
        return self.folder / f"{pdf_id}.history"

    def _all(self, pdf_id: str) -> list[dict[str, Any]]:
        """Every readable version, oldest first. An unreadable one is logged and left out."""
        found = []
        for path in sorted(self._folder(pdf_id).glob("*.json")):
            try:
                version = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                logger.error(
                    "Could not read a wiki version", extra={"path": str(path), "error": str(e)}
                )
                continue
            if is_version(version, self.wiki_format):
                found.append(version)
            else:
                logger.error(
                    "Could not read a wiki version",
                    extra={"path": str(path), "error": "not a version"},
                )
        return sorted(found, key=lambda v: v["at"])

    def _write(self, pdf_id: str, version: dict[str, Any]) -> None:
        """Called with the lock held. The file gets a new name of its own, never one taken from
        the version, which may come from a file the user loaded; _all sorts them by time."""
        folder = self._folder(pdf_id)
        path = folder / f"{uuid.uuid4().hex}.json"
        writing = path.with_suffix(".writing")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            writing.write_text(json.dumps(version, ensure_ascii=False), encoding="utf-8")
            writing.replace(path)
        except OSError as e:
            with contextlib.suppress(OSError):
                writing.unlink(missing_ok=True)
            logger.error(
                "Could not keep the wiki version", extra={"path": str(path), "error": str(e)}
            )
            raise HistoryError("The wiki's history could not be saved. Try again.", 500) from e


def wiki_file(
    pdf_id: str,
    pdf_name: str,
    pdf_version: str,
    current: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """A PDF's current wiki and its whole history, as saved to a file."""
    return {
        "kind": FILE_KIND,
        "format": FILE_FORMAT,
        "saved_at": datetime.now(UTC).isoformat(),
        "pdf_id": pdf_id,
        "pdf_name": pdf_name,
        "pdf_version": pdf_version,
        "current": current,
        "history": history,
    }


def read_wiki_file(data: bytes, wiki_format: int) -> dict[str, Any]:
    """A wiki file's contents, checked. Raises HistoryError (422) when it isn't one."""
    try:
        loaded = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise HistoryError(NOT_A_WIKI_FILE) from e
    if (
        not isinstance(loaded, dict)
        or loaded.get("kind") != FILE_KIND
        or loaded.get("format") != FILE_FORMAT
        or not isinstance(loaded.get("pdf_id"), str)
        or not isinstance(loaded.get("pdf_version"), str)
        or not isinstance(loaded.get("current"), dict)
        or not is_wiki(loaded["current"].get("wiki"), wiki_format)
        or not is_edits(loaded["current"].get("edits"))
        or not isinstance(loaded.get("history"), list)
        or not all(is_version(v, wiki_format) for v in loaded["history"])
    ):
        raise HistoryError(NOT_A_WIKI_FILE)
    return loaded


NOT_A_WIKI_FILE = "This isn't a wiki file saved by ImageSkinForLLM, or it was saved by a newer one."
