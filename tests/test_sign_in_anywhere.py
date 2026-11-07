"""A host signs in at any address and lands on their own site, signed in (roadmap R255).

Larry, 2026-11-03: signing in at app.me0.ai was refused with "Your site is at
larry-freeman.me0.ai. Sign in there." The right password at another site's address now sends the
browser to the host's own site with a one-time link, which signs them in there."""

import logging
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_site_addresses import PASSWORD, quick_hashes, served  # noqa: F401 (the fixture)

from imageskin import hosts
from imageskin.host_api import MAIN_ADDRESS_VARIABLE
from imageskin.hosts import DEFAULT_SITE, SIGN_IN_LINK_S, WRONG, trial_cookie

ANN = "ann@example.com"  # site a's host, at a.localhost
BOB = "bob@example.com"  # the main address's host
CY = "cy@example.com"

pytestmark = pytest.mark.real_hosts


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now


def sent_to(client: TestClient, email: str, path: str = "") -> str:
    """Sign in at the client's address: the one-time link to the host's own site."""
    answer = client.post(f"{path}/api/host/sign-in", json={"email": email, "password": PASSWORD})
    assert answer.status_code == 200 and answer.json()["signed_in"] is False
    return str(answer.json()["sign_in_at"])


def test_a_host_signs_in_at_the_main_address_and_lands_on_their_site(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, _ = served(tmp_path)
    main = TestClient(sites, base_url="http://localhost")
    with caplog.at_level(logging.INFO):
        link = sent_to(main, ANN)
    sent = next(r for r in caplog.records if r.message == "Host sent to their own site")
    assert sent.__dict__["here"] == DEFAULT_SITE and sent.__dict__["site"] == "a"
    assert link.startswith("http://a.localhost/api/host/sign-in/")
    # Nothing is signed in at the main address, which isn't Ann's.
    assert main.get("/api/host/session").json()["signed_in"] is False

    a = TestClient(sites, base_url="http://a.localhost")
    caplog.clear()
    with caplog.at_level(logging.INFO):
        opened = a.get(link.removeprefix("http://a.localhost"), follow_redirects=False)
    assert opened.status_code == 303 and opened.headers["location"] == "/#/"
    assert "imageskin_host=" in opened.headers["set-cookie"]
    signed = next(r for r in caplog.records if r.message == "Host signed in")
    assert signed.__dict__["email"] == ANN and signed.__dict__["from"] == "another address"
    assert a.get("/api/host/session").json()["email"] == ANN
    assert a.get("/api/host/me").status_code == 200

    # The link works once.
    again = TestClient(sites, base_url="http://a.localhost")
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        used = again.get(link.removeprefix("http://a.localhost"), follow_redirects=False)
    assert used.headers["location"] == "/#/sign-in" and "set-cookie" not in used.headers
    refused = next(r for r in caplog.records if r.message == "Host sign-in link refused")
    assert refused.__dict__["why"] == "unknown link"


def test_a_host_signs_in_at_another_sites_subdomain(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path)
    a = TestClient(sites, base_url="http://a.localhost:8000")
    link = sent_to(a, BOB)
    assert link.startswith("http://localhost:8000/api/host/sign-in/")
    assert a.get("/api/host/session").json()["signed_in"] is False
    main = TestClient(sites, base_url="http://localhost:8000")
    assert main.get(link.removeprefix("http://localhost:8000"), follow_redirects=False).is_redirect
    assert main.get("/api/host/session").json()["email"] == BOB


def test_a_trial_sites_host_lands_on_its_trial_path(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path)
    service.host_accounts.sign_up(CY, PASSWORD, "test")
    code, _ = service.sites.add_trial(CY)
    for start in ("http://a.localhost:8000", "http://localhost:8000"):
        browser = TestClient(sites, base_url=start)
        link = sent_to(browser, CY)
        assert link.startswith(f"http://localhost:8000/t/{code}/api/host/sign-in/")
        trial = TestClient(sites, base_url="http://localhost:8000")
        opened = trial.get(link.removeprefix("http://localhost:8000"), follow_redirects=False)
        assert opened.headers["location"] == f"/t/{code}/#/"
        # The trial site's own cookie, for its path only (R62).
        assert opened.headers["set-cookie"].startswith(f"{trial_cookie(code)}=")
        assert f"Path=/t/{code}/" in opened.headers["set-cookie"]
        assert trial.get(f"/t/{code}/api/host/session").json()["email"] == CY
        assert trial.get("/api/host/session").json()["signed_in"] is False


def test_a_link_works_only_on_the_hosts_own_site_and_for_a_minute(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path)
    clock = Clock()
    service.host_accounts.clock = clock
    main = TestClient(sites, base_url="http://localhost")
    a = TestClient(sites, base_url="http://a.localhost")

    # Opened on another site, it signs in nobody there.
    link = sent_to(main, ANN).removeprefix("http://a.localhost")
    with caplog.at_level(logging.WARNING):
        elsewhere = main.get(link, follow_redirects=False)
    assert elsewhere.headers["location"] == "/#/sign-in"
    assert main.get("/api/host/session").json()["signed_in"] is False
    why = [r.__dict__["why"] for r in caplog.records if r.message == "Host sign-in link refused"]
    assert why == ["another site's host"]

    caplog.clear()
    link = sent_to(main, ANN).removeprefix("http://a.localhost")
    clock.now += SIGN_IN_LINK_S + 1
    with caplog.at_level(logging.WARNING):
        assert a.get(link, follow_redirects=False).headers["location"] == "/#/sign-in"
    assert a.get("/api/host/session").json()["signed_in"] is False
    why = [r.__dict__["why"] for r in caplog.records if r.message == "Host sign-in link refused"]
    assert why == ["link too old"]


def test_a_wrong_password_elsewhere_learns_nothing(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path)
    main = TestClient(sites, base_url="http://localhost")
    for email in (ANN, "nobody@example.com"):
        wrong = main.post("/api/host/sign-in", json={"email": email, "password": "x" * 12})
        assert wrong.status_code == 401 and wrong.json() == {"detail": WRONG}


def test_the_links_kept_are_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sites, _, service = served(tmp_path)
    monkeypatch.setattr(hosts, "SIGN_IN_LINKS_KEPT", 2)
    accounts = service.host_accounts
    first = accounts.sign_in_link(ANN)
    accounts.sign_in_link(ANN)
    last = accounts.sign_in_link(ANN)
    assert accounts.open_sign_in_link(first, "a", "test") is None  # the oldest was dropped
    assert accounts.open_sign_in_link(last, "a", "test") is not None
    # A host deleted since the link was made isn't signed in.
    link = accounts.sign_in_link(CY)
    assert accounts.open_sign_in_link(link, DEFAULT_SITE, "test") is None


def test_a_main_site_host_on_the_hosted_service_is_sent_to_the_main_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """From anna.me0.ai, a host of the main address's site goes to app.me0.ai, where Caddy
    serves the app, not to the bare me0.ai (Codex's review of PR #295)."""
    monkeypatch.setenv(MAIN_ADDRESS_VARIABLE, "app.me0.ai")
    sites, _, service = served(tmp_path)
    service.host_accounts.sign_up(CY, PASSWORD, "test")
    code, _ = service.sites.add_trial(CY)
    a = TestClient(sites, base_url="https://a.me0.ai")
    assert sent_to(a, BOB).startswith("https://app.me0.ai/api/host/sign-in/")
    assert sent_to(a, CY).startswith(f"https://app.me0.ai/t/{code}/api/host/sign-in/")
    # From the main address, another site is still its subdomain of me0.ai.
    main = TestClient(sites, base_url="https://app.me0.ai")
    assert sent_to(main, ANN).startswith("https://a.me0.ai/api/host/sign-in/")
    link = sent_to(a, BOB).removeprefix("https://app.me0.ai")
    assert main.get(link, follow_redirects=False).headers["location"] == "/#/"
    assert main.get("/api/host/session").json()["email"] == BOB


@pytest.mark.parametrize("reset", ["forgot password", "from the server"])
def test_a_password_reset_ends_a_link_not_yet_opened(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, reset: str
) -> None:
    """A link made with the old password signs nobody in once the password is reset, by
    Forgot password or by the server (Codex's review of PR #295)."""
    sites, _, service = served(tmp_path)
    accounts = service.host_accounts
    main = TestClient(sites, base_url="http://localhost")
    link = sent_to(main, ANN).removeprefix("http://a.localhost")
    if reset == "forgot password":
        token = accounts.reset_link(ANN)
        assert token is not None and accounts.reset_with(token, "n" * 12) == ANN
    else:
        assert accounts.reset_password(ANN, "n" * 12)
    a = TestClient(sites, base_url="http://a.localhost")
    with caplog.at_level(logging.WARNING):
        assert a.get(link, follow_redirects=False).headers["location"] == "/#/sign-in"
    assert a.get("/api/host/session").json()["signed_in"] is False
    why = [r.__dict__["why"] for r in caplog.records if r.message == "Host sign-in link refused"]
    assert why == ["password changed"]
