import io
import json
import logging
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pdf_samples import TABLE, slides_pdf, table_pdf, text_pdf

from imageskin.app import create_app
from imageskin.content import ContentStore
from imageskin.pdf_reading import Piece, Progress, Reading, ReadingError
from imageskin.reading_job import READING_FORMAT, ReadingJob, ReadingStatus

PDF = b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF\n"


def one_paragraph(path: Path, progress: Progress) -> Reading:
    progress(1, 1)
    return Reading("text", 1, [Piece(1, "paragraph", "Hello.")], [])


def test_an_added_pdf_is_read_and_saved(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = ContentStore(tmp_path)
    job = ReadingJob(store, one_paragraph)
    pdf = store.add("notes.pdf", io.BytesIO(PDF))
    with caplog.at_level(logging.INFO):
        job.queue(pdf)
        job.wait()

    status = ReadingStatus("done", 1, 1, "text", {"paragraph": 1, "slide": 0, "table": 0}, [])
    assert job.statuses() == {pdf.id: status}
    saved = json.loads((tmp_path / "content" / "read" / f"{pdf.id}.json").read_text())
    assert saved == job.reading(pdf.id)
    assert saved["name"] == "notes.pdf" and saved["version"] == pdf.added_at
    assert saved["format"] == READING_FORMAT
    assert saved["pieces"] == [{"page": 1, "kind": "paragraph", "text": "Hello.", "rows": None}]
    read = [r for r in caplog.records if r.message == "PDF read"][0]
    assert read.__dict__["pages"] == 1 and read.__dict__["duration_ms"] >= 0
    assert any(r.message == "Reading PDF" for r in caplog.records)


def test_a_replaced_pdf_is_read_again_and_the_old_reading_is_not_used(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    job = ReadingJob(store, one_paragraph)
    pdf = store.add("v1.pdf", io.BytesIO(PDF))
    job.queue(pdf)
    job.wait()
    new = store.replace(pdf.id, "v2.pdf", io.BytesIO(b"%PDF-1.4" + PDF))

    assert job.reading(pdf.id) is None  # the saved one is for v1
    assert job.statuses() == {}
    job.queue(new)
    job.wait()
    reading = job.reading(pdf.id)
    assert reading is not None and reading["name"] == "v2.pdf"


def test_a_pdf_that_cannot_be_read_fails_with_the_reason(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(path: Path, progress: Progress) -> Reading:
        raise ReadingError("This PDF could not be read.")

    store = ContentStore(tmp_path)
    job = ReadingJob(store, broken)
    pdf = store.add("bad.pdf", io.BytesIO(PDF))
    job.queue(pdf)
    job.wait()

    assert job.statuses()[pdf.id] == ReadingStatus("failed", error="This PDF could not be read.")
    assert job.reading(pdf.id) is None
    assert any(r.message == "Could not read the PDF" for r in caplog.records)


def test_catch_up_reads_only_pdfs_with_no_up_to_date_reading(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = store.add("a.pdf", io.BytesIO(PDF))
    job = ReadingJob(store, one_paragraph)
    job.queue(first)
    job.wait()
    second = store.add("b.pdf", io.BytesIO(b"%PDF-1.4" + PDF))
    third = store.add("c.pdf", io.BytesIO(b"%PDF-1.3" + PDF))
    job.queue(third)
    job.wait()
    (tmp_path / "content" / "read" / f"{third.id}.json").write_text("{not json")

    read: list[bytes] = []

    def counting(path: Path, progress: Progress) -> Reading:
        read.append(path.read_bytes())
        return one_paragraph(path, progress)

    later = ReadingJob(store, counting)  # as after a restart
    later.catch_up()
    later.wait()
    # The second was never read, and the third's reading is broken; the first is up to date.
    assert read == [b"%PDF-1.4" + PDF, b"%PDF-1.3" + PDF]
    assert set(later.statuses()) == {first.id, second.id, third.id}


def test_a_reading_in_an_older_format_is_not_used_and_is_read_again(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    pdf = store.add("riemann.pdf", io.BytesIO(PDF))
    job = ReadingJob(store, one_paragraph)
    job.queue(pdf)
    job.wait()
    path = tmp_path / "content" / "read" / f"{pdf.id}.json"
    older = json.loads(path.read_text())
    del older["format"]  # as saved before formulas were read as one line
    path.write_text(json.dumps(older))

    later = ReadingJob(store, one_paragraph)  # as after updating the app
    assert later.reading(pdf.id) is None
    later.catch_up()
    later.wait()
    assert later.reading(pdf.id)["format"] == READING_FORMAT  # type: ignore[index]


def test_progress_is_reported_and_a_removed_pdf_is_forgotten(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    halfway, go_on = threading.Event(), threading.Event()

    def slow(path: Path, progress: Progress) -> Reading:
        progress(1, 2)
        halfway.set()
        go_on.wait(5)
        return one_paragraph(path, progress)

    job = ReadingJob(store, slow)
    pdf = store.add("long.pdf", io.BytesIO(PDF))
    job.queue(pdf)
    assert halfway.wait(5)
    assert job.statuses() == {pdf.id: ReadingStatus("reading", 1, 2)}
    store.remove(pdf.id)
    job.forget(pdf.id)
    go_on.set()
    job.wait()

    assert job.statuses() == {} and job.reading(pdf.id) is None
    assert not (tmp_path / "content" / "read" / f"{pdf.id}.json").exists()


def test_a_pdf_replaced_while_it_is_read_waits_for_its_new_reading(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    halfway, go_on = threading.Event(), threading.Event()
    names: list[str] = []

    def slow(path: Path, progress: Progress) -> Reading:
        names.append(store.list()[0].name)
        if len(names) == 1:
            halfway.set()
            go_on.wait(5)
            progress(1, 1)  # from the old file: must not hide that the new one waits
        return one_paragraph(path, progress)

    job = ReadingJob(store, slow)
    pdf = store.add("v1.pdf", io.BytesIO(PDF))
    job.queue(pdf)
    assert halfway.wait(5)
    job.queue(store.replace(pdf.id, "v2.pdf", io.BytesIO(PDF)))
    assert job.statuses()[pdf.id].state == "waiting"
    go_on.set()
    job.wait()

    reading = job.reading(pdf.id)
    assert names == ["v1.pdf", "v2.pdf"]
    assert reading is not None and reading["name"] == "v2.pdf"


def test_the_content_api_reads_each_kind_of_pdf(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    ids = {}
    for make in (text_pdf, slides_pdf, table_pdf):
        path = make(tmp_path / f"{make.__name__}.pdf")
        response = client.post("/api/content", files={"file": (path.name, path.read_bytes())})
        ids[make.__name__] = response.json()["id"]
    client.app.state.readings.wait()  # type: ignore[attr-defined]

    statuses = client.get("/api/content/readings").json()
    assert {name: statuses[pdf_id]["kind"] for name, pdf_id in ids.items()} == {
        "text_pdf": "text",
        "slides_pdf": "slides",
        "table_pdf": "tables",
    }
    table = client.get(f"/api/content/{ids['table_pdf']}/reading").json()["pieces"][1]
    assert table["kind"] == "table" and table["rows"] == TABLE

    # Replacing reads it again; removing takes its reading away.
    replacement = slides_pdf(tmp_path / "new.pdf").read_bytes()
    client.put(f"/api/content/{ids['text_pdf']}", files={"file": ("new.pdf", replacement)})
    client.app.state.readings.wait()  # type: ignore[attr-defined]
    assert client.get(f"/api/content/{ids['text_pdf']}/reading").json()["kind"] == "slides"
    assert client.delete(f"/api/content/{ids['text_pdf']}").status_code == 200
    assert client.get(f"/api/content/{ids['text_pdf']}/reading").status_code == 404
    assert ids["text_pdf"] not in client.get("/api/content/readings").json()


def test_a_copy_is_read_so_the_stored_pdf_can_be_replaced_or_removed_meanwhile(
    tmp_path: Path,
) -> None:
    store = ContentStore(tmp_path)
    halfway, go_on = threading.Event(), threading.Event()
    read: list[Path] = []

    def slow(path: Path, progress: Progress) -> Reading:
        read.append(path)
        with path.open("rb"):  # held open the whole time, as pdfplumber does
            halfway.set()
            go_on.wait(5)
        return one_paragraph(path, progress)

    job = ReadingJob(store, slow)
    first = store.add("a.pdf", io.BytesIO(PDF))
    second = store.add("b.pdf", io.BytesIO(PDF))
    job.queue(first)
    job.queue(second)
    assert halfway.wait(5)
    stored = store.path(first.id)
    assert read[0] != stored and read[0].read_bytes() == PDF
    store.replace(first.id, "a2.pdf", io.BytesIO(b"%PDF-1.4" + PDF))
    store.remove(second.id)
    go_on.set()
    job.wait()

    assert [p.exists() for p in read] == [False]  # the copy is gone; b.pdf was never read
    assert list((tmp_path / "content" / "tmp").iterdir()) == []


def test_a_reading_that_cannot_be_saved_fails_and_the_next_pdf_is_still_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = ContentStore(tmp_path)
    blocker = tmp_path / "content" / "read"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("a file where the folder should be")

    calls: list[Path] = []

    def unblocking(path: Path, progress: Progress) -> Reading:
        calls.append(path)
        if len(calls) == 2:  # the first PDF's reading has failed to save by now
            blocker.unlink()
        return one_paragraph(path, progress)

    job = ReadingJob(store, unblocking)
    first = store.add("a.pdf", io.BytesIO(PDF))
    second = store.add("b.pdf", io.BytesIO(PDF))
    job.queue(first)
    job.queue(second)
    job.wait()

    statuses = job.statuses()
    assert statuses[first.id].state == "failed"
    assert statuses[first.id].error == "What was read could not be saved. Try replacing the PDF."
    assert statuses[second.id].state == "done"
    assert any(r.message == "Could not save the reading" for r in caplog.records)


def test_an_unexpected_error_fails_that_pdf_and_the_next_is_still_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def first_breaks(path: Path, progress: Progress) -> Reading:
        if not calls:
            calls.append(path)
            raise MemoryError("too big")
        return one_paragraph(path, progress)

    calls: list[Path] = []
    store = ContentStore(tmp_path)
    job = ReadingJob(store, first_breaks)
    first = store.add("a.pdf", io.BytesIO(PDF))
    second = store.add("b.pdf", io.BytesIO(PDF))
    job.queue(first)
    job.queue(second)
    job.wait()

    statuses = job.statuses()
    assert statuses[first.id] == ReadingStatus("failed", error="Something went wrong reading it.")
    assert statuses[second.id].state == "done"
    assert any(r.message == "Could not read the PDF" and r.exc_info for r in caplog.records)
