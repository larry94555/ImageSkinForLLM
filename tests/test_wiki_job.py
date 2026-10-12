import io
import json
import logging
import threading
import urllib.error
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from imageskin.app import create_app
from imageskin.chat import LlmError, Message
from imageskin.content import ContentStore
from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.reading_job import ReadingJob
from imageskin.wiki import WIKI_PROMPT, WaitForLlm, Wiki, WikiError, WikiPage, build_wiki
from imageskin.wiki import Progress as WikiProgress
from imageskin.wiki_job import BuildWiki, WikiJob, WikiStatus, remaining
from imageskin.wiki_outline import Entry, OutlineProgress

PDF = b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF\n"


def two_pages(path: Path, progress: Progress) -> Reading:
    return Reading("text", 2, [Piece(1, "paragraph", "Rain."), Piece(2, "paragraph", "Snow.")], [])


def one_page_per_piece(
    pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: Any = None
) -> Wiki:
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


def timeless(status: WikiStatus) -> WikiStatus:
    return replace(status, elapsed_s=None, remaining_s=None)


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

    status = wiki.statuses()[pdf.id]
    assert timeless(status) == WikiStatus("done", 1, 1, 2, [], detail_pages=0)
    assert status.elapsed_s is not None and status.elapsed_s >= 0  # how long it took
    listed = {"pdf_id": pdf.id, "pdf_name": "weather.pdf"}
    assert wiki.pages() == [
        {**listed, "id": f"{pdf.id}-p1", "title": "Rain.", "pages": [1]},
        {**listed, "id": f"{pdf.id}-p2", "title": "Snow.", "pages": [2]},
    ]
    page: dict[str, object] = {**listed, "id": f"{pdf.id}-p2", "title": "Snow.", "pages": [2]}
    page |= {"text": "Snow.", "summary": "Snow.", "detail": False, "entries": []}
    assert wiki.page(f"{pdf.id}-p2") == page
    assert wiki.page(f"{pdf.id}-nope") is None and wiki.page("nope") is None
    saved = json.loads((tmp_path / "content" / "wiki" / f"{pdf.id}.json").read_text())
    assert saved["version"] == pdf.added_at and len(saved["pages"]) == 2
    assert saved["duration_s"] == status.elapsed_s
    assert [e["id"] for e in saved["outline"]] == [f"{pdf.id}-p1", f"{pdf.id}-p2"]
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

    def counting(
        pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: WaitForLlm
    ) -> Wiki:
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

    def counting(
        pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: WaitForLlm
    ) -> Wiki:
        built.append(pdf_id)
        return one_page_per_piece(pdf_id, pieces, progress)

    restarted = WikiJob(store, readings, counting)
    restarted.catch_up()
    restarted.wait()
    assert built == [read.id]  # not a (up to date), nor b (not read yet)
    assert unread.id not in restarted.statuses()


def down() -> LlmError:
    error = LlmError("Could not reach the LLM")
    error.__cause__ = urllib.error.URLError("refused")
    return error


def topics(title: str) -> str:
    return json.dumps({"topics": [{"title": title, "pages": [1], "text": "Text."}]})


def test_the_build_waits_for_the_llm_and_asks_the_same_part_again(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    asked: list[str] = []

    def ask(messages: list[Message]) -> str:
        part = messages[1]["content"]
        asked.append(part)
        if len(asked) == 2:  # the LLM goes away while part 2 is asked
            raise down()
        return topics(part[:8])

    def build(
        pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: WaitForLlm
    ) -> Wiki:
        # A piece counts 150 tokens and anything else 1, so each part has room for one piece.
        def count(text: str) -> int:
            return 150 if "Rain" in text or "Snow" in text else 1

        return build_wiki(pdf_id, pieces, ask, count, 1400, progress, wait)

    store, readings, wiki = jobs(tmp_path, build, retry_s=0.01)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    settle(readings, wiki)

    # Part 2 is asked again; part 1 is not.
    assert asked == ["[page 1] Rain.", "[page 2] Snow.", "[page 2] Snow."]
    assert timeless(wiki.statuses()[pdf.id]) == WikiStatus("done", 2, 2, 2, [], detail_pages=0)
    assert "Waiting for the LLM to build the wiki" in caplog.text


def test_a_pdf_removed_while_its_build_waits_for_the_llm_is_dropped(tmp_path: Path) -> None:
    waiting = threading.Event()

    def build(
        pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: WaitForLlm
    ) -> Wiki:
        while True:
            waiting.set()
            wait(down(), 1, 1)

    store, readings, wiki = jobs(tmp_path, build, retry_s=0.05)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    readings.wait()
    assert waiting.wait(5)
    assert wiki.statuses()[pdf.id].error == "Could not reach the LLM"
    store.remove(pdf.id)
    wiki.forget(pdf.id)
    wiki.wait()
    assert wiki.statuses() == {} and wiki.pages() == []


def test_a_build_that_fails_says_why_and_the_next_pdf_is_still_built(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def failing(
        pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: WaitForLlm
    ) -> Wiki:
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
    assert statuses[pdfs[2].id].error == "The LLM refused the prompt (400)"
    assert statuses[pdfs[3].id].state == "done"
    assert "Could not build the wiki" in caplog.text


def test_pages_built_for_a_pdf_replaced_meanwhile_are_not_saved(tmp_path: Path) -> None:
    started, go_on = threading.Event(), threading.Event()

    def slow(
        pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: WaitForLlm
    ) -> Wiki:
        started.set()
        go_on.wait(5)
        return one_page_per_piece(pdf_id, pieces, progress)

    store, readings, wiki = jobs(tmp_path, slow)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    readings.wait()
    assert started.wait(5)
    status = wiki.statuses()[pdf.id]
    assert timeless(status) == WikiStatus("building") and status.elapsed_s is not None
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
    assert "Wiki pages built" not in caplog.text


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


def test_a_pdf_already_being_built_is_not_queued_again(tmp_path: Path) -> None:
    started, go_on = threading.Event(), threading.Event()
    built: list[str] = []

    def slow(
        pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: WaitForLlm
    ) -> Wiki:
        built.append(pdf_id)
        started.set()
        go_on.wait(5)
        return one_page_per_piece(pdf_id, pieces, progress)

    store, readings, wiki = jobs(tmp_path, slow)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    readings.wait()
    assert started.wait(5)
    wiki.catch_up()  # read, with no pages saved yet: the start-up race
    wiki.queue(pdf.id)
    status = wiki.statuses()[pdf.id]
    assert timeless(status) == WikiStatus("building") and status.elapsed_s is not None
    go_on.set()
    wiki.wait()
    assert built == [pdf.id]

    # A replaced version still queues behind the one being built.
    go_on.clear()
    started.clear()
    readings.queue(store.replace(pdf.id, "a2.pdf", io.BytesIO(b"%PDF-1.4" + PDF)))
    assert started.wait(5)
    readings.queue(store.replace(pdf.id, "a3.pdf", io.BytesIO(b"%PDF-1.5" + PDF)))
    readings.wait()  # a3 is read and queued for its pages while a2's are built
    go_on.set()
    settle(readings, wiki)
    assert len(built) == 3
    assert {p["pdf_name"] for p in wiki.pages()} == {"a3.pdf"}


LONG = " ".join(f"Rain {n} falls." for n in range(1, 9))  # too long to show as it is


def long_topic(
    pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: Any = None
) -> Wiki:
    progress(1, 1)
    return Wiki(1, [WikiPage(f"{pdf_id}-rain", "Rain", LONG, [1])])


def test_the_outline_is_built_after_the_topics_and_saved_with_them(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    seen: list[WikiStatus] = []
    estimates: list[float | None] = []

    def outline(
        pdf_id: str,
        topics: list[WikiPage],
        pieces: list[dict[str, Any]],
        progress: OutlineProgress,
        wait: WaitForLlm,
    ) -> list[Entry]:
        seen.append(timeless(wiki.statuses()[pdf_id]))
        wait(down(), 1, 0)  # the LLM goes away for a moment
        seen.append(timeless(wiki.statuses()[pdf_id]))
        progress(1, 2)
        estimates.append(wiki.statuses()[pdf_id].remaining_s)
        seen.append(timeless(wiki.statuses()[pdf_id]))
        parts = [Entry(f"{pdf_id}-drops", "Drops", "Drops.", [1])]
        return [Entry(topics[0].id, "Rain", "Rain falls.", [1], parts, detail=True)]

    store, readings, wiki = jobs(tmp_path, long_topic, outline=outline, retry_s=0.01)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    with caplog.at_level(logging.INFO):
        readings.queue(pdf)
        settle(readings, wiki)

    assert seen == [
        WikiStatus("building", 1, 1, stage="outline"),
        WikiStatus("building", 1, 1, stage="outline"),
        WikiStatus("building", 1, 1, stage="outline", steps=1, steps_planned=2),
    ]
    assert estimates[0] is not None and estimates[0] >= 0  # one step done, one left
    assert timeless(wiki.statuses()[pdf.id]) == WikiStatus("done", 1, 1, 1, [], detail_pages=1)
    waited = [r for r in caplog.records if r.message == "Waiting for the LLM to build the wiki"]
    assert waited[0].__dict__["stage"] == "outline"
    topic = wiki.page(f"{pdf.id}-rain")
    assert topic is not None and topic["text"] == LONG and topic["summary"] == "Rain falls."
    assert topic["detail"] and [e["title"] for e in topic["entries"]] == ["Drops"]
    part = wiki.page(f"{pdf.id}-drops")
    assert part is not None and part["summary"] == "Drops." and "text" not in part
    built = [r for r in caplog.records if r.message == "Wiki pages built"][0]
    assert built.__dict__["detail_pages"] == 1


def test_a_refused_outline_keeps_the_topics_as_they_are(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def refused(
        pdf_id: str,
        topics: list[WikiPage],
        pieces: list[dict[str, Any]],
        progress: OutlineProgress,
        wait: WaitForLlm,
    ) -> list[Entry]:
        raise LlmError("The LLM refused the prompt (400)")

    store, readings, wiki = jobs(tmp_path, long_topic, outline=refused)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    settle(readings, wiki)
    assert wiki.statuses()[pdf.id].state == "done"
    page = wiki.page(f"{pdf.id}-rain")
    assert page is not None and page["summary"] == LONG and page["entries"] == []
    assert "Could not build the wiki outline" in caplog.text


def test_pages_saved_before_the_outline_are_built_again(tmp_path: Path) -> None:
    store, readings, wiki = jobs(tmp_path)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    settle(readings, wiki)
    path = tmp_path / "content" / "wiki" / f"{pdf.id}.json"
    saved = json.loads(path.read_text())
    del saved["format"], saved["outline"]  # as R37 saved them
    path.write_text(json.dumps(saved))
    assert wiki.pages() == [] and wiki.page(f"{pdf.id}-p1") is None

    restarted = WikiJob(store, readings, one_page_per_piece)
    restarted.catch_up()
    restarted.wait()
    assert len(restarted.pages()) == 2


def test_the_app_builds_the_outline_with_the_chat_llm(tmp_path: Path) -> None:
    def ask(messages: list[Message]) -> str:
        if messages[0]["content"].startswith(WIKI_PROMPT):
            return json.dumps({"topics": [{"title": "Rain", "pages": [1], "text": LONG}]})
        parts = [{"title": "Drops", "paragraphs": [1]}, {"title": "Puddles", "paragraphs": [2]}]
        return json.dumps({"summary": "Rain falls.", "parts": parts})

    def long_page(path: Path, progress: Progress) -> Reading:
        return Reading("text", 1, [Piece(1, "paragraph", LONG)], [])

    app = create_app(tmp_path, read_pdf=long_page, ask_llm=ask)
    client = TestClient(app)
    pdf = client.post("/api/content", files={"file": ("w.pdf", PDF, "application/pdf")}).json()
    settle(app.state.readings, app.state.wiki)
    assert client.get("/api/wiki/builds").json()[pdf["id"]]["detail_pages"] == 1
    built = client.get(f"/api/content/{pdf['id']}/wiki").json()
    assert [e["title"] for e in built["outline"][0]["entries"]] == ["Drops", "Puddles"]
    page = client.get(f"/api/wiki/{pdf['id']}-puddles").json()
    assert page["summary"] == "Rain 6 falls. Rain 7 falls. Rain 8 falls."  # the PDF's words
    assert page["pdf_name"] == "w.pdf"


def test_the_time_left_is_estimated_from_the_steps_done_so_far() -> None:
    topics = WikiStatus("building", 2, 5)
    assert remaining(topics, 60, 0) == 90  # 30 s a part, 3 parts left
    assert remaining(topics, 60, 20) == 70  # counting down until the next part is done
    assert remaining(topics, 60, 200) == 0
    assert remaining(WikiStatus("building", 0, 5), 0, 60) is None  # nothing to go on yet
    outline = WikiStatus("building", 5, 5, stage="outline", steps=3, steps_planned=4)
    assert remaining(outline, 30, 0) == 10
    assert remaining(replace(outline, steps_planned=3), 30, 0) == 0
