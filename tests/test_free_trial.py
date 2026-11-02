"""A free trial (roadmap R66): one per email address, which its customer can cancel from Settings,
pausing the site."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_customer_sign_up import confirmation_link, sign_up
from test_site_addresses import PASSWORD, served

from imageskin import admin
from imageskin.app import PAUSED_WORDS
from imageskin.hosts import TRIAL_USED
from imageskin.sites import TrialUsed, email_key

pytestmark = pytest.mark.real_hosts

DAN, EVE = "dan@example.com", "eve@example.com"
MAIN = "http://localhost:8000"


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def forget_account(home: Path, email: str) -> None:
    """Remove the host's account and site, as deleting a site will (R69)."""
    hosts = json.loads((home / "hosts.json").read_text())
    hosts["hosts"].pop(email, None)
    (home / "hosts.json").write_text(json.dumps(hosts))
    sites = json.loads((home / "sites.json").read_text())
    sites["sites"] = {k: v for k, v in sites["sites"].items() if v["host"] != email}
    (home / "sites.json").write_text(json.dumps(sites))


def test_one_free_trial_per_email_address(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    browser = TestClient(sites, base_url=MAIN)
    sign_up(browser, DAN)
    # Kept as a hash, never the address.
    saved = json.loads((home / "sites.json").read_text())
    assert saved["trials_used"] == [email_key(DAN)] and DAN not in json.dumps(saved["trials_used"])
    # Even once the account and its site are gone, the address has had its trial.
    forget_account(home, DAN)
    assert not service.host_accounts.exists(DAN)
    with caplog.at_level(logging.WARNING):
        again = TestClient(sites, base_url=MAIN).post(
            "/api/host/sign-up", json={"email": " Dan@Example.com", "password": PASSWORD}
        )
    assert again.status_code == 409 and again.json()["detail"] == TRIAL_USED
    assert "Trial refused: email already used" in caplog.messages
    assert not service.host_accounts.exists(DAN)  # no account made for it
    # Another address has its own.
    assert sign_up(TestClient(sites, base_url=MAIN), EVE)["site"]
    # Made by hand, as `imageskin site add` does, it is refused too.
    forget_account(home, EVE)
    service.host_accounts.sign_up(EVE, PASSWORD, "test")
    with pytest.raises(TrialUsed):
        service.sites.add_trial(EVE)


def made_before_trials_were_recorded(home: Path) -> None:
    """sites.json as it was before R66: no `trials_used`."""
    saved = json.loads((home / "sites.json").read_text())
    del saved["trials_used"]
    (home / "sites.json").write_text(json.dumps(saved))


def test_a_trial_from_before_trials_were_recorded_counts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    sign_up(TestClient(sites, base_url=MAIN), DAN)
    made_before_trials_were_recorded(home)
    with caplog.at_level(logging.INFO):
        assert service.sites.trial_used(DAN) and not service.sites.trial_used(EVE)
    assert "Trials made before recorded" in caplog.messages
    # Recorded in the file at once, so it outlasts the site (Codex's review of PR #292).
    assert json.loads((home / "sites.json").read_text())["trials_used"] == [email_key(DAN)]
    forget_account(home, DAN)
    again = TestClient(sites, base_url=MAIN).post(
        "/api/host/sign-up", json={"email": DAN, "password": PASSWORD}
    )
    assert again.status_code == 409 and again.json()["detail"] == TRIAL_USED


def test_an_old_trials_host_who_changed_email_keeps_both_used(tmp_path: Path) -> None:
    # Codex's review of PR #292: a trial from before, its email changed, then its account gone.
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    code = str(sign_up(TestClient(sites, base_url=MAIN), DAN)["site"])
    made_before_trials_were_recorded(home)
    assert service.sites.set_host(code, DAN, EVE)  # as R62c does, with the account's email
    forget_account(home, DAN)
    forget_account(home, EVE)
    for email in (DAN, EVE):
        again = TestClient(sites, base_url=MAIN).post(
            "/api/host/sign-up", json={"email": email, "password": PASSWORD}
        )
        assert again.status_code == 409 and again.json()["detail"] == TRIAL_USED, email


def test_a_new_email_address_has_had_the_trial_too(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    code = str(sign_up(TestClient(sites, base_url=MAIN), DAN)["site"])
    assert service.sites.set_host(code, DAN, EVE)  # as changing the email does (R62c)
    assert service.sites.trial_used(DAN) and service.sites.trial_used(EVE)
    assert not service.sites.set_host(code, DAN, EVE)  # no longer its host


def test_cancelling_a_trial_pauses_the_site(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    dan = TestClient(sites, base_url=MAIN)
    code = str(sign_up(dan, DAN)["site"])
    dan.get(confirmation_link(tmp_path / "home"), follow_redirects=False)
    site = f"/t/{code}"
    assert dan.get(f"{site}/api/host/session").json()["trial"] is True
    visitor = TestClient(sites, base_url=MAIN)
    assert visitor.get(f"{site}/api/content").status_code == 200
    with caplog.at_level(logging.INFO):
        assert dan.post(f"{site}/api/site/cancel").json() == {"paused": True}
    assert "Trial cancelled" in caplog.messages
    assert service.sites.paused(code) == "cancelled"
    # Visitors see the notice: the page loads, and says so; every other call is refused.
    assert visitor.get(f"{site}/api/host/session").json()["paused"] is True
    assert visitor.get(f"{site}/").status_code == 200
    assert visitor.get(f"{site}/api/settings").status_code == 200
    with caplog.at_level(logging.INFO):
        refused = visitor.post(f"{site}/api/chat", json={"prompt": "Hello?"})
    assert refused.status_code == 403 and refused.json()["detail"] == PAUSED_WORDS
    assert visitor.get(f"{site}/api/content").json()["detail"] == PAUSED_WORDS
    record = next(r for r in caplog.records if r.message == "Paused site refused a visitor")
    assert record.__dict__["why"] == "cancelled" and record.__dict__["path"] == "/api/chat"
    # The host still signs in and uses it.
    assert dan.post(f"{site}/api/host/sign-out").is_success
    answer = dan.post(f"{site}/api/host/sign-in", json={"email": DAN, "password": PASSWORD})
    assert answer.is_success
    assert dan.get(f"{site}/api/content").status_code == 200
    # Once only, and only a trial.
    again = dan.post(f"{site}/api/site/cancel")
    assert (
        again.status_code == 409 and again.json()["detail"] == "This trial was cancelled already."
    )
    # The main address and other sites are unaffected.
    assert visitor.get("/api/content").status_code == 200
    assert visitor.get("/api/host/session").json().get("paused") is None


def test_only_a_trial_is_cancelled_and_only_by_its_host(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path)
    ann = TestClient(sites, base_url="http://a.localhost:8000")
    assert ann.post("/api/site/cancel").status_code == 401
    ann.post("/api/host/sign-in", json={"email": "ann@example.com", "password": PASSWORD})
    refused = ann.post("/api/site/cancel")
    assert refused.status_code == 409 and refused.json()["detail"] == (
        "Only a free trial is cancelled here."
    )
    assert "trial" not in ann.get("/api/host/session").json()
