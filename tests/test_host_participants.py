"""Participants belong to the host (roadmap R260, items 211 and 32): an account made on one of a
host's sites is the host's, kept once for all their sites, and its sign-in works on each of them;
history and Teach me progress stay with each site, and another host's sites never know it."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from test_host_content import ANN, BOB, Served, quick_hashes

from imageskin.app import participant_cookie_domain
from imageskin.participants import (
    COOKIE,
    FILENAME,
    ParticipantAccounts,
    move_site_participants,
)
from imageskin.sites import site_home
from imageskin.visitor_chat import key as conversation_key

pytestmark = pytest.mark.real_hosts
__all__ = ["quick_hashes"]  # the fixture, used by name

PAT, PASSWORD = "pat@example.com", "a long secret"
A, B, C = "http://a.me0.ai", "http://b.me0.ai", "http://c.me0.ai"


def session(browser: TestClient, address: str) -> dict[str, object]:
    answer: dict[str, object] = browser.get(f"{address}/api/participant/session").json()
    return answer


def test_one_sign_up_works_on_every_site_of_the_host(tmp_path: Path) -> None:
    s = Served(tmp_path)
    browser = TestClient(s.apps, base_url=A)
    up = browser.post("/api/participant/sign-up", json={"email": PAT, "password": PASSWORD})
    assert up.status_code == 200
    cookie = up.headers["set-cookie"]
    key = s.library(ANN).name
    # Named for Ann's folder, and sent to every address under me0.ai.
    assert cookie.startswith(f"{COOKIE}_{key}=") and "Domain=me0.ai" in cookie
    assert session(browser, B) == {"signed_in": True, "email": PAT}
    # Bob's site c has the cookie too, but neither reads it nor knows the account.
    assert session(browser, C)["signed_in"] is False
    assert (
        browser.post(
            f"{C}/api/participant/sign-in", json={"email": PAT, "password": PASSWORD}
        ).status_code
        == 401
    )
    # Kept once, in Ann's folder; neither site keeps a file of its own.
    kept = json.loads((s.library(ANN) / FILENAME).read_text())
    assert list(kept["participants"]) == [PAT]
    assert not (site_home("a", s.home) / FILENAME).exists()
    # Signing out on b signs them out on a as well: it is one sign-in.
    browser.post(f"{B}/api/participant/sign-out")
    assert session(browser, A)["signed_in"] is False


def test_history_and_progress_stay_with_each_site(tmp_path: Path) -> None:
    s = Served(tmp_path)
    browser = TestClient(s.apps, base_url=A)
    browser.post("/api/participant/sign-up", json={"email": PAT, "password": PASSWORD})
    lesson = {"lesson": {"topic": "Mars", "part": 1, "active": True}}
    assert browser.put(f"{A}/api/participant/progress", json=lesson).status_code == 204
    assert browser.get(f"{A}/api/participant/progress").json() == lesson
    assert browser.get(f"{B}/api/participant/progress").json() == {}


def test_a_sites_own_participants_join_the_hosts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Accounts made on a site before R260 move to the host's file the first time it opens, with
    their passwords, sign-ins and each site's conversation."""
    s = Served(tmp_path)
    a_home, b_home = site_home("a", s.home), site_home("b", s.home)
    a_token = ParticipantAccounts(a_home, "a").sign_up(PAT, PASSWORD)
    b_token = ParticipantAccounts(b_home, "b").sign_up(PAT, "b's own password")
    ParticipantAccounts(b_home, "b").sign_up("sam@example.com", PASSWORD)
    old_a = ParticipantAccounts(a_home, "a").participant(a_token)
    old_b = ParticipantAccounts(b_home, "b").participant(b_token)
    assert old_a and old_b and old_a.id != old_b.id
    with caplog.at_level(logging.INFO):
        s.make("a")
        s.make("b")
    assert "Participants moved to the host" in caplog.text
    assert not (a_home / FILENAME).exists() and not (b_home / FILENAME).exists()
    host = ParticipantAccounts(a_home, "a", accounts=s.library(ANN))
    on_b = ParticipantAccounts(b_home, "b", accounts=s.library(ANN))
    # Both sign-ins still work; each site keeps the conversation it had.
    found_a, found_b = host.participant(a_token), on_b.participant(b_token)
    assert found_a and found_a.id == old_a.id
    assert found_b and found_b.id == old_b.id
    # The email on two sites is one account now, with the password it had first.
    assert host.sign_in(PAT, PASSWORD)
    assert on_b.participant(on_b.sign_in("sam@example.com", PASSWORD))
    # Opened again, there is nothing more to move.
    assert move_site_participants(a_home, host) == 0


def test_a_browser_signed_in_before_r260_stays_signed_in(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Codex's review of PR #309: a browser with the site's own cookie from before R260 is still
    signed in once the accounts move, keeps its conversation, and is given the host's cookie."""
    s = Served(tmp_path)
    a_home = site_home("a", s.home)
    token = ParticipantAccounts(a_home, "a").sign_up(PAT, PASSWORD)
    old = ParticipantAccounts(a_home, "a").participant(token)
    assert old
    browser = TestClient(s.apps, base_url=A, cookies={COOKIE: token})
    with caplog.at_level(logging.INFO):
        answer = browser.get(f"{A}/api/participant/session")
    assert answer.json() == {"signed_in": True, "email": PAT}
    assert "Participant cookie moved to the host" in caplog.text
    given = answer.headers.get_list("set-cookie")
    name = f"{COOKIE}_{s.library(ANN).name}"
    assert any(c.startswith(f'{COOKIE}=""') and "Max-Age=0" in c for c in given), given
    assert any(c.startswith(f"{name}={token}") and "Domain=me0.ai" in c for c in given), given
    browser.cookies.delete(COOKIE)  # as a browser does for the cookie taken away
    assert session(browser, A)["signed_in"] is True
    # The chat is the account's conversation from before, on this site.
    s.host(A, ANN)  # who consented, as setup asks
    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert browser.get(f"{A}/api/chat").status_code == 200
    opened = [r for r in caplog.records if r.getMessage() == "Visitor conversation started"]
    assert [getattr(r, "visitor", None) for r in opened] == [conversation_key(old.id)[:8]]
    assert session(browser, B)["signed_in"] is True
    # The old cookie is taken only on the site it was made on, and never on another host's.
    for address in (B, C):
        elsewhere = TestClient(s.apps, base_url=address, cookies={COOKIE: token})
        assert session(elsewhere, address)["signed_in"] is False


def test_signing_in_with_an_old_cookie_keeps_the_new_sign_in(tmp_path: Path) -> None:
    s = Served(tmp_path)
    a_home = site_home("a", s.home)
    token = ParticipantAccounts(a_home, "a").sign_up(PAT, PASSWORD)
    ParticipantAccounts(a_home, "a").sign_up("sam@example.com", PASSWORD)
    browser = TestClient(s.apps, base_url=A, cookies={COOKIE: token})
    answer = browser.post(
        "/api/participant/sign-in", json={"email": "sam@example.com", "password": PASSWORD}
    )
    assert answer.status_code == 200
    assert session(browser, A)["email"] == "sam@example.com"
    # Signing out with the old cookie signs out, and takes both cookies.
    other = TestClient(s.apps, base_url=A, cookies={COOKIE: token})
    other.post("/api/participant/sign-out")
    assert session(other, A)["signed_in"] is False
    assert session(TestClient(s.apps, base_url=A, cookies={COOKIE: token}), A)["signed_in"] is False


def test_an_unreadable_hosts_file_moves_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    s = Served(tmp_path)
    a_home = site_home("a", s.home)
    ParticipantAccounts(a_home, "a").sign_up(PAT, PASSWORD)
    s.service.host_accounts.library_of(ANN)  # given her folder, as her first site's app does
    s.library(ANN).mkdir(parents=True, exist_ok=True)
    (s.library(ANN) / FILENAME).write_text("{broken")
    host = ParticipantAccounts(a_home, "a", accounts=s.library(ANN))
    with caplog.at_level(logging.ERROR):
        assert move_site_participants(a_home, host) == 0
    assert "Participants not moved to the host" in caplog.text
    assert (a_home / FILENAME).exists()  # kept, to try again


def request_for(host: str, root_path: str = "") -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"host", host.encode())],
            "root_path": root_path,
            "path": "/",
            "query_string": b"",
        }
    )


@pytest.mark.parametrize(
    ("host", "root_path", "domain"),
    [
        ("a.me0.ai", "", "me0.ai"),
        ("a.me0.ai:443", "", "me0.ai"),
        ("me0.ai", "/t/k7q2", "me0.ai"),
        ("a.localhost:8000", "", None),
        ("localhost:8000", "/t/k7q2", None),
        ("me0.ai", "", None),
        ("127.0.0.1:8000", "", None),
        ("[::1]:8000", "", None),
    ],
)
def test_the_cookie_is_for_the_hosts_sites_address(
    host: str, root_path: str, domain: str | None
) -> None:
    assert participant_cookie_domain(request_for(host, root_path)) == domain


def test_bobs_participants_are_his_own(tmp_path: Path) -> None:
    s = Served(tmp_path)
    ann_side = TestClient(s.apps, base_url=A)
    bob_side = TestClient(s.apps, base_url=C)
    for browser in (ann_side, bob_side):
        answer = browser.post("/api/participant/sign-up", json={"email": PAT, "password": PASSWORD})
        assert answer.status_code == 200
    assert s.library(ANN) != s.library(BOB)
    for email in (ANN, BOB):
        kept = json.loads((s.library(email) / FILENAME).read_text())
        assert list(kept["participants"]) == [PAT]
