"""A customer who signs up at the main address confirms their email from a link before managing
their site (roadmap R62b)."""

import logging
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_customer_sign_up import DAN, SITE, confirmation_link, sign_up
from test_site_addresses import PASSWORD, served

from imageskin import admin
from imageskin.email_sending import FAILED, Email, EmailFailed
from imageskin.host_api import ALREADY_CONFIRMED, CONFIRM_SUBJECT, NOT_SIGNED_IN
from imageskin.hosts import CONFIRM_DAYS, TOO_SOON, HostRefused

pytestmark = pytest.mark.real_hosts


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


def outbox(home: Path) -> list[Path]:
    return sorted((home / "outbox").glob("*.eml"))


def test_a_new_customer_confirms_their_email_before_managing_their_site(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, _ = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    browser = TestClient(sites, base_url="http://localhost:8000")
    with caplog.at_level(logging.INFO):
        code = str(sign_up(browser, DAN)["site"])
    assert "Confirmation email sent" in caplog.messages
    [sent] = outbox(home)
    assert CONFIRM_SUBJECT in sent.read_text()
    link = confirmation_link(home)
    assert link.startswith(f"http://localhost:8000/t/{code}/api/host/confirm/")

    # Until then the site's host pages are refused, and the browser is told to confirm.
    session = browser.get(f"/t/{code}/api/host/session").json()
    assert session == {"signed_in": True, "email": DAN, "confirmed": False, "trial": True, **SITE}
    assert browser.get(f"/t/{code}/api/host/me").status_code == 401
    assert browser.get(f"/t/{code}/api/settings").json()["view"] == "participant"
    assert browser.post(f"/t/{code}/api/settings/access", json={}).json()["shown"] is False

    with caplog.at_level(logging.INFO):
        confirmed = browser.get(link, follow_redirects=False)
    assert confirmed.status_code == 303
    assert confirmed.headers["location"] == f"/t/{code}/#/setup"
    assert "Host email confirmed" in caplog.messages
    session = browser.get(f"/t/{code}/api/host/session").json()
    assert session == {"signed_in": True, "email": DAN, "confirmed": True, "trial": True, **SITE}
    assert browser.get(f"/t/{code}/api/host/me").status_code == 200

    # A used link says it didn't work.
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        again = browser.get(link, follow_redirects=False)
    assert again.headers["location"] == f"/t/{code}/#/host/confirm-failed"
    unknown = next(r for r in caplog.records if r.message == "Host email not confirmed")
    assert unknown.__dict__["why"] == "unknown link"
    sent_again = browser.post(f"/t/{code}/api/host/confirm/send")
    assert sent_again.status_code == 409 and sent_again.json()["detail"] == ALREADY_CONFIRMED


def test_a_link_works_for_seven_days(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    clock = Clock()
    service.host_accounts.clock = clock
    browser = TestClient(sites, base_url="http://localhost:8000")
    code = str(sign_up(browser, DAN)["site"])
    clock.now += CONFIRM_DAYS * 86400 + 60
    with caplog.at_level(logging.WARNING):
        old = browser.get(confirmation_link(tmp_path / "home"), follow_redirects=False)
    assert old.headers["location"] == f"/t/{code}/#/host/confirm-failed"
    too_old = next(r for r in caplog.records if r.message == "Host email not confirmed")
    assert too_old.__dict__["why"] == "link too old"
    assert browser.get(f"/t/{code}/api/host/session").json()["confirmed"] is False


def test_send_it_again_sends_a_new_link_at_most_once_a_minute(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    clock = Clock()
    service.host_accounts.clock = clock
    browser = TestClient(sites, base_url="http://localhost:8000")
    code = str(sign_up(browser, DAN)["site"])
    first = confirmation_link(home)

    soon = browser.post(f"/t/{code}/api/host/confirm/send")
    assert soon.status_code == 429 and soon.json()["detail"] == TOO_SOON
    clock.now += 61
    assert browser.post(f"/t/{code}/api/host/confirm/send").json() == {"sent": True}
    assert len(outbox(home)) == 2
    second = confirmation_link(home)
    assert second != first
    # Only the newest link works.
    failed = browser.get(first, follow_redirects=False)
    assert failed.headers["location"].endswith("#/host/confirm-failed")
    assert browser.get(second, follow_redirects=False).headers["location"].endswith("#/setup")

    stranger = TestClient(sites, base_url="http://localhost:8000")
    refused = stranger.post(f"/t/{code}/api/host/confirm/send")
    assert refused.status_code == 401 and refused.json()["detail"] == NOT_SIGNED_IN


def test_an_email_that_cant_be_sent_still_makes_the_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    clock = Clock()
    service.host_accounts.clock = clock

    def down(email: Email) -> Path | None:
        raise EmailFailed(FAILED)

    # The routes were given the mailer's send when the app was made, so it is its own.
    monkeypatch.setattr(service.mailer, "_write", lambda *a: down(a[0]))
    browser = TestClient(sites, base_url="http://localhost:8000")
    with caplog.at_level(logging.ERROR):
        code = str(sign_up(browser, DAN)["site"])
    assert "Confirmation email failed" in caplog.messages
    assert browser.get(f"/t/{code}/api/host/session").json()["confirmed"] is False
    clock.now += 61
    again = browser.post(f"/t/{code}/api/host/confirm/send")
    assert again.status_code == 503 and again.json()["detail"] == FAILED


def test_signing_up_again_once_confirmed_keeps_it_confirmed(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    browser = TestClient(sites, base_url="http://localhost:8000")
    code = str(sign_up(browser, DAN)["site"])
    browser.get(confirmation_link(home), follow_redirects=False)
    again = browser.post("/api/host/sign-up", json={"email": DAN, "password": PASSWORD})
    assert again.status_code == 200 and again.json()["confirmed"] is True
    assert again.json()["go_to"] == f"/t/{code}/"
    assert len(outbox(home)) == 1


def test_hosts_who_signed_up_without_a_site_need_no_confirmation(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path, sign_up_makes_site=False)
    browser = TestClient(sites, base_url="http://localhost:8000")
    body = sign_up(browser, DAN)
    assert body["confirmed"] is True
    assert browser.get("/api/host/me").status_code == 200
    assert not (tmp_path / "home" / "outbox").exists()


def test_only_an_unconfirmed_host_gets_a_link(tmp_path: Path) -> None:
    _, _, service = served(tmp_path)
    accounts = service.host_accounts
    with pytest.raises(HostRefused):
        accounts.confirmation("nobody@example.com")
    assert accounts.confirmation("ann@example.com") is None  # from before R62b
    accounts.sign_up(DAN, PASSWORD, "test", confirm=True)
    token = accounts.confirmation(DAN)
    assert token is not None and accounts.confirm(token) == DAN
    assert accounts.confirmation(DAN) is None


def test_signing_up_again_sends_another_link_only_as_send_it_again_would(
    tmp_path: Path,
) -> None:
    # Codex's review of PR #280: signing up again doesn't get round the minute between emails.
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    clock = Clock()
    service.host_accounts.clock = clock
    browser = TestClient(sites, base_url="http://localhost:8000")
    code = str(sign_up(browser, DAN)["site"])
    first = confirmation_link(home)

    again = sign_up(browser, DAN)
    assert again["go_to"] == f"/t/{code}/" and again["confirmed"] is False
    assert len(outbox(home)) == 1
    clock.now += 61
    sign_up(browser, DAN)
    assert len(outbox(home)) == 2
    second = confirmation_link(home)
    assert second != first
    failed = browser.get(first, follow_redirects=False)
    assert failed.headers["location"].endswith("#/host/confirm-failed")
    assert browser.get(second, follow_redirects=False).headers["location"].endswith("#/setup")


def test_the_first_link_still_works_after_signing_up_again_at_once(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path, sign_up_makes_site=True)
    browser = TestClient(sites, base_url="http://localhost:8000")
    code = str(sign_up(browser, DAN)["site"])
    first = confirmation_link(tmp_path / "home")
    sign_up(browser, DAN)
    assert browser.get(first, follow_redirects=False).headers["location"].endswith("#/setup")
    assert browser.get(f"/t/{code}/api/host/session").json()["confirmed"] is True
