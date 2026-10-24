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

The user's edits (R38) are kept apart and shown over what was built; a rebuild keeps them and
flags them for review. Every change keeps a version of the whole wiki in its history (R38a), so
an earlier state can be restored, and the wiki and its history can be saved to a file and loaded
back.
"""

import contextlib
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from imageskin import reply_times
from imageskin.chat import LlmCancelled, LlmError, ask_stop
from imageskin.content import ContentStore
from imageskin.reading_job import ReadingJob, version
from imageskin.wiki import Progress, WaitForLlm, Wiki, WikiError, WikiPage
from imageskin.wiki_edits import EditError, WikiEdits, lost, marked
from imageskin.wiki_history import (
    HistoryError,
    Kind,
    WikiHistory,
    read_wiki_file,
    wiki_file,
)
from imageskin.wiki_outline import (
    Entry,
    OutlineProgress,
    ancestors,
    count_detail,
    find,
    from_saved,
    plain_outline,
    shown,
)

logger = logging.getLogger(__name__)

PACE_FILE = "pace.json"  # in the wiki folder: how long a part took in the last build

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
# How long to wait before trying again when the LLM can't be reached or is still loading its
# model: short, so the build goes on soon after llama-server is ready.
RETRY_S = 5.0
# Why a wiki wasn't built, when the LLM refused to build it.
AI_REFUSED = "The AI couldn't build a wiki from this PDF. Rebuild the wiki to try again."


class Superseded(Exception):
    """The PDF was replaced or removed while it was built."""


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
    # While queued: the PDF being built was removed or replaced, and its build is stopping.
    stopping: bool = False
    # While queued: how many PDFs are built first, counting the one being built now, and that
    # one's name.
    ahead: int = 0
    building_name: str | None = None


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
        # After the wiki changes: built, edited, gone back to, loaded or removed (R98a).
        when_changed: Callable[[], None] | None = None,
    ) -> None:
        self.store = store
        self.readings = readings
        self.build = build
        self.outline = outline or (
            lambda pdf_id, topics, pieces, progress, wait: plain_outline(topics)
        )
        self.retry_s = retry_s
        self.when_idle = when_idle
        self.when_changed = when_changed
        self.folder = store.root / "wiki"
        self.edits = WikiEdits(self.folder)
        self.history = WikiHistory(self.folder, WIKI_FORMAT)
        self._lock = threading.Lock()
        self._waiting: list[str] = []
        self._status: dict[str, WikiStatus] = {}
        self._worker: threading.Thread | None = None
        self._building: tuple[str, str] | None = None  # the PDF and version being built now
        self._stop = threading.Event()  # set to cut the LLM off while _building is built
        # Seconds a part took in the last build, so the first part of the next one has a time
        # left too (Larry's test of PR #123), not only once a part is done.
        self._part_s: float | None = self._load_pace()
        self._started: dict[str, float] = {}  # when the build now running started (monotonic)
        self._stage_started: dict[str, float] = {}  # and when its stage started
        self._last_step: dict[str, float] = {}  # and when its last step was done

    def catch_up(self) -> None:
        """Queue every PDF that has been read but whose pages are missing or out of date."""
        for pdf in self.store.list():
            if self._saved(pdf.id) is None and self.readings.reading(pdf.id) is not None:
                self.queue(pdf.id)

    def read(self, pdf_id: str) -> None:
        """Called once a PDF's reading is saved: builds its wiki unless it is already built
        for this version of the PDF. A reading redone only because the app reads PDFs better
        now keeps the wiki (and the user's edits); "Rebuild the wiki" builds it from the new
        reading."""
        if self._saved(pdf_id) is not None:
            logger.info("Wiki kept for a PDF read again", extra={"id": pdf_id})
            return
        self.queue(pdf_id)

    def queue(self, pdf_id: str) -> None:
        pdf = self.store.get(pdf_id)
        with self._lock:
            if pdf is not None and self._building == (pdf_id, version(pdf)):
                return  # this very version is being built now
            self._stop_if_building(pdf_id)  # an older version: its answers are not wanted
            if pdf_id not in self._waiting:
                self._waiting.append(pdf_id)
            self._status[pdf_id] = WikiStatus("waiting")
            ahead = self._waiting.index(pdf_id) + (self._building is not None)
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, name="wiki", daemon=True)
                self._worker.start()
        logger.info("Wiki queued", extra={"id": pdf_id, "ahead": ahead})

    def reset(self, pdf_id: str) -> None:
        """After a PDF is replaced: its pages are out of date until it is read again."""
        with self._lock:
            self._status.pop(pdf_id, None)
            if pdf_id in self._waiting:
                self._waiting.remove(pdf_id)
            self._stop_if_building(pdf_id)

    def _stop_if_building(self, pdf_id: str) -> None:
        """Cut off the LLM's answer for the PDF being built, if it is this one (under the
        lock): it is removed or replaced, so the next PDF starts now, not once the LLM is
        done (Larry's test of PR #123)."""
        if self._building is not None and self._building[0] == pdf_id and not self._stop.is_set():
            logger.info("Stopping the wiki build", extra={"id": pdf_id})
            self._stop.set()

    def forget(self, pdf_id: str) -> None:
        """After a PDF is removed: its pages go too, and the user's edits to them."""
        self.reset(pdf_id)
        with self._lock:
            (self.folder / f"{pdf_id}.json").unlink(missing_ok=True)
        self.edits.forget(pdf_id)
        self.history.forget(pdf_id)
        self._changed()

    def rebuild(self, pdf_id: str) -> bool:
        """Builds a PDF's wiki again with the LLM (R38), keeping the user's edits; whether it
        was queued (False: no such PDF, or not read yet). The pages built before stay readable
        until the new ones are saved."""
        if self.store.get(pdf_id) is None or self.readings.reading(pdf_id) is None:
            return False
        logger.info("Rebuilding wiki", extra={"id": pdf_id})
        self.queue(pdf_id)
        return True

    def edit(self, page_id: str, title: str, summary: str) -> dict[str, Any]:
        """Keeps the user's title and summary for an entry (R38) and returns its page. Raises
        EditError when there is no such entry or the edit can't be kept."""
        start = time.perf_counter()
        pdf_id = page_id.split("-", 1)[0]
        # Under the lock a new build is saved and its edits flagged with, so an edit belongs
        # either to the pages before it (and is flagged) or to the new ones (and isn't).
        with self._lock:
            saved = self._saved(pdf_id)
            if saved is None or find(from_saved(saved["outline"]), page_id) is None:
                raise EditError("No such wiki page.", status=404)
            self._start_history(pdf_id)
            edit = self.edits.save(pdf_id, page_id, title, summary)
            self._keep(pdf_id, "edited", title=edit["title"])
        logger.info(
            "Wiki entry edited",
            extra={
                "id": pdf_id,
                "entry": page_id,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        page = self.page(page_id)
        assert page is not None  # found above
        return page

    def undo_edit(self, page_id: str) -> bool:
        """Back to what the LLM built for an entry, or a lost edit discarded; whether there was
        an edit."""
        pdf_id = page_id.split("-", 1)[0]
        with self._lock:
            edit = self.edits.get(pdf_id).get(page_id)
            if edit is None:
                return False
            saved = self._saved(pdf_id)
            gone = saved is None or find(from_saved(saved["outline"]), page_id) is None
            self._start_history(pdf_id)
            if not self.edits.discard(pdf_id, page_id):
                return False
            self._keep(pdf_id, "discarded" if gone else "undone", title=edit["title"])
        logger.info("Wiki edit undone", extra={"id": pdf_id, "entry": page_id})
        return True

    def reviewed(self, page_id: str) -> bool:
        """The user has checked an edit flagged after a rebuild; whether there was one."""
        pdf_id = page_id.split("-", 1)[0]
        with self._lock:
            edit = self.edits.get(pdf_id).get(page_id)
            if edit is None:
                return False
            self._start_history(pdf_id)
            if not self.edits.reviewed(pdf_id, page_id):
                return False
            self._keep(pdf_id, "kept", title=edit["title"])
        logger.info("Wiki edit checked", extra={"id": pdf_id, "entry": page_id})
        return True

    def versions(self, pdf_id: str) -> list[dict[str, Any]] | None:
        """The PDF's wiki versions, newest first (R38a), or None if it has no wiki yet. A wiki
        built before its history began shows as it is now."""
        with self._lock:
            if self._saved(pdf_id) is None:
                return None
            self._start_history(pdf_id)
        return self.history.versions(pdf_id)

    def version(self, pdf_id: str, version_id: str) -> dict[str, Any] | None:
        """One version as the Wiki page shows it, to read: like contents()."""
        found = self.history.get(pdf_id, version_id)
        if found is None:
            return None
        wiki, edits = found["wiki"], found["edits"]
        return {
            "pdf_id": pdf_id,
            "pdf_name": wiki["name"],
            "id": found["id"],
            "at": found["at"],
            "change": found["change"],
            "entries": [marked(e, edits) for e in wiki["outline"]],
            "lost_edits": lost(wiki["outline"], edits),
        }

    def restore(self, pdf_id: str, version_id: str, force: bool = False) -> None:
        """Makes an earlier version the current wiki, as a new version (R38a). Raises
        HistoryError: 404 no such version, 409 while the wiki is being built, 412 when the
        version was built from an earlier copy of the PDF (unless `force`)."""
        found = self.history.get(pdf_id, version_id)
        if found is None:
            raise HistoryError("No such version of the wiki.", 404)
        with self._lock:
            self._make_current(pdf_id, found["wiki"], found["edits"], force)
            self._keep(pdf_id, "restored", restored_at=found["at"])
        logger.info("Wiki version restored", extra={"id": pdf_id, "version": version_id})

    def export(self, pdf_id: str) -> dict[str, Any] | None:
        """The PDF's current wiki and its whole history, to save to a file (R38a)."""
        with self._lock:
            saved = self._saved(pdf_id)
            if saved is None:
                return None
            self._start_history(pdf_id)
            # Under the lock every change keeps its version with, so the history matches.
            current = {"wiki": saved, "edits": self.edits.get(pdf_id)}
            history = self.history.everything(pdf_id)
        logger.info("Wiki saved to a file", extra={"id": pdf_id, "versions": len(history)})
        return wiki_file(pdf_id, saved["name"], saved["version"], current, history)

    def load(self, pdf_id: str, data: bytes, force: bool = False) -> int:
        """Loads a wiki file saved by export(): its current wiki becomes the PDF's, as a new
        version, and its versions join the history. How many versions it added. Raises
        HistoryError as restore() does, and 422 when it isn't this PDF's wiki file."""
        loaded = read_wiki_file(data, WIKI_FORMAT)
        if loaded["pdf_id"] != pdf_id:
            raise HistoryError(
                f"This file is the wiki of another PDF ({loaded.get('pdf_name') or 'unnamed'})."
            )
        current = loaded["current"]
        with self._lock:
            self._make_current(pdf_id, current["wiki"], current["edits"], force)
            added = self.history.add(pdf_id, loaded["history"])
            self._keep(pdf_id, "loaded")
        logger.info("Wiki loaded from a file", extra={"id": pdf_id, "versions_added": added})
        return added

    def _make_current(
        self, pdf_id: str, wiki: dict[str, Any], edits: dict[str, Any], force: bool
    ) -> None:
        """Saves a wiki and its edits as the PDF's current one. Called with the lock held."""
        pdf = self.store.get(pdf_id)
        if pdf is None:
            raise HistoryError("No such PDF.", 404)
        if pdf_id in self._waiting or (self._building or ("",))[0] == pdf_id:
            raise HistoryError(
                "The wiki is being built. Wait for it to finish, then try again.", 409
            )
        if wiki["version"] != version(pdf) and not force:
            raise HistoryError(
                "This wiki was built from an earlier copy of the PDF, so some of it may not "
                "match the PDF as it is now.",
                412,
            )
        self._start_history(pdf_id)
        before = self._stored(pdf_id)
        failed = HistoryError(
            "The wiki could not be saved, so nothing was changed. Try again.", 500
        )
        if not self._save({**wiki, "id": pdf_id, "name": pdf.name, "version": version(pdf)}):
            self._back_to(pdf_id, before)
            raise failed
        try:
            self.edits.replace(pdf_id, edits)  # all at once, or not at all
        except EditError as e:
            # The edits are as they were, so the wiki goes back to what they were made on.
            self._back_to(pdf_id, before)
            raise failed from e

    def _back_to(self, pdf_id: str, before: dict[str, Any] | None) -> None:
        """After a failed restore or load: the wiki as it was. Called with the lock held."""
        if before is None:
            (self.folder / f"{pdf_id}.json").unlink(missing_ok=True)
            self._status.pop(pdf_id, None)
            return
        if self._stored(pdf_id) != before and not self._save(before):
            logger.error("Could not put the wiki back after a failed change", extra={"id": pdf_id})
            return
        self._status[pdf_id] = done_status(before)  # still the current wiki, not a failed build

    def _start_history(self, pdf_id: str) -> None:
        """Before the first change to a wiki with no history yet (built before R38a, say), the
        wiki as it is now is kept, so the change can be undone. Called with the lock held."""
        if self.history.started(pdf_id):
            return
        saved = self._stored(pdf_id)
        if saved is not None:
            self._keep_version(pdf_id, saved, "start")

    def _keep(self, pdf_id: str, kind: Kind, **about: str) -> None:
        """Keeps the wiki as it is now as a new version. Called with the lock held."""
        saved = self._stored(pdf_id)
        if saved is not None:
            self._keep_version(pdf_id, saved, kind, **about)
        self._changed()

    def _changed(self) -> None:
        if self.when_changed is not None:
            self.when_changed()

    def building(self) -> bool:
        """Whether a wiki is being built or waits to be."""
        with self._lock:
            return self._worker is not None

    def _keep_version(self, pdf_id: str, saved: dict[str, Any], kind: Kind, **about: str) -> None:
        try:
            self.history.record(pdf_id, saved, self.edits.get(pdf_id), kind, **about)
        except HistoryError:
            pass  # logged; the change itself is made, only its version is missing

    def _stored(self, pdf_id: str) -> dict[str, Any] | None:
        """The wiki saved for a PDF, even one built from an earlier copy of it (so a rebuild of
        a replaced PDF keeps the old one in the history first)."""
        try:
            saved: dict[str, Any] = json.loads(
                (self.folder / f"{pdf_id}.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return None
        return saved if saved.get("format") == WIKI_FORMAT else None

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
                    remaining_s=remaining(
                        status, last_step - stage_started, now - last_step, self._part_s
                    ),
                )
            if status is not None and status.state == "waiting" and status.error is None:
                status = self._queued(pdf.id, status)
            if status is None or status.state == "done":
                saved = self._saved(pdf.id)
                status = done_status(saved) if saved else None
            if status is not None:
                result[pdf.id] = status
        return result

    def _queued(self, pdf_id: str, status: WikiStatus) -> WikiStatus:
        """A queued PDF's status, with what is built before it."""
        with self._lock:
            if pdf_id not in self._waiting:
                return status
            building = self._building
            ahead = self._waiting.index(pdf_id) + (building is not None)
        now = self.store.get(building[0]) if building is not None else None
        name = now.name if now is not None and now.id != pdf_id else None
        # The PDF being built was removed or replaced: its build stops once the LLM has given
        # the answer it is giving now.
        gone = building is not None and (now is None or version(now) != building[1])
        return replace(status, ahead=ahead, building_name=name, stopping=gone)

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
        """One PDF's up-to-date pages with their text, as saved, and the user's edits, or None
        if not built yet."""
        saved = self._saved(pdf_id)
        return None if saved is None else {**saved, "edits": self.edits.get(pdf_id)}

    def contents(self, pdf_id: str | None = None) -> list[dict[str, Any]]:
        """Every up-to-date table of contents (or one PDF's), as the wiki shows it (R37b): the
        whole outline, every level of it, detail pages' parts too, with the user's edits (R38)
        and any edits whose entries a rebuild no longer has."""
        found = []
        for pdf in self.store.list():
            saved = self._saved(pdf.id) if pdf_id in (None, pdf.id) else None
            if saved is not None:
                edits = self.edits.get(pdf.id)
                entries = [marked(e, edits) for e in saved["outline"]]
                found.append(
                    {
                        **summary(saved),
                        "entries": entries,
                        "lost_edits": lost(saved["outline"], edits),
                    }
                )
        return found

    def page(self, page_id: str) -> dict[str, Any] | None:
        """One entry of the outline as its page shows it, or None, with the trail of detail
        pages above it (R37b). A topic's has its whole text too."""
        pdf_id = page_id.split("-", 1)[0]
        saved = self._saved(pdf_id)
        if saved is None:
            return None
        outline = from_saved(saved["outline"])
        entry = find(outline, page_id)
        if entry is None:
            return None
        edits = self.edits.get(pdf_id)
        above = ancestors(outline, page_id) or []
        trail = [
            {"id": e.id, "title": edits[e.id]["title"] if e.id in edits else e.title}
            for e in above
            if e.detail
        ]
        texts = {page["id"]: page["text"] for page in saved["pages"]}
        text = {"text": texts[page_id]} if page_id in texts else {}
        return {**summary(saved), **marked(shown(entry), edits), "trail": trail, **text}

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
                self._stop = threading.Event()
                stop = self._stop
            token = ask_stop.set(stop)  # the LLM's answers for this PDF can be cut off
            try:
                built = self._build(pdf_id) or built
            except Exception as e:  # never let one PDF stop the PDFs queued after it
                logger.exception("Could not build the wiki", extra={"id": pdf_id, "error": repr(e)})
                self._set(pdf_id, WikiStatus("failed", error="Something went wrong building it."))
            finally:
                ask_stop.reset(token)
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
        # Each part's and outline step's time, with llama-server's timings for its requests,
        # saved with the pages for `imageskin time-pdf` (R96a).
        timings: list[dict[str, Any]] = []
        requests: list[dict[str, Any]] = []
        kept = reply_times.requests.set(requests)
        last = start

        def timed(stage: Stage, step: int) -> None:
            nonlocal last
            now = time.perf_counter()
            timings.append(
                {
                    "stage": stage,
                    "step": step,
                    "ended_ms": round((now - start) * 1000, 1),
                    "duration_ms": round((now - last) * 1000, 1),
                    "requests": requests[:],
                }
            )
            # Each step's time, and how much of its prompts llama-server reused (R98).
            logger.info(
                "Wiki step timed",
                extra={"id": pdf_id, "stage": stage, "step": step, **step_totals(timings[-1])},
            )
            requests.clear()
            last = now

        def still_wanted() -> None:
            """Stops the build, by Superseded, once the PDF is removed or replaced: after the
            answer the LLM is giving now, not after every part (Larry's test of PR #123)."""
            with self._lock:
                if (
                    self.store.get(pdf_id) != pdf
                    or pdf_id not in self._status
                    or pdf_id in self._waiting
                ):
                    raise Superseded

        def progress(part: int, parts: int) -> None:
            still_wanted()
            if part:  # 0: the parts are known, none is done yet
                self._stepped(pdf_id)
                timed("topics", part)
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
            still_wanted()  # replaced or removed meanwhile
            self._set(pdf_id, building)

        def wait_for_llm(error: LlmError, part: int, parts: int) -> None:
            pause(error, WikiStatus("building", part - 1, parts), part)

        try:
            parts_started = time.monotonic()
            wiki = self.build(pdf_id, reading["pieces"], progress, wait_for_llm)
            parts = wiki.parts
            if parts:
                self._save_pace(pdf_id, (time.monotonic() - parts_started) / parts)

            planned = 0

            def outline_progress(steps: int, steps_planned: int) -> None:
                still_wanted()
                self._stepped(pdf_id)
                if steps:
                    timed("outline", steps)
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
        except (Superseded, LlmCancelled):
            logger.info(
                "Wiki build stopped: the PDF was removed or replaced",
                extra={"id": pdf_id, "duration_s": round(time.perf_counter() - start, 1)},
            )
            return True
        except (WikiError, LlmError) as e:  # an LlmError here is a refusal, not an outage
            logger.error("Could not build the wiki", extra={"id": pdf_id, "error": str(e)})
            # A refusal's message names the LLM's address and its error, so the host is told
            # in plain words instead; the log keeps what it said.
            said = str(e) if isinstance(e, WikiError) else AI_REFUSED
            self._set(pdf_id, WikiStatus("failed", error=said))
            return True
        finally:
            reply_times.requests.reset(kept)
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
            "timings": timings,
        }
        with self._lock:
            if self.store.get(pdf_id) != pdf:
                return True  # replaced or removed meanwhile; it is built again, or not needed
            before = self._stored(pdf_id)
            self._start_history(pdf_id)  # the pages built before, if they have no history yet
            if not self._save(saved):
                return True
            try:
                # The edits made before these pages are to be checked against them.
                flagged = self.edits.flag_all(pdf_id)
            except EditError:
                flagged = 0  # logged; the edits are kept, just not flagged
            self._keep(pdf_id, "built" if before is None else "rebuilt")
        logger.info(
            "Wiki pages built",
            extra={
                "id": pdf_id,
                "upload_name": pdf.name,
                "parts": wiki.parts,
                "pages": len(wiki.pages),
                "detail_pages": sum(count_detail(e) for e in outline),
                "skipped_parts": wiki.skipped_parts,
                "flagged_edits": flagged,
                **(totals := llm_totals(timings)),
                "llm_reused_pct": reused_pct(totals),
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

    def _load_pace(self) -> float | None:
        try:
            pace = json.loads((self.folder / PACE_FILE).read_text(encoding="utf-8"))["part_s"]
            return float(pace) if pace > 0 else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _save_pace(self, pdf_id: str, part_s: float) -> None:
        self._part_s = part_s
        # Under the lock forget() takes, and not for a PDF removed meanwhile, so Delete my data
        # never finds the file made again after it (R31a).
        with self._lock:
            if self.store.get(pdf_id) is None:
                return
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
                (self.folder / PACE_FILE).write_text(
                    json.dumps({"part_s": round(part_s, 1)}), encoding="utf-8"
                )
            except OSError as e:
                logger.error("Could not save the wiki's pace", extra={"error": str(e)})
        logger.info("Wiki pace", extra={"part_s": round(part_s, 1)})

    def _stepped(self, pdf_id: str) -> None:
        with self._lock:
            self._last_step[pdf_id] = time.monotonic()

    def _set(self, pdf_id: str, status: WikiStatus) -> None:
        with self._lock:
            # A PDF replaced while it was built waits for its new pages; don't hide that.
            if pdf_id not in self._waiting and pdf_id in self._status:
                self._status[pdf_id] = status


def remaining(
    status: WikiStatus, steps_s: float, since_s: float, part_s: float | None = None
) -> float | None:
    """About how long the stage has left: the time its steps done so far took (`steps_s`), on
    average, for each step left, less the time since the last one (`since_s`), so it counts
    down between steps. Before the first part is done, the last build's time a part (`part_s`)
    stands in for it; with none, None."""
    if status.stage != "outline" and status.part < 1 and status.parts and part_s:
        return round(max(0.0, part_s * status.parts - since_s), 1)
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


def llm_totals(timings: list[dict[str, Any]]) -> dict[str, int]:
    """The LLM requests a build made, and llama-server's tokens read, reused from its cache and
    written across them (R96a); a provider sends no timings, so its tokens count 0."""
    requests = [r for step in timings for r in step["requests"]]
    totals = {"llm_requests": len(requests)}
    for key in ("prompt_n", "cache_n", "predicted_n"):
        totals[f"llm_{key}"] = sum(r.get(key, 0) for r in requests)
    return totals


def step_totals(step: dict[str, Any]) -> dict[str, Any]:
    """One step's time, its tokens read, reused and written, and the share of its prompts that
    was reused from llama-server's cache, in percent (R98)."""
    totals = llm_totals([step])
    return {"duration_ms": step["duration_ms"], **totals, "reused_pct": reused_pct(totals)}


def reused_pct(totals: dict[str, int]) -> float:
    """The share of the prompts' tokens llama-server reused from its cache, in percent."""
    prompt = totals["llm_prompt_n"] + totals["llm_cache_n"]
    return round(100 * totals["llm_cache_n"] / prompt, 1) if prompt else 0.0


def summary(saved: dict[str, Any]) -> dict[str, Any]:
    return {"pdf_id": saved["id"], "pdf_name": saved["name"]}
