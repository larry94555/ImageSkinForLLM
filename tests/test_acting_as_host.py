"""The administrator acting as a host (roadmap R44a): a one-time link from the main address gives
them the host's site, with all of the host's abilities, while they stay signed in."""

import logging
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_site_addresses import PASSWORD, served

from imageskin import acting, admin
from imageskin.acting import LINK_S, ActingAsHost, site_address
from imageskin.hosts import DEFAULT_SITE

pytestmark = pytest.mark.real_hosts

ANN, BOB = "ann@example.com", "bob@example.com"  # site a's host, and the main address's


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now


def administrator(sites: object, tmp_path: Path) -> TestClient:
    """Signed in as the administrator at the main address (and as its host, which R191 asks
    for before an admin sign-in)."""
    (tmp_path / "home" / "admin.toml").write_text('password = "secret"\n')
    browser = TestClient(sites, base_url="http://localhost:8000")  # type: ignore[arg-type]
    assert browser.post("/api/host/sign-in", json={"email": BOB, "password": PASSWORD}).is_success
    assert browser.post("/api/admin/sign-in", json={"password": "secret"}).is_success
    return browser


def link_for(admin_browser: TestClient, email: str = ANN) -> str:
    made = admin_browser.post("/api/admin/act-as", json={"email": email})
    assert made.status_code == 200, made.text
    return str(made.json()["link"])


def opened(sites: object, link: str) -> TestClient:
    address, path = link.split("/api/", 1)
    base = address.split("/t/")[0]
    browser = TestClient(sites, base_url=base, follow_redirects=False)  # type: ignore[arg-type]
    answer = browser.get(link)
    assert answer.status_code == 303 and answer.headers["location"].endswith("/#/"), answer.text
    return browser


def test_the_administrator_acts_as_a_host_with_all_their_abilities(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path)
    boss = administrator(sites, tmp_path)
    with caplog.at_level(logging.INFO):
        link = link_for(boss)
    assert link.startswith("http://a.localhost:8000/api/host/act-as/")
    with caplog.at_level(logging.INFO):
        browser = opened(sites, link)
    started = next(r for r in caplog.records if r.message == "Admin acting as host started")
    assert started.__dict__["email"] == ANN
    session = browser.get("/api/host/session").json()
    assert session["email"] == ANN and session["acting_as_admin"] is True
    # Everything the host can do: Settings, the LLM, a PDF, their disk space.
    assert browser.patch("/api/settings", json={"general_prompts": True}).status_code == 200
    assert browser.get("/api/llm").status_code == 200
    added = browser.post("/api/content", files={"file": ("a.pdf", b"%PDF-1.4 x")})
    assert added.status_code == 200, added.text
    assert browser.get("/api/host/disk").status_code == 200
    with caplog.at_level(logging.INFO):
        browser.get("/api/host/me")
    handled = [r for r in caplog.records if r.message == "Request handled"]
    assert handled[-1].__dict__["acting_as"] == ANN
    # Only on site a: the main address keeps its own settings, and the cookie is site a's.
    assert boss.get("/api/settings").json()["general_prompts"] is False
    elsewhere = TestClient(sites, base_url="http://localhost:8000")
    elsewhere.cookies.set("imageskin_host", browser.cookies.get("imageskin_host") or "")
    assert elsewhere.get("/api/host/me").status_code == 401
    # The host's own sign-in is untouched.
    ann = TestClient(sites, base_url="http://a.localhost:8000")
    assert ann.post("/api/host/sign-in", json={"email": ANN, "password": PASSWORD}).is_success
    assert "acting_as_admin" not in ann.get("/api/host/session").json()
    assert service.host_accounts.site_of(ANN) == "a"


def test_the_link_works_once_for_a_minute_and_only_on_the_hosts_site(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path)
    assert service.acting is not None
    service.acting.clock = clock = Clock()
    boss = administrator(sites, tmp_path)
    link = link_for(boss)
    path = "/api/" + link.split("/api/", 1)[1]
    # Opened on another site, it changes nothing and still works on its own.
    other = TestClient(sites, base_url="http://localhost:8000", follow_redirects=False)
    with caplog.at_level(logging.WARNING):
        refused = other.get(path)
    assert refused.headers["location"] == "/#/host/act-as-failed"
    assert other.get("/api/host/session").json()["signed_in"] is False
    assert "Admin acting link refused" in caplog.messages
    opened(sites, link)
    again = TestClient(sites, base_url="http://a.localhost:8000", follow_redirects=False)
    assert again.get(path).headers["location"] == "/#/host/act-as-failed"  # used
    late = link_for(boss)
    clock.now += LINK_S + 1
    stale = TestClient(sites, base_url="http://a.localhost:8000", follow_redirects=False)
    assert stale.get(late).headers["location"].endswith("act-as-failed")


def test_only_the_administrator_at_the_main_address_makes_a_link(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path)
    boss = administrator(sites, tmp_path)
    assert boss.post("/api/admin/act-as", json={"email": "no@example.com"}).status_code == 404
    host = TestClient(sites, base_url="http://localhost:8000")
    assert host.post("/api/host/sign-in", json={"email": BOB, "password": PASSWORD}).is_success
    assert host.post("/api/admin/act-as", json={"email": ANN}).status_code == 401
    # On a customer's site there are no admin routes (R44), even with the admin's cookie.
    on_a = TestClient(sites, base_url="http://a.localhost:8000")
    on_a.cookies.set("imageskin_admin", boss.cookies.get("imageskin_admin") or "")
    assert on_a.post("/api/admin/act-as", json={"email": ANN}).status_code == 404


def test_acting_ends_with_stop_sign_out_or_acting_as_another_host(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path)
    boss = administrator(sites, tmp_path)
    browser = opened(sites, link_for(boss))
    assert browser.post("/api/host/act-as/activity").status_code == 204
    with caplog.at_level(logging.INFO):
        stopped = browser.post("/api/host/act-as/stop")
    assert stopped.json() == {"stopped": True}
    assert browser.get("/api/host/me").status_code == 401
    why = next(r for r in caplog.records if r.message == "Admin acting as host stopped")
    assert why.__dict__["why"] == "stopped"
    assert browser.post("/api/host/act-as/activity").status_code == 401

    # Acting as another host (the main address's own) ends the first.
    first = opened(sites, link_for(boss))
    token = first.cookies.get("imageskin_host") or ""
    second = opened(sites, link_for(boss, BOB))
    assert second.get("/api/host/me").json()["email"] == BOB
    assert first.get("/api/host/me").status_code == 401

    # The administrator signing out ends it.
    caplog.clear()
    boss.post("/api/admin/sign-out")
    with caplog.at_level(logging.INFO):
        assert second.get("/api/host/me").status_code == 401
    why = next(r for r in caplog.records if r.message == "Admin acting as host stopped")
    assert why.__dict__["why"] == "administrator signed out"
    assert service.host_accounts.host(token) is None


def test_a_link_from_an_administrator_signed_out_since_is_refused(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path)
    boss = administrator(sites, tmp_path)
    link = link_for(boss)
    boss.post("/api/admin/sign-out")
    browser = TestClient(sites, base_url="http://a.localhost:8000", follow_redirects=False)
    assert browser.get(link).headers["location"].endswith("act-as-failed")


def test_a_trial_sites_host_is_acted_as_at_its_path(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    service.host_accounts.sign_up("cy@example.com", PASSWORD, "test")
    code, _ = service.sites.add_trial("cy@example.com")
    boss = administrator(sites, tmp_path)
    link = link_for(boss, "cy@example.com")
    assert link.startswith(f"http://localhost:8000/t/{code}/api/host/act-as/")
    browser = TestClient(sites, base_url="http://localhost:8000", follow_redirects=False)
    answer = browser.get(link)
    assert answer.headers["location"] == f"/t/{code}/#/"
    assert f"imageskin_host_{code}=" in answer.headers["set-cookie"]
    assert browser.get(f"/t/{code}/api/host/me").json()["email"] == "cy@example.com"


def test_where_each_site_is_from_the_main_address() -> None:
    class Asked:
        def __init__(self, host: str, proto: str = "") -> None:
            self.headers = {"host": host, "x-forwarded-proto": proto}
            self.url = type("U", (), {"scheme": "http"})()

    def where(site: str, host: str = "app.me0.ai", proto: str = "https") -> str:
        return site_address(Asked(host, proto), site, lambda s: s == "k7q2")  # type: ignore[arg-type]

    assert where(DEFAULT_SITE) == "https://app.me0.ai"
    assert where("k7q2") == "https://app.me0.ai/t/k7q2"
    assert where("anna") == "https://anna.me0.ai"
    assert where("anna", "localhost:8000", "") == "http://anna.localhost:8000"


def test_an_unknown_acting_token_is_no_one() -> None:
    signs = admin.AdminSignIns(Path("/nonexistent/admin.toml"))
    acts = ActingAsHost(signs)
    assert acts.email_of("act-nothing") is None
    assert acts.stop("act-nothing") is False
    assert acts.activity("act-nothing") is False
    assert acting.key("x") != acting.key("y")


def test_acting_ends_when_the_administrator_is_signed_out_for_inactivity(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path)
    service.admin_sign_ins.clock = clock = Clock()
    boss = administrator(sites, tmp_path)
    browser = opened(sites, link_for(boss))
    clock.now += 20 * 60
    assert browser.post("/api/host/act-as/activity").status_code == 204  # a click counts
    clock.now += 20 * 60
    assert browser.get("/api/host/me").status_code == 200  # 20 minutes since the click
    clock.now += 31 * 60
    assert browser.get("/api/host/me").status_code == 401
