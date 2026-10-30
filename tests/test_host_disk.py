"""The disk space a host has used (roadmap R192)."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_uploads import wav_bytes

from imageskin import admin
from imageskin.app import create_app
from imageskin.host_disk import Owners, count

pytestmark = pytest.mark.real_hosts

PDF = b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF\n"
FIRST = {"email": "first@example.com", "password": "a long secret"}
SECOND = {"email": "second@example.com", "password": "a long secret"}


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    caplog.set_level(logging.INFO)


def write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def on_disk(home: Path, *globs: str) -> int:
    return sum(p.stat().st_size for g in globs for p in home.glob(g))


def test_a_host_counts_only_what_they_added(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    first = TestClient(create_app(tmp_path))
    first.post("/api/host/sign-up", json=FIRST)
    first.post("/api/consent", json={"agreed": True})
    second = TestClient(first.app)
    second.post("/api/host/sign-up", json=SECOND)
    assert first.get("/api/host/disk").json() == {
        "images_and_recordings": 0,
        "pdfs": 0,
        "total": 0,
    }

    added = first.post("/api/content", files={"file": ("a.pdf", PDF, "application/pdf")})
    pdf_id = added.json()["id"]
    sound = first.post("/api/uploads/sounds", files={"file": ("a.wav", wav_bytes(), "audio/wav")})
    sound_id = sound.json()["id"]
    # What is read from the PDF counts too, once it is written.
    first.app.state.readings.wait()  # type: ignore[attr-defined]
    first.app.state.wiki.wait()  # type: ignore[attr-defined]

    amounts = first.get("/api/host/disk").json()
    # Only the recording and the PDF themselves, not what is made from them (Larry, 2026-10-30).
    assert amounts["images_and_recordings"] == on_disk(tmp_path, f"uploads/sounds/{sound_id}.wav")
    assert amounts["pdfs"] == len(PDF)
    assert amounts["total"] == amounts["images_and_recordings"] + amounts["pdfs"]
    assert second.get("/api/host/disk").json() == {
        "images_and_recordings": 0,
        "pdfs": 0,
        "total": 0,
    }

    owners = json.loads((tmp_path / "owners.json").read_text())
    assert owners == {"pdfs": {pdf_id: FIRST["email"]}, "sounds": {sound_id: FIRST["email"]}}
    counted = [r for r in caplog.records if r.getMessage() == "Host disk space counted"]
    assert counted[-1].email == SECOND["email"]  # type: ignore[attr-defined]
    assert counted[-2].total == amounts["total"]  # type: ignore[attr-defined]
    assert counted[-2].took_ms >= 0  # type: ignore[attr-defined]


def test_only_a_signed_in_host_asks(tmp_path: Path) -> None:
    assert TestClient(create_app(tmp_path)).get("/api/host/disk").status_code == 401


def test_only_the_files_a_host_added_count(tmp_path: Path) -> None:
    write(tmp_path / "uploads" / "photos" / "p1.jpg", 1000)
    write(tmp_path / "uploads" / "photos" / "p1.json", 10)
    write(tmp_path / "uploads" / "photos" / "p2.png", 2000)
    write(tmp_path / "uploads" / "sounds" / "s1.wav", 3000)
    write(tmp_path / "uploads" / "voice-sample.wav", 400)  # made from the recordings
    write(tmp_path / "photoreal" / "key" / "library.json", 500)  # made from a photo
    write(tmp_path / "content" / "pdfs" / "d1.pdf", 100)
    write(tmp_path / "content" / "pdfs" / "d1.json", 20)
    write(tmp_path / "content" / "read" / "d1.json", 30)  # read from the PDF
    write(tmp_path / "content" / "pdfs" / "d2.pdf", 200)
    write(tmp_path / "content" / "pdfs" / "d3.pdf", 50)  # from before host accounts
    owners = Owners(tmp_path)
    owners.record("photos", "p1", "a@example.com")
    owners.record("sounds", "s1", "a@example.com")
    owners.record("pdfs", "d1", "a@example.com")
    owners.record("photos", "p2", "b@example.com")
    owners.record("pdfs", "d2", "b@example.com")
    assert count(tmp_path, owners, "a@example.com") == {
        "images_and_recordings": 4000,
        "pdfs": 100,
        "total": 4100,
    }
    assert count(tmp_path, owners, "b@example.com") == {
        "images_and_recordings": 2000,
        "pdfs": 200,
        "total": 2200,
    }
    assert count(tmp_path, owners, "c@example.com")["total"] == 0


def test_an_unreadable_owners_file_counts_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write(tmp_path / "content" / "pdfs" / "d1.pdf", 100)
    (tmp_path / "owners.json").write_text("not json")
    assert count(tmp_path, Owners(tmp_path), "a@example.com")["total"] == 0
    assert "Could not read who added each file" in caplog.messages
