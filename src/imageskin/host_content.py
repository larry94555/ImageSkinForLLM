"""A host's PDFs, kept once for all their sites (roadmap R258, item 209).

R61f moved each host's PDFs into their site. A host can now have several sites (R256), so each
host's PDFs, with everything made from them (what was read, the wiki with its outline, the
host's edits and the wiki's history), are kept once in a folder of the host's beside their
sites, `hosts/<library>/content`, where `<library>` is a name kept with the host's account. The
folder's `sites.json` says which of the host's sites use each PDF.

The PDFs are read and their wikis built once, by one reading job and one wiki job for the host,
whichever of their sites asks. Each site sees only the PDFs it uses, through `SiteContent`,
`SiteReadings` and `SiteWiki`, which stand in for the store and the two jobs in the site's app:
another host's sites never see them, and taking a PDF off a site deletes it only once no site of
the host uses it. A change to a PDF or its wiki shows on every site that uses it. The lessons
written ahead (R98a) are each site's own, from the PDFs it uses, so they stay in the site's
folder.

The main address, and a site with no host, keep their PDFs in their own folder, as before.
"""

import filecmp
import json
import logging
import os
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from imageskin.content import ContentStore, Pdf
from imageskin.reading_job import ReadingJob, ReadingStatus
from imageskin.uploads import UploadError
from imageskin.wiki_edits import EditError
from imageskin.wiki_history import HistoryError
from imageskin.wiki_job import WikiJob, WikiStatus

logger = logging.getLogger(__name__)

LIBRARIES_FOLDER = "hosts"  # beside `sites`, in the service's home
USES_FILE = "sites.json"  # in the host's content folder
# Where each PDF's files are, by its id, as R61f moved them (`site_moves`).
PDF_FOLDERS = ("pdfs", "read", "wiki")
NOT_SAVED = "The PDF's sites could not be saved just now. Try again."


def library_home(home: Path, key: str) -> Path:
    """The folder the host's PDFs are kept in, whose name is kept with their account."""
    if not key.isalnum():
        raise ValueError(f"{key!r} is not a host folder's name.")
    return home / LIBRARIES_FOLDER / key


class UsesUnreadable(Exception):
    """`sites.json` is there but can't be read as a record of each PDF's sites."""


class PdfSites:
    """Which of the host's sites use each PDF, kept in `sites.json` in their content folder:
    each PDF's id with its sites, in the order they were given it."""

    def __init__(self, root: Path) -> None:
        self.path = root / USES_FILE
        self._lock = threading.Lock()

    def read(self) -> dict[str, list[str]]:
        """The record; UsesUnreadable when the file is there but isn't one, so it is never
        written over."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.error("Could not read the PDFs' sites", extra={"error": str(e)})
            raise UsesUnreadable(str(e)) from e
        if not (
            isinstance(data, dict)
            and all(
                isinstance(sites, list) and all(isinstance(s, str) for s in sites)
                for sites in data.values()
            )
        ):
            logger.error("Could not read the PDFs' sites", extra={"error": "not a record"})
            raise UsesUnreadable("not a record")
        return data

    def used_by(self, site: str) -> set[str]:
        """The PDFs the site uses; none when the record can't be read, so a site never sees
        another's."""
        try:
            return {pdf for pdf, sites in self.read().items() if site in sites}
        except UsesUnreadable:
            return set()

    def sites_of(self, pdf_id: str) -> list[str]:
        try:
            return list(self.read().get(pdf_id, []))
        except UsesUnreadable:
            return []

    def change(self, change: Callable[[dict[str, list[str]]], None]) -> dict[str, list[str]]:
        """Change the record and save it, under the lock: the record saved. Raises
        UsesUnreadable or OSError, with nothing changed."""
        with self._lock:
            data = self.read()
            change(data)
            data = {pdf: sites for pdf, sites in data.items() if sites}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            part = self.path.with_suffix(".part")
            part.write_text(json.dumps(data, indent=1), encoding="utf-8")
            os.replace(part, self.path)
            return data

    def add(self, pdf_id: str, site: str) -> None:
        def given(data: dict[str, list[str]]) -> None:
            sites = data.setdefault(pdf_id, [])
            if site not in sites:
                sites.append(site)

        self.change(given)

    def take_off(self, pdf_id: str, site: str) -> list[str]:
        """Take the PDF off the site: the sites that still use it."""

        def taken(data: dict[str, list[str]]) -> None:
            data[pdf_id] = [s for s in data.get(pdf_id, []) if s != site]

        return self.change(taken).get(pdf_id, [])

    def drop_site(self, site: str) -> list[str]:
        """Take every PDF off a deleted site: the PDFs no site uses now."""
        before = self.read()

        def dropped(data: dict[str, list[str]]) -> None:
            for pdf_id in data:
                data[pdf_id] = [s for s in data[pdf_id] if s != site]

        after = self.change(dropped)
        return sorted(pdf for pdf in before if pdf not in after)


@dataclass
class Library:
    """The host's PDFs, and the one reading job and wiki job that serve all their sites. What
    each site's app gives the jobs to call once a wiki changes, or the builds are done, is
    called for every site that gave one."""

    folder: Path
    store: ContentStore
    readings: ReadingJob
    wiki: WikiJob
    uses: PdfSites
    changed: dict[str, Callable[[], None]] = field(default_factory=dict)
    idle: dict[str, Callable[[], None]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.readings.on_read = self.wiki.read
        self.wiki.when_changed = lambda: self._each(self.changed, "changed")
        self.wiki.when_idle = lambda: self._each(self.idle, "idle")

    @staticmethod
    def _each(calls: dict[str, Callable[[], None]], what: str) -> None:
        for site, call in list(calls.items()):
            try:
                call()
            except Exception:
                logger.exception("Site not told the wiki changed", extra={"site": site, "on": what})

    def delete(self, pdf_id: str) -> bool:
        """Delete the PDF, with everything made from it: whether there was one. UploadError when
        its file can't be deleted, with nothing changed."""
        removed = self.store.remove(pdf_id)
        if removed:
            self.readings.forget(pdf_id)
            self.wiki.forget(pdf_id)
        return removed

    def site_deleted(self, site: str) -> list[str]:
        """A deleted site's PDFs (R69a): taken off it, and deleted when no other site of the
        host uses them. The PDFs deleted; each one that can't be is logged, and kept."""
        try:
            unused = self.uses.drop_site(site)
        except (UsesUnreadable, OSError) as e:
            logger.error("Deleted site's PDFs kept", extra={"site": site, "error": str(e)})
            return []
        self.changed.pop(site, None)
        self.idle.pop(site, None)
        deleted = []
        for pdf_id in unused:
            try:
                if self.delete(pdf_id):
                    deleted.append(pdf_id)
            except UploadError as e:
                logger.error("Deleted site's PDF kept", extra={"id": pdf_id, "error": str(e)})
        logger.info("Deleted site's PDFs taken off", extra={"site": site, "deleted": deleted})
        return deleted


class Libraries:
    """Each host's library, made once, the first time one of their sites' apps asks for it."""

    def __init__(self) -> None:
        self._made: dict[Path, Library] = {}
        self._lock = threading.Lock()

    def open(self, folder: Path, make: Callable[[ContentStore], Library]) -> Library:
        with self._lock:
            library = self._made.get(folder)
            if library is None:
                start = time.perf_counter()
                library = make(ContentStore(folder))
                self._made[folder] = library
                logger.info(
                    "Host's PDFs opened",
                    extra={
                        "folder": str(folder),
                        "pdfs": len(library.store.list()),
                        "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    },
                )
            return library

    def find(self, folder: Path) -> Library | None:
        with self._lock:
            return self._made.get(folder)

    def site_deleted(self, home: Path, site: str) -> list[str]:
        """A site was deleted (R69a): its PDFs are taken off it in its host's folder, and each
        one no other site uses is deleted, with everything made from it. The PDFs deleted. Each
        host's folder is looked in, as the site's record, which named its host, is gone."""
        deleted: list[str] = []
        top = home / LIBRARIES_FOLDER
        for folder in sorted(top.iterdir()) if top.is_dir() else []:
            uses = PdfSites(folder / "content")
            if not any(site in sites for sites in _readable(uses).values()):
                continue
            library = self.find(folder)
            if library is not None:
                deleted += library.site_deleted(site)
                continue
            try:
                unused = uses.drop_site(site)
            except (UsesUnreadable, OSError) as e:
                logger.error("Deleted site's PDFs kept", extra={"site": site, "error": str(e)})
                continue
            for pdf_id in unused:
                if delete_files(folder, pdf_id):
                    deleted.append(pdf_id)
            logger.info("Deleted site's PDFs taken off", extra={"site": site, "deleted": unused})
        return deleted


def _readable(uses: PdfSites) -> dict[str, list[str]]:
    try:
        return uses.read()
    except UsesUnreadable:
        return {}


def delete_files(library: Path, pdf_id: str) -> bool:
    """Delete a PDF and every file made from it in the host's folder, while no app has it open:
    whether all went. One that can't be deleted is logged."""
    done = True
    for folder in PDF_FOLDERS:
        for path in sorted((library / "content" / folder).glob(f"{pdf_id}.*")):
            try:
                shutil.rmtree(path) if path.is_dir() else path.unlink()
            except OSError as e:
                logger.error(
                    "Deleted site's PDF file kept", extra={"path": str(path), "error": str(e)}
                )
                done = False
    return done


def move_site_pdfs(site_folder: Path, library: Path, site: str, uses: PdfSites) -> int:
    """Move the site's PDFs, with everything made from them, into the host's folder, each one
    used by this site (R258): the PDFs moved. Each moves once all its files have; a file already
    there is left where it was, as R61f's move does. Run each time the site's app is made, so a
    move cut short is finished at the next start."""
    pdfs = site_folder / "content" / "pdfs"
    # By every file there, so a file a move cut short left behind is seen too.
    ids = sorted({p.name.split(".", 1)[0] for p in pdfs.iterdir()}) if pdfs.is_dir() else []
    moved = 0
    for pdf_id in ids:
        paths = [
            path
            for folder in PDF_FOLDERS
            for path in sorted((site_folder / "content" / folder).glob(f"{pdf_id}.*"))
        ]
        went = False
        try:
            uses.add(pdf_id, site)  # first, so a moved PDF is never left with no site
            for path in paths:
                target = library / path.relative_to(site_folder)
                if target.exists():
                    if path.is_file() and target.is_file() and filecmp.cmp(path, target, False):
                        path.unlink()  # a move cut short: the same file is there already
                    else:
                        logger.warning(
                            "Already with the host; left where it was", extra={"path": str(path)}
                        )
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(path, target)
                went = True
        except (UsesUnreadable, OSError) as e:
            logger.error(
                "Site's PDF left in the site", extra={"site": site, "id": pdf_id, "error": str(e)}
            )
            continue
        moved += went
    if moved:
        logger.info(
            "Site PDFs moved to the host's folder",
            extra={"site": site, "pdfs": moved, "folder": str(library)},
        )
    return moved


class SiteContent:
    """The host's PDF store as one of their sites sees it: only the PDFs it uses."""

    def __init__(self, library: Library, site: str) -> None:
        self._library = library
        self._store = library.store
        self._uses = library.uses
        self.site = site
        self.root = self._store.root
        self.folder = self._store.folder

    def uses(self, pdf_id: str | None) -> bool:
        return bool(pdf_id) and pdf_id in self._uses.used_by(self.site)

    def list(self) -> list[Pdf]:
        used = self._uses.used_by(self.site)
        return [pdf for pdf in self._store.list() if pdf.id in used]

    def get(self, pdf_id: str | None) -> Pdf | None:
        return self._store.get(pdf_id) if self.uses(pdf_id) else None

    def path(self, pdf_id: str | None) -> Path | None:
        return self._store.path(pdf_id) if self.uses(pdf_id) else None

    def snapshot(self, pdf_id: str, dest: Path) -> Pdf | None:
        return self._store.snapshot(pdf_id, dest) if self.uses(pdf_id) else None

    def add(self, name: str | None, data: BinaryIO) -> Pdf:
        pdf = self._store.add(name, data)
        try:
            self._uses.add(pdf.id, self.site)
        except (UsesUnreadable, OSError) as e:
            logger.error("PDF not given to the site", extra={"site": self.site, "error": str(e)})
            self._store.remove(pdf.id)
            raise UploadError(NOT_SAVED, status=500) from e
        return pdf

    def replace(self, pdf_id: str, name: str | None, data: BinaryIO) -> Pdf:
        if not self.uses(pdf_id):
            raise UploadError("No such PDF.", status=404)
        return self._store.replace(pdf_id, name, data)

    def remove(self, pdf_id: str) -> bool:
        """Take the PDF off this site: deleted, with all made from it, once no other site of
        the host uses it. False when this site doesn't use it."""
        if not self.uses(pdf_id):
            return False
        others = [s for s in self._uses.sites_of(pdf_id) if s != self.site]
        if not others:
            self._library.delete(pdf_id)  # UploadError, with nothing changed, if it can't be
        try:
            self._uses.take_off(pdf_id, self.site)
        except (UsesUnreadable, OSError) as e:
            logger.error("PDF not taken off the site", extra={"site": self.site, "error": str(e)})
            raise UploadError(NOT_SAVED, status=500) from e
        logger.info(
            "PDF taken off the site", extra={"site": self.site, "id": pdf_id, "still_on": others}
        )
        return True


class SiteReadings:
    """The host's reading job as one of their sites sees it."""

    def __init__(self, library: Library, content: SiteContent) -> None:
        self._job = library.readings
        self._content = content
        self.store = content
        self.folder = self._job.folder

    def catch_up(self) -> None:
        self._job.catch_up()

    def queue(self, pdf: Pdf) -> None:
        self._job.queue(pdf)

    def forget(self, pdf_id: str) -> None:
        """Only once the PDF is deleted, not when it is only taken off this site."""
        if self._content._store.get(pdf_id) is None:
            self._job.forget(pdf_id)

    def statuses(self) -> dict[str, ReadingStatus]:
        used = {pdf.id for pdf in self._content.list()}
        return {k: v for k, v in self._job.statuses().items() if k in used}

    def reading(self, pdf_id: str) -> dict[str, Any] | None:
        return self._job.reading(pdf_id) if self._content.uses(pdf_id) else None

    def wait(self, timeout: float = 30) -> None:
        self._job.wait(timeout)


class SiteWiki:
    """The host's wiki job as one of their sites sees it: the wikis of the PDFs it uses. Its
    `folder` is the site's own, where its lessons are written ahead (R98a)."""

    def __init__(self, library: Library, content: SiteContent, folder: Path) -> None:
        self._library = library
        self._job = library.wiki
        self._content = content
        self.store = content
        self.readings = library.readings
        self.folder = folder

    @property
    def when_changed(self) -> Callable[[], None] | None:
        return self._library.changed.get(self._content.site)

    @when_changed.setter
    def when_changed(self, call: Callable[[], None] | None) -> None:
        self._set(self._library.changed, call)

    @property
    def when_idle(self) -> Callable[[], None] | None:
        return self._library.idle.get(self._content.site)

    @when_idle.setter
    def when_idle(self, call: Callable[[], None] | None) -> None:
        self._set(self._library.idle, call)

    def _set(self, calls: dict[str, Callable[[], None]], call: Callable[[], None] | None) -> None:
        if call is None:
            calls.pop(self._content.site, None)
        else:
            calls[self._content.site] = call

    def _uses(self, pdf_or_page: str | None) -> bool:
        return pdf_or_page is not None and self._content.uses(pdf_or_page.split("-", 1)[0])

    # The whole job, for every site.
    def catch_up(self) -> None:
        self._job.catch_up()

    def read(self, pdf_id: str) -> None:
        self._job.read(pdf_id)

    def queue(self, pdf_id: str) -> None:
        self._job.queue(pdf_id)

    def reset(self, pdf_id: str) -> None:
        self._job.reset(pdf_id)

    def building(self) -> bool:
        return self._job.building()

    def wait(self, timeout: float = 30) -> None:
        self._job.wait(timeout)

    def forget(self, pdf_id: str) -> None:
        """Only once the PDF is deleted, not when it is only taken off this site."""
        if self._library.store.get(pdf_id) is None:
            self._job.forget(pdf_id)

    # What the site sees: only the wikis of the PDFs it uses.
    def statuses(self) -> dict[str, WikiStatus]:
        used = {pdf.id for pdf in self._content.list()}
        return {k: v for k, v in self._job.statuses().items() if k in used}

    def pages(self, pdf_id: str | None = None) -> list[dict[str, Any]]:
        if pdf_id is not None and not self._uses(pdf_id):
            return []
        used = {pdf.id for pdf in self._content.list()}
        return [p for p in self._job.pages(pdf_id) if p.get("pdf_id") in used]

    def contents(self, pdf_id: str | None = None) -> list[dict[str, Any]]:
        if pdf_id is not None and not self._uses(pdf_id):
            return []
        used = {pdf.id for pdf in self._content.list()}
        return [c for c in self._job.contents(pdf_id) if c.get("pdf_id") in used]

    def page(self, page_id: str) -> dict[str, Any] | None:
        return self._job.page(page_id) if self._uses(page_id) else None

    def built(self, pdf_id: str) -> dict[str, Any] | None:
        return self._job.built(pdf_id) if self._uses(pdf_id) else None

    def rebuild(self, pdf_id: str) -> bool:
        return self._uses(pdf_id) and self._job.rebuild(pdf_id)

    def edit(self, page_id: str, title: str, summary: str) -> dict[str, Any]:
        if not self._uses(page_id):
            raise EditError("No such wiki page.", status=404)
        return self._job.edit(page_id, title, summary)

    def undo_edit(self, page_id: str) -> bool:
        return self._uses(page_id) and self._job.undo_edit(page_id)

    def reviewed(self, page_id: str) -> bool:
        return self._uses(page_id) and self._job.reviewed(page_id)

    def versions(self, pdf_id: str) -> list[dict[str, Any]] | None:
        return self._job.versions(pdf_id) if self._uses(pdf_id) else None

    def version(self, pdf_id: str, version_id: str) -> dict[str, Any] | None:
        return self._job.version(pdf_id, version_id) if self._uses(pdf_id) else None

    def restore(self, pdf_id: str, version_id: str, force: bool = False) -> None:
        if not self._uses(pdf_id):
            raise HistoryError("No such version of the wiki.", 404)
        self._job.restore(pdf_id, version_id, force)

    def export(self, pdf_id: str) -> dict[str, Any] | None:
        return self._job.export(pdf_id) if self._uses(pdf_id) else None

    def load(self, pdf_id: str, data: bytes, force: bool = False) -> int:
        if not self._uses(pdf_id):
            raise HistoryError("No such PDF.", 404)
        return self._job.load(pdf_id, data, force)
