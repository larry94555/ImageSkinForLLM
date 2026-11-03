"""A site's host changes its subdomain in Settings (roadmap R64): the same checks as picking it
(R63), the site at the new address, and the old name released at once."""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_site_addresses import PASSWORD, quick_hashes, served  # noqa: F401 (the fixture)
from test_subdomain_picking import CY, trial

from imageskin import cli
from imageskin.sites import NO_SUBDOMAIN_YET, SiteError, site_home

pytestmark = pytest.mark.real_hosts

ANN = "ann@example.com"  # site a's host, at a.localhost


def signed_in(apps: object, base: str, email: str) -> TestClient:
    browser = TestClient(apps, base_url=base)  # type: ignore[arg-type]
    answer = browser.post("/api/host/sign-in", json={"email": email, "password": PASSWORD})
    assert answer.status_code == 200 and answer.json()["signed_in"] is True, answer.text
    return browser


def test_a_site_changes_its_subdomain_and_the_old_one_is_free(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    apps, _, service = served(tmp_path)
    a = signed_in(apps, "http://a.localhost:8000", ANN)
    (site_home("a", service.home) / "person.txt").write_text("Ann's person", encoding="utf-8")
    # A site added from the command line has its address, and can change it.
    assert a.get("/api/site/subscription").json()["change_subdomain"] is True
    assert a.get("/api/site/subdomain/check", params={"name": "a"}).json()["problem"] == (
        "a is taken. Choose another name."
    )
    same = a.post("/api/site/subdomain", json={"name": "A"})
    assert same.status_code == 409 and same.json()["detail"] == "a is your site's address already."

    with caplog.at_level(logging.INFO):
        changed = a.post("/api/site/subdomain", json={"name": "anna"})
    assert changed.status_code == 200
    answer = changed.json()
    assert answer["subdomain"] == "anna" and answer["address"] == "http://anna.localhost:8000"
    assert answer["sign_in_at"].startswith("http://anna.localhost:8000/api/host/sign-in/")
    logged = next(r for r in caplog.records if r.message == "Subdomain changed")
    assert logged.__dict__["old"] == "a" and logged.__dict__["subdomain"] == "anna"

    # The same site at the new address, signed in through the link; none at the old one.
    anna = TestClient(apps, base_url="http://anna.localhost:8000")
    assert anna.get(answer["sign_in_at"].removeprefix("http://anna.localhost:8000")).is_success
    assert anna.get("/api/host/session").json()["email"] == ANN
    assert anna.get("/api/site/subscription").json()["subdomain"] == "anna"
    assert service.sites.site_at("anna") == "a"
    assert (site_home("a", service.home) / "person.txt").read_text() == "Ann's person"
    old = TestClient(apps, base_url="http://a.localhost:8000")
    assert old.get("/api/settings").status_code == 404
    assert service.sites.site_at("a") is None and service.sites.name_problem("a") is None
    # Sign-in from elsewhere and acting as Ann go to the new address.
    main = TestClient(apps, base_url="http://localhost:8000")
    sent = main.post("/api/host/sign-in", json={"email": ANN, "password": PASSWORD}).json()
    assert sent["sign_in_at"].startswith("http://anna.localhost:8000/api/host/sign-in/")


def test_another_paid_site_takes_the_old_name(tmp_path: Path) -> None:
    apps, service, code, browser = trial(tmp_path)
    service.sites.change_subdomain("a", "anna")  # site a lets go of "a"
    picked = browser.post(f"/t/{code}/api/site/subdomain", json={"name": "a"})
    assert picked.status_code == 200 and picked.json()["subdomain"] == "a"
    a = TestClient(apps, base_url="http://a.localhost:8000")
    a.get(picked.json()["sign_in_at"].removeprefix("http://a.localhost:8000"))
    assert a.get("/api/host/session").json()["email"] == CY
    assert service.sites.site_at("a") == code and service.sites.site_at("anna") == "a"
    # Site a can't have its old name back while Cy's site has it.
    with pytest.raises(SiteError, match="a is taken"):
        service.sites.change_subdomain("a", "a")


def test_a_moved_trial_path_follows_the_change(tmp_path: Path) -> None:
    apps, service, code, _ = trial(tmp_path)
    service.sites.pick_subdomain(code, "cy")
    cy = signed_in(apps, "http://cy.localhost:8000", CY)
    assert cy.post("/api/site/subdomain", json={"name": "cy-two"}).status_code == 200
    browser = TestClient(apps, base_url="http://localhost:8000")
    moved = browser.get(f"/t/{code}/", follow_redirects=False)
    assert moved.headers["location"] == "http://cy-two.localhost:8000/"
    # The trial's code stays the site's: it can't be anyone's subdomain.
    assert service.sites.name_problem(code) == f"{code} is taken. Choose another name."
    # The name changed away from is free, and the site can have it back.
    assert service.sites.name_problem("cy") is None
    assert service.sites.change_subdomain(code, "cy") == ("cy-two", "cy")


def test_a_trial_at_its_path_and_the_main_address_change_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    apps, service, code, browser = trial(tmp_path, paid=False)
    assert browser.get(f"/t/{code}/api/site/subscription").json()["change_subdomain"] is False
    with caplog.at_level(logging.WARNING), pytest.raises(SiteError, match=NO_SUBDOMAIN_YET):
        service.sites.change_subdomain(code, "cy")
    why = [r.__dict__["why"] for r in caplog.records if r.message == "Subdomain not changed"]
    assert why == ["no subdomain yet"]
    main = signed_in(apps, "http://localhost:8000", "bob@example.com")
    assert main.get("/api/site/subscription").json()["change_subdomain"] is False
    refused = main.post("/api/site/subdomain", json={"name": "bob"})
    assert refused.status_code == 409


def test_the_command_line_lists_the_new_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, service = served(tmp_path)
    service.sites.change_subdomain("a", "anna")
    monkeypatch.setenv("IMAGESKIN_HOME", str(service.home))
    assert cli.main(["site", "list"]) == 0
    assert f"a: {ANN} at anna.localhost" in capsys.readouterr().out
