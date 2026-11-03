"""A trial site is at a path of the main address, /t/<code>, with every call under it
(roadmap R61a)."""

import io
import logging
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_chatgpt_signin import NOW, FakeOpenAi
from test_site_addresses import PASSWORD, PDF, served, with_hosts

from imageskin import admin, cli
from imageskin.app import create_app
from imageskin.chatgpt_signin import ChatGptSignIn
from imageskin.sites import TRIAL_CODE_LENGTH, SignInReturns, SiteApps, site_home, site_matcher
from imageskin.uploads import PhotoResult

pytestmark = pytest.mark.real_hosts

ANN, BOB, CY = "ann@example.com", "bob@example.com", "cy@example.com"


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def sign_in(client: TestClient, email: str, prefix: str = "") -> int:
    response = client.post(
        f"{prefix}/api/host/sign-in", json={"email": email, "password": PASSWORD}
    )
    return response.status_code


def http(host: str, path: str) -> dict[str, object]:
    return {"type": "http", "path": path, "headers": [(b"host", host.encode())]}


def test_a_trial_site_is_matched_by_its_path_at_the_main_address(tmp_path: Path) -> None:
    service = with_hosts(tmp_path, ANN, BOB)
    code, folder = service.sites.add_trial(ANN)
    assert re.fullmatch(rf"[a-z0-9]{{{TRIAL_CODE_LENGTH}}}", code)
    assert folder == tmp_path / "sites" / code and folder.is_dir()
    assert service.host_accounts.site_of(ANN) == code
    site_of = site_matcher(service.sites, "me0.ai")
    for host in ("localhost", "me0.ai", "www.me0.ai", "127.0.0.1"):
        assert site_of(http(host, f"/t/{code}/api/content")) == code
        assert site_of(http(host, f"/t/{code}")) == code
    # A trial site has no subdomain, and an unknown code is no site.
    assert site_of(http(f"{code}.localhost", "/")) is None
    assert site_of(http("localhost", "/t/aaaaaaaaaaaa/")) is None
    # Another path, or another site's address, is matched as before (R61).
    assert site_of(http("localhost", "/api/content")) == "default"
    assert site_of(http("localhost", f"/t/{code}x/")) == "default"
    assert not service.sites.exists(code) and service.sites.is_trial(code)
    other, _ = service.sites.add_trial(BOB)
    assert other != code


def test_a_trial_sites_page_and_calls_reach_it_under_its_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, made, service = served(tmp_path)
    service.host_accounts.sign_up(CY, PASSWORD, "test")
    code, _ = service.sites.add_trial(CY)
    trial = TestClient(sites, base_url="http://localhost:8000")
    a = TestClient(sites, base_url="http://a.localhost:8000")
    caplog.set_level(logging.INFO, logger="imageskin.sites")
    # The page is at its path with a slash, and its files load under it.
    moved = trial.get(f"/t/{code}?x=1", follow_redirects=False)
    assert moved.status_code == 308 and moved.headers["location"] == f"/t/{code}/?x=1"
    page = trial.get(f"/t/{code}/")
    assert page.status_code == 200 and 'src="./assets/app.js"' in page.text
    assert trial.get(f"/t/{code}/assets/app.js").status_code == 200
    with caplog.at_level(logging.INFO, logger="imageskin.sites"):
        assert (
            trial.post(
                f"/t/{code}/api/host/sign-in", json={"email": CY, "password": PASSWORD}
            ).status_code
            == 200
        )
    assert sign_in(a, ANN) == 200
    for client, prefix in ((trial, f"/t/{code}"), (a, "")):
        client.post(f"{prefix}/api/consent", json={"agreed": True})
    trial.post(f"/t/{code}/api/content", files={"file": ("mars.pdf", io.BytesIO(PDF))})
    made[code].state.readings.wait()
    # Its own PDFs, apart from the site at a.localhost and the main address's.
    assert [p["name"] for p in trial.get(f"/t/{code}/api/content").json()] == ["mars.pdf"]
    assert a.get("/api/content").json() == []
    assert (tmp_path / "home" / "sites" / code / "content" / "pdfs").is_dir()
    matched = [r.__dict__ for r in caplog.records if r.message == "Site matched"]
    assert matched[0]["site"] == code and matched[0]["trial"] == code


def test_a_host_of_a_trial_site_is_sent_to_its_path(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path)
    service.host_accounts.sign_up(CY, PASSWORD, "test")
    code, _ = service.sites.add_trial(CY)
    main = TestClient(sites, base_url="http://www.localhost:8000")
    sent = main.post("/api/host/sign-in", json={"email": CY, "password": PASSWORD})
    # The browser stays at the main address it came to, where the trial site is.
    assert sent.json()["sign_in_at"].startswith(
        f"http://www.localhost:8000/t/{code}/api/host/sign-in/"
    )
    trial = TestClient(sites, base_url="http://localhost:8000")
    sent = trial.post(f"/t/{code}/api/host/sign-in", json={"email": ANN, "password": PASSWORD})
    assert sent.json()["sign_in_at"].startswith("http://a.localhost:8000/api/host/sign-in/")


def test_a_trial_site_is_added_and_listed_from_the_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("IMAGESKIN_HOME", str(tmp_path))
    with_hosts(tmp_path, ANN)
    assert cli.main(["site", "trial", "--host", ANN]) == 0
    code = re.search(r"localhost/t/([a-z0-9]+)/", capsys.readouterr().out)
    assert code is not None
    assert cli.main(["site", "trial", "--host", ANN]) == 1
    assert "Nothing changed." in capsys.readouterr().err
    assert cli.main(["site", "list"]) == 0
    assert capsys.readouterr().out == f"{code.group(1)}: {ANN} at /t/{code.group(1)}\n"


def test_sign_in_with_chatgpt_is_not_offered_on_a_trial_site(tmp_path: Path) -> None:
    """The ChatGPT plan is for the app on the user's own computer, or the main address's own
    server, never a customer's site (R44, which replaces Codex's review of PR #277 that brought
    the sign-in back to the trial site that started it)."""
    openai = FakeOpenAi()
    home = tmp_path / "home"
    service = with_hosts(home, CY)
    code, _ = service.sites.add_trial(CY)
    signins: dict[str, ChatGptSignIn] = {}

    def make(site: str) -> FastAPI:
        signins[site] = ChatGptSignIn(
            site_home(site, home), http=openai, clock=lambda: NOW, sleep=openai.sleeps.append
        )
        return create_app(
            site_home(site, home),
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            chatgpt=signins[site],
            service=service,
            site=site,
        )

    sites = SiteApps(make, site_matcher(service.sites, "me0.ai", service.sign_in_returns))
    browser = TestClient(sites, base_url="http://127.0.0.1:8000", follow_redirects=False)
    assert sign_in(browser, CY, f"/t/{code}") == 200
    assert browser.get(f"/t/{code}/api/chatgpt/sign-in").status_code == 404
    assert browser.get(f"/t/{code}/api/chatgpt").status_code == 404
    assert openai.forms == [] and openai.jwks_reads == 0  # OpenAI was never asked
    assert not (site_home(code, home) / "chatgpt.json").exists()


def test_sign_ins_started_are_kept_a_while_and_only_so_many() -> None:
    now = [0.0]
    returns = SignInReturns(clock=lambda: now[0])
    returns.started("old", "a", "http://a.localhost/")
    now[0] = SignInReturns.KEEP_S + 1
    for n in range(SignInReturns.MOST + 1):
        returns.started(f"s{n}", "b", "http://localhost/t/b/")
    assert returns.site_of("old") is None  # expired
    assert returns.site_of("s0") is None and returns.site_of(f"s{SignInReturns.MOST}") == "b"
    assert returns.page_of("s1") == "http://localhost/t/b/" and returns.page_of("s1") is None
