"""A host's PDFs on several of their sites: kept once (roadmap R258, item 209). Each host's PDFs,
with everything made from them, are kept once in a folder of the host's beside their sites, read
and built once, and each site sees only the PDFs it uses; another host's sites never see them."""

import io
import json
import logging
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_site_addresses import PASSWORD, with_hosts
from test_wiki_job import one_page_per_piece

from imageskin import admin
from imageskin.app import create_app
from imageskin.content import ContentStore
from imageskin.host_content import (
    LIBRARIES_FOLDER,
    Libraries,
    Library,
    PdfSites,
    SiteContent,
    delete_files,
    library_home,
    move_site_pdfs,
)
from imageskin.hosts import LIBRARY
from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.reading_job import ReadingJob
from imageskin.sites import Service, SiteApps, site_home, site_matcher
from imageskin.uploads import PhotoResult, UploadError
from imageskin.wiki_job import WikiJob

pytestmark = pytest.mark.real_hosts

ANN, BOB = "ann@example.com", "bob@example.com"
A, B, C = "http://a.localhost", "http://b.localhost", "http://c.localhost"
PDF = b"%PDF-1.4\n%fake\n"


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


class Served:
    """Ann with sites a and b, Bob with site c; how often a PDF was read."""

    def __init__(self, tmp_path: Path) -> None:
        self.home = tmp_path / "home"
        self.service: Service = with_hosts(self.home, ANN, BOB)
        self.service.sites.add("a", ANN)
        self.service.sites.add("b", ANN)
        self.service.sites.add("c", BOB)
        self.made: dict[str, FastAPI] = {}
        self.read: list[str] = []
        self.apps = SiteApps(self.make, site_matcher(self.service.sites, "me0.ai"))

    def reading(self, path: Path, progress: Progress) -> Reading:
        self.read.append(path.name)
        return Reading("text", 1, [Piece(1, "paragraph", "Mars is red.")], [])

    def make(self, site: str) -> FastAPI:
        self.made[site] = create_app(
            site_home(site, self.home),
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            read_pdf=self.reading,
            build_wiki=one_page_per_piece,
            lessons_ahead=False,
            service=self.service,
            site=site,
        )
        return self.made[site]

    def host(self, address: str, email: str) -> TestClient:
        browser = TestClient(self.apps, base_url=address)
        answer = browser.post("/api/host/sign-in", json={"email": email, "password": PASSWORD})
        assert answer.is_success, answer.text
        browser.post("/api/consent", json={"agreed": True})
        return browser

    def library(self, email: str = ANN) -> Path:
        key = self.service.host_accounts.library_of(email, make=False)
        assert key
        return library_home(self.home, key)

    def uses(self, email: str = ANN) -> dict[str, list[str]]:
        return PdfSites(self.library(email) / "content").read()

    def settle(self, site: str) -> None:
        self.made[site].state.readings.wait()
        self.made[site].state.wiki.wait()


def seen(browser: TestClient) -> dict[str, Any]:
    """What a site shows of its PDFs: the list, the wiki's pages and builds."""
    return {
        "pdfs": [p["name"] for p in browser.get("/api/content").json()],
        "pages": [p["id"] for p in browser.get("/api/wiki").json()],
        "builds": sorted(browser.get("/api/wiki/builds").json()),
    }


def test_a_pdf_is_kept_once_in_the_hosts_folder_and_seen_only_where_it_is_used(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    s = Served(tmp_path)
    with caplog.at_level(logging.INFO):
        ann_a, ann_b, bob_c = s.host(A, ANN), s.host(B, ANN), s.host(C, BOB)
        pdf = ann_a.post("/api/content", files={"file": ("mars.pdf", io.BytesIO(PDF))}).json()
    s.settle("a")
    assert "Host's PDFs opened" in caplog.messages
    # Kept in Ann's own folder beside her sites, used by site a, and in no site's folder.
    library = s.library()
    assert library.parent == s.home / LIBRARIES_FOLDER
    assert (library / "content" / "pdfs" / f"{pdf['id']}.pdf").read_bytes() == PDF
    assert (library / "content" / "wiki" / f"{pdf['id']}.json").is_file()
    assert s.uses() == {pdf["id"]: ["a"]}
    assert not list(s.home.glob("sites/*/content/pdfs/*.pdf"))
    page = f"{pdf['id']}-p1"
    assert seen(ann_a) == {"pdfs": ["mars.pdf"], "pages": [page], "builds": [pdf["id"]]}
    assert ann_a.get(f"/api/wiki/{page}").json()["text"] == "Mars is red."
    exported = ann_a.get(f"/api/content/{pdf['id']}/wiki/file").content
    version = ann_a.get(f"/api/content/{pdf['id']}/wiki/history").json()[0]["id"]
    history = f"/api/content/{pdf['id']}/wiki/history/{version}"
    # Ann's other site doesn't use it, and Bob's never sees it: nothing listed, nothing at its
    # address, whether the PDF, its wiki or its history.
    for other in (ann_b, bob_c):
        assert seen(other) == {"pdfs": [], "pages": [], "builds": []}
        assert other.get(f"/api/content/{pdf['id']}").status_code == 404
        assert other.get(f"/api/wiki/{page}").status_code == 404
        assert other.get(f"/api/wiki/contents?pdf={pdf['id']}").json() == []
        assert other.get(f"/api/content/{pdf['id']}/wiki/history").status_code == 404
        assert (
            other.put(f"/api/wiki/{page}", json={"title": "x", "summary": "y"}).status_code == 404
        )
        assert other.post(f"/api/content/{pdf['id']}/wiki/rebuild").status_code == 404
        assert other.delete(f"/api/content/{pdf['id']}").status_code == 404
        assert other.get(f"/api/content/{pdf['id']}/wiki").status_code == 404
        assert other.get(f"/api/content/{pdf['id']}/wiki/file").status_code == 404
        assert other.get(history).status_code == 404
        assert other.post(f"{history}/restore").status_code == 404
        loaded = other.post(
            f"/api/content/{pdf['id']}/wiki/file", files={"file": ("w.json", exported)}
        )
        assert loaded.status_code == 404
        assert other.delete(f"/api/wiki/{page}/edit").status_code == 404
        assert other.post(f"/api/wiki/{page}/reviewed").status_code == 404
        replaced = other.put(f"/api/content/{pdf['id']}", files={"file": ("x.pdf", PDF)})
        assert replaced.status_code == 404
    assert (library / "content" / "pdfs" / f"{pdf['id']}.pdf").is_file()

    # Given site b too (R258a's picker): b sees the same PDF and wiki, read and built once.
    PdfSites(library / "content").add(pdf["id"], "b")
    assert seen(ann_b) == seen(ann_a)
    assert len(s.read) == 1
    # An edit on one site shows on the other.
    edited = ann_b.put(f"/api/wiki/{page}", json={"title": "Red planet", "summary": "Mars."})
    assert edited.is_success, edited.text
    assert ann_a.get(f"/api/wiki/{page}").json()["title"] == "Red planet"

    # Removed on a, it stays on b with its wiki; removed on b, it is deleted with all of it.
    with caplog.at_level(logging.INFO):
        assert ann_a.delete(f"/api/content/{pdf['id']}").is_success
    assert "PDF taken off the site" in caplog.messages
    assert seen(ann_a)["pdfs"] == [] and seen(ann_b)["pdfs"] == ["mars.pdf"]
    assert ann_b.get(f"/api/wiki/{page}").json()["title"] == "Red planet"
    assert s.uses() == {pdf["id"]: ["b"]}
    assert ann_b.delete(f"/api/content/{pdf['id']}").is_success
    assert seen(ann_b) == {"pdfs": [], "pages": [], "builds": []}
    assert s.uses() == {}
    assert not [p for p in (library / "content").rglob(f"{pdf['id']}*")]


def test_a_sites_pdfs_move_to_its_hosts_folder_when_its_app_is_made(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A site from before keeps its PDFs in its own folder (R61f): they move to the host's
    folder, with all made from them, each used by that site."""
    s = Served(tmp_path)
    site_a = site_home("a", s.home)
    store = ContentStore(site_a)
    pdf = store.add("old.pdf", io.BytesIO(PDF))
    (site_a / "content" / "wiki").mkdir(parents=True)
    (site_a / "content" / "wiki" / f"{pdf.id}.edits.json").write_text("{}")
    (site_a / "content" / "wiki" / "lessons.json").write_text("{}")  # the site's own
    with caplog.at_level(logging.INFO):
        ann_a = s.host(A, ANN)
        s.settle("a")
    assert "Site PDFs moved to the host's folder" in caplog.messages
    library = s.library()
    assert (library / "content" / "pdfs" / f"{pdf.id}.pdf").is_file()
    assert (library / "content" / "wiki" / f"{pdf.id}.edits.json").is_file()
    assert (site_a / "content" / "wiki" / "lessons.json").is_file()
    assert not list((site_a / "content" / "pdfs").glob("*"))
    assert s.uses() == {pdf.id: ["a"]}
    assert seen(ann_a)["pdfs"] == ["old.pdf"]
    assert seen(s.host(B, ANN))["pdfs"] == []
    # Made again, as at the next start, nothing more moves, and a file left behind by a move
    # cut short, the same as the one moved, goes.
    left = site_a / "content" / "pdfs" / f"{pdf.id}.pdf"
    left.write_bytes(PDF)
    assert move_site_pdfs(site_a, library, "a", PdfSites(library / "content")) == 0
    assert not left.exists()


def test_a_deleted_sites_pdfs_go_unless_another_of_the_hosts_sites_uses_them(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    s = Served(tmp_path)
    ann_a = s.host(A, ANN)
    only_a = ann_a.post("/api/content", files={"file": ("a.pdf", io.BytesIO(PDF))}).json()["id"]
    shared = ann_a.post("/api/content", files={"file": ("ab.pdf", io.BytesIO(PDF))}).json()["id"]
    s.settle("a")
    PdfSites(s.library() / "content").add(shared, "b")
    with caplog.at_level(logging.INFO):
        assert s.service.sites.delete("a", "test")
    assert "Deleted site's PDFs taken off" in caplog.messages
    assert s.uses() == {shared: ["b"]}
    pdfs = s.library() / "content" / "pdfs"
    assert not (pdfs / f"{only_a}.pdf").exists() and (pdfs / f"{shared}.pdf").is_file()
    assert seen(s.host(B, ANN))["pdfs"] == ["ab.pdf"]


def test_a_deleted_sites_pdfs_go_while_no_app_has_its_hosts_folder_open(tmp_path: Path) -> None:
    """At a start, a site can be deleted before any of its host's sites is used."""
    s = Served(tmp_path)
    key = s.service.host_accounts.library_of(ANN)
    assert key
    library = library_home(s.home, key)
    pdf = ContentStore(library).add("a.pdf", io.BytesIO(PDF))
    (library / "content" / "wiki").mkdir(parents=True)
    (library / "content" / "wiki" / f"{pdf.id}.history").mkdir()
    (library / "content" / "wiki" / f"{pdf.id}.history" / "v.json").write_text("{}")
    PdfSites(library / "content").add(pdf.id, "a")
    assert s.service.sites.delete("a", "test")
    assert s.uses() == {}
    assert not list((library / "content").rglob(f"{pdf.id}*"))
    assert delete_files(library, pdf.id)  # nothing left to delete


def test_the_hosts_pdfs_count_once_in_their_disk_space(tmp_path: Path) -> None:
    s = Served(tmp_path)
    ann_a, ann_b = s.host(A, ANN), s.host(B, ANN)
    before = ann_a.get("/api/host/disk").json()["pdfs"]
    pdf = ann_a.post("/api/content", files={"file": ("a.pdf", io.BytesIO(PDF))}).json()["id"]
    s.settle("a")
    once = ann_a.get("/api/host/disk").json()["pdfs"]
    own = site_home("a", s.home) / "content"
    library = sum(p.stat().st_size for p in s.library().rglob("*") if p.is_file())
    assert once == library + sum(p.stat().st_size for p in own.rglob("*") if p.is_file())
    assert once - before >= library
    PdfSites(s.library() / "content").add(pdf, "b")
    # Used by both sites, counted once: the same on each, and the PDF's size only once.
    twice = ann_b.get("/api/host/disk").json()["pdfs"]
    assert twice == ann_a.get("/api/host/disk").json()["pdfs"] < once + len(PDF)
    bobs = s.host(C, BOB).get("/api/host/disk").json()["pdfs"]
    assert bobs == 0  # Ann's folder is never Bob's


def test_delete_my_data_takes_the_pdfs_off_its_own_site_only(tmp_path: Path) -> None:
    s = Served(tmp_path)
    ann_a, ann_b = s.host(A, ANN), s.host(B, ANN)
    pdf = ann_a.post("/api/content", files={"file": ("a.pdf", io.BytesIO(PDF))}).json()["id"]
    s.settle("a")
    PdfSites(s.library() / "content").add(pdf, "b")
    deleted = ann_a.delete("/api/data")
    assert deleted.is_success, deleted.text
    assert seen(ann_b)["pdfs"] == ["a.pdf"]
    assert s.uses() == {pdf: ["b"]}


def test_a_record_of_sites_that_cant_be_read_shows_nothing_and_adds_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    s = Served(tmp_path)
    ann_a = s.host(A, ANN)
    ann_a.post("/api/content", files={"file": ("a.pdf", io.BytesIO(PDF))})
    s.settle("a")
    uses = s.library() / "content" / "sites.json"
    uses.write_text("not json")
    with caplog.at_level(logging.ERROR):
        assert seen(ann_a)["pdfs"] == []
        refused = ann_a.post("/api/content", files={"file": ("b.pdf", io.BytesIO(PDF))})
    assert refused.status_code == 500
    assert "Could not read the PDFs' sites" in caplog.messages
    assert uses.read_text() == "not json"  # never written over
    assert len(list((s.library() / "content" / "pdfs").glob("*.pdf"))) == 1


def test_the_hosts_folder_is_named_once_and_kept_when_their_email_changes(tmp_path: Path) -> None:
    s = Served(tmp_path)
    accounts = s.service.host_accounts
    assert accounts.library_of(ANN, make=False) is None
    key = accounts.library_of(ANN)
    assert key and accounts.library_of(ANN) == key
    assert json.loads((s.home / "hosts.json").read_text())["hosts"][ANN][LIBRARY] == key
    assert accounts.library_of("nobody@example.com") is None
    token = accounts.email_change(ANN, "ann2@example.com")
    assert accounts.change_email(token) is not None
    assert accounts.library_of("ann2@example.com", make=False) == key
    with pytest.raises(ValueError):
        library_home(s.home, "../x")


def shared_pdf(s: Served) -> tuple[str, Path]:
    """A PDF on Ann's sites a and b, read and built: its id and Ann's folder."""
    ann_a = s.host(A, ANN)
    s.host(B, ANN)
    pdf = ann_a.post("/api/content", files={"file": ("a.pdf", io.BytesIO(PDF))}).json()["id"]
    s.settle("a")
    PdfSites(s.library() / "content").add(pdf, "b")
    return pdf, s.library()


def reopened(s: Served, folder: Path) -> Library:
    """Ann's folder opened again, as at the next start."""

    def make(store: ContentStore) -> Library:
        readings = ReadingJob(store, s.reading)
        return Library(
            folder,
            store,
            readings,
            WikiJob(store, readings, one_page_per_piece),
            PdfSites(store.root),
        )

    return Libraries().open(folder, make)


def test_two_sites_taking_a_pdf_off_at_once_delete_it_once(tmp_path: Path) -> None:
    """Codex's review of PR #305: both sites see the other still using it before either takes
    it off; the one whose change leaves no site deletes it, so it is never left behind."""
    s = Served(tmp_path)
    pdf, folder = shared_pdf(s)
    library = s.service.libraries.find(folder)
    assert library is not None
    both = threading.Barrier(2)
    checked = SiteContent.uses

    def uses(self: SiteContent, pdf_id: str | None) -> bool:
        found = checked(self, pdf_id)
        both.wait(timeout=5)  # each has seen the PDF on both sites
        return found

    results: list[bool] = []
    with patch.object(SiteContent, "uses", uses):
        threads = [
            threading.Thread(
                target=lambda site=site: results.append(SiteContent(library, site).remove(pdf))
            )
            for site in ("a", "b")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
    assert results == [True, True]
    assert s.uses() == {}
    assert not list((folder / "content").rglob(f"{pdf}*"))


def test_a_record_that_cant_be_saved_leaves_the_pdf_as_it_was(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Codex's review of PR #305: the last site's Remove can't save the record; nothing is
    deleted, the PDF is still on the site, and still there once the folder is opened again."""
    s = Served(tmp_path)
    ann_a = s.host(A, ANN)
    pdf = ann_a.post("/api/content", files={"file": ("a.pdf", io.BytesIO(PDF))}).json()["id"]
    s.settle("a")
    with patch.object(PdfSites, "change", side_effect=OSError("disk full")):
        with caplog.at_level(logging.ERROR):
            assert ann_a.delete(f"/api/content/{pdf}").status_code == 500
    assert "PDF not taken off the site" in caplog.messages
    assert s.uses() == {pdf: ["a"]}
    assert seen(ann_a)["pdfs"] == ["a.pdf"] and seen(ann_a)["pages"] == [f"{pdf}-p1"]
    library = reopened(s, s.library())
    assert library.store.get(pdf) is not None
    assert (s.library() / "content" / "wiki" / f"{pdf}.json").is_file()


def test_files_that_cant_be_deleted_are_collected_when_the_folder_is_opened_again(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The record is saved first: a PDF whose files can't be deleted then, or whose deletion a
    stop cut short, is no site's, and goes the next time the host's folder is opened."""
    s = Served(tmp_path)
    ann_a = s.host(A, ANN)
    pdf = ann_a.post("/api/content", files={"file": ("a.pdf", io.BytesIO(PDF))}).json()["id"]
    s.settle("a")
    refused = UploadError("The PDF could not be removed. Try again.", status=500)
    with patch.object(ContentStore, "remove", side_effect=refused):
        with caplog.at_level(logging.ERROR):
            assert ann_a.delete(f"/api/content/{pdf}").is_success
    assert "Unused PDF kept until the host's folder is opened again" in caplog.messages
    assert s.uses() == {} and seen(ann_a)["pdfs"] == []
    content = s.library() / "content"
    assert (content / "pdfs" / f"{pdf}.pdf").is_file()
    # A stop after the PDF went but before what was made from it: only those files are left.
    other = "0" * 32
    (content / "read" / f"{other}.json").write_text("{}")
    with caplog.at_level(logging.WARNING):
        reopened(s, s.library())
    assert "Unused PDFs collected" in caplog.messages
    assert not list(content.rglob(f"{pdf}*")) and not list(content.rglob(f"{other}*"))
    assert (content / "wiki" / "pace.json").is_file()  # not a PDF's


def test_nothing_is_collected_while_the_record_cant_be_read(tmp_path: Path) -> None:
    s = Served(tmp_path)
    ann_a = s.host(A, ANN)
    pdf = ann_a.post("/api/content", files={"file": ("a.pdf", io.BytesIO(PDF))}).json()["id"]
    s.settle("a")
    (s.library() / "content" / "sites.json").write_text("not json")
    assert reopened(s, s.library()).collect() == []
    assert (s.library() / "content" / "pdfs" / f"{pdf}.pdf").is_file()
