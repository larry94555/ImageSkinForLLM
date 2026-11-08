"""One Sign in for everyone (roadmap R269): the display name it fills in for a new account, the
email before the @ and a number unlike every other, and a participant's own display name."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_chat import FakeLlm2
from test_visitor_conversations import accepted, quick_hashes, site

from imageskin.hosts import (
    MAX_DISPLAY_NAME,
    NO_DISPLAY_NAME,
    HostAccounts,
    HostsUnreadable,
    numbered_display_name,
)
from imageskin.participants import FILENAME, ParticipantAccounts, ParticipantRefused

pytestmark = pytest.mark.real_hosts
__all__ = ["accepted", "quick_hashes"]  # the fixtures, used by name

PAT, PASSWORD = "pat@example.com", "a long secret"


def test_the_suggested_name_is_the_email_before_the_at_with_the_first_free_number() -> None:
    assert numbered_display_name("Larry.Freeman@Gmail.com", set()) == "larry.freeman1"
    assert numbered_display_name("pat@example.com", {"PAT1", "pat2", "Dr. Smith"}) == "pat3"
    assert numbered_display_name("@example.com", set()) == "user1"
    long = "a" * 80 + "@example.com"
    name = numbered_display_name(long, {"a" * (MAX_DISPLAY_NAME - 1) + "1"})
    assert name == "a" * (MAX_DISPLAY_NAME - 1) + "2" and len(name) == MAX_DISPLAY_NAME


def test_every_hosts_display_name_is_taken(tmp_path: Path) -> None:
    accounts = HostAccounts(tmp_path)
    assert accounts.display_names() == set()
    accounts.sign_up("ann@example.com", PASSWORD, "test", display_name="Dr. Smith")
    accounts.sign_up("bo@example.com", PASSWORD, "test")
    assert accounts.display_names() == {"Dr. Smith", "bo"}


def test_the_route_suggests_a_name_unlike_the_hosts_and_participants(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    browser = TestClient(site(tmp_path, FakeLlm2()))
    taken = browser.post(
        "/api/participant/sign-up",
        json={"email": "pat@other.org", "password": PASSWORD, "display_name": "pat1"},
    )
    assert taken.status_code == 200
    browser.post("/api/participant/sign-out")
    with caplog.at_level(logging.INFO):
        answer = browser.get("/api/host/display-name/suggestion", params={"email": PAT})
    assert answer.json() == {"display_name": "pat2"}
    record = next(r for r in caplog.records if r.message == "Display name suggested")
    assert "duration_ms" in record.__dict__
    assert browser.get(
        "/api/host/display-name/suggestion", params={"email": "pat@example.com-admin"}
    ).json() == {"display_name": "pat2"}


def test_the_route_says_when_the_hosts_cant_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser = TestClient(site(tmp_path, FakeLlm2()))

    def unreadable(self: HostAccounts) -> set[str]:
        raise HostsUnreadable()

    monkeypatch.setattr(HostAccounts, "display_names", unreadable)
    answer = browser.get("/api/host/display-name/suggestion", params={"email": PAT})
    assert answer.status_code == 503


def test_a_participant_keeps_the_display_name_they_sign_up_with(tmp_path: Path) -> None:
    browser = TestClient(site(tmp_path, FakeLlm2()))
    up = browser.post(
        "/api/participant/sign-up",
        json={"email": PAT, "password": PASSWORD, "display_name": "  Pat   Lee "},
    )
    assert up.json() == {"signed_in": True, "email": PAT, "display_name": "Pat Lee"}
    session = browser.get("/api/participant/session").json()
    assert session == {"signed_in": True, "email": PAT, "display_name": "Pat Lee"}
    browser.post("/api/participant/sign-out")
    again = browser.post("/api/participant/sign-in", json={"email": PAT, "password": PASSWORD})
    assert again.json()["display_name"] == "Pat Lee"


def test_a_participant_with_no_display_name_has_none(tmp_path: Path) -> None:
    accounts = ParticipantAccounts(tmp_path, "a")
    pat = accounts.participant(accounts.sign_up(PAT, PASSWORD, "  "))
    assert pat is not None and pat.display_name is None
    assert "display_name" not in json.loads((tmp_path / FILENAME).read_text())["participants"][PAT]
    assert accounts.display_names() == set()


def test_a_display_name_that_isnt_one_is_refused(tmp_path: Path) -> None:
    accounts = ParticipantAccounts(tmp_path, "a")
    with pytest.raises(ParticipantRefused, match="at most"):
        accounts.sign_up(PAT, PASSWORD, "x" * (MAX_DISPLAY_NAME + 1))
    with pytest.raises(ParticipantRefused):
        accounts.sign_up(PAT, PASSWORD, "Pat\nLee")
    browser = TestClient(site(tmp_path / "s", FakeLlm2()))
    refused = browser.post(
        "/api/participant/sign-up",
        json={"email": PAT, "password": PASSWORD, "display_name": "x" * 99},
    )
    assert refused.status_code == 400
    assert NO_DISPLAY_NAME  # the host's words for an empty name; a blank one here is just none


def test_an_unreadable_file_has_no_display_names(tmp_path: Path) -> None:
    accounts = ParticipantAccounts(tmp_path, "a")
    accounts.sign_up(PAT, PASSWORD, "Pat")
    assert accounts.display_names() == {"Pat"}
    (tmp_path / FILENAME).write_text("{not json")
    assert accounts.display_names() == set()
