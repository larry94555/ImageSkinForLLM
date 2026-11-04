"""Participant sign-up and login (roadmap R46): an account belongs to one site, a cookie
keeps them signed in, their conversation follows the account to any browser, and Teach me's
progress is kept for the account."""

import json
import logging
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_chat import FakeLlm2
from test_site_addresses import served
from test_visitor_conversations import accepted, quick_hashes, said, site, the_host

from imageskin.hosts import BAD_EMAIL, SHORT_PASSWORD, WRONG
from imageskin.participants import (
    BAD_PROGRESS,
    COOKIE,
    FILENAME,
    MAX_PROGRESS_BYTES,
    SESSIONS_KEPT_S,
    TAKEN,
    ParticipantAccounts,
    ParticipantRefused,
    ParticipantsUnreadable,
)
from imageskin.sites import trial_cookies_in

pytestmark = pytest.mark.real_hosts
__all__ = ["accepted", "quick_hashes"]  # the fixtures, used by name

PAT, PASSWORD = "pat@example.com", "a long secret"


def sign_up(client: TestClient, email: str = PAT, password: str = PASSWORD) -> int:
    response = client.post("/api/participant/sign-up", json={"email": email, "password": password})
    return response.status_code


def sign_in(client: TestClient, email: str = PAT, password: str = PASSWORD) -> int:
    response = client.post("/api/participant/sign-in", json={"email": email, "password": password})
    return response.status_code


def test_an_account_signs_up_in_and_out(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    clock = [1000.0]
    accounts = ParticipantAccounts(tmp_path, "a", clock=lambda: clock[0])
    with caplog.at_level(logging.INFO):
        token = accounts.sign_up(" Pat@Example.com ", PASSWORD)
    pat = accounts.participant(token)
    assert pat is not None and pat.email == PAT and pat.site == "a" and len(pat.id) >= 20
    assert "Participant signed up" in caplog.text
    saved = json.loads((tmp_path / FILENAME).read_text())
    assert token not in json.dumps(saved)  # only its hash is kept
    assert saved["participants"][PAT]["site"] == "a"
    again = accounts.sign_in(PAT, PASSWORD)
    assert accounts.participant(again) == pat  # the same account, so the same conversation
    accounts.sign_out(again)
    assert accounts.participant(again) is None and accounts.participant(token) == pat
    # A sign-in older than its cookie is no longer good.
    clock[0] += SESSIONS_KEPT_S
    assert accounts.participant(token) is None
    assert accounts.participant(None) is None and accounts.participant("made-up") is None


@pytest.mark.parametrize(
    ("email", "password", "says"),
    [("nope", PASSWORD, BAD_EMAIL), (PAT, "short", SHORT_PASSWORD), (PAT, PASSWORD, TAKEN)],
)
def test_a_sign_up_that_cant_be_made_says_why(
    tmp_path: Path, email: str, password: str, says: str
) -> None:
    accounts = ParticipantAccounts(tmp_path, "a")
    accounts.sign_up(PAT, PASSWORD)
    with pytest.raises(ParticipantRefused, match=says):
        accounts.sign_up(email, password)


def test_a_wrong_password_and_an_unknown_email_get_the_same_words(tmp_path: Path) -> None:
    accounts = ParticipantAccounts(tmp_path, "a")
    accounts.sign_up(PAT, PASSWORD)
    for email, password in ((PAT, "not the password"), ("who@example.com", PASSWORD)):
        with pytest.raises(ParticipantRefused, match=WRONG):
            accounts.sign_in(email, password)


def test_an_unreadable_file_signs_no_one_in(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    accounts = ParticipantAccounts(tmp_path, "a")
    token = accounts.sign_up(PAT, PASSWORD)
    (tmp_path / FILENAME).write_text("{not json")
    with caplog.at_level(logging.ERROR):
        assert accounts.participant(token) is None
        with pytest.raises(ParticipantsUnreadable):
            accounts.sign_up("sam@example.com", PASSWORD)
    assert "Could not read the participants file" in caplog.text
    browser = TestClient(site(tmp_path, FakeLlm2()))
    assert sign_up(browser, "sam@example.com") == 503


def test_the_api_signs_a_participant_up_in_and_out(tmp_path: Path) -> None:
    browser = TestClient(site(tmp_path, FakeLlm2()))
    assert browser.get("/api/participant/session").json() == {"signed_in": False, "email": None}
    up = browser.post("/api/participant/sign-up", json={"email": PAT, "password": PASSWORD})
    assert up.json() == {"signed_in": True, "email": PAT}
    cookie = up.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=") and "HttpOnly" in cookie and "Max-Age=" in cookie
    assert browser.get("/api/participant/session").json() == {"signed_in": True, "email": PAT}
    # A participant is not a host: no host page, and no settings (R46).
    assert browser.get("/api/host/me").status_code == 401
    assert browser.get("/api/settings/access").json().get("shown") is not True
    assert sign_up(browser) == 409
    assert sign_up(browser, "x@example.com", "short") == 400
    assert browser.post("/api/participant/sign-out").json() == {"signed_in": False}
    assert browser.get("/api/participant/session").json()["signed_in"] is False
    assert sign_in(browser, password="not the password") == 401
    assert sign_in(browser) == 200
    # Closing the browser keeps the cookie: a new client with it is still signed in.
    kept = TestClient(browser.app, cookies={COOKIE: browser.cookies.get(COOKIE) or ""})
    assert kept.get("/api/participant/session").json()["email"] == PAT


def test_the_conversation_follows_the_account_to_another_browser(tmp_path: Path) -> None:
    app = site(tmp_path, FakeLlm2())
    the_host(app, tmp_path)
    laptop, phone, stranger = TestClient(app), TestClient(app), TestClient(app)
    assert sign_up(laptop) == 200
    assert laptop.post("/api/chat", json={"prompt": "I am Pat."}).status_code == 200
    assert "I am Pat." in said(laptop)
    assert sign_in(phone) == 200
    assert "I am Pat." in said(phone)
    assert "I am Pat." not in said(stranger)
    # Signed out, the browser has its own visitor's conversation again.
    phone.post("/api/participant/sign-out")
    assert "I am Pat." not in said(phone)


def test_the_same_email_on_two_sites_is_two_accounts(tmp_path: Path) -> None:
    sites, made, service = served(tmp_path)
    a = TestClient(sites, base_url="http://a.localhost")
    main = TestClient(sites, base_url="http://localhost")
    assert sign_up(a) == 200
    # Site a's sign-in counts as none at the main address, and the email is free there.
    by_hand = TestClient(sites, base_url="http://localhost", cookies={COOKIE: a.cookies[COOKIE]})
    assert by_hand.get("/api/participant/session").json()["signed_in"] is False
    assert sign_in(main) == 401
    assert sign_up(main, password="another long one") == 200
    assert sign_in(a, password="another long one") == 401


def test_a_trial_sites_participant_cookie_is_its_own(tmp_path: Path) -> None:
    headers = [(b"cookie", f"{COOKIE}=main; {COOKIE}_k7q2=trial; other=1".encode())]
    assert trial_cookies_in(headers, "k7q2") == [(b"cookie", f"{COOKIE}=trial; other=1".encode())]
    sites, made, service = served(tmp_path, sign_up_makes_site=True)
    browser = TestClient(sites, base_url="http://localhost:8000")
    up = browser.post("/api/host/sign-up", json={"email": "dan@example.com", "password": PASSWORD})
    code = up.json()["site"]
    visitor = TestClient(sites, base_url="http://localhost:8000")
    joined = visitor.post(
        f"/t/{code}/api/participant/sign-up", json={"email": PAT, "password": PASSWORD}
    )
    assert f"{COOKIE}_{code}=" in joined.headers["set-cookie"]
    assert f"Path=/t/{code}/" in joined.headers["set-cookie"]
    assert visitor.get(f"/t/{code}/api/participant/session").json()["email"] == PAT
    assert visitor.get("/api/participant/session").json()["signed_in"] is False


def test_teach_me_progress_is_kept_for_the_account(tmp_path: Path) -> None:
    browser = TestClient(site(tmp_path, FakeLlm2()))
    assert browser.get("/api/participant/progress").status_code == 401
    assert browser.put("/api/participant/progress", json={}).status_code == 401
    sign_up(browser)
    assert browser.get("/api/participant/progress").json() == {}
    lesson = {"lesson": {"topic": "Ponds", "part": 2, "active": True}}
    assert browser.put("/api/participant/progress", json=lesson).status_code == 204
    other = TestClient(browser.app)
    sign_in(other)
    assert other.get("/api/participant/progress").json() == lesson
    refused = browser.put("/api/participant/progress", json={"secrets": 1})
    assert refused.status_code == 400 and refused.json() == {"detail": BAD_PROGRESS}
    big = {"quiz": "x" * MAX_PROGRESS_BYTES}
    assert browser.put("/api/participant/progress", json=big).status_code == 400
    assert other.get("/api/participant/progress").json() == lesson


def test_progress_that_cant_be_read_is_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    accounts = ParticipantAccounts(tmp_path, "a")
    pat = accounts.participant(accounts.sign_up(PAT, PASSWORD))
    assert pat is not None
    accounts.save_progress(pat, {"quiz": {"topic": "Ponds"}})
    path = tmp_path / "participant_progress" / f"{pat.id}.json"
    path.write_text("{broken")
    with caplog.at_level(logging.ERROR):
        assert accounts.progress(pat) == {}
    assert "Could not read a participant's progress" in caplog.text
    path.write_text('["not an object"]')
    assert accounts.progress(pat) == {}


def test_progress_saved_at_once_by_two_browsers_is_all_kept(tmp_path: Path) -> None:
    """Codex's review of PR #308: saves at the same moment never trip over each other's file."""
    accounts = ParticipantAccounts(tmp_path, "a")
    pat = accounts.participant(accounts.sign_up(PAT, PASSWORD))
    assert pat is not None
    errors: list[BaseException] = []

    def save(n: int) -> None:
        try:
            for i in range(20):
                accounts.save_progress(pat, {"lesson": {"topic": f"T{n}", "part": i}})
        except BaseException as e:  # noqa: BLE001 - every failure is the finding
            errors.append(e)

    threads = [threading.Thread(target=save, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert accounts.progress(pat)["lesson"]["part"] == 19
    assert list((tmp_path / "participant_progress").glob("*.part")) == []
