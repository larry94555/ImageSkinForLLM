"""Admin settings' Host properties: every host, and a search by any part of the email (R241)."""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from imageskin import admin
from imageskin.app import create_app
from imageskin.hosts import FILENAME, HostAccounts, HostsUnreadable

# These tests sign up hosts for themselves.
pytestmark = pytest.mark.real_hosts

PASSWORD = "a long secret"
EMAILS = ["joanne@site.org", "ann@example.com", "bob@ann.net"]


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def hosts_of(tmp_path: Path) -> HostAccounts:
    accounts = HostAccounts(tmp_path)
    for email in EMAILS:
        accounts.sign_up(email, PASSWORD, "127.0.0.1")
    return accounts


@pytest.mark.parametrize(
    ("contains", "found"),
    [
        ("ann", ["ann@example.com", "bob@ann.net", "joanne@site.org"]),
        ("ANN@", ["ann@example.com"]),
        (".org", ["joanne@site.org"]),
        ("", ["ann@example.com", "bob@ann.net", "joanne@site.org"]),
        ("  ", ["ann@example.com", "bob@ann.net", "joanne@site.org"]),
        ("zed", []),
    ],
)
def test_the_emails_containing_the_text_anywhere(
    tmp_path: Path, contains: str, found: list[str]
) -> None:
    assert hosts_of(tmp_path).emails(contains) == found


def test_no_hosts_yet_is_an_empty_list(tmp_path: Path) -> None:
    assert HostAccounts(tmp_path).emails() == []


def test_an_unreadable_file_is_said(tmp_path: Path) -> None:
    (tmp_path / FILENAME).write_text("not json")
    with pytest.raises(HostsUnreadable):
        HostAccounts(tmp_path).emails()


def admin_client(tmp_path: Path) -> TestClient:
    (tmp_path / "admin.toml").write_text('password = "secret"\n')
    client = TestClient(create_app(tmp_path))
    for email in EMAILS:
        client.post("/api/host/sign-up", json={"email": email, "password": PASSWORD})
    # The admin sign-in is only for a signed-in host or a listed laptop (R191).
    client.post("/api/admin/sign-in", json={"password": "secret"})
    return client


def test_the_administrator_searches_the_hosts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = admin_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="imageskin.app"):
        every = client.get("/api/admin/hosts")
        some = client.get("/api/admin/hosts", params={"q": "ANN@"})
    assert every.json() == {"hosts": ["ann@example.com", "bob@ann.net", "joanne@site.org"]}
    assert some.json() == {"hosts": ["ann@example.com"]}
    shown = [r for r in caplog.records if r.message == "Host list shown"]
    assert [(r.matched, r.searched) for r in shown] == [(3, False), (1, True)]  # type: ignore[attr-defined]
    assert all(isinstance(r.__dict__["duration_ms"], float) for r in shown)
    # The text searched for may be part of an email, so the app never logs it (the test
    # client's own log of the request is not the app's).
    app_logs = [r for r in caplog.records if r.name.startswith("imageskin")]
    assert not any("ANN" in r.getMessage() or "ANN" in str(r.__dict__) for r in app_logs)


def test_only_the_administrator_sees_the_hosts(tmp_path: Path) -> None:
    client = admin_client(tmp_path)
    client.post("/api/admin/sign-out")
    assert client.get("/api/admin/hosts").status_code == 401
    assert TestClient(client.app).get("/api/admin/hosts").status_code == 401  # nor a visitor
    client.post("/api/admin/sign-in", json={"password": "secret"})
    assert client.get("/api/admin/hosts", params={"q": "x" * 321}).status_code == 422


def test_an_unreadable_hosts_file_is_503(tmp_path: Path) -> None:
    client = admin_client(tmp_path)
    (tmp_path / FILENAME).write_text("not json")
    refused = client.get("/api/admin/hosts")
    assert refused.status_code == 503
