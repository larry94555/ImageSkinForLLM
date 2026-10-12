import io
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin import content
from imageskin.app import create_app
from imageskin.content import ContentStore, is_pdf
from imageskin.uploads import UploadError

PDF = b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF\n"
OTHER_PDF = b"%PDF-1.4\n" + b"y" * 50 + b"\n%%EOF\n"


@pytest.mark.parametrize(
    ("head", "ok"),
    [
        (PDF, True),
        (b"\xef\xbb\xbf%PDF-1.7", True),  # a little junk before the header is allowed
        (b"\xff\xd8\xff\xe0", False),
        (b"junk %PDF-1.5", True),
        (b" " * 1100 + b"%PDF-1.7", False),
        (b"", False),
    ],
)
def test_a_pdf_is_known_by_its_first_bytes(head: bytes, ok: bool) -> None:
    assert is_pdf(head) is ok


def test_pdfs_are_added_listed_and_kept_apart_from_uploads(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = ContentStore(tmp_path)
    assert store.list() == []
    with caplog.at_level(logging.INFO):
        first = store.add("../../notes.pdf", io.BytesIO(PDF))
        second = store.add("slides.pdf", io.BytesIO(OTHER_PDF))

    assert first.name == "notes.pdf" and first.size == len(PDF) and first.replaced_at is None
    assert store.list() == [first, second]
    assert store.path(first.id) == tmp_path / "content" / "pdfs" / f"{first.id}.pdf"
    assert (tmp_path / "content" / "pdfs" / f"{first.id}.pdf").read_bytes() == PDF
    assert not (tmp_path / "uploads").exists()
    assert list((tmp_path / "content" / "tmp").iterdir()) == []
    added = [r for r in caplog.records if r.message == "PDF added"]
    assert len(added) == 2 and added[0].__dict__["id"] == first.id
    assert added[0].__dict__["duration_ms"] >= 0


def test_replacing_keeps_the_id_and_records_when(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    old = store.add("v1.pdf", io.BytesIO(PDF))
    new = store.replace(old.id, "v2.pdf", io.BytesIO(OTHER_PDF))
    assert new.id == old.id and new.added_at == old.added_at
    assert new.name == "v2.pdf" and new.size == len(OTHER_PDF) and new.replaced_at
    assert store.list() == [new]
    assert store.get(old.id) == new
    assert (store.path(old.id) or Path()).read_bytes() == OTHER_PDF


def test_a_refused_replacement_leaves_the_old_pdf(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    old = store.add("v1.pdf", io.BytesIO(PDF))
    with pytest.raises(UploadError) as e:
        store.replace(old.id, "photo.pdf", io.BytesIO(b"\xff\xd8\xff\xe0 not a pdf"))
    assert e.value.status == 415
    assert store.list() == [old]
    assert (store.path(old.id) or Path()).read_bytes() == PDF


def test_replacing_or_removing_a_missing_pdf(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    with pytest.raises(UploadError) as e:
        store.replace("0" * 32, "x.pdf", io.BytesIO(PDF))
    assert e.value.status == 404
    assert store.remove("0" * 32) is False
    assert store.remove("../../etc/passwd") is False


def test_removing_deletes_both_files(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = ContentStore(tmp_path)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    with caplog.at_level(logging.INFO):
        assert store.remove(pdf.id) is True
    assert store.list() == [] and store.get(pdf.id) is None
    assert list((tmp_path / "content" / "pdfs").iterdir()) == []
    assert any(r.message == "PDF removed" and r.__dict__["id"] == pdf.id for r in caplog.records)


@pytest.mark.parametrize(
    ("data", "status", "message"),
    [
        (b"", 400, "The file is empty."),
        (b"\x89PNG\r\n\x1a\n", 415, "This is not a PDF."),
    ],
)
def test_bad_files_are_refused_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, data: bytes, status: int, message: str
) -> None:
    store = ContentStore(tmp_path)
    with pytest.raises(UploadError) as e, caplog.at_level(logging.WARNING):
        store.add("x.pdf", io.BytesIO(data))
    assert e.value.status == status and str(e.value).startswith(message)
    assert store.list() == []
    assert any(r.message == "PDF refused" for r in caplog.records)


def test_size_limits(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    with patch.object(content, "MAX_PDF_BYTES", 50), pytest.raises(UploadError) as e:
        store.add("big.pdf", io.BytesIO(PDF))
    assert e.value.status == 413 and "MB limit" in str(e.value)

    first = store.add("a.pdf", io.BytesIO(PDF))
    with patch.object(content, "MAX_CONTENT_BYTES", len(PDF) + 10):
        with pytest.raises(UploadError) as e:
            store.add("b.pdf", io.BytesIO(PDF))
        assert e.value.status == 413 and "in total" in str(e.value)
        # A replacement counts instead of the file it replaces, not on top of it.
        assert store.replace(first.id, "a2.pdf", io.BytesIO(PDF)).size == len(PDF)


def test_a_pdf_removed_while_its_replacement_arrives(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    pdf = store.add("a.pdf", io.BytesIO(PDF))

    class RemovedWhileReading(io.BytesIO):
        def read(self, n: int | None = -1) -> bytes:
            if store.get(pdf.id):
                threading.Thread(target=store.remove, args=(pdf.id,)).run()
            return super().read(n)

    with pytest.raises(UploadError) as e:
        store.replace(pdf.id, "a2.pdf", RemovedWhileReading(OTHER_PDF))
    assert e.value.status == 404
    assert store.list() == []


def test_unreadable_info_is_logged_and_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = ContentStore(tmp_path)
    good = store.add("a.pdf", io.BytesIO(PDF))
    for bad in ("f" * 32, "e" * 32):
        (tmp_path / "content" / "pdfs" / f"{bad}.pdf").write_bytes(PDF)
    (tmp_path / "content" / "pdfs" / ("f" * 32 + ".json")).write_text("{oops", encoding="utf-8")
    (tmp_path / "content" / "pdfs" / ("e" * 32 + ".json")).write_text(
        json.dumps({"id": "e" * 32}), encoding="utf-8"
    )
    with caplog.at_level(logging.ERROR):
        assert store.list() == [good]
    errors = [r.message for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors == ["Could not read PDF info"] * 2


def test_content_api_adds_fetches_replaces_and_removes(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/content").json() == []

    sent = client.post("/api/content", files={"file": ("Week 1.pdf", PDF, "text/plain")})
    assert sent.status_code == 200
    pdf = sent.json()
    assert pdf["name"] == "Week 1.pdf" and pdf["size"] == len(PDF)
    assert client.get("/api/content").json() == [pdf]

    fetched = client.get(f"/api/content/{pdf['id']}")
    assert fetched.content == PDF
    assert fetched.headers["content-type"] == "application/pdf"
    assert fetched.headers["x-content-type-options"] == "nosniff"
    assert fetched.headers["content-disposition"].startswith("inline")

    put = client.put(f"/api/content/{pdf['id']}", files={"file": ("Week 1 v2.pdf", OTHER_PDF)})
    assert put.status_code == 200
    assert put.json()["id"] == pdf["id"] and put.json()["name"] == "Week 1 v2.pdf"
    assert client.get(f"/api/content/{pdf['id']}").content == OTHER_PDF

    assert client.delete(f"/api/content/{pdf['id']}").json() == {"removed": True}
    assert client.get("/api/content").json() == []
    assert client.get(f"/api/content/{pdf['id']}").status_code == 404
    assert client.delete(f"/api/content/{pdf['id']}").status_code == 404


def test_content_api_errors_are_plain_messages(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    renamed = client.post("/api/content", files={"file": ("notes.pdf", b"hello")})
    assert renamed.status_code == 415
    assert renamed.json()["detail"].startswith("This is not a PDF.")
    missing = client.put(f"/api/content/{'0' * 32}", files={"file": ("x.pdf", PDF)})
    assert missing.status_code == 404 and missing.json()["detail"] == "No such PDF."
    assert client.get("/api/content/..%2F..%2Fsecret").status_code == 404


def fail_info_commit(real: Callable[[Path, Path], Path]) -> Callable[[Path, Path], Path]:
    """Path.replace that fails when the info file is moved into place, after the PDF."""

    def replace(self: Path, target: Path) -> Path:
        if self.suffix == ".writing":
            raise PermissionError("locked by antivirus")
        return real(self, target)

    return replace


def pdf_folder(home: Path) -> list[str]:
    return sorted(p.name for p in (home / "content" / "pdfs").iterdir())


def test_a_failed_add_leaves_nothing_behind(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = ContentStore(tmp_path)
    with (
        patch.object(Path, "replace", fail_info_commit(Path.replace)),
        pytest.raises(UploadError) as e,
        caplog.at_level(logging.ERROR),
    ):
        store.add("a.pdf", io.BytesIO(PDF))
    assert e.value.status == 500 and str(e.value).startswith("The PDF could not be stored.")
    assert store.list() == [] and pdf_folder(tmp_path) == []
    assert list((tmp_path / "content" / "tmp").iterdir()) == []
    assert any(r.message == "Could not store the PDF" for r in caplog.records)


def test_a_failed_replacement_keeps_the_old_pdf_and_info(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    old = store.add("v1.pdf", io.BytesIO(PDF))
    with (
        patch.object(Path, "replace", fail_info_commit(Path.replace)),
        pytest.raises(UploadError) as e,
    ):
        store.replace(old.id, "v2.pdf", io.BytesIO(OTHER_PDF))
    assert e.value.status == 500
    assert store.list() == [old]
    assert (store.path(old.id) or Path()).read_bytes() == PDF
    assert pdf_folder(tmp_path) == [f"{old.id}.json", f"{old.id}.pdf"]

    # And a later replacement works.
    assert store.replace(old.id, "v2.pdf", io.BytesIO(OTHER_PDF)).name == "v2.pdf"
    assert pdf_folder(tmp_path) == [f"{old.id}.json", f"{old.id}.pdf"]


def test_a_pdf_that_cannot_be_deleted_stays_listed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = ContentStore(tmp_path)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self.suffix == ".pdf":
            raise PermissionError("open in another program")
        real_unlink(self, missing_ok=missing_ok)

    with patch.object(Path, "unlink", unlink), caplog.at_level(logging.ERROR):
        with pytest.raises(UploadError) as e:
            store.remove(pdf.id)
        client = TestClient(create_app(tmp_path))
        sent = client.delete(f"/api/content/{pdf.id}")
    assert e.value.status == 500
    assert sent.status_code == 500 and sent.json()["detail"].startswith("The PDF could not be")
    assert any(r.message == "Could not remove the PDF" for r in caplog.records)
    assert store.list() == [pdf]
    assert store.remove(pdf.id) is True
    assert store.list() == []


def test_info_without_its_pdf_is_not_listed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    (tmp_path / "content" / "pdfs" / f"{pdf.id}.pdf").unlink()
    assert store.list() == []
