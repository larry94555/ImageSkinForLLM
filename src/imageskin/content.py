"""PDF content, kept apart from the photos and sounds (roadmap R34, item 24).

PDFs are stored in <home>/content/pdfs under a generated id, with the same safe-storage rules as
the uploads (roadmap R6): a size limit per file and in total, the type read from the file's first
bytes, never from its name, and the uploaded name kept only for display. A small JSON file next to
each PDF keeps that name and when it was added and last replaced. Replacing a PDF keeps its id, so
what is later built from it (the wiki, roadmap R37) can be rebuilt for that one PDF.
"""

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from imageskin.uploads import UploadError, copy_limited, display_name

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_CONTENT_BYTES = 2 * 1024 * 1024 * 1024
PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class Pdf:
    id: str
    name: str  # the name it was uploaded with, for display only
    size: int  # bytes
    added_at: str  # ISO 8601, UTC
    replaced_at: str | None = None  # when its file was last replaced, or None


def is_pdf(head: bytes) -> bool:
    """Whether the first bytes are a PDF's. Readers allow a little junk before the header."""
    return PDF_MAGIC in head[:1024]


def now() -> str:
    # To the microsecond, so PDFs added together keep their order.
    return datetime.now(UTC).isoformat(timespec="microseconds")


class ContentStore:
    """PDFs kept in <home>/content/pdfs, each as <id>.pdf with <id>.json beside it."""

    def __init__(self, home: Path) -> None:
        self.root = home / "content"
        self.folder = self.root / "pdfs"
        # Held while a PDF is stored, replaced or removed, so the total limit and an id's two
        # files never see a half-made change.
        self._lock = threading.Lock()
        self._recover()

    def _recover(self) -> None:
        """Finish or undo a change the app was stopped in the middle of (see _commit): a
        leftover .writing means the info was never committed, so the change is undone; a
        leftover .old with no .writing means it was committed, so the backup goes."""
        if not self.folder.is_dir():
            return
        for leftover in sorted({*self.folder.glob("*.writing"), *self.folder.glob("*.old")}):
            stored = leftover.with_suffix(".pdf")
            backup, writing = stored.with_suffix(".old"), stored.with_suffix(".writing")
            if not leftover.exists():  # handled with its pair
                continue
            if writing.exists():
                if backup.exists():
                    backup.replace(stored)
                elif not stored.with_suffix(".json").exists():
                    stored.unlink(missing_ok=True)  # a new PDF that was never committed
                writing.unlink()
                outcome = "undone"
            elif stored.exists():
                backup.unlink()
                outcome = "finished"
            else:
                backup.replace(stored)
                outcome = "undone"
            logger.warning(
                "Recovered an interrupted PDF change", extra={"id": stored.stem, "outcome": outcome}
            )

    def _total_bytes(self, leaving_out: str | None = None) -> int:
        if not self.folder.is_dir():
            return 0
        return sum(
            p.stat().st_size
            for p in self.folder.glob("*.pdf")
            if p.is_file() and p.stem != leaving_out
        )

    def add(self, name: str | None, data: BinaryIO) -> Pdf:
        """Store a new PDF, or raise UploadError saying why not."""
        return self._store(None, name, data)

    def replace(self, pdf_id: str, name: str | None, data: BinaryIO) -> Pdf:
        """Put a new file in place of a stored PDF, keeping its id, or raise UploadError."""
        if self.get(pdf_id) is None:
            raise UploadError("No such PDF.", status=404)
        return self._store(pdf_id, name, data)

    def _store(self, pdf_id: str | None, name: str | None, data: BinaryIO) -> Pdf:
        start = time.perf_counter()
        shown = display_name(name)
        action = "replaced" if pdf_id else "added"
        try:
            pdf = self._receive(pdf_id, shown, data)
        except UploadError as e:
            logger.warning(
                "PDF refused",
                extra={"id": pdf_id, "upload_name": shown, "action": action, "reason": str(e)},
            )
            raise
        logger.info(
            f"PDF {action}",
            extra={
                "id": pdf.id,
                "upload_name": shown,
                "size": pdf.size,
                "path": str(self.folder / f"{pdf.id}.pdf"),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return pdf

    def _receive(self, pdf_id: str | None, name: str, data: BinaryIO) -> Pdf:
        tmp_dir = self.root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        received = tmp_dir / f"{uuid.uuid4().hex}.upload"
        try:
            size = copy_limited(data, received, MAX_PDF_BYTES)
            if size == 0:
                raise UploadError("The file is empty.")
            with received.open("rb") as f:
                if not is_pdf(f.read(1024)):
                    raise UploadError(
                        "This is not a PDF. The file's contents were checked, not its name.",
                        status=415,
                    )
            with self._lock:
                old = self.get(pdf_id) if pdf_id else None
                if pdf_id and old is None:  # removed while this one was being received
                    raise UploadError("No such PDF.", status=404)
                if self._total_bytes(leaving_out=pdf_id) + size > MAX_CONTENT_BYTES:
                    raise UploadError(
                        f"PDFs are limited to {MAX_CONTENT_BYTES // 2**30} GB in total."
                        " Remove some first.",
                        status=413,
                    )
                if old is None:
                    pdf = Pdf(id=uuid.uuid4().hex, name=name, size=size, added_at=now())
                else:
                    pdf = replace(old, name=name, size=size, replaced_at=now())
                self._commit(pdf, received, replacing=old is not None)
            return pdf
        finally:
            received.unlink(missing_ok=True)

    def _commit(self, pdf: Pdf, received: Path, replacing: bool) -> None:
        """Move the received file and its info into place. If either step fails, the store is
        left as it was: a new PDF is taken out again, a replaced one gets its old file back."""
        self.folder.mkdir(parents=True, exist_ok=True)
        final = self.folder / f"{pdf.id}.pdf"
        info = final.with_suffix(".json")
        writing = info.with_suffix(".writing")
        backup = final.with_suffix(".old")
        try:
            writing.write_text(json.dumps(asdict(pdf)), encoding="utf-8")
            if replacing:
                final.replace(backup)
            received.replace(final)
            writing.replace(info)
        except OSError as e:
            if replacing and backup.exists():
                backup.replace(final)
            elif not replacing:
                final.unlink(missing_ok=True)
            writing.unlink(missing_ok=True)
            logger.error(
                "Could not store the PDF", extra={"id": pdf.id, "path": str(final), "error": str(e)}
            )
            raise UploadError("The PDF could not be stored. Try again.", status=500) from e
        backup.unlink(missing_ok=True)

    def list(self) -> list[Pdf]:
        """Stored PDFs, oldest first."""
        if not self.folder.is_dir():
            return []
        pdfs = [
            p
            for info in self.folder.glob("*.json")
            if info.with_suffix(".pdf").is_file() and (p := self._read(info)) is not None
        ]
        return sorted(pdfs, key=lambda p: p.added_at)

    def get(self, pdf_id: str | None) -> Pdf | None:
        path = self.path(pdf_id)
        return self._read(path.with_suffix(".json")) if path else None

    def path(self, pdf_id: str | None) -> Path | None:
        """The stored file for an id, or None. Ids are 32 hex digits, so never a path."""
        if not pdf_id or len(pdf_id) != 32 or any(c not in "0123456789abcdef" for c in pdf_id):
            return None
        stored = self.folder / f"{pdf_id}.pdf"
        return stored if stored.is_file() else None

    def remove(self, pdf_id: str) -> bool:
        """Delete a PDF; False when there is none with that id."""
        with self._lock:
            stored = self.path(pdf_id)
            if stored is None:
                return False
            # The file first: if it can't be deleted (open elsewhere), the PDF stays listed
            # and can be removed again.
            try:
                stored.unlink()
            except OSError as e:
                logger.error("Could not remove the PDF", extra={"id": pdf_id, "error": str(e)})
                raise UploadError("The PDF could not be removed. Try again.", status=500) from e
            stored.with_suffix(".json").unlink(missing_ok=True)
        logger.info("PDF removed", extra={"id": pdf_id})
        return True

    @staticmethod
    def _read(info: Path) -> Pdf | None:
        try:
            return Pdf(**json.loads(info.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError) as e:
            logger.error("Could not read PDF info", extra={"path": str(info), "error": str(e)})
            return None
