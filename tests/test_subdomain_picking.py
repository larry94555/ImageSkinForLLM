"""A trial site's host picks its subdomain at the first payment (roadmap R63): the name is
checked as it is typed, the subdomain shows the same site, and the trial path goes there and is
never given to another trial."""

import logging
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_acting_as_host import administrator, link_for
from test_site_addresses import PASSWORD, quick_hashes, served  # noqa: F401 (the fixture)

from imageskin import cli
from imageskin.host_api import MAIN_ADDRESS_VARIABLE
from imageskin.sites import (
    NAME_LETTERS,
    NOT_A_TRIAL,
    SUBSCRIBE_FIRST,
    SiteError,
    site_home,
    site_matcher,
)

pytestmark = pytest.mark.real_hosts

ANN = "ann@example.com"  # site a's host, at a.localhost
CY = "cy@example.com"  # a trial site's host


def trial(tmp_path: Path, paid: bool = True):  # type: ignore[no-untyped-def]
    """The sites, the service and Cy's trial site's code, subscribed when `paid`, with Cy
    signed in at its path."""
    apps, _, service = served(tmp_path)
    service.host_accounts.sign_up(CY, PASSWORD, "test")
    code, folder = service.sites.add_trial(CY)
    (folder / "person.txt").write_text("Cy's person", encoding="utf-8")
    if paid:
        assert service.sites.subscribe(code, "sub_1", "cus_1")
    browser = TestClient(apps, base_url="http://localhost:8000")
    signed = browser.post(f"/t/{code}/api/host/sign-in", json={"email": CY, "password": PASSWORD})
    assert signed.status_code == 200
    return apps, service, code, browser


def test_the_name_is_checked_as_it_is_typed(tmp_path: Path) -> None:
    _, _, code, browser = trial(tmp_path)
    check = f"/t/{code}/api/site/subdomain/check"
    assert browser.get(check, params={"name": " Cy-Site "}).json() == {
        "name": "cy-site",
        "problem": None,
    }
    assert browser.get(check, params={"name": "a"}).json()["problem"] == (
        "a is taken. Choose another name."
    )
    assert browser.get(check, params={"name": "admin"}).json()["problem"] == (
        "admin is kept for the service. Choose another name."
    )
    for bad in ("-cy", "cy_site", "cy.site", "", "x" * 64):
        assert browser.get(check, params={"name": bad}).json()["problem"] == NAME_LETTERS, bad
    # A trial's code, its own included, is never a subdomain.
    assert browser.get(check, params={"name": code}).json()["problem"] is not None
    # Only for a signed-in host.
    stranger = TestClient(browser.app, base_url="http://localhost:8000")
    assert stranger.get(check, params={"name": "cy"}).status_code == 401


def test_a_paid_trial_moves_to_its_subdomain(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    apps, service, code, browser = trial(tmp_path)
    session = browser.get(f"/t/{code}/api/site/subscription").json()
    assert session["pick_subdomain"] is True and session["subdomain"] is None

    refused = browser.post(f"/t/{code}/api/site/subdomain", json={"name": "a"})
    assert refused.status_code == 409 and refused.json()["detail"] == (
        "a is taken. Choose another name."
    )
    with caplog.at_level(logging.INFO):
        picked = browser.post(f"/t/{code}/api/site/subdomain", json={"name": "Cy-Site"})
    assert picked.status_code == 200
    answer = picked.json()
    assert answer["subdomain"] == "cy-site"
    assert answer["address"] == "http://cy-site.localhost:8000"
    assert answer["sign_in_at"].startswith("http://cy-site.localhost:8000/api/host/sign-in/")
    logged = next(r for r in caplog.records if r.message == "Subdomain picked")
    assert logged.__dict__["site"] == code and logged.__dict__["subdomain"] == "cy-site"

    # The subdomain is the same site: its folder, its host and its subscription.
    assert service.sites.site_at("cy-site") == code
    assert (site_home(code, service.home) / "person.txt").read_text() == "Cy's person"
    sub = TestClient(apps, base_url="http://cy-site.localhost:8000")
    opened = sub.get(answer["sign_in_at"].removeprefix(sub.base_url.__str__().rstrip("/")))
    assert opened.status_code == 200
    assert sub.get("/api/host/session").json()["email"] == CY
    assert sub.get("/api/site/subscription").json() == {
        **session,
        "pick_subdomain": False,
        "subdomain": "cy-site",
        "subscribed": True,
    }
    # Sign in at the main address now sends Cy to the subdomain (R255).
    main = TestClient(apps, base_url="http://localhost:8000")
    sent = main.post("/api/host/sign-in", json={"email": CY, "password": PASSWORD}).json()
    assert sent["sign_in_at"].startswith("http://cy-site.localhost:8000/api/host/sign-in/")

    # Picked once: a second name is refused.
    again = sub.post("/api/site/subdomain", json={"name": "cy-two"})
    assert again.status_code == 409 and again.json()["detail"] == NOT_A_TRIAL


def test_the_trial_path_goes_to_the_subdomain(tmp_path: Path) -> None:
    apps, service, code, _ = trial(tmp_path)
    service.sites.pick_subdomain(code, "cy")
    for base, to in (
        ("http://localhost:8000", "http://cy.localhost:8000"),
        ("https://app.me0.ai", "https://cy.me0.ai"),
        ("http://203.0.113.5", "http://cy.me0.ai"),
    ):
        browser = TestClient(apps, base_url=base)
        page = browser.get(f"/t/{code}/assets/app.js?v=1", follow_redirects=False)
        assert page.status_code == 308, base
        assert page.headers["location"] == f"{to}/assets/app.js?v=1"
        home = browser.get(f"/t/{code}", follow_redirects=False)
        assert home.headers["location"] == f"{to}/"
    # Behind Caddy, the scheme the browser used is kept.
    proxied = TestClient(apps, base_url="http://app.me0.ai")
    moved = proxied.get(
        f"/t/{code}/", headers={"x-forwarded-proto": "https"}, follow_redirects=False
    )
    assert moved.headers["location"] == "https://cy.me0.ai/"
    assert (
        site_matcher(service.sites, "me0.ai")({"headers": [(b"host", b"cy.me0.ai")], "path": "/"})
        == code
    )


def test_a_tab_opened_before_the_move_is_told_where_the_site_went(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A page opened at the trial path before the move keeps calling there. A redirect to the
    subdomain's origin would be blocked, so each call is answered at the trial path with the new
    address, which the page goes to (Codex's review of PR #297)."""
    apps, service, code, tab = trial(tmp_path)
    service.sites.pick_subdomain(code, "cy")
    with caplog.at_level(logging.INFO):
        for method, path in (("GET", "/api/settings?x=1"), ("POST", "/api/chat/prompt")):
            answer = tab.request(method, f"/t/{code}{path}", follow_redirects=False)
            assert answer.status_code == 409, path
            assert answer.headers["x-site-moved"] == "http://cy.localhost:8000/"
            assert answer.json() == {
                "detail": "This site has moved to http://cy.localhost:8000/",
                "moved_to": "http://cy.localhost:8000/",
            }
    logged = [r for r in caplog.records if r.message == "Trial path moved"]
    assert [r.__dict__["call"] for r in logged] == [True, True]
    proxied = TestClient(apps, base_url="http://app.me0.ai")
    answer = proxied.get(f"/t/{code}/api/settings", headers={"x-forwarded-proto": "https"})
    assert answer.headers["x-site-moved"] == "https://cy.me0.ai/"


def test_a_new_trial_never_gets_a_moved_trials_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, service, code, _ = trial(tmp_path)
    service.sites.pick_subdomain(code, "cy")
    service.host_accounts.sign_up("dee@example.com", PASSWORD, "test")
    picks = iter(code + "x" * 12)  # the moved trial's code first, then another
    monkeypatch.setattr(secrets, "choice", lambda letters: next(picks))
    new, _ = service.sites.add_trial("dee@example.com")
    assert new == "x" * 12 and new != code
    # Nor can a subdomain picked, or added from the command line, be a site's code.
    assert service.sites.name_problem(code) == f"{code} is taken. Choose another name."
    service.host_accounts.sign_up("eve@example.com", PASSWORD, "test")
    with pytest.raises(SiteError, match="already a site called cy"):
        service.sites.add("cy", "eve@example.com")


def test_only_a_subscribed_trial_picks_a_subdomain(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _, service, code, browser = trial(tmp_path, paid=False)
    assert browser.get(f"/t/{code}/api/site/subscription").json()["pick_subdomain"] is False
    with caplog.at_level(logging.WARNING):
        refused = browser.post(f"/t/{code}/api/site/subdomain", json={"name": "cy"})
    assert refused.status_code == 409 and refused.json()["detail"] == SUBSCRIBE_FIRST
    why = [r.__dict__["why"] for r in caplog.records if r.message == "Subdomain not picked"]
    assert why == ["not subscribed"]
    assert service.sites.is_trial(code) and service.sites.site_at("cy") is None
    # A site added with its name has its address already.
    with pytest.raises(SiteError, match=NOT_A_TRIAL):
        service.sites.pick_subdomain("a", "a-two")


def test_the_administrator_acting_as_the_host_picks_it_and_acts_there(tmp_path: Path) -> None:
    """Acting as the host, the administrator gets the address but no link that would sign them
    in as the host there; acting as the host again then goes to the subdomain."""
    apps, service, code, _ = trial(tmp_path)
    boss = administrator(apps, tmp_path)
    browser = TestClient(apps, base_url="http://localhost:8000", follow_redirects=False)
    assert browser.get(link_for(boss, CY)).status_code == 303
    picked = browser.post(f"/t/{code}/api/site/subdomain", json={"name": "cy"}).json()
    assert picked == {"subdomain": "cy", "address": "http://cy.localhost:8000"}
    assert link_for(boss, CY).startswith("http://cy.localhost:8000/api/host/act-as/")


def test_the_hosted_service_gives_the_subdomain_of_the_main_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(MAIN_ADDRESS_VARIABLE, "app.me0.ai")
    apps, service, code, _ = trial(tmp_path)
    browser = TestClient(apps, base_url="https://app.me0.ai")
    browser.post(f"/t/{code}/api/host/sign-in", json={"email": CY, "password": PASSWORD})
    picked = browser.post(f"/t/{code}/api/site/subdomain", json={"name": "cy"}).json()
    assert picked["address"] == "https://cy.me0.ai"


def test_the_command_line_lists_a_moved_trial_at_its_subdomain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, service, code, _ = trial(tmp_path)
    service.sites.pick_subdomain(code, "cy")
    monkeypatch.setenv("IMAGESKIN_HOME", str(service.home))
    assert cli.main(["site", "list"]) == 0
    assert f"{code}: {CY} at cy.localhost" in capsys.readouterr().out
