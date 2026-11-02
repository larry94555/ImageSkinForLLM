"""Every site file in the resource view (roadmap R65b): a host's disk space is the whole of their
site's folder, in six lines, so the total always matches the folder."""

import io
import logging
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_acting_as_host import administrator
from test_chat import FakeLlm2
from test_site_addresses import PASSWORD, lesson, with_hosts
from test_uploads import wav_bytes

from imageskin import admin
from imageskin.app import create_app
from imageskin.host_disk import AMOUNTS, SERVICE, count
from imageskin.review import Review
from imageskin.sites import SiteApps, site_home, site_matcher
from imageskin.uploads import PhotoResult

pytestmark = pytest.mark.real_hosts

ANN, BOB = "ann@example.com", "bob@example.com"  # site a's host, and the main address's
SITE_A, MAIN = "http://a.localhost:8000", "http://localhost:8000"
PDF = b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF\n"
JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def served(tmp_path: Path) -> tuple[SiteApps, dict[str, FastAPI], Path]:
    home = tmp_path / "home"
    service = with_hosts(home, ANN, BOB)
    service.sites.add("a", ANN)
    made: dict[str, FastAPI] = {}

    def make(site: str) -> FastAPI:
        made[site] = create_app(
            site_home(site, home),
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            ask_llm=FakeLlm2(),
            read_pdf=lesson,
            build_wiki=MagicMock(),
            service=service,
            site=site,
        )
        return made[site]

    return SiteApps(make, site_matcher(service.sites, "me0.ai")), made, home


def signed_in(sites: SiteApps, address: str, email: str) -> TestClient:
    browser = TestClient(sites, base_url=address)
    answer = browser.post("/api/host/sign-in", json={"email": email, "password": PASSWORD})
    assert answer.is_success, answer.text
    return browser


def on_disk(folder: Path, leave_out: frozenset[str] = frozenset()) -> int:
    """The size of every file under the folder, but those under the names in `leave_out`."""
    return sum(
        p.stat().st_size
        for p in folder.rglob("*")
        if p.relative_to(folder).parts[0] not in leave_out and p.is_file()
    )


def disk(browser: TestClient) -> dict[str, int]:
    answer = browser.get("/api/host/disk")
    assert answer.status_code == 200, answer.text
    amounts = dict(answer.json())
    assert set(amounts) == {*AMOUNTS, "total"}
    assert amounts["total"] == sum(amounts[k] for k in AMOUNTS)
    return amounts


def test_the_total_is_the_whole_site_folder_and_no_other_sites(tmp_path: Path) -> None:
    sites, made, home = served(tmp_path)
    ann = signed_in(sites, SITE_A, ANN)
    bob = signed_in(sites, MAIN, BOB)
    a_home = site_home("a", home)
    assert ann.post("/api/consent", json={"agreed": True}).is_success
    bobs = disk(bob)
    assert bobs["total"] == on_disk(home, SERVICE)

    def matches() -> dict[str, int]:
        amounts = disk(ann)
        assert amounts["total"] == on_disk(a_home)
        assert disk(bob) == bobs  # another site's amounts unchanged throughout
        return amounts

    # A photo and a recording, with what is made from them.
    photo = ann.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)}).json()["id"]
    sound = ann.post("/api/uploads/sounds", files={"file": ("a.wav", wav_bytes(), "audio/wav")})
    assert sound.is_success, sound.text
    media = matches()["images_and_recordings"]
    assert media >= len(JPG)
    # A PDF, read, with its wiki.
    added = ann.post("/api/content", files={"file": ("a.pdf", io.BytesIO(PDF))})
    pdf = added.json()["id"]
    made["a"].state.readings.wait()
    assert matches()["pdfs"] > len(PDF)
    # The identity saved, a visitor's question, a changed setting.
    assert ann.put("/api/customization/identity", json={"name": "Ada"}).is_success
    assert matches()["guidelines"] > 0
    visitor = TestClient(sites, base_url=SITE_A)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        asked = visitor.post("/api/chat", json={"prompt": "Hello?"})
    assert asked.is_success, asked.text
    assert matches()["conversations"] > 0
    assert ann.patch("/api/settings", json={"general_prompts": True}).is_success
    assert matches()["preferences"] > 0
    assert matches()["other"] > 0  # consent.json, owners.json
    # The PDF deleted and the photo replaced.
    assert ann.delete(f"/api/content/{pdf}").is_success
    assert matches()["pdfs"] < len(PDF)
    ann.post("/api/uploads/photos", files={"file": ("you.jpg", JPG + b"more")})
    assert ann.delete(f"/api/uploads/photos/{photo}").is_success
    matches()


def test_the_administrator_counts_a_hosts_own_site(tmp_path: Path) -> None:
    sites, _, home = served(tmp_path)
    ann = signed_in(sites, SITE_A, ANN)
    ann.post("/api/consent", json={"agreed": True})
    ann.post("/api/content", files={"file": ("a.pdf", io.BytesIO(PDF))})
    boss = administrator(sites, tmp_path)
    asked = boss.get("/api/host/disk", params={"email": ANN}).json()
    assert asked["total"] == on_disk(site_home("a", home)) == disk(ann)["total"]
    bobs = boss.get("/api/host/disk", params={"email": BOB}).json()
    assert bobs["total"] == on_disk(home, SERVICE)


def write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_each_file_is_counted_once_in_its_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write(tmp_path / "uploads" / "photos" / "p1.jpg", 1000)
    write(tmp_path / "photoreal" / "key" / "library.json", 500)
    write(tmp_path / "replies" / "idle" / "me.mp4", 70)
    write(tmp_path / "content" / "pdfs" / "d1.pdf", 100)
    write(tmp_path / "content" / "wiki" / "d1.json", 30)
    write(tmp_path / "customization.json", 40)
    write(tmp_path / "customization.history.json", 5)
    write(tmp_path / "conversation.json", 20)
    write(tmp_path / "conversations" / "abc.json", 8)
    write(tmp_path / "ui-settings.json", 3)
    write(tmp_path / "llm.json", 2)
    write(tmp_path / "consent.json", 9)
    write(tmp_path / "hosts.json", 600)  # the service's, at the main address
    write(tmp_path / "models" / "faces" / "m.bin", 9000)
    os.link(tmp_path / "content" / "pdfs" / "d1.pdf", tmp_path / "content" / "pdfs" / "d1.copy")
    os.symlink(tmp_path / "models", tmp_path / "content" / "models")  # never followed or counted
    with caplog.at_level(logging.INFO):
        amounts = count(tmp_path, ANN, SERVICE)
    assert amounts == {
        "images_and_recordings": 1570,
        "pdfs": 130,  # the PDF linked twice counted once
        "guidelines": 45,
        "conversations": 28,
        "preferences": 5,
        "other": 9,
        "total": 1787,
    }
    counted = next(r for r in caplog.records if r.message == "Host disk space counted")
    assert counted.__dict__["total"] == amounts["total"] and counted.__dict__["took_ms"] >= 0
    # Another site's folder holds only its own, so nothing is left out there.
    assert count(tmp_path, ANN)["other"] == 9 + 600 + 9000


def test_a_file_that_cant_be_read_is_logged_and_left_out(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path / "content" / "pdfs" / "d1.pdf", 100)
    write(tmp_path / "content" / "pdfs" / "gone.pdf", 50)
    real = Path.lstat

    def lstat(self: Path) -> os.stat_result:
        if self.name == "gone.pdf":
            raise FileNotFoundError(2, "removed meanwhile", str(self))
        return real(self)

    monkeypatch.setattr(Path, "lstat", lstat)
    assert count(tmp_path, ANN)["pdfs"] == 100
    failed = next(r for r in caplog.records if r.message == "Could not count a file of the site")
    assert failed.__dict__["path"].endswith("gone.pdf")
