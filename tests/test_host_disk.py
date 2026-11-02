"""The disk space a host has used (roadmap R192)."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_uploads import wav_bytes

from imageskin import admin
from imageskin.app import create_app
from imageskin.host_disk import NOT_RECORDED, Owners, OwnersUnreadable

pytestmark = pytest.mark.real_hosts

PDF = b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF\n"
FIRST = {"email": "first@example.com", "password": "a long secret"}
SECOND = {"email": "second@example.com", "password": "a long secret"}


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    caplog.set_level(logging.INFO)


def on_disk(home: Path, *globs: str) -> int:
    return sum(p.stat().st_size for g in globs for p in home.glob(g))


def test_hosts_at_one_address_count_its_whole_folder(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # R65b, in place of Larry's choice of 2026-10-30: the whole of the site's folder counts, so
    # two hosts of one address (an app on its own, as locally) see the same amounts.
    first = TestClient(create_app(tmp_path))
    first.post("/api/host/sign-up", json=FIRST)
    first.post("/api/consent", json={"agreed": True})
    second = TestClient(first.app)
    second.post("/api/host/sign-up", json=SECOND)

    added = first.post("/api/content", files={"file": ("a.pdf", PDF, "application/pdf")})
    pdf_id = added.json()["id"]
    sound = first.post("/api/uploads/sounds", files={"file": ("a.wav", wav_bytes(), "audio/wav")})
    sound_id = sound.json()["id"]
    first.app.state.readings.wait()  # type: ignore[attr-defined]
    first.app.state.wiki.wait()  # type: ignore[attr-defined]

    amounts = first.get("/api/host/disk").json()
    # What is made from the recording and the PDF counts too (R65b).
    assert amounts["images_and_recordings"] >= on_disk(tmp_path, f"uploads/sounds/{sound_id}.*")
    assert amounts["pdfs"] == on_disk(tmp_path, "content/**/*.*")
    assert amounts["pdfs"] > len(PDF)
    # The host accounts serve every site, so they count for no host.
    assert amounts["other"] < on_disk(tmp_path, "*.json")
    assert second.get("/api/host/disk").json() == amounts

    # Who added each file is still recorded, for R61e and R61f's moves.
    owners = json.loads((tmp_path / "owners.json").read_text())
    assert owners == {"pdfs": {pdf_id: FIRST["email"]}, "sounds": {sound_id: FIRST["email"]}}
    counted = [r for r in caplog.records if r.getMessage() == "Host disk space counted"]
    assert counted[-1].email == SECOND["email"]  # type: ignore[attr-defined]
    assert counted[-2].total == amounts["total"]  # type: ignore[attr-defined]
    assert counted[-2].took_ms >= 0  # type: ignore[attr-defined]


def refused(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.why  # type: ignore[attr-defined]
        for r in caplog.records
        if r.getMessage() == "Host disk space refused"
    ]


def test_a_host_sees_only_their_own_and_anyone_else_is_refused(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Larry, 2026-10-30: a host for their own files, the administrator for any host's.
    first = TestClient(create_app(tmp_path))
    first.post("/api/host/sign-up", json=FIRST)
    second = TestClient(first.app)
    second.post("/api/host/sign-up", json=SECOND)
    nobody = TestClient(first.app)

    assert first.get("/api/host/disk", params={"email": "First@Example.com "}).status_code == 200
    other = first.get("/api/host/disk", params={"email": SECOND["email"]})
    assert other.status_code == 403
    assert other.json() == {"detail": "A host can only see their own disk space."}
    assert nobody.get("/api/host/disk").status_code == 401
    assert nobody.get("/api/host/disk", params={"email": FIRST["email"]}).status_code == 401
    assert refused(caplog) == ["another host's", "not signed in", "not signed in"]


def test_the_administrator_sees_any_hosts(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "admin.toml").write_text('password = "first secret"\n')
    browser = TestClient(create_app(tmp_path))
    browser.post("/api/host/sign-up", json=FIRST)
    TestClient(browser.app).post("/api/host/sign-up", json=SECOND)
    # Signed in as a host too, as the admin sign-in is on Settings (R191).
    assert browser.post("/api/admin/sign-in", json={"password": "first secret"}).status_code == 200
    browser.post("/api/host/sign-out")

    answer = browser.get("/api/host/disk", params={"email": SECOND["email"]})
    assert answer.status_code == 200 and answer.json()["pdfs"] == 0
    assert browser.get("/api/host/disk", params={"email": FIRST["email"]}).status_code == 200
    missing = browser.get("/api/host/disk", params={"email": "nobody@example.com"})
    assert missing.status_code == 404
    assert missing.json() == {"detail": "There is no host with that email address."}
    assert browser.get("/api/host/disk").status_code == 400
    assert refused(caplog) == ["no such host", "no host named"]
    counted = [r for r in caplog.records if r.getMessage() == "Host disk space counted"]
    assert [r.email for r in counted] == [SECOND["email"], FIRST["email"]]  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "broken",
    [
        b"not json",
        b"[]",
        b'{"pdfs": ["d1"]}',
        b'{"pdfs": {"d1": 7}}',
    ],
)
def test_an_unreadable_owners_file_is_never_written_over(tmp_path: Path, broken: bytes) -> None:
    # Codex's review of PR #236: a write after a failed read would have lost every host's record.
    (tmp_path / "owners.json").write_bytes(broken)
    owners = Owners(tmp_path)
    with pytest.raises(OwnersUnreadable):
        owners.record("pdfs", "d2", "a@example.com")
    assert (tmp_path / "owners.json").read_bytes() == broken


def test_a_file_is_refused_not_stored_unrecorded_while_owners_cant_be_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    browser = TestClient(create_app(tmp_path))
    browser.post("/api/host/sign-up", json=FIRST)
    browser.post("/api/consent", json={"agreed": True})
    (tmp_path / "owners.json").write_text("not json")

    pdf = browser.post("/api/content", files={"file": ("a.pdf", PDF, "application/pdf")})
    assert (pdf.status_code, pdf.json()) == (500, {"detail": NOT_RECORDED})
    sound = browser.post("/api/uploads/sounds", files={"file": ("a.wav", wav_bytes(), "audio/wav")})
    assert (sound.status_code, sound.json()) == (500, {"detail": NOT_RECORDED})
    assert browser.get("/api/content").json() == []
    assert browser.get("/api/uploads/sounds").json() == []
    assert (tmp_path / "owners.json").read_text() == "not json"
    assert "File refused: its host can't be recorded" in caplog.messages


def test_a_file_stored_as_owners_breaks_is_taken_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Readable when checked, broken by the time the file is recorded: the file is removed.
    browser = TestClient(create_app(tmp_path))
    browser.post("/api/host/sign-up", json=FIRST)
    browser.post("/api/consent", json={"agreed": True})

    def broken(*_: object) -> None:
        raise OwnersUnreadable("broken meanwhile")

    monkeypatch.setattr(Owners, "record", broken)
    pdf = browser.post("/api/content", files={"file": ("a.pdf", PDF, "application/pdf")})
    assert pdf.status_code == 500
    sound = browser.post("/api/uploads/sounds", files={"file": ("a.wav", wav_bytes(), "audio/wav")})
    assert sound.status_code == 500
    assert browser.get("/api/content").json() == []
    assert browser.get("/api/uploads/sounds").json() == []


def test_the_resources_page_opening_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # R193: the page asks with `opened`, so the log says the view was opened, with the amounts.
    browser = TestClient(create_app(tmp_path))
    browser.post("/api/host/sign-up", json=FIRST)
    browser.get("/api/host/disk")
    assert "Resource view opened" not in caplog.messages
    answer = browser.get("/api/host/disk", params={"opened": "true"}).json()
    [opened] = [r for r in caplog.records if r.getMessage() == "Resource view opened"]
    assert opened.email == FIRST["email"]  # type: ignore[attr-defined]
    assert {k: getattr(opened, k) for k in answer} == answer
