"""Signing in as the administrator (roadmap R149)."""

import hashlib
import logging
import os
import re
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from imageskin import admin
from imageskin.admin import (
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


@contextmanager
def refused_for(reason: str) -> Iterator[None]:
    """A refusal whose cause, kept for the log, is this one."""
    with pytest.raises(AdminRefused) as refused:
        yield
    assert refused.value.reason == reason


REAL_DUMMY = admin._dummy
CODE = re.compile(r"A-[A-HJ-NP-Z2-9]{6}")


@pytest.fixture(autouse=True)
def quick_dummy(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cheaper hash to check when there is nothing real to check, so the many failed sign-ins
    here run quickly; the app's own is as costly as a real one."""
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = Secret("hash", hash_password("never typed"))
    monkeypatch.undo()
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


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
    with pytest.raises(AdminRefused) as refused:
        AdminSignIns(file).sign_in("guess", "1.2.3.4")
    assert refused.value.reason == "wrong password" and CODE.fullmatch(refused.value.code)
    assert str(refused.value) == f"Admin login failed with error code {refused.value.code}."
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
    with refused_for("no password set"):
        sign_ins.sign_in("", "1.2.3.4")


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
    with refused_for("wrong password"):
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
    with refused_for("wrong password"):
        sign_ins.sign_in("plain", "1.2.3.4")


GOOD_SALT, GOOD_DIGEST = "c2FsdHNhbHRzYWx0c2FsdA==", "ZGlnZXN0ZGlnZXN0ZGlnZXN0ZGlnZXN0"


@pytest.mark.parametrize(
    "value",
    [
        "scrypt$bad",
        "scrypt$16384$8$1$!!$!!",
        "plain text",
        # Codex's review: an N too big for scrypt raised TypeError, a server error.
        "scrypt$18446744073709551616$8$1$cw==$cw==",
        f"scrypt$16385$8$1${GOOD_SALT}${GOOD_DIGEST}",  # N not a power of two
        f"scrypt$1048576$8$1${GOOD_SALT}${GOOD_DIGEST}",  # more than 32 MB a try
        f"scrypt$16384$0$1${GOOD_SALT}${GOOD_DIGEST}",
        f"scrypt$16384$8$99${GOOD_SALT}${GOOD_DIGEST}",
        f"scrypt$-16384$8$1${GOOD_SALT}${GOOD_DIGEST}",
        f"scrypt$16384$8$1$cw==${GOOD_DIGEST}",  # a salt too short
        f"scrypt$16384$8$1${GOOD_SALT}$cw==",  # a digest too short
        f"bcrypt$16384$8$1${GOOD_SALT}${GOOD_DIGEST}",
    ],
)
def test_a_hash_that_is_not_valid_matches_nothing(
    value: str, caplog: pytest.LogCaptureFixture
) -> None:
    assert not password_matches("plain text", Secret("hash", value))
    assert "Admin password hash is not valid" in caplog.text


def test_after_five_wrong_passwords_the_next_try_waits_a_minute(file: Path) -> None:
    clock = Clock()
    sign_ins = AdminSignIns(file, clock=clock)
    for _ in range(5):
        with refused_for("wrong password"):
            sign_ins.sign_in("guess", "1.2.3.4")
    with refused_for("waiting"):
        sign_ins.sign_in("first secret", "1.2.3.4")  # even the right one, for now
    clock.now += 61
    token = sign_ins.sign_in("first secret", "1.2.3.4")
    assert sign_ins.signed_in(token)
    with refused_for("wrong password"):  # counting starts again
        sign_ins.sign_in("guess", "1.2.3.4")


def test_one_addresss_wrong_passwords_never_make_another_wait(file: Path) -> None:
    # Codex's review: anyone could lock the administrator out with five wrong passwords.
    sign_ins = AdminSignIns(file, clock=Clock())
    for _ in range(10):
        with pytest.raises(AdminRefused):
            sign_ins.sign_in("guess", "203.0.113.9")
    with refused_for("waiting"):
        sign_ins.sign_in("first secret", "203.0.113.9")
    assert sign_ins.signed_in(sign_ins.sign_in("first secret", "198.51.100.7"))


def test_many_guessing_addresses_are_not_all_kept(
    file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin, "WRONG_KEPT", 3)
    clock = Clock()
    sign_ins = AdminSignIns(file, clock=clock)
    for n in range(3):
        with pytest.raises(AdminRefused):
            sign_ins.sign_in("guess", f"10.0.0.{n}")
    clock.now += 61  # their waits are over
    with pytest.raises(AdminRefused):
        sign_ins.sign_in("guess", "10.0.0.9")
    assert list(sign_ins._wrong) == ["10.0.0.9"]


def test_a_flood_of_addresses_within_the_minute_stays_within_the_cap(
    file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Codex's review: without the clock moving on, no wait is over, so none could be dropped.
    monkeypatch.setattr(admin, "WRONG_KEPT", 50)
    sign_ins = AdminSignIns(file, clock=Clock())
    for _ in range(5):
        with refused_for("wrong password"):
            sign_ins.sign_in("guess", "203.0.113.9")
    for n in range(48):
        with pytest.raises(AdminRefused):
            sign_ins.sign_in("guess", f"10.0.{n // 256}.{n % 256}")
    with refused_for("waiting"):  # kept: still waiting
        sign_ins.sign_in("first secret", "203.0.113.9")
    for n in range(48, 500):
        with pytest.raises(AdminRefused):
            sign_ins.sign_in("guess", f"10.0.{n // 256}.{n % 256}")
        assert len(sign_ins._wrong) <= 50
    assert list(sign_ins._wrong)[-1] == "10.0.1.243"  # the newest is kept, the oldest went


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


def refusals(caplog: pytest.LogCaptureFixture) -> dict[str, str]:
    """Each logged refusal's code, with its reason."""
    return {
        r.code: r.reason  # type: ignore[attr-defined]
        for r in caplog.records
        if r.getMessage() == "Admin sign-in refused"
    }


def test_every_failed_sign_in_gets_one_answer_and_only_the_log_says_why(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    browser = client(tmp_path)
    answers = [browser.post("/api/admin/sign-in", json={"password": "x"})]  # no password set
    assert browser.get("/api/admin/session").json()["password_set"] is False
    write(tmp_path / "admin.toml", 'password = "first secret"\n')
    for _ in range(4):
        answers.append(browser.post("/api/admin/sign-in", json={"password": "x"}))
    # Five failures in a row, whatever their cause: even the right password waits.
    answers.append(browser.post("/api/admin/sign-in", json={"password": "first secret"}))
    codes = []
    for answer in answers:
        body = answer.json()
        assert answer.status_code == 401 and "retry-after" not in answer.headers
        assert set(body) == {"detail", "code"} and CODE.fullmatch(body["code"])
        assert body["detail"] == f"Admin login failed with error code {body['code']}."
        assert "password" not in body["detail"].lower() and "wait" not in body["detail"].lower()
        codes.append(body["code"])
    assert len(set(codes)) == len(codes)  # a new code each time, never one for each cause
    logged = refusals(caplog)
    assert [logged[code] for code in codes] == ["no password set"] + ["wrong password"] * 4 + [
        "waiting"
    ]
    lines = [r for r in caplog.records if r.getMessage() == "Admin sign-in refused"]
    assert all(r.levelname == "WARNING" for r in lines)
    assert [r.failures_in_a_row for r in lines] == [1, 2, 3, 4, 5, 5]  # type: ignore[attr-defined]
    assert {r.address for r in lines} == {"testclient"}  # type: ignore[attr-defined]


def test_every_cause_checks_a_password_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The same work whatever the cause, so the time taken doesn't tell the causes apart.
    runs: list[int] = []
    scrypt = hashlib.scrypt

    def counted(*args: Any, **kwargs: Any) -> bytes:
        runs.append(1)
        return scrypt(*args, **kwargs)

    path = tmp_path / "admin.toml"
    sign_ins = AdminSignIns(path, clock=Clock())
    monkeypatch.setattr(hashlib, "scrypt", counted)
    for password, text in [("x", None), ("x", 'password = "plain"\n'), ("plain", None)]:
        if text:
            write(path, text)
        runs.clear()
        with pytest.raises(AdminRefused) if password == "x" else _nothing():
            sign_ins.sign_in(password, "1.2.3.4")
        assert len(runs) == 1
    write(path, f'password_hash = "{hash_password("hashed")}"\n')
    for _ in range(5):
        with refused_for("wrong password"):
            sign_ins.sign_in("x", "1.2.3.4")
    runs.clear()
    with refused_for("waiting"):
        sign_ins.sign_in("hashed", "1.2.3.4")
    assert len(runs) == 1


@contextmanager
def _nothing() -> Iterator[None]:
    yield


def test_the_api_makes_only_the_guessing_browser_wait(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write(tmp_path / "admin.toml", 'password = "first secret"\n')
    app = create_app(tmp_path)
    guesser = TestClient(app, client=("203.0.113.9", 40000))
    for n in range(6):
        # Its own X-Forwarded-For changes nothing: it isn't a trusted proxy.
        guesser.post(
            "/api/admin/sign-in", json={"password": "x"}, headers={"X-Forwarded-For": f"1.1.1.{n}"}
        )
    code = guesser.post("/api/admin/sign-in", json={"password": "x"}).json()["code"]
    assert refusals(caplog)[code] == "waiting"
    administrator = TestClient(app, client=("198.51.100.7", 40001))
    assert administrator.post("/api/admin/sign-in", json={"password": "first secret"}).json() == {
        "signed_in": True
    }


def test_a_hash_that_cant_be_used_refuses_the_sign_in_without_a_server_error(
    tmp_path: Path,
) -> None:
    write(tmp_path / "admin.toml", 'password_hash = "scrypt$18446744073709551616$8$1$cw==$cw=="\n')
    refused = client(tmp_path).post("/api/admin/sign-in", json={"password": "anything"})
    assert refused.status_code == 401 and refused.json()["detail"].startswith("Admin login failed")


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
    assert refused.status_code == 401 and refused.json()["detail"] == "Not supported at this time."
    browser.post("/api/admin/sign-in", json={"password": "first secret"})
    assert browser.get("/api/admin/test-only").json() == {"ok": True}
    browser.cookies.clear()
    browser.cookies.set(COOKIE, "made up")
    assert browser.get("/api/admin/test-only").status_code == 401


# The command that makes the hash


def test_the_dummy_hash_is_as_costly_as_a_real_one() -> None:
    n, r, p, _, _ = admin.parse_hash(REAL_DUMMY.__wrapped__().value)
    assert (n, r, p) == (admin.SCRYPT_N, admin.SCRYPT_R, admin.SCRYPT_P)


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
