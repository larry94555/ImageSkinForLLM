"""Each request goes to its site by its address, each site in its own folder with its one host
(roadmap R61)."""

import asyncio
import io
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imageskin import admin, cli
from imageskin.app import create_app
from imageskin.config import ConfigError, load_settings
from imageskin.host_api import SITE_HAS_HOST
from imageskin.hosts import DEFAULT_SITE, WRONG, HostAccounts, HostsUnreadable
from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.sites import (
    SITES_FILE,
    Service,
    SiteApps,
    SiteDirectory,
    SiteError,
    make_service,
    site_home,
    site_matcher,
)
from imageskin.uploads import PhotoResult

# These tests sign in for themselves.
pytestmark = pytest.mark.real_hosts

PASSWORD = "a long secret"
PDF = b"%PDF-1.4\n%fake\n"


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cheaper scrypt runs, so the sign-ins here stay quick."""
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def scope(host: str, kind: str = "http") -> dict[str, Any]:
    return {"type": kind, "path": "/", "headers": [(b"host", host.encode())]}


def with_hosts(home: Path, *emails: str) -> Service:
    service = make_service(home)
    for email in emails:
        service.host_accounts.sign_up(email, PASSWORD, "test")
    return service


def test_each_address_is_matched_to_its_site(tmp_path: Path) -> None:
    service = with_hosts(tmp_path, "ann@example.com")
    service.sites.add("a", "ann@example.com")
    site_of = site_matcher(service.sites, "me0.ai")
    for main in ("localhost:8000", "127.0.0.1", "[::1]:8000", "me0.ai", "www.me0.ai", "app.me0.ai"):
        assert site_of(scope(main)) == DEFAULT_SITE, main
    for address in ("a.localhost:8000", "a.me0.ai", "A.ME0.AI"):
        assert site_of(scope(address)) == "a", address
    for unknown in ("b.localhost", "b.me0.ai", "x.a.localhost"):
        assert site_of(scope(unknown)) is None, unknown


def test_a_site_is_added_with_its_one_host(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    service = with_hosts(tmp_path, "ann@example.com", "bob@example.com")
    token = service.host_accounts.sign_in("ann@example.com", PASSWORD, "test")
    with caplog.at_level(logging.INFO):
        folder = service.sites.add(" A ", "Ann@Example.com")
    assert folder == tmp_path / "sites" / "a" and folder.is_dir()
    assert service.sites.names() == ["a"] and service.sites.host("a") == "ann@example.com"
    assert service.host_accounts.site_of("ann@example.com") == "a"
    assert service.host_accounts.site_of("bob@example.com") == DEFAULT_SITE
    assert service.host_accounts.site_of("nobody@example.com") is None
    assert service.host_accounts.host(token) is None  # the old site's sign-in ended
    assert "Site added" in caplog.text and "Host site set" in caplog.text
    saved = json.loads((tmp_path / SITES_FILE).read_text())
    assert saved["sites"]["a"]["host"] == "ann@example.com"
    # A running server's directory sees the new site, as the file changed.
    assert SiteDirectory(tmp_path, service.host_accounts).exists("a")


@pytest.mark.parametrize(
    ("name", "email", "says"),
    [
        ("-a", "bob@example.com", "letters, digits and hyphens"),
        ("a" * 64, "bob@example.com", "letters, digits and hyphens"),
        ("www", "bob@example.com", "kept for the service"),
        ("default", "bob@example.com", "kept for the service"),
        ("a", "bob@example.com", "already a site called a"),
        ("b", "nobody@example.com", "No host has signed up"),
        ("b", "ann@example.com", "already the host of a"),
    ],
)
def test_a_site_that_cant_be_added_says_why(
    tmp_path: Path, name: str, email: str, says: str
) -> None:
    service = with_hosts(tmp_path, "ann@example.com", "bob@example.com")
    service.sites.add("a", "ann@example.com")
    with pytest.raises(SiteError, match=says):
        service.sites.add(name, email)
    assert service.sites.names() == ["a"]


def test_an_unreadable_sites_file_has_no_sites(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites = SiteDirectory(tmp_path, HostAccounts(tmp_path))
    (tmp_path / SITES_FILE).write_text("{not json")
    with caplog.at_level(logging.ERROR):
        assert not sites.exists("a") and sites.names() == []
    assert "Could not read the sites file" in caplog.text
    (tmp_path / SITES_FILE).write_text('{"sites": []}')
    assert sites.names() == []


def lesson(path: Path, progress: Progress) -> Reading:
    return Reading("text", 1, [Piece(1, "paragraph", "Text.")], [])


def served(tmp_path: Path) -> tuple[SiteApps, dict[str, FastAPI], Service]:
    home = tmp_path / "home"
    service = with_hosts(home, "ann@example.com", "bob@example.com")
    service.sites.add("a", "ann@example.com")
    made: dict[str, FastAPI] = {}

    def make(site: str) -> FastAPI:
        made[site] = create_app(
            site_home(site, home),
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            ask_llm=MagicMock(),
            read_pdf=lesson,
            build_wiki=MagicMock(),
            service=service,
            site=site,
        )
        return made[site]

    return SiteApps(make, site_matcher(service.sites, "me0.ai")), made, service


def sign_in(client: TestClient, email: str) -> int:
    response = client.post("/api/host/sign-in", json={"email": email, "password": PASSWORD})
    return response.status_code


def test_only_the_sites_own_host_signs_in_there(tmp_path: Path) -> None:
    sites, made, service = served(tmp_path)
    a = TestClient(sites, base_url="http://a.localhost")
    main = TestClient(sites, base_url="http://localhost")
    assert sign_in(main, "ann@example.com") == 401  # ann is site a's now
    refused = a.post("/api/host/sign-in", json={"email": "bob@example.com", "password": PASSWORD})
    assert refused.status_code == 401 and refused.json()["detail"] == WRONG  # bob is main's
    assert sign_in(a, "ann@example.com") == 200
    assert a.get("/api/host/me").json()["email"] == "ann@example.com"
    assert sign_in(main, "bob@example.com") == 200
    assert main.get("/api/host/session").json()["email"] == "bob@example.com"
    sign_up = a.post("/api/host/sign-up", json={"email": "cy@example.com", "password": PASSWORD})
    assert sign_up.status_code == 403 and sign_up.json()["detail"] == SITE_HAS_HOST

    # Ann's sign-in, sent to the main address by hand, counts as none there, and Bob's on a.
    ann = a.cookies.get("imageskin_host") or ""
    bob = main.cookies.get("imageskin_host") or ""
    by_hand = TestClient(sites, base_url="http://localhost", cookies={"imageskin_host": ann})
    assert by_hand.get("/api/host/me").status_code == 401
    assert by_hand.get("/api/host/session").json()["signed_in"] is False
    assert by_hand.get("/api/settings").json()["view"] == "participant"
    assert service.settings_access.who(ann, None, DEFAULT_SITE) is None
    assert service.settings_access.who(bob, None, "a") is None
    assert service.settings_access.who(ann, None, "a") == "host"


def test_each_site_keeps_its_files_in_its_own_folder(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, made, _ = served(tmp_path)
    a = TestClient(sites, base_url="http://a.localhost:8000")
    main = TestClient(sites, base_url="http://localhost:8000")
    with caplog.at_level(logging.DEBUG, logger="imageskin.sites"):
        assert sign_in(a, "ann@example.com") == 200
        assert sign_in(main, "bob@example.com") == 200
        for client in (a, main):
            client.post("/api/consent", json={"agreed": True})
        a.post("/api/content", files={"file": ("mars.pdf", io.BytesIO(PDF))})
        made["a"].state.readings.wait()
        assert [p["name"] for p in a.get("/api/content").json()] == ["mars.pdf"]
        assert main.get("/api/content").json() == []
    home = tmp_path / "home"
    assert (home / "sites" / "a" / "content").is_dir()
    assert (home / "sites" / "a" / "consent.json").exists() and (home / "consent.json").exists()
    assert not (home / "content").exists() or not any((home / "content").glob("*.pdf"))
    matched = [r for r in caplog.records if r.message == "Site matched"]
    infos = [r.__dict__["site"] for r in matched if r.levelno == logging.INFO]
    assert sorted(infos) == ["a", DEFAULT_SITE]  # once each at info, then at debug
    assert len(matched) > 2 and matched[0].__dict__["address"].endswith("localhost")


def test_an_address_with_no_site_is_not_found(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, made, _ = served(tmp_path)
    with caplog.at_level(logging.WARNING):
        response = TestClient(sites, base_url="http://b.localhost").get("/")
    assert response.status_code == 404 and "Site not found" in response.text
    logged = [r for r in caplog.records if r.message == "Site not found"]
    assert logged[0].__dict__["address"] == "b.localhost"
    assert "b" not in made

    sent: list[Any] = []

    async def receive() -> dict[str, str]:
        return {"type": "websocket.connect"}

    async def send(message: Any) -> None:
        sent.append(message)

    asyncio.run(sites(scope("b.localhost", "websocket"), receive, send))
    assert sent == [{"type": "websocket.close", "code": 4404}]


def test_sites_are_added_and_listed_from_the_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("IMAGESKIN_HOME", str(tmp_path))
    with_hosts(tmp_path, "ann@example.com")
    assert cli.main(["site", "add", "a", "--host", "ann@example.com"]) == 0
    assert "Added the site a" in capsys.readouterr().out
    assert cli.main(["site", "add", "b", "--host", "ann@example.com"]) == 1
    assert "already the host of a. Nothing changed." in capsys.readouterr().err
    assert cli.main(["site", "list"]) == 0
    assert capsys.readouterr().out == "a: ann@example.com\n"


def test_a_site_cant_be_added_while_the_host_accounts_cant_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("IMAGESKIN_HOME", str(tmp_path))
    (tmp_path / "hosts.json").write_text("{broken")
    assert cli.main(["site", "add", "a", "--host", "ann@example.com"]) == 1
    assert "Nothing changed." in capsys.readouterr().err
    with pytest.raises(HostsUnreadable):
        HostAccounts(tmp_path).site_of("ann@example.com")


def test_the_main_domain_is_set_in_the_config(tmp_path: Path) -> None:
    assert load_settings(None).main_domain == "me0.ai"
    config = tmp_path / "config.toml"
    config.write_text('main_domain = "example.org"\n')
    assert load_settings(config).main_domain == "example.org"
    for wrong in ('"localhost"', "3"):
        config.write_text(f"main_domain = {wrong}\n")
        with pytest.raises(ConfigError, match="main_domain"):
            load_settings(config)


def test_a_host_set_back_to_the_main_address_signs_in_there(tmp_path: Path) -> None:
    service = with_hosts(tmp_path, "ann@example.com")
    accounts = service.host_accounts
    assert accounts.set_site("ann@example.com", "a")
    assert accounts.set_site("ann@example.com", DEFAULT_SITE)
    assert (
        "site" not in json.loads((tmp_path / "hosts.json").read_text())["hosts"]["ann@example.com"]
    )
    token = accounts.sign_in("ann@example.com", PASSWORD, "test")
    assert accounts.host(token, DEFAULT_SITE) is not None
    assert not accounts.set_site("nobody@example.com", "a")
