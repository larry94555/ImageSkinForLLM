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
from imageskin.reading_job import ReadingJob, ReadingStatus

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
    second = store.add("b.pdf", io.BytesIO(PDF))
    (tmp_path / "content" / "read" / f"{first.id}.json").write_text("{not json")

    read: list[Path] = []

    def counting(path: Path, progress: Progress) -> Reading:
        read.append(path)
        return one_paragraph(path, progress)

    later = ReadingJob(store, counting)  # as after a restart
    later.catch_up()
    later.wait()
    assert read == [store.path(first.id), store.path(second.id)]  # first's reading is broken
    assert set(later.statuses()) == {first.id, second.id}


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
