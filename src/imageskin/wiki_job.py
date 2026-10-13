"""Builds each PDF's wiki pages in the background once it has been read (roadmap R37), and reports
how far it has got, like the reading job (R36).

A PDF's pages are saved in <data folder>/content/wiki/<id>.json with the PDF's version, so pages
built from an older file are never used. Replacing a PDF rebuilds only its pages once it has been
read again, and removing it removes them; other PDFs' pages are left alone. On start, every PDF
that has been read but has no up-to-date pages is built again. One PDF is built at a time. While
the LLM can't be reached (llama-server not started yet, say), the build waits and asks for the
same part again, keeping the parts already done.

Once a PDF's topics are found, the LLM builds the wiki's outline from them (R37a): the table of
contents, and the detail pages of the topics too long to say in a few sentences.
"""

import contextlib
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from imageskin.chat import LlmError
from imageskin.content import ContentStore
from imageskin.reading_job import ReadingJob, version
from imageskin.wiki import Progress, WaitForLlm, Wiki, WikiError, WikiPage
from imageskin.wiki_outline import (
    Entry,
    OutlineProgress,
    count_detail,
    find,
    from_saved,
    plain_outline,
    shown,
)

logger = logging.getLogger(__name__)

State = Literal["waiting", "building", "done", "failed"]
Stage = Literal["topics", "outline"]
# Builds the wiki pages for a PDF (its id and the pieces read from it).
BuildWiki = Callable[[str, list[dict[str, Any]], Progress, WaitForLlm], Wiki]
# Builds a PDF's outline from its topics (its id, its wiki pages and the pieces read from it).
BuildOutline = Callable[
    [str, list[WikiPage], list[dict[str, Any]], OutlineProgress, WaitForLlm], list[Entry]
]
# What saved pages look like; pages saved in an older form are built again. 4: detail pages
# show the PDF's own words.
WIKI_FORMAT = 4
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
    stage: Stage = "topics"  # while building: finding the topics, then building the outline
    steps: int = 0  # outline requests made to the LLM so far
    steps_planned: int = 0  # outline requests planned so far; more as long parts are found
    detail_pages: int | None = None  # once done: the outline's detail pages
    elapsed_s: float | None = None  # how long the build has taken so far, or took once done
    # About how long this stage has left, from how long its steps have taken so far.
    remaining_s: float | None = None


def done_status(saved: dict[str, Any]) -> WikiStatus:
    parts = saved["parts"]
    detail = sum(count_detail(e) for e in from_saved(saved["outline"]))
    return WikiStatus(
        "done",
        parts,
        parts,
        len(saved["pages"]),
        saved["skipped_parts"],
        detail_pages=detail,
        elapsed_s=saved.get("duration_s"),
    )


class WikiJob:
    def __init__(
        self,
        store: ContentStore,
        readings: ReadingJob,
        build: BuildWiki,
        outline: BuildOutline | None = None,  # None: the topics as they are
        retry_s: float = RETRY_S,
        when_idle: Callable[[], None] | None = None,  # after the last build in the queue
    ) -> None:
        self.store = store
        self.readings = readings
        self.build = build
        self.outline = outline or (
            lambda pdf_id, topics, pieces, progress, wait: plain_outline(topics)
        )
        self.retry_s = retry_s
        self.when_idle = when_idle
        self.folder = store.root / "wiki"
        self._lock = threading.Lock()
        self._waiting: list[str] = []
        self._status: dict[str, WikiStatus] = {}
        self._worker: threading.Thread | None = None
        self._building: tuple[str, str] | None = None  # the PDF and version being built now
        self._started: dict[str, float] = {}  # when the build now running started (monotonic)
        self._stage_started: dict[str, float] = {}  # and when its stage started
        self._last_step: dict[str, float] = {}  # and when its last step was done

    def catch_up(self) -> None:
        """Queue every PDF that has been read but whose pages are missing or out of date."""
        for pdf in self.store.list():
            if self._saved(pdf.id) is None and self.readings.reading(pdf.id) is not None:
                self.queue(pdf.id)

    def queue(self, pdf_id: str) -> None:
        pdf = self.store.get(pdf_id)
        with self._lock:
            if pdf is not None and self._building == (pdf_id, version(pdf)):
                return  # this very version is being built now
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
                started = self._started.get(pdf.id)
                stage_started = self._stage_started.get(pdf.id)
                last_step = self._last_step.get(pdf.id)
            if status is not None and status.state != "done" and started is not None:
                now = time.monotonic()
                stage_started = stage_started or started
                last_step = last_step or stage_started
                status = replace(
                    status,
                    elapsed_s=round(now - started, 1),
                    remaining_s=remaining(status, last_step - stage_started, now - last_step),
                )
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
        """One entry of the outline as its page shows it, or None. A topic's has its whole text
        too."""
        pdf_id = page_id.split("-", 1)[0]
        saved = self._saved(pdf_id)
        if saved is None:
            return None
        entry = find(from_saved(saved["outline"]), page_id)
        if entry is None:
            return None
        texts = {page["id"]: page["text"] for page in saved["pages"]}
        text = {"text": texts[page_id]} if page_id in texts else {}
        return {**summary(saved), **shown(entry), **text}

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
        if saved.get("format") != WIKI_FORMAT:
            return None  # saved before the outline (R37a): built again
        return saved if saved.get("version") == version(pdf) else None

    def _run(self) -> None:
        built = False
        while True:
            with self._lock:
                if not self._waiting:
                    self._worker = None
                    break
                pdf_id = self._waiting.pop(0)
                pdf = self.store.get(pdf_id)
                self._building = (pdf_id, version(pdf)) if pdf else None
            try:
                built = self._build(pdf_id) or built
            except Exception as e:  # never let one PDF stop the PDFs queued after it
                logger.exception("Could not build the wiki", extra={"id": pdf_id, "error": repr(e)})
                self._set(pdf_id, WikiStatus("failed", error="Something went wrong building it."))
            finally:
                with self._lock:
                    self._building = None
                    self._started.pop(pdf_id, None)
                    self._stage_started.pop(pdf_id, None)
                    self._last_step.pop(pdf_id, None)
        if built and self.when_idle is not None:
            self.when_idle()

    def _build(self, pdf_id: str) -> bool:
        """Build one PDF's pages; whether the LLM was asked."""
        pdf = self.store.get(pdf_id)
        reading = self.readings.reading(pdf_id)
        if pdf is None or reading is None:
            return False  # removed, or replaced and not read again yet (it is queued then)
        start = time.perf_counter()
        with self._lock:
            self._started[pdf_id] = self._stage_started[pdf_id] = time.monotonic()
        logger.info("Building wiki pages", extra={"id": pdf_id, "upload_name": pdf.name})
        self._set(pdf_id, WikiStatus("building"))

        def progress(part: int, parts: int) -> None:
            self._stepped(pdf_id)
            self._set(pdf_id, WikiStatus("building", part, parts))

        def pause(error: LlmError, building: WikiStatus, step: int) -> None:
            logger.warning(
                "Waiting for the LLM to build the wiki",
                extra={
                    "id": pdf_id,
                    "stage": building.stage,
                    "part": step,
                    "error": str(error),
                    "retry_s": self.retry_s,
                },
            )
            self._set(pdf_id, replace(building, state="waiting", error=str(error)))
            time.sleep(self.retry_s)
            with self._lock:
                if (
                    self.store.get(pdf_id) != pdf
                    or pdf_id not in self._status
                    or pdf_id in self._waiting
                ):
                    raise Superseded  # replaced or removed meanwhile
            self._set(pdf_id, building)

        def wait_for_llm(error: LlmError, part: int, parts: int) -> None:
            pause(error, WikiStatus("building", part - 1, parts), part)

        try:
            wiki = self.build(pdf_id, reading["pieces"], progress, wait_for_llm)
            parts = wiki.parts

            planned = 0

            def outline_progress(steps: int, steps_planned: int) -> None:
                self._stepped(pdf_id)
                nonlocal planned
                planned = steps_planned
                status = WikiStatus("building", parts, parts, stage="outline", steps=steps)
                self._set(pdf_id, replace(status, steps_planned=steps_planned))

            def wait_for_outline(error: LlmError, step: int, _: int) -> None:
                status = WikiStatus("building", parts, parts, stage="outline", steps=step - 1)
                pause(error, replace(status, steps_planned=planned), step)

            with self._lock:
                self._stage_started[pdf_id] = time.monotonic()
                self._last_step.pop(pdf_id, None)
            outline_progress(0, 0)
            try:
                outline = self.outline(
                    pdf_id, wiki.pages, reading["pieces"], outline_progress, wait_for_outline
                )
            except LlmError as e:  # refused: the topics are kept, as they are
                logger.error(
                    "Could not build the wiki outline", extra={"id": pdf_id, "error": str(e)}
                )
                outline = plain_outline(wiki.pages)
        except Superseded:
            return True
        except (WikiError, LlmError) as e:  # an LlmError here is a refusal, not an outage
            logger.error("Could not build the wiki", extra={"id": pdf_id, "error": str(e)})
            self._set(pdf_id, WikiStatus("failed", error=str(e)))
            return True
        saved = {
            "format": WIKI_FORMAT,
            "id": pdf_id,
            "name": pdf.name,
            "version": version(pdf),
            "parts": wiki.parts,
            "skipped_parts": wiki.skipped_parts,
            "pages": [asdict(page) for page in wiki.pages],
            "outline": [asdict(entry) for entry in outline],
            "duration_s": round(time.perf_counter() - start, 1),
        }
        with self._lock:
            if self.store.get(pdf_id) != pdf:
                return True  # replaced or removed meanwhile; it is built again, or not needed
            if not self._save(saved):
                return True
        logger.info(
            "Wiki pages built",
            extra={
                "id": pdf_id,
                "upload_name": pdf.name,
                "parts": wiki.parts,
                "pages": len(wiki.pages),
                "detail_pages": sum(count_detail(e) for e in outline),
                "skipped_parts": wiki.skipped_parts,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return True

    def _save(self, saved: dict[str, Any]) -> bool:
        """Whether the pages were saved. Called with the lock held."""
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
            return False
        self._status[pdf_id] = done_status(saved)
        return True

    def _stepped(self, pdf_id: str) -> None:
        with self._lock:
            self._last_step[pdf_id] = time.monotonic()

    def _set(self, pdf_id: str, status: WikiStatus) -> None:
        with self._lock:
            # A PDF replaced while it was built waits for its new pages; don't hide that.
            if pdf_id not in self._waiting and pdf_id in self._status:
                self._status[pdf_id] = status


def remaining(status: WikiStatus, steps_s: float, since_s: float) -> float | None:
    """About how long the stage has left: the time its steps done so far took (`steps_s`), on
    average, for each step left, less the time since the last one (`since_s`), so it counts
    down between steps; None until a step is done."""
    done, total = (
        (status.steps, status.steps_planned)
        if status.stage == "outline"
        else (
            status.part,
            status.parts,
        )
    )
    if done < 1 or total < done:
        return None
    return round(max(0.0, steps_s / done * (total - done) - since_s), 1)


def summary(saved: dict[str, Any]) -> dict[str, Any]:
    return {"pdf_id": saved["id"], "pdf_name": saved["name"]}
