import io
import json
import logging
import threading
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from imageskin.app import create_app
from imageskin.chat import LlmError, Message
from imageskin.content import ContentStore
from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.reading_job import ReadingJob
from imageskin.wiki import Progress as WikiProgress
from imageskin.wiki import Wiki, WikiError, WikiPage
from imageskin.wiki_job import BuildWiki, WikiJob, WikiStatus

PDF = b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF\n"


def two_pages(path: Path, progress: Progress) -> Reading:
    return Reading("text", 2, [Piece(1, "paragraph", "Rain."), Piece(2, "paragraph", "Snow.")], [])


def one_page_per_piece(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress) -> Wiki:
    progress(1, 1)
    pages = [WikiPage(f"{pdf_id}-p{p['page']}", p["text"], p["text"], [p["page"]]) for p in pieces]
    return Wiki(1, pages)


def jobs(
    tmp_path: Path, build: BuildWiki = one_page_per_piece, **kw: Any
) -> tuple[ContentStore, ReadingJob, WikiJob]:
    store = ContentStore(tmp_path)
    readings = ReadingJob(store, two_pages)
    wiki = WikiJob(store, readings, build, **kw)
    readings.on_read = wiki.queue
    return store, readings, wiki


def settle(readings: ReadingJob, wiki: WikiJob) -> None:
    readings.wait()
    wiki.wait()


def test_a_read_pdf_gets_its_wiki_pages(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    idle = threading.Event()
    store, readings, wiki = jobs(tmp_path, when_idle=idle.set)
    pdf = store.add("weather.pdf", io.BytesIO(PDF))
    with caplog.at_level(logging.INFO):
        readings.queue(pdf)
        settle(readings, wiki)

    assert wiki.statuses() == {pdf.id: WikiStatus("done", 1, 1, 2, [])}
    listed = {"pdf_id": pdf.id, "pdf_name": "weather.pdf"}
    assert wiki.pages() == [
        {**listed, "id": f"{pdf.id}-p1", "title": "Rain.", "pages": [1]},
        {**listed, "id": f"{pdf.id}-p2", "title": "Snow.", "pages": [2]},
    ]
    page = {**listed, "id": f"{pdf.id}-p2", "title": "Snow.", "text": "Snow.", "pages": [2]}
    assert wiki.page(f"{pdf.id}-p2") == page
    assert wiki.page(f"{pdf.id}-nope") is None and wiki.page("nope") is None
    saved = json.loads((tmp_path / "content" / "wiki" / f"{pdf.id}.json").read_text())
    assert saved["version"] == pdf.added_at and len(saved["pages"]) == 2
    built = [r for r in caplog.records if r.message == "Wiki pages built"][0]
    assert built.__dict__["pages"] == 2 and built.__dict__["duration_ms"] >= 0
    assert any(r.message == "Building wiki pages" for r in caplog.records)
    assert idle.is_set()


def test_replacing_a_pdf_rebuilds_only_its_pages_and_removing_it_removes_them(
    tmp_path: Path,
) -> None:
    store, readings, wiki = jobs(tmp_path)
    first, second = store.add("a.pdf", io.BytesIO(PDF)), store.add("b.pdf", io.BytesIO(PDF))
    readings.queue(first)
    readings.queue(second)
    settle(readings, wiki)
    built: list[str] = []

    def counting(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress) -> Wiki:
        built.append(pdf_id)
        return one_page_per_piece(pdf_id, pieces, progress)

    wiki.build = counting
    new = store.replace(first.id, "a2.pdf", io.BytesIO(b"%PDF-1.4" + PDF))
    wiki.reset(first.id)
    assert {p["pdf_name"] for p in wiki.pages()} == {"b.pdf"}  # a's pages are out of date
    assert list(wiki.statuses()) == [second.id]
    readings.queue(new)
    settle(readings, wiki)
    assert built == [first.id]
    assert [p["pdf_name"] for p in wiki.pages()] == ["a2.pdf", "a2.pdf", "b.pdf", "b.pdf"]

    store.remove(first.id)
    wiki.forget(first.id)
    assert not (tmp_path / "content" / "wiki" / f"{first.id}.json").exists()
    assert [p["pdf_name"] for p in wiki.pages(second.id)] == ["b.pdf", "b.pdf"]
    assert wiki.pages(first.id) == []


def test_catch_up_builds_read_pdfs_with_no_up_to_date_pages(tmp_path: Path) -> None:
    store, readings, wiki = jobs(tmp_path)
    built_before, unread, read = (store.add(n, io.BytesIO(PDF)) for n in ("a", "b", "c"))
    readings.queue(built_before)
    settle(readings, wiki)
    readings.on_read = None  # c is read, but its pages are never built
    readings.queue(read)
    readings.wait()
    built: list[str] = []

    def counting(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress) -> Wiki:
        built.append(pdf_id)
        return one_page_per_piece(pdf_id, pieces, progress)

    restarted = WikiJob(store, readings, counting)
    restarted.catch_up()
    restarted.wait()
    assert built == [read.id]  # not a (up to date), nor b (not read yet)
    assert unread.id not in restarted.statuses()


def test_the_build_waits_while_the_llm_cannot_be_reached(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    calls = 0

    def flaky(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress) -> Wiki:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise LlmError("Could not reach the LLM") from urllib.error.URLError("refused")
        return one_page_per_piece(pdf_id, pieces, progress)

    store, readings, wiki = jobs(tmp_path, flaky, retry_s=0.01)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    settle(readings, wiki)
    assert calls == 2
    assert wiki.statuses()[pdf.id].state == "done"
    assert "Waiting for the LLM to build the wiki" in caplog.text


def test_a_build_that_fails_says_why_and_the_next_pdf_is_still_built(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def failing(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress) -> Wiki:
        pdf = store.get(pdf_id)
        assert pdf is not None
        if pdf.name == "bad.pdf":
            raise WikiError("The LLM gave no usable answer.")
        if pdf.name == "worse.pdf":
            raise RuntimeError("boom")
        if pdf.name == "refused.pdf":
            raise LlmError("The LLM refused the prompt (400)")
        return one_page_per_piece(pdf_id, pieces, progress)

    store, readings, wiki = jobs(tmp_path, failing)
    names = ["bad.pdf", "worse.pdf", "refused.pdf", "good.pdf"]
    pdfs = [store.add(name, io.BytesIO(PDF)) for name in names]
    for pdf in pdfs:
        readings.queue(pdf)
    settle(readings, wiki)

    statuses = wiki.statuses()
    assert statuses[pdfs[0].id] == WikiStatus("failed", error="The LLM gave no usable answer.")
    assert statuses[pdfs[1].id].error == "Something went wrong building it."
    assert statuses[pdfs[2].id].state == "failed"
    assert statuses[pdfs[3].id].state == "done"
    assert "Could not build the wiki" in caplog.text


def test_pages_built_for_a_pdf_replaced_meanwhile_are_not_saved(tmp_path: Path) -> None:
    started, go_on = threading.Event(), threading.Event()

    def slow(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress) -> Wiki:
        started.set()
        go_on.wait(5)
        return one_page_per_piece(pdf_id, pieces, progress)

    store, readings, wiki = jobs(tmp_path, slow)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    readings.wait()
    assert started.wait(5)
    assert wiki.statuses()[pdf.id] == WikiStatus("building")
    store.replace(pdf.id, "a2.pdf", io.BytesIO(b"%PDF-1.4" + PDF))
    wiki.reset(pdf.id)
    go_on.set()
    wiki.wait()
    assert not (tmp_path / "content" / "wiki" / f"{pdf.id}.json").exists()
    assert wiki.statuses() == {}


def test_pages_that_cannot_be_saved_fail_with_the_reason(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store, readings, wiki = jobs(tmp_path)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    (tmp_path / "content" / "wiki").write_text("a file where the folder should be")
    readings.queue(pdf)
    settle(readings, wiki)
    assert wiki.statuses()[pdf.id].error == (
        "The wiki pages could not be saved. Try replacing the PDF."
    )
    assert "Could not save the wiki pages" in caplog.text


def test_broken_saved_pages_are_logged_and_not_used(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store, readings, wiki = jobs(tmp_path)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    settle(readings, wiki)
    (tmp_path / "content" / "wiki" / f"{pdf.id}.json").write_text("{ broken")
    assert wiki.pages() == []
    assert "Could not read saved wiki pages" in caplog.text


def test_the_wiki_api_lists_pages_and_progress(tmp_path: Path) -> None:
    app = create_app(tmp_path, read_pdf=two_pages, build_wiki=one_page_per_piece)
    client = TestClient(app)
    pdf = client.post("/api/content", files={"file": ("w.pdf", PDF, "application/pdf")}).json()
    settle(app.state.readings, app.state.wiki)

    assert client.get("/api/wiki/builds").json()[pdf["id"]]["state"] == "done"
    pages = client.get("/api/wiki").json()
    assert [p["title"] for p in pages] == ["Rain.", "Snow."]
    assert client.get("/api/wiki", params={"pdf": "f" * 32}).json() == []
    page = client.get(f"/api/wiki/{pages[0]['id']}").json()
    assert page["text"] == "Rain." and page["pdf_name"] == "w.pdf" and page["pages"] == [1]
    assert client.get("/api/wiki/nope").status_code == 404
    built = client.get(f"/api/content/{pdf['id']}/wiki").json()
    assert built["name"] == "w.pdf" and [p["text"] for p in built["pages"]] == ["Rain.", "Snow."]

    files = {"file": ("w2.pdf", b"%PDF-1.4" + PDF, "application/pdf")}
    client.put(f"/api/content/{pdf['id']}", files=files)
    settle(app.state.readings, app.state.wiki)
    assert {p["pdf_name"] for p in client.get("/api/wiki").json()} == {"w2.pdf"}
    client.delete(f"/api/content/{pdf['id']}")
    assert client.get("/api/wiki").json() == []
    assert client.get(f"/api/content/{pdf['id']}/wiki").status_code == 404


def test_the_app_builds_with_the_chat_llm_when_none_is_given(tmp_path: Path) -> None:
    asked: list[list[Message]] = []

    def ask(messages: list[Message]) -> str:
        asked.append(messages)
        return json.dumps({"topics": [{"title": "Weather", "pages": [1], "text": "Rain."}]})

    app = create_app(tmp_path, read_pdf=two_pages, ask_llm=ask)
    client = TestClient(app)
    client.post("/api/content", files={"file": ("w.pdf", PDF, "application/pdf")})
    settle(app.state.readings, app.state.wiki)
    assert [p["title"] for p in client.get("/api/wiki").json()] == ["Weather"]
    assert "[page 1] Rain." in asked[0][1]["content"]
