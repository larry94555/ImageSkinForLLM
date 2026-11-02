"""Changing a host's email address: asked for with the password, confirmed from the new address,
with a notice to the old one (roadmap R62c)."""

import logging
import re
import time
from email import message_from_bytes
from email.policy import default
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_site_addresses import PASSWORD, served

from imageskin import admin
from imageskin.email_change import CHANGE_SUBJECT, CHANGED_SUBJECT, WRONG_PASSWORD
from imageskin.host_disk import Owners
from imageskin.hosts import (
    BAD_EMAIL,
    CHANGE_HOURS,
    CONFIRMED,
    EMAIL_TAKEN,
    SAME_EMAIL,
    TOO_SOON,
)
from imageskin.sites import site_home

pytestmark = pytest.mark.real_hosts

ANN, NEW, BOB = "ann@example.com", "ann.new@example.com", "bob@example.com"


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now


def emails(home: Path) -> list[dict[str, str]]:
    files = sorted((home / "outbox").glob("*.eml"), key=lambda p: p.stat().st_mtime_ns)
    parsed = [message_from_bytes(f.read_bytes(), policy=default) for f in files]
    return [
        {"to": str(m["To"]), "subject": str(m["Subject"]), "text": m.get_body().get_content()}  # type: ignore[union-attr]
        for m in parsed
    ]


def link_in(text: str) -> str:
    found = re.search(r"https?://\S+/api/host/email/confirm/\S+", text)
    assert found is not None
    return found.group(0)


def signed_in(sites: object) -> TestClient:
    browser = TestClient(sites, base_url="http://a.localhost:8000")  # type: ignore[arg-type]
    assert browser.post("/api/host/sign-in", json={"email": ANN, "password": PASSWORD}).is_success
    return browser


def ask(browser: TestClient, new: str = NEW, password: str = PASSWORD) -> tuple[int, str]:
    asked = browser.post("/api/host/email", json={"new_email": new, "password": password})
    return asked.status_code, asked.json().get("detail", asked.json().get("sent_to"))


def test_a_host_changes_their_email_from_a_link_sent_to_the_new_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path)
    home = tmp_path / "home"
    Owners(site_home("a", home)).record("photos", "p1", ANN)
    browser = signed_in(sites)
    assert ask(browser, password="not the password") == (401, WRONG_PASSWORD)
    with caplog.at_level(logging.INFO):
        assert ask(browser, "Ann.New@Example.com") == (200, NEW)
    assert "Email change link sent" in caplog.messages
    [sent] = emails(home)
    assert sent["to"] == NEW and sent["subject"] == CHANGE_SUBJECT
    link = link_in(sent["text"])
    assert link.startswith("http://a.localhost:8000/api/host/email/confirm/")
    # Nothing changes until the link is used.
    assert service.host_accounts.site_of(ANN) == "a"

    with caplog.at_level(logging.INFO):
        changed = browser.get(link, follow_redirects=False)
    assert changed.status_code == 303 and changed.headers["location"] == "/#/host/email-changed"
    assert "Host email changed" in caplog.messages
    accounts = service.host_accounts
    assert accounts.site_of(NEW) == "a" and accounts.site_of(ANN) is None
    assert service.sites.host("a") == NEW
    assert Owners(site_home("a", home)).read() == {"photos": {"p1": NEW}}
    # Still signed in, as the new email; the old address is told.
    assert browser.get("/api/host/session").json()["email"] == NEW
    notice = emails(home)[-1]
    assert notice["to"] == ANN and notice["subject"] == CHANGED_SUBJECT and NEW in notice["text"]
    other = TestClient(sites, base_url="http://a.localhost:8000")
    old = other.post("/api/host/sign-in", json={"email": ANN, "password": PASSWORD})
    assert old.status_code == 401
    new = other.post("/api/host/sign-in", json={"email": NEW, "password": PASSWORD})
    assert new.is_success

    used = browser.get(link, follow_redirects=False)
    assert used.headers["location"] == "/#/host/email-failed"


def test_a_change_is_refused_with_its_reason(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path)
    service.host_accounts.clock = clock = Clock()
    browser = signed_in(sites)
    assert ask(browser, ANN) == (400, SAME_EMAIL)
    assert ask(browser, "not an email") == (400, BAD_EMAIL)
    assert ask(browser, BOB) == (409, EMAIL_TAKEN)
    assert ask(browser)[0] == 200
    assert ask(browser, "ann.other@example.com") == (429, TOO_SOON)
    clock.now += 61
    assert ask(browser, "ann.other@example.com")[0] == 200
    stranger = TestClient(sites, base_url="http://a.localhost:8000")
    assert ask(stranger)[0] == 401


def test_a_link_works_for_a_day_and_only_while_the_email_is_free(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path)
    home = tmp_path / "home"
    service.host_accounts.clock = clock = Clock()
    browser = signed_in(sites)
    ask(browser)
    late = link_in(emails(home)[-1]["text"])
    clock.now += CHANGE_HOURS * 3600 + 1
    assert browser.get(late, follow_redirects=False).headers["location"].endswith("email-failed")
    clock.now += 61
    ask(browser)
    taken = link_in(emails(home)[-1]["text"])
    service.host_accounts.sign_up(NEW, PASSWORD, "test")
    assert browser.get(taken, follow_redirects=False).headers["location"].endswith("email-failed")
    assert service.host_accounts.site_of(ANN) == "a" and service.sites.host("a") == ANN


def test_the_site_and_the_files_are_put_back_if_the_account_cant_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sites, _, service = served(tmp_path)
    home = tmp_path / "home"
    Owners(site_home("a", home)).record("pdfs", "d1", ANN)
    browser = signed_in(sites)
    ask(browser)
    monkeypatch.setattr(service.host_accounts, "change_email", lambda token: None)
    failed = browser.get(link_in(emails(home)[-1]["text"]), follow_redirects=False)
    assert failed.headers["location"].endswith("email-failed")
    assert service.sites.host("a") == ANN
    assert Owners(site_home("a", home)).read() == {"pdfs": {"d1": ANN}}


def test_a_new_email_confirmed_from_its_link_counts_as_confirmed(tmp_path: Path) -> None:
    _, _, service = served(tmp_path)
    accounts = service.host_accounts
    accounts.sign_up("dan@example.com", PASSWORD, "test", confirm=True)
    token = accounts.email_change("dan@example.com", "dan2@example.com")
    assert accounts.change_email(token) == ("dan@example.com", "dan2@example.com")
    assert accounts._load()["hosts"]["dan2@example.com"][CONFIRMED] is True
    assert accounts.password_is("dan2@example.com", PASSWORD)
    assert not accounts.password_is("dan@example.com", PASSWORD)
