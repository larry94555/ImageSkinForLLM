"""Host accounts on the server (roadmap R188)."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from imageskin import admin, cli
from imageskin.app import create_app
from imageskin.hosts import (
    BAD_EMAIL,
    EMAIL_TAKEN,
    FILENAME,
    SHORT_PASSWORD,
    WRONG,
    HostAccounts,
    HostRefused,
)

PASSWORD = "a long secret"


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Cheaper scrypt runs, so the many sign-ins here stay quick."""
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)
    caplog.set_level(logging.INFO)


def refused(e: pytest.ExceptionInfo[HostRefused]) -> tuple[str, str]:
    return str(e.value), e.value.reason


def test_sign_up_keeps_only_hashes(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    accounts = HostAccounts(tmp_path, clock=lambda: 1000.0)
    token = accounts.sign_up(" Host@Example.com ", PASSWORD, "1.2.3.4")
    host = accounts.host(token)
    assert host is not None and (host.email, host.created_at) == ("host@example.com", 1000.0)
    text = (tmp_path / FILENAME).read_text()
    assert (tmp_path / FILENAME).stat().st_mode & 0o077 == 0
    assert PASSWORD not in text and token not in text
    saved = json.loads(text)
    assert saved["hosts"]["host@example.com"]["password_hash"].startswith("scrypt$")
    assert list(saved["sessions"]) == [hashlib.sha256(token.encode()).hexdigest()]
    line = next(r for r in caplog.records if r.getMessage() == "Host signed up")
    assert (line.email, line.address) == ("host@example.com", "1.2.3.4")  # type: ignore[attr-defined]
    assert line.took_ms >= 0  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("email", "password", "message", "reason"),
    [
        ("not an email", PASSWORD, BAD_EMAIL, "not an email address"),
        ("a@b.c", "too short", SHORT_PASSWORD, "password too short"),
    ],
)
def test_sign_up_refuses_bad_fields(
    tmp_path: Path, email: str, password: str, message: str, reason: str
) -> None:
    with pytest.raises(HostRefused) as e:
        HostAccounts(tmp_path).sign_up(email, password, "1.2.3.4")
    assert refused(e) == (message, reason)
    assert not (tmp_path / FILENAME).exists()


def test_the_same_email_signs_up_once(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    accounts = HostAccounts(tmp_path)
    accounts.sign_up("host@example.com", PASSWORD, "1.2.3.4")
    with pytest.raises(HostRefused) as e:
        accounts.sign_up("HOST@example.com", "another password", "1.2.3.4")
    assert refused(e) == (EMAIL_TAKEN, "email already signed up")
    assert "Host sign-up failed" in caplog.text
    # Any number of other hosts may sign up (R188's default).
    accounts.sign_up("second@example.com", PASSWORD, "1.2.3.4")


def test_sign_in_and_out(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    accounts = HostAccounts(tmp_path)
    accounts.sign_up("host@example.com", PASSWORD, "1.2.3.4")
    token = accounts.sign_in("host@example.com", PASSWORD, "5.6.7.8")
    assert accounts.host(token) is not None
    # A restart keeps the sign-in: a new HostAccounts reads it from the file.
    assert HostAccounts(tmp_path).host(token) is not None
    accounts.sign_out(token, "5.6.7.8")
    assert accounts.host(token) is None and HostAccounts(tmp_path).host(token) is None
    accounts.sign_out(token, "5.6.7.8")  # signing out again does nothing
    accounts.sign_out(None, "5.6.7.8")
    assert [r.getMessage() for r in caplog.records].count("Host signed out") == 1
    assert "Host signed in" in caplog.text


def test_wrong_email_or_password_gets_the_same_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    accounts = HostAccounts(tmp_path)
    accounts.sign_up("host@example.com", PASSWORD, "1.2.3.4")
    runs: list[int] = []
    scrypt = hashlib.scrypt

    def counted(*args: Any, **kwargs: Any) -> bytes:
        runs.append(1)
        return scrypt(*args, **kwargs)

    monkeypatch.setattr(hashlib, "scrypt", counted)
    reasons = []
    for email, password in [("host@example.com", "wrong guess!"), ("who@example.com", PASSWORD)]:
        runs.clear()
        with pytest.raises(HostRefused) as e:
            accounts.sign_in(email, password, "1.2.3.4")
        assert str(e.value) == WRONG
        reasons.append(e.value.reason)
        assert len(runs) == 1  # one scrypt run either way, so the time doesn't tell
    assert reasons == ["wrong password", "no such host"]
    lines = [r for r in caplog.records if r.getMessage() == "Host sign-in failed"]
    assert [r.reason for r in lines] == reasons  # type: ignore[attr-defined]
    assert "wrong guess!" not in caplog.text


def test_reset_password_ends_the_hosts_sign_ins(tmp_path: Path) -> None:
    accounts = HostAccounts(tmp_path)
    token = accounts.sign_up("host@example.com", PASSWORD, "1.2.3.4")
    other = accounts.sign_up("other@example.com", PASSWORD, "1.2.3.4")
    # Reset by the command, as a separate process, while the server keeps its own HostAccounts.
    assert HostAccounts(tmp_path).reset_password("HOST@example.com", "a new long one")
    assert accounts.host(token) is None and accounts.host(other) is not None
    accounts.sign_in("host@example.com", "a new long one", "1.2.3.4")
    with pytest.raises(HostRefused):
        accounts.sign_in("host@example.com", PASSWORD, "1.2.3.4")
    assert not accounts.reset_password("nobody@example.com", "a new long one")
    with pytest.raises(HostRefused):
        accounts.reset_password("host@example.com", "short")


def test_an_unreadable_file_means_no_hosts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / FILENAME).write_text("{ not json")
    accounts = HostAccounts(tmp_path)
    assert accounts.host("anything") is None
    assert "Could not read the host accounts file" in caplog.text


def test_the_api_signs_up_in_and_out(tmp_path: Path) -> None:
    browser = TestClient(create_app(tmp_path))
    assert browser.get("/api/host/session").json() == {"signed_in": False, "email": None}
    assert browser.get("/api/host/me").status_code == 401
    up = browser.post("/api/host/sign-up", json={"email": "Host@example.com", "password": PASSWORD})
    assert up.json() == {"signed_in": True, "email": "host@example.com"}
    cookie = up.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Max-Age=" in cookie
    assert browser.get("/api/host/me").json()["email"] == "host@example.com"
    again = browser.post("/api/host/sign-up", json={"email": "host@example.com", "password": "x"})
    assert again.status_code == 400 and again.json() == {"detail": SHORT_PASSWORD}
    host = {"email": "host@example.com", "password": PASSWORD}
    taken = browser.post("/api/host/sign-up", json=host)
    assert taken.status_code == 409 and taken.json() == {"detail": EMAIL_TAKEN}

    old = browser.cookies.get("imageskin_host") or ""
    assert browser.post("/api/host/sign-out").json() == {"signed_in": False}
    assert browser.get("/api/host/me").status_code == 401
    # The old cookie, sent again, is refused: signing out ended it on the server.
    stale = TestClient(browser.app, cookies={"imageskin_host": old})
    assert stale.get("/api/host/me").status_code == 401

    wrong = browser.post("/api/host/sign-in", json={**host, "password": "nope"})
    assert wrong.status_code == 401 and wrong.json() == {"detail": WRONG}
    right = browser.post("/api/host/sign-in", json=host)
    assert right.status_code == 200
    assert browser.get("/api/host/session").json() == {
        "signed_in": True,
        "email": "host@example.com",
    }


def test_the_reset_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("IMAGESKIN_HOME", str(tmp_path))
    HostAccounts(tmp_path).sign_up("host@example.com", PASSWORD, "1.2.3.4")
    answers: list[str] = []
    monkeypatch.setattr("getpass.getpass", lambda prompt: answers.pop(0))

    answers[:] = ["a new long one", "a new long one"]
    assert cli.main(["host-password-reset", "host@example.com"]) == 0
    assert "is changed" in capsys.readouterr().out
    HostAccounts(tmp_path).sign_in("host@example.com", "a new long one", "1.2.3.4")

    answers[:] = ["a new long one", "different"]
    assert cli.main(["host-password-reset", "host@example.com"]) == 1
    answers[:] = ["short", "short"]
    assert cli.main(["host-password-reset", "host@example.com"]) == 1
    answers[:] = ["a new long one", "a new long one"]
    assert cli.main(["host-password-reset", "nobody@example.com"]) == 1
    assert "No host has signed up" in capsys.readouterr().err
