"""Builds each PDF's wiki pages in the background once it has been read (roadmap R37), and reports
how far it has got, like the reading job (R36).

A PDF's pages are saved in <data folder>/content/wiki/<id>.json with the PDF's version, so pages
built from an older file are never used. Replacing a PDF rebuilds only its pages once it has been
read again, and removing it removes them; other PDFs' pages are left alone. On start, every PDF
that has been read but has no up-to-date pages is built again. One PDF is built at a time. While
the LLM can't be reached (llama-server not started yet, say), the build waits and asks for the
same part again, keeping the parts already done.
"""

import contextlib
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal

from imageskin.chat import LlmError
from imageskin.content import ContentStore
from imageskin.reading_job import ReadingJob, version
from imageskin.wiki import Progress, WaitForLlm, Wiki, WikiError

logger = logging.getLogger(__name__)

State = Literal["waiting", "building", "done", "failed"]
# Builds the wiki pages for a PDF (its id and the pieces read from it).
BuildWiki = Callable[[str, list[dict[str, Any]], Progress, WaitForLlm], Wiki]
# How long to wait before trying again when the LLM can't be reached.
RETRY_S = 30.0


class Superseded(Exception):
    """The PDF was replaced or removed while its build waited for the LLM."""


@dataclass(frozen=True)
class WikiStatus:
    state: State
    part: int = 0  # parts done so far
    parts: int = 0  # parts in all, once known
    pages: int | None = None  # once done: wiki pages built
    skipped_parts: list[int] | None = None  # once done: parts the LLM gave no usable answer for
    error: str | None = None  # why it failed, or what it is waiting for


def done_status(saved: dict[str, Any]) -> WikiStatus:
    parts = saved["parts"]
    return WikiStatus("done", parts, parts, len(saved["pages"]), saved["skipped_parts"])


class WikiJob:
    def __init__(
        self,
        store: ContentStore,
        readings: ReadingJob,
        build: BuildWiki,
        retry_s: float = RETRY_S,
        when_idle: Callable[[], None] | None = None,  # after the last build in the queue
    ) -> None:
        self.store = store
        self.readings = readings
        self.build = build
        self.retry_s = retry_s
        self.when_idle = when_idle
        self.folder = store.root / "wiki"
        self._lock = threading.Lock()
        self._waiting: list[str] = []
        self._status: dict[str, WikiStatus] = {}
        self._worker: threading.Thread | None = None

    def catch_up(self) -> None:
        """Queue every PDF that has been read but whose pages are missing or out of date."""
        for pdf in self.store.list():
            if self._saved(pdf.id) is None and self.readings.reading(pdf.id) is not None:
                self.queue(pdf.id)

    def queue(self, pdf_id: str) -> None:
        with self._lock:
            if pdf_id not in self._waiting:
                self._waiting.append(pdf_id)
            self._status[pdf_id] = WikiStatus("waiting")
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, name="wiki", daemon=True)
                self._worker.start()

    def reset(self, pdf_id: str) -> None:
        """After a PDF is replaced: its pages are out of date until it is read again."""
        with self._lock:
            self._status.pop(pdf_id, None)
            if pdf_id in self._waiting:
                self._waiting.remove(pdf_id)

    def forget(self, pdf_id: str) -> None:
        """After a PDF is removed: its pages go too."""
        self.reset(pdf_id)
        with self._lock:
            (self.folder / f"{pdf_id}.json").unlink(missing_ok=True)

    def statuses(self) -> dict[str, WikiStatus]:
        """How far each stored PDF's pages have got."""
        result = {}
        for pdf in self.store.list():
            with self._lock:
                status = self._status.get(pdf.id)
            if status is None or status.state == "done":
                saved = self._saved(pdf.id)
                status = done_status(saved) if saved else None
            if status is not None:
                result[pdf.id] = status
        return result

    def pages(self, pdf_id: str | None = None) -> list[dict[str, Any]]:
        """Every up-to-date page (or one PDF's), without its text: id, title, PDF and pages."""
        found = []
        for pdf in self.store.list():
            saved = self._saved(pdf.id) if pdf_id in (None, pdf.id) else None
            if saved is None:
                continue
            for page in saved["pages"]:
                listed = {key: page[key] for key in ("id", "title", "pages")}
                found.append({**summary(saved), **listed})
        return found

    def built(self, pdf_id: str) -> dict[str, Any] | None:
        """One PDF's up-to-date pages with their text, as saved, or None if not built yet."""
        return self._saved(pdf_id)

    def page(self, page_id: str) -> dict[str, Any] | None:
        """One page with its text, or None."""
        pdf_id = page_id.split("-", 1)[0]
        saved = self._saved(pdf_id)
        if saved is None:
            return None
        for page in saved["pages"]:
            if page["id"] == page_id:
                return {**summary(saved), **page}
        return None

    def wait(self, timeout: float = 30) -> None:
        """Until every queued PDF is built (tests)."""
        worker = self._worker
        if worker is not None:
            worker.join(timeout)

    def _saved(self, pdf_id: str) -> dict[str, Any] | None:
        pdf = self.store.get(pdf_id)
        if pdf is None:
            return None
        path = self.folder / f"{pdf_id}.json"
        try:
            saved: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            logger.error(
                "Could not read saved wiki pages", extra={"path": str(path), "error": str(e)}
            )
            return None
        return saved if saved.get("version") == version(pdf) else None

    def _run(self) -> None:
        built = False
        while True:
            with self._lock:
                if not self._waiting:
                    self._worker = None
                    break
                pdf_id = self._waiting.pop(0)
            try:
                built = self._build(pdf_id) or built
            except Exception as e:  # never let one PDF stop the PDFs queued after it
                logger.exception("Could not build the wiki", extra={"id": pdf_id, "error": repr(e)})
                self._set(pdf_id, WikiStatus("failed", error="Something went wrong building it."))
        if built and self.when_idle is not None:
            self.when_idle()

    def _build(self, pdf_id: str) -> bool:
        """Build one PDF's pages; whether the LLM was asked."""
        pdf = self.store.get(pdf_id)
        reading = self.readings.reading(pdf_id)
        if pdf is None or reading is None:
            return False  # removed, or replaced and not read again yet (it is queued then)
        start = time.perf_counter()
        logger.info("Building wiki pages", extra={"id": pdf_id, "upload_name": pdf.name})
        self._set(pdf_id, WikiStatus("building"))

        def progress(part: int, parts: int) -> None:
            self._set(pdf_id, WikiStatus("building", part, parts))

        def wait_for_llm(error: LlmError, part: int, parts: int) -> None:
            logger.warning(
                "Waiting for the LLM to build the wiki",
                extra={"id": pdf_id, "part": part, "error": str(error), "retry_s": self.retry_s},
            )
            self._set(pdf_id, WikiStatus("waiting", part - 1, parts, error=str(error)))
            time.sleep(self.retry_s)
            with self._lock:
                if (
                    self.store.get(pdf_id) != pdf
                    or pdf_id not in self._status
                    or pdf_id in self._waiting
                ):
                    raise Superseded  # replaced or removed meanwhile
            self._set(pdf_id, WikiStatus("building", part - 1, parts))

        try:
            wiki = self.build(pdf_id, reading["pieces"], progress, wait_for_llm)
        except Superseded:
            return True
        except WikiError as e:
            logger.error("Could not build the wiki", extra={"id": pdf_id, "error": str(e)})
            self._set(pdf_id, WikiStatus("failed", error=str(e)))
            return True
        saved = {
            "id": pdf_id,
            "name": pdf.name,
            "version": version(pdf),
            "parts": wiki.parts,
            "skipped_parts": wiki.skipped_parts,
            "pages": [asdict(page) for page in wiki.pages],
        }
        with self._lock:
            if self.store.get(pdf_id) != pdf:
                return True  # replaced or removed meanwhile; it is built again, or not needed
            self._save(saved)
        logger.info(
            "Wiki pages built",
            extra={
                "id": pdf_id,
                "upload_name": pdf.name,
                "parts": wiki.parts,
                "pages": len(wiki.pages),
                "skipped_parts": wiki.skipped_parts,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return True

    def _save(self, saved: dict[str, Any]) -> None:
        """Called with the lock held."""
        pdf_id = saved["id"]
        writing = self.folder / f"{pdf_id}.writing"
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            writing.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
            writing.replace(self.folder / f"{pdf_id}.json")
        except OSError as e:
            with contextlib.suppress(OSError):  # the folder may be what failed
                writing.unlink(missing_ok=True)
            logger.error(
                "Could not save the wiki pages",
                extra={"id": pdf_id, "path": str(writing), "error": str(e)},
            )
            self._status[pdf_id] = WikiStatus(
                "failed", error="The wiki pages could not be saved. Try replacing the PDF."
            )
            return
        self._status[pdf_id] = done_status(saved)

    def _set(self, pdf_id: str, status: WikiStatus) -> None:
        with self._lock:
            # A PDF replaced while it was built waits for its new pages; don't hide that.
            if pdf_id not in self._waiting and pdf_id in self._status:
                self._status[pdf_id] = status


def summary(saved: dict[str, Any]) -> dict[str, Any]:
    return {"pdf_id": saved["id"], "pdf_name": saved["name"]}
