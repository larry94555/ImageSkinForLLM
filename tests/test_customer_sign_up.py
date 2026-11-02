"""Each customer signs up at the main address and gets a trial site of their own, at a path of
it, signed in there only (roadmap R62)."""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_site_addresses import PASSWORD, served

from imageskin import admin
from imageskin.host_api import NO_SITE_MADE, SITE_HAS_HOST
from imageskin.hosts import HOST_COOKIE, trial_cookie
from imageskin.sites import trial_cookies_in

pytestmark = pytest.mark.real_hosts

DAN, EVE = "dan@example.com", "eve@example.com"


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def sign_up(client: TestClient, email: str) -> dict[str, object]:
    response = client.post("/api/host/sign-up", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_signing_up_makes_a_trial_site_and_signs_in_there(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, made, service = served(tmp_path, sign_up_makes_site=True)
    browser = TestClient(sites, base_url="http://localhost:8000")
    with caplog.at_level(logging.INFO):
        body = sign_up(browser, DAN)
    code = str(body["site"])
    assert body["go_to"] == f"/t/{code}/" and body["email"] == DAN
    assert service.sites.is_trial(code) and service.host_accounts.site_of(DAN) == code
    assert (tmp_path / "home" / "sites" / code).is_dir()
    cookie = next(c for c in browser.cookies.jar if c.name == trial_cookie(code))
    assert cookie.path == f"/t/{code}/" and HOST_COOKIE not in browser.cookies
    created = next(r for r in caplog.records if r.message == "Site created")
    assert created.__dict__["trial"] == code and "duration_ms" in created.__dict__
    # Signed in at the new site's path, and not at the main address.
    session = browser.get(f"/t/{code}/api/host/session").json()
    assert session == {"signed_in": True, "email": DAN}
    assert browser.get("/api/host/session").json()["signed_in"] is False
    # The host's pages there are theirs.
    assert browser.get(f"/t/{code}/api/host/me").status_code == 200


def test_two_customers_at_the_same_address_are_each_signed_in_to_their_own_site(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, _ = served(tmp_path, sign_up_makes_site=True)
    browser = TestClient(sites, base_url="http://localhost:8000")
    dan = str(sign_up(browser, DAN)["site"])
    eve = str(sign_up(browser, EVE)["site"])
    assert dan != eve
    assert browser.get(f"/t/{dan}/api/host/session").json()["email"] == DAN
    assert browser.get(f"/t/{eve}/api/host/session").json()["email"] == EVE
    # Dan's sign-in, sent to Eve's site by hand, is refused there.
    token = browser.cookies.get(trial_cookie(dan), path=f"/t/{dan}/")
    other = TestClient(sites, base_url="http://localhost:8000")
    with caplog.at_level(logging.WARNING):
        refused = other.get(
            f"/t/{eve}/api/host/me", headers={"cookie": f"{trial_cookie(eve)}={token}"}
        )
    assert refused.status_code == 401
    assert "Host sign-in refused: another site" in caplog.messages
    # Signing out at Dan's site leaves Eve signed in at hers.
    assert browser.post(f"/t/{dan}/api/host/sign-out").status_code == 200
    assert browser.get(f"/t/{dan}/api/host/session").json()["signed_in"] is False
    assert browser.get(f"/t/{eve}/api/host/session").json()["email"] == EVE
    # Signing in again at Dan's path keeps the cookie for it alone.
    again = browser.post(f"/t/{dan}/api/host/sign-in", json={"email": DAN, "password": PASSWORD})
    assert again.status_code == 200
    set_cookie = again.headers["set-cookie"]
    assert set_cookie.startswith(f"{trial_cookie(dan)}=") and f"Path=/t/{dan}/" in set_cookie


def test_sign_up_is_at_the_main_address_only(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    code, _ = service.sites.add_trial("bob@example.com")
    browser = TestClient(sites, base_url="http://localhost:8000")
    for at in (f"/t/{code}", ""):
        client = browser if at else TestClient(sites, base_url="http://a.localhost:8000")
        refused = client.post(f"{at}/api/host/sign-up", json={"email": DAN, "password": PASSWORD})
        assert refused.status_code == 403 and refused.json()["detail"] == SITE_HAS_HOST


def test_a_site_that_cant_be_made_is_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)

    def broken(email: str) -> tuple[str, Path]:
        raise OSError("disk full")

    monkeypatch.setattr(service.sites, "add_trial", broken)
    browser = TestClient(sites, base_url="http://localhost:8000")
    with caplog.at_level(logging.ERROR):
        failed = browser.post("/api/host/sign-up", json={"email": DAN, "password": PASSWORD})
    assert failed.status_code == 503 and failed.json()["detail"] == NO_SITE_MADE
    assert "Site not created" in caplog.messages


def test_a_trial_site_sees_its_own_cookie_as_the_host_cookie_and_no_other() -> None:
    code = "k7q2x9mf3a8w"
    headers = [
        (b"host", b"localhost"),
        (b"cookie", f"{HOST_COOKIE}=main; {trial_cookie(code)}=own; other=1".encode()),
    ]
    assert trial_cookies_in(headers, code) == [
        (b"host", b"localhost"),
        (b"cookie", f"{HOST_COOKIE}=own; other=1".encode()),
    ]
    only_main = [(b"cookie", f"{HOST_COOKIE}=main".encode())]
    assert trial_cookies_in(only_main, code) == [(b"cookie", b"")]
