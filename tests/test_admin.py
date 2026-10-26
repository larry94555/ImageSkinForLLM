"""Signing in as the administrator (roadmap R149)."""

import logging
import os
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from imageskin import admin
from imageskin.admin import (
    NOT_SET,
    WAIT,
    WRONG,
    AdminRefused,
    AdminSignIns,
    Secret,
    hash_password,
    password_matches,
    read_secret,
)
from imageskin.admin_api import COOKIE
from imageskin.app import create_app
from imageskin.cli import main

ROOT = Path(__file__).resolve().parent.parent


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    # A new modification time each write, as an editor's save would make, even within one tick.
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))


@pytest.fixture
def file(tmp_path: Path) -> Path:
    path = tmp_path / "admin.toml"
    write(path, 'password = "first secret"\n')
    return path


def test_the_password_in_the_file_signs_in(file: Path, caplog: pytest.LogCaptureFixture) -> None:
    sign_ins = AdminSignIns(file)
    with caplog.at_level(logging.INFO):
        token = sign_ins.sign_in("first secret", "1.2.3.4")
    assert sign_ins.signed_in(token)
    assert not sign_ins.signed_in("another") and not sign_ins.signed_in(None)
    assert "Admin signed in" in caplog.text
    assert "first secret" not in caplog.text  # never the password


def test_a_wrong_password_is_refused(file: Path, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(AdminRefused, match=WRONG) as refused:
        AdminSignIns(file).sign_in("guess", "1.2.3.4")
    assert refused.value.status == 401
    assert "Admin sign-in refused" in caplog.text and "guess" not in caplog.text


@pytest.mark.parametrize(
    "text",
    [None, "", 'password = ""\npassword_hash = ""\n', "not = [toml", "password = 3\n"],
)
def test_no_file_or_no_password_in_it_turns_signing_in_off(
    tmp_path: Path, text: str | None
) -> None:
    path = tmp_path / "admin.toml"
    if text is not None:
        write(path, text)
    sign_ins = AdminSignIns(path)
    assert sign_ins.secret() is None
    with pytest.raises(AdminRefused, match="signing in as the administrator is off") as refused:
        sign_ins.sign_in("", "1.2.3.4")
    assert refused.value.status == 403 and str(refused.value) == NOT_SET


def test_the_committed_template_has_no_password() -> None:
    template = ROOT / "admin.example.toml"
    assert read_secret(template) is None
    assert tomllib.loads(template.read_text()) == {"password_hash": "", "password": ""}
    assert "admin.toml" in (ROOT / ".gitignore").read_text().splitlines()


def test_a_new_password_works_at_once_and_signs_out_the_old_one(
    file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sign_ins = AdminSignIns(file)
    old = sign_ins.sign_in("first secret", "1.2.3.4")
    write(file, 'password = "second secret"\n')
    with caplog.at_level(logging.INFO):
        assert not sign_ins.signed_in(old)
    assert sign_ins.ended(old) == "password changed"
    assert sign_ins.ended(old) is None  # said once
    assert "Admin password file read" in caplog.text
    with pytest.raises(AdminRefused, match=WRONG):
        sign_ins.sign_in("first secret", "1.2.3.4")
    assert sign_ins.signed_in(sign_ins.sign_in("second secret", "1.2.3.4"))


def test_the_same_password_saved_again_keeps_the_sign_in(file: Path) -> None:
    sign_ins = AdminSignIns(file)
    token = sign_ins.sign_in("first secret", "1.2.3.4")
    write(file, '# a comment added\npassword = "first secret"\n')
    assert sign_ins.signed_in(token)


def test_removing_the_password_signs_out(file: Path) -> None:
    sign_ins = AdminSignIns(file)
    token = sign_ins.sign_in("first secret", "1.2.3.4")
    file.unlink()
    assert not sign_ins.signed_in(token)
    assert sign_ins.ended(token) == "password changed"


def test_a_hash_signs_in_with_its_password(tmp_path: Path) -> None:
    path = tmp_path / "admin.toml"
    line = hash_password("hashed secret")
    assert "hashed secret" not in line and line.startswith("scrypt$")
    # The hash wins over a password line, as the template says.
    write(path, f'password_hash = "{line}"\npassword = "plain"\n')
    sign_ins = AdminSignIns(path)
    assert sign_ins.signed_in(sign_ins.sign_in("hashed secret", "1.2.3.4"))
    with pytest.raises(AdminRefused, match=WRONG):
        sign_ins.sign_in("plain", "1.2.3.4")


@pytest.mark.parametrize("value", ["scrypt$bad", "scrypt$16384$8$1$!!$!!", "plain text"])
def test_a_hash_that_is_not_valid_matches_nothing(
    value: str, caplog: pytest.LogCaptureFixture
) -> None:
    assert not password_matches("plain text", Secret("hash", value))
    assert "Admin password hash is not valid" in caplog.text


def test_after_five_wrong_passwords_the_next_try_waits_a_minute(file: Path) -> None:
    clock = Clock()
    sign_ins = AdminSignIns(file, clock=clock)
    for _ in range(5):
        with pytest.raises(AdminRefused, match=WRONG):
            sign_ins.sign_in("guess", "1.2.3.4")
    with pytest.raises(AdminRefused, match=WAIT) as refused:
        sign_ins.sign_in("first secret", "1.2.3.4")  # even the right one, for now
    assert refused.value.status == 429
    clock.now += 61
    token = sign_ins.sign_in("first secret", "1.2.3.4")
    assert sign_ins.signed_in(token)
    with pytest.raises(AdminRefused, match=WRONG):  # counting starts again
        sign_ins.sign_in("guess", "1.2.3.4")


def test_thirty_minutes_without_activity_signs_out(
    file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = Clock()
    sign_ins = AdminSignIns(file, clock=clock)
    token = sign_ins.sign_in("first secret", "1.2.3.4")
    clock.now += 29 * 60
    assert sign_ins.activity(token)  # a click: the half hour starts again
    clock.now += 29 * 60
    assert sign_ins.signed_in(token)  # asking is not activity
    clock.now += 2 * 60
    with caplog.at_level(logging.INFO):
        assert not sign_ins.signed_in(token)
    assert sign_ins.ended(token) == "inactive"
    assert not sign_ins.activity(token)
    assert [getattr(r, "why", None) for r in caplog.records] == ["inactive"]


def test_the_timeout_is_read_each_time(file: Path) -> None:
    clock, minutes = Clock(), [30]
    sign_ins = AdminSignIns(file, timeout_minutes=lambda: minutes[0], clock=clock)
    token = sign_ins.sign_in("first secret", "1.2.3.4")
    clock.now += 6 * 60
    minutes[0] = 5
    assert not sign_ins.signed_in(token)


def test_signing_out(file: Path, caplog: pytest.LogCaptureFixture) -> None:
    sign_ins = AdminSignIns(file)
    token = sign_ins.sign_in("first secret", "1.2.3.4")
    with caplog.at_level(logging.INFO):
        sign_ins.sign_out(token)
    assert not sign_ins.signed_in(token) and sign_ins.ended(token) is None
    assert "Admin signed out" in caplog.text
    sign_ins.sign_out(token)  # twice does nothing
    sign_ins.sign_out(None)


def test_an_unreadable_file_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "admin.toml"
    path.mkdir()  # a folder where the file should be
    assert read_secret(path) is None
    assert "Could not read the admin password file" in caplog.text


# The API


def client(home: Path, admin_file: Path | None = None) -> TestClient:
    return TestClient(create_app(home, admin_file=admin_file))


def test_the_api_signs_in_and_out(tmp_path: Path) -> None:
    write(tmp_path / "admin.toml", 'password = "first secret"\n')
    browser = client(tmp_path)
    assert browser.get("/api/admin/session").json() == {
        "signed_in": False,
        "password_set": True,
        "timeout_minutes": 30,
        "ended": None,
    }
    response = browser.post("/api/admin/sign-in", json={"password": "first secret"})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Secure" not in cookie
    assert browser.get("/api/admin/session").json()["signed_in"] is True
    assert browser.post("/api/admin/activity").status_code == 204
    assert browser.post("/api/admin/sign-out").json() == {"signed_in": False}
    assert browser.get("/api/admin/session").json()["signed_in"] is False
    assert browser.post("/api/admin/activity").status_code == 401


def test_the_api_says_why_a_sign_in_was_refused(tmp_path: Path) -> None:
    browser = client(tmp_path)
    no_file = browser.post("/api/admin/sign-in", json={"password": "x"})
    assert no_file.status_code == 403 and no_file.json()["detail"] == NOT_SET
    assert browser.get("/api/admin/session").json()["password_set"] is False
    write(tmp_path / "admin.toml", 'password = "first secret"\n')
    for _ in range(5):
        wrong = browser.post("/api/admin/sign-in", json={"password": "x"})
        assert wrong.status_code == 401 and wrong.json()["detail"] == WRONG
    waiting = browser.post("/api/admin/sign-in", json={"password": "x"})
    assert waiting.status_code == 429 and waiting.headers["retry-after"] == "60"


def test_the_api_says_when_the_password_changed(tmp_path: Path) -> None:
    file = tmp_path / "elsewhere.toml"
    write(file, 'password = "first secret"\n')
    browser = client(tmp_path / "home", admin_file=file)
    browser.post("/api/admin/sign-in", json={"password": "first secret"})
    write(file, 'password = "second secret"\n')
    assert browser.get("/api/admin/session").json()["ended"] == "password changed"
    assert browser.get("/api/admin/session").json()["ended"] is None


def test_the_cookie_is_secure_behind_https(tmp_path: Path) -> None:
    write(tmp_path / "admin.toml", 'password = "first secret"\n')
    response = client(tmp_path).post(
        "/api/admin/sign-in",
        json={"password": "first secret"},
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "5.6.7.8, 10.0.0.1"},
    )
    assert "Secure" in response.headers["set-cookie"]


def test_require_admin_guards_a_route(tmp_path: Path) -> None:
    write(tmp_path / "admin.toml", 'password = "first secret"\n')
    app = create_app(tmp_path)
    from fastapi import Depends

    @app.get("/api/admin/test-only", dependencies=[Depends(app.state.require_admin)])
    def guarded() -> dict[str, bool]:
        return {"ok": True}

    # Ahead of the static files' catch-all, as an admin route added in create_app would be.
    app.router.routes.insert(0, app.router.routes.pop())
    browser = TestClient(app)
    refused = browser.get("/api/admin/test-only")
    assert refused.status_code == 401 and "Sign in as administrator" in refused.json()["detail"]
    browser.post("/api/admin/sign-in", json={"password": "first secret"})
    assert browser.get("/api/admin/test-only").json() == {"ok": True}
    browser.cookies.clear()
    browser.cookies.set(COOKIE, "made up")
    assert browser.get("/api/admin/test-only").status_code == 401


# The command that makes the hash


def test_the_hash_command_prints_a_line_that_signs_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(admin.__name__ + ".SCRYPT_N", 2**10)  # quicker; read back from the hash
    monkeypatch.setattr("getpass.getpass", lambda prompt: "typed secret")
    assert main(["admin-password-hash"]) == 0
    line = capsys.readouterr().out.splitlines()[-1]
    assert line.startswith('password_hash = "scrypt$1024$')
    write(tmp_path / "admin.toml", line + "\n")
    sign_ins = AdminSignIns(tmp_path / "admin.toml")
    assert sign_ins.signed_in(sign_ins.sign_in("typed secret", "1.2.3.4"))


@pytest.mark.parametrize("typed", [["", ""], ["one", "two"]])
def test_the_hash_command_needs_the_same_password_twice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], typed: list[str]
) -> None:
    answers = iter(typed)
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))
    assert main(["admin-password-hash"]) == 1
    assert "nothing to write" in capsys.readouterr().err
