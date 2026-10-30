"""The disk space a host has used (roadmap R192)."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_uploads import wav_bytes

from imageskin import admin
from imageskin.app import create_app
from imageskin.host_disk import Owners, count, size_of
from imageskin.photoreal_library import library_key

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
    return sum(size_of(p) for g in globs for p in home.glob(g))


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
    # The recording with its info file; the voice sample made from it goes with the first host,
    # as no photo is chosen.
    assert amounts["images_and_recordings"] == on_disk(
        tmp_path, f"uploads/sounds/{sound_id}.*", "uploads/voice-sample.wav"
    )
    assert amounts["pdfs"] == on_disk(tmp_path, f"content/*/{pdf_id}.*")
    assert amounts["pdfs"] >= len(PDF)
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


def test_files_from_before_host_accounts_count_for_the_first_host(tmp_path: Path) -> None:
    write(tmp_path / "uploads" / "photos" / "p1.jpg", 1000)
    write(tmp_path / "uploads" / "photos" / "p1.json", 10)
    write(tmp_path / "uploads" / "photos" / "p2.jpg", 2000)
    face = tmp_path / "photoreal" / library_key(tmp_path / "uploads" / "photos" / "p1.jpg")
    write(face / "library.json", 300)
    write(face / "frames" / "0.png", 400)
    write(tmp_path / "uploads" / "chosen-photo.json", 0)
    (tmp_path / "uploads" / "chosen-photo.json").write_text('{"id": "p2"}')
    write(tmp_path / "clips" / "sample.mp4", 5000)
    write(tmp_path / "replies" / "r.mp4", 7000)
    write(tmp_path / "content" / "pdfs" / "d1.pdf", 100)
    write(tmp_path / "content" / "pdfs" / "d1.json", 20)
    write(tmp_path / "content" / "read" / "d1.json", 30)
    write(tmp_path / "content" / "wiki" / "d1.history" / "v1.json", 40)
    write(tmp_path / "content" / "wiki" / "pace.json", 9)  # from no one PDF
    write(tmp_path / "content" / "pdfs" / "d2.pdf", 200)
    owners = Owners(tmp_path)
    owners.record("photos", "p2", "second@example.com")
    owners.record("pdfs", "d2", "second@example.com")

    chosen = len('{"id": "p2"}')
    first = count(tmp_path, owners, "first@example.com", "first@example.com")
    assert first == {"images_and_recordings": 1710, "pdfs": 190, "total": 1900}
    # The second host's photo is the one chosen, so what was prepared from it is theirs.
    second = count(tmp_path, owners, "second@example.com", "first@example.com")
    assert second == {
        "images_and_recordings": 2000 + chosen + 5000 + 7000,
        "pdfs": 200,
        "total": 14200 + chosen,
    }


def test_an_unreadable_owners_file_counts_everything_for_the_first_host(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write(tmp_path / "content" / "pdfs" / "d1.pdf", 100)
    (tmp_path / "owners.json").write_text("not json")
    assert count(tmp_path, Owners(tmp_path), "a@example.com", "a@example.com")["pdfs"] == 100
    assert "Could not read who added each file" in caplog.messages
    assert count(tmp_path, Owners(tmp_path), "b@example.com", "a@example.com")["total"] == 0
