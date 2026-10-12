"""Reads each PDF in the background when it is added or replaced (roadmap R36), and reports how
far it has got, like the prepare job (R12).

What was read is saved in <data folder>/content/read/<id>.json with the PDF's version (when it
was added or last replaced), so a reading left over from an older file is never used. On start,
every PDF with no up-to-date reading is read again. One PDF is read at a time.
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from imageskin.content import ContentStore, Pdf
from imageskin.pdf_reading import Progress, Reading, ReadingError, read_pdf

logger = logging.getLogger(__name__)

State = Literal["waiting", "reading", "done", "failed"]
ReadPdf = Callable[[Path, Progress], Reading]


@dataclass(frozen=True)
class ReadingStatus:
    state: State
    page: int = 0  # pages read so far
    pages: int = 0  # pages in all, once known
    kind: str | None = None  # once done: text, slides or tables
    counts: dict[str, int] | None = None  # once done: paragraphs, slides and tables found
    pages_without_text: list[int] | None = None  # once done: maybe scanned, not read
    error: str | None = None  # why it failed


def version(pdf: Pdf) -> str:
    return pdf.replaced_at or pdf.added_at


def done_status(reading: dict[str, Any]) -> ReadingStatus:
    counts: dict[str, int] = {"paragraph": 0, "slide": 0, "table": 0}
    for piece in reading["pieces"]:
        counts[piece["kind"]] += 1
    return ReadingStatus(
        "done",
        reading["pages"],
        reading["pages"],
        reading["kind"],
        counts,
        reading["pages_without_text"],
    )


class ReadingJob:
    def __init__(self, store: ContentStore, read: ReadPdf = read_pdf) -> None:
        self.store = store
        self.read = read
        self.folder = store.root / "read"
        self._lock = threading.Lock()
        self._waiting: list[str] = []
        self._status: dict[str, ReadingStatus] = {}
        self._worker: threading.Thread | None = None

    def catch_up(self) -> None:
        """Queue every PDF whose reading is missing or out of date."""
        for pdf in self.store.list():
            if self._saved(pdf) is None:
                self.queue(pdf)

    def queue(self, pdf: Pdf) -> None:
        with self._lock:
            if pdf.id not in self._waiting:
                self._waiting.append(pdf.id)
            self._status[pdf.id] = ReadingStatus("waiting")
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, name="pdf-reading", daemon=True)
                self._worker.start()

    def forget(self, pdf_id: str) -> None:
        """After a PDF is removed: its reading goes too."""
        with self._lock:
            self._status.pop(pdf_id, None)
            if pdf_id in self._waiting:
                self._waiting.remove(pdf_id)
            (self.folder / f"{pdf_id}.json").unlink(missing_ok=True)

    def statuses(self) -> dict[str, ReadingStatus]:
        """How far each stored PDF has got."""
        result = {}
        for pdf in self.store.list():
            with self._lock:
                status = self._status.get(pdf.id)
            if status is None or status.state == "done":
                saved = self._saved(pdf)
                status = done_status(saved) if saved else None
            if status is not None:
                result[pdf.id] = status
        return result

    def reading(self, pdf_id: str) -> dict[str, Any] | None:
        """What was read from the current version of a PDF, or None if not yet."""
        pdf = self.store.get(pdf_id)
        return self._saved(pdf) if pdf else None

    def wait(self, timeout: float = 30) -> None:
        """Until every queued PDF is read (tests and the command line)."""
        worker = self._worker
        if worker is not None:
            worker.join(timeout)

    def _saved(self, pdf: Pdf) -> dict[str, Any] | None:
        path = self.folder / f"{pdf.id}.json"
        try:
            saved: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            logger.error(
                "Could not read a saved reading", extra={"path": str(path), "error": str(e)}
            )
            return None
        return saved if saved.get("version") == version(pdf) else None

    def _run(self) -> None:
        while True:
            with self._lock:
                if not self._waiting:
                    self._worker = None
                    return
                pdf_id = self._waiting.pop(0)
            pdf, path = self.store.get(pdf_id), self.store.path(pdf_id)
            if pdf is not None and path is not None:
                self._read(pdf, path)

    def _read(self, pdf: Pdf, path: Path) -> None:
        start = time.perf_counter()
        logger.info("Reading PDF", extra={"id": pdf.id, "upload_name": pdf.name})

        def progress(page: int, pages: int) -> None:
            self._set(pdf.id, ReadingStatus("reading", page, pages))

        self._set(pdf.id, ReadingStatus("reading"))
        try:
            reading = self.read(path, progress)
        except ReadingError as e:
            logger.error(
                "Could not read the PDF",
                extra={"id": pdf.id, "upload_name": pdf.name, "error": repr(e.__cause__ or e)},
            )
            self._set(pdf.id, ReadingStatus("failed", error=str(e)))
            return
        saved = {"id": pdf.id, "name": pdf.name, "version": version(pdf), **asdict(reading)}
        with self._lock:
            if self.store.get(pdf.id) != pdf:
                return  # replaced or removed meanwhile; a newer reading is queued, or none needed
            self.folder.mkdir(parents=True, exist_ok=True)
            writing = self.folder / f"{pdf.id}.writing"
            writing.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
            writing.replace(self.folder / f"{pdf.id}.json")
            status = done_status(saved)
            self._status[pdf.id] = status
        logger.info(
            "PDF read",
            extra={
                "id": pdf.id,
                "upload_name": pdf.name,
                "kind": reading.kind,
                "pages": reading.pages,
                "counts": status.counts,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )

    def _set(self, pdf_id: str, status: ReadingStatus) -> None:
        with self._lock:
            # A PDF replaced while it was read waits for its new reading; don't hide that.
            if pdf_id not in self._waiting:
                self._status[pdf_id] = status
