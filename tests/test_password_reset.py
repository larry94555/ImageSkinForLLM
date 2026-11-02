"""Forgot password: a one-time link by email, valid for an hour, to set a new password (roadmap
R62a)."""

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
from imageskin.email_sending import FAILED, Email, EmailFailed
from imageskin.hosts import CONFIRMED, RESET_HOURS, SHORT_PASSWORD, HostRefused
from imageskin.password_reset import LINK_FAILED, LINK_ON_ITS_WAY, RESET_SUBJECT

pytestmark = pytest.mark.real_hosts

ANN = "ann@example.com"  # the host of site a
NEW = "a new long secret"


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


def emails(home: Path) -> list[str]:
    files = sorted((home / "outbox").glob("*.eml"), key=lambda p: p.stat().st_mtime_ns)
    parsed = [message_from_bytes(f.read_bytes(), policy=default) for f in files]
    return [f"Subject: {m['Subject']}\n{m.get_body().get_content()}" for m in parsed]  # type: ignore[union-attr]


def token_in(text: str) -> str:
    found = re.search(r"#/host/reset/(\S+)", text)
    assert found is not None
    return found.group(1)


def forgot(browser: TestClient, email: str, at: str = "") -> None:
    asked = browser.post(f"{at}/api/host/forgot", json={"email": email})
    assert asked.status_code == 200 and asked.json() == {"detail": LINK_ON_ITS_WAY}


def test_forgot_password_sets_a_new_password_from_the_email_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path)
    home = tmp_path / "home"
    site = TestClient(sites, base_url="http://a.localhost:8000")
    signed_in = site.post("/api/host/sign-in", json={"email": ANN, "password": PASSWORD})
    assert signed_in.status_code == 200
    browser = TestClient(sites, base_url="http://a.localhost:8000")
    with caplog.at_level(logging.INFO):
        forgot(browser, "Ann@Example.com")
    assert "Password reset link sent" in caplog.messages
    [sent] = emails(home)
    assert f"Subject: {RESET_SUBJECT}" in sent
    assert "http://a.localhost:8000/#/host/reset/" in sent
    token = token_in(sent)

    short = browser.post("/api/host/reset", json={"token": token, "password": "short"})
    assert short.status_code == 400 and short.json()["detail"] == SHORT_PASSWORD
    with caplog.at_level(logging.INFO):
        done = browser.post("/api/host/reset", json={"token": token, "password": NEW})
    assert done.json() == {"reset": True, "email": ANN}
    record = next(r for r in caplog.records if r.message == "Host password reset")
    assert record.__dict__["by"] == "link" and record.__dict__["sign_ins_ended"] == 1
    # The sign-in from before ended; the old password no longer works, the new one does.
    assert site.get("/api/host/session").json()["signed_in"] is False
    old = browser.post("/api/host/sign-in", json={"email": ANN, "password": PASSWORD})
    assert old.status_code == 401
    assert (
        browser.post("/api/host/sign-in", json={"email": ANN, "password": NEW}).status_code == 200
    )

    # The same link again is refused.
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        again = browser.post("/api/host/reset", json={"token": token, "password": NEW + "!"})
    assert again.status_code == 400 and again.json()["detail"] == LINK_FAILED
    why = next(r for r in caplog.records if r.message == "Host password not reset")
    assert why.__dict__["why"] == "unknown link"
    assert service.host_accounts.site_of(ANN) == "a"


def test_an_unknown_email_gets_the_same_answer_and_no_email(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, _ = served(tmp_path)
    browser = TestClient(sites, base_url="http://localhost:8000")
    with caplog.at_level(logging.WARNING):
        forgot(browser, "nobody@example.com")
    assert not (tmp_path / "home" / "outbox").exists()
    record = next(r for r in caplog.records if r.message == "Password reset link not made")
    assert record.__dict__["why"] == "no such host"


def test_a_link_works_for_an_hour_and_only_the_newest(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path)
    home = tmp_path / "home"
    clock = Clock()
    service.host_accounts.clock = clock
    browser = TestClient(sites, base_url="http://a.localhost:8000")
    forgot(browser, ANN)
    first = token_in(emails(home)[0])
    # Asked again within a minute: the same answer, no second email, the first link kept.
    forgot(browser, ANN)
    assert len(emails(home)) == 1
    clock.now += 61
    forgot(browser, ANN)
    second = token_in(emails(home)[1])
    assert second != first
    stale = browser.post("/api/host/reset", json={"token": first, "password": NEW})
    assert stale.status_code == 400 and stale.json()["detail"] == LINK_FAILED
    clock.now += RESET_HOURS * 3600 + 1
    old = browser.post("/api/host/reset", json={"token": second, "password": NEW})
    assert old.status_code == 400 and old.json()["detail"] == LINK_FAILED


def test_the_link_comes_to_the_site_it_was_asked_from(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    code, _ = service.sites.add_trial("bob@example.com")
    browser = TestClient(sites, base_url="http://localhost:8000")
    forgot(browser, "bob@example.com", at=f"/t/{code}")
    [sent] = emails(tmp_path / "home")
    assert f"http://localhost:8000/t/{code}/#/host/reset/" in sent


def test_a_new_password_from_the_email_confirms_it(tmp_path: Path) -> None:
    _, _, service = served(tmp_path)
    accounts = service.host_accounts
    accounts.sign_up("dan@example.com", PASSWORD, "test", confirm=True)
    token = accounts.reset_link("dan@example.com")
    assert token is not None
    assert accounts.reset_with(token, NEW) == "dan@example.com"
    assert accounts._load()["hosts"]["dan@example.com"][CONFIRMED] is True
    with pytest.raises(HostRefused):
        accounts.reset_with(token, "short")


def test_an_email_that_cant_be_sent_gets_the_same_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path)

    def down(email: Email, *rest: object) -> Path:
        raise EmailFailed(FAILED)

    monkeypatch.setattr(service.mailer, "_write", down)
    browser = TestClient(sites, base_url="http://a.localhost:8000")
    with caplog.at_level(logging.ERROR):
        forgot(browser, ANN)
    assert "Password reset email failed" in caplog.messages
