"""The host's display name (roadmap R259): asked for at sign-up and changed on the account page,
it is how participants and visitors see the host, and the host's email is in none of what they
are sent."""

import logging
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from test_customer_sign_up import quick_hashes  # noqa: F401
from test_site_addresses import PASSWORD, served

from imageskin.app import create_app
from imageskin.hosts import (
    LONG_DISPLAY_NAME,
    MAX_DISPLAY_NAME,
    NO_DISPLAY_NAME,
    HostAccounts,
    HostRefused,
    checked_display_name,
    default_display_name,
)

pytestmark = pytest.mark.real_hosts

ANN = "ann@example.com"
# What a participant's page asks for that could name the host; host-only and admin calls
# refuse a visitor, and are skipped as making no sense here.
SKIPPED = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc", "/auth/callback"}


def test_a_host_with_no_display_name_is_their_email_before_the_at(tmp_path: Path) -> None:
    accounts = HostAccounts(tmp_path)
    accounts.sign_up("Ann.Smith@Example.com", PASSWORD, "test")
    assert accounts.display_name_of("ann.smith@example.com") == "ann.smith"
    assert default_display_name(" Bo@x.org ") == "bo"
    assert accounts.display_name_of("nobody@example.com") is None
    assert accounts.set_display_name("nobody@example.com", "Dr. Nobody") is None


def test_sign_up_keeps_the_display_name_and_the_account_page_changes_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    accounts = HostAccounts(tmp_path)
    accounts.sign_up(ANN, PASSWORD, "test", display_name="  Dr.   Smith ")
    assert accounts.display_name_of(ANN) == "Dr. Smith"
    with caplog.at_level(logging.INFO):
        assert accounts.set_display_name(ANN, "Ann Smith, PhD") == "Ann Smith, PhD"
    assert accounts.display_name_of(ANN) == "Ann Smith, PhD"
    record = next(r for r in caplog.records if r.message == "Host display name set")
    assert record.__dict__["was_set"] is True
    # A blank one at sign-up is none: the email before the @ until they set one.
    accounts.sign_up("bo@example.com", PASSWORD, "test", display_name="   ")
    assert accounts.display_name_of("bo@example.com") == "bo"


@pytest.mark.parametrize(
    ("name", "says"),
    [
        ("", NO_DISPLAY_NAME),
        ("  \n ", NO_DISPLAY_NAME),
        ("Dr.\x00Smith", NO_DISPLAY_NAME),
        ("x" * (MAX_DISPLAY_NAME + 1), LONG_DISPLAY_NAME),
    ],
)
def test_a_display_name_that_isnt_one_is_refused(tmp_path: Path, name: str, says: str) -> None:
    with pytest.raises(HostRefused, match=says.replace(".", r"\.")):
        checked_display_name(name)
    if not name.strip():
        return  # at sign-up, a blank one is none (above)
    accounts = HostAccounts(tmp_path)
    with pytest.raises(HostRefused, match=says.replace(".", r"\.")):
        accounts.sign_up(ANN, PASSWORD, "test", display_name=name)
    assert not accounts.exists(ANN)


def test_the_display_name_stays_when_the_email_changes(tmp_path: Path) -> None:
    accounts = HostAccounts(tmp_path)
    accounts.sign_up(ANN, PASSWORD, "test", display_name="Dr. Smith")
    accounts.change_email(accounts.email_change(ANN, "smith@example.com"))
    assert accounts.display_name_of("smith@example.com") == "Dr. Smith"


def test_the_api_asks_for_it_at_sign_up_and_changes_it(tmp_path: Path) -> None:
    browser = TestClient(create_app(tmp_path))
    up = browser.post(
        "/api/host/sign-up", json={"email": ANN, "password": PASSWORD, "display_name": "Dr. Smith"}
    )
    assert up.status_code == 200
    assert browser.get("/api/host/me").json()["display_name"] == "Dr. Smith"
    changed = browser.put("/api/host/display-name", json={"display_name": " Ann  Smith "})
    assert changed.json() == {"display_name": "Ann Smith"}
    session = browser.get("/api/host/session").json()
    assert session["display_name"] == "Ann Smith" and session["host_name"] == "Ann Smith"
    refused = browser.put("/api/host/display-name", json={"display_name": " "})
    assert refused.status_code == 400 and refused.json() == {"detail": NO_DISPLAY_NAME}
    bad = browser.post(
        "/api/host/sign-up",
        json={"email": "bo@example.com", "password": PASSWORD, "display_name": "x" * 99},
    )
    assert bad.status_code == 400 and bad.json() == {"detail": LONG_DISPLAY_NAME}
    browser.post("/api/host/sign-out")
    assert browser.put("/api/host/display-name", json={"display_name": "Bo"}).status_code == 401
    # The one host of a computer of its own is its host for visitors too.
    assert browser.get("/api/host/session").json()["host_name"] == "Ann Smith"


def test_a_visitor_sees_the_display_name_and_the_email_nowhere(tmp_path: Path) -> None:
    sites, made, service = served(tmp_path)
    service.host_accounts.set_display_name(ANN, "Dr. Smith")
    visitor = TestClient(sites, base_url="http://a.localhost")
    session = visitor.get("/api/host/session").json()
    assert session["host_name"] == "Dr. Smith" and session["email"] is None
    assert "display_name" not in session
    asked = ["/", "/api/host/session"] + [
        route.path
        for route in made["a"].routes
        if isinstance(route, APIRoute)
        and "GET" in (route.methods or set())
        and "{" not in route.path
        and route.path not in SKIPPED
    ]
    answered = 0
    for path in asked:
        response = visitor.get(path)
        assert ANN not in response.text, path
        assert "ann@" not in response.text, path
        answered += response.status_code == 200
    assert answered >= 10  # the participant's page and its calls, not only refusals
    # The main address's host, Bob, is named there only.
    main = TestClient(sites, base_url="http://localhost").get("/api/host/session").json()
    assert main["host_name"] == "bob"


def test_a_site_whose_host_cant_be_read_names_no_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    sites, made, service = served(tmp_path)
    visitor = TestClient(sites, base_url="http://a.localhost")
    visitor.get("/api/host/session")

    def unreadable(name: str) -> str | None:
        raise OSError("disk gone")

    monkeypatch.setattr(service.sites, "host", unreadable)
    with caplog.at_level(logging.ERROR):
        assert visitor.get("/api/host/session").json()["host_name"] is None
    assert "Host's display name not read" in caplog.text
