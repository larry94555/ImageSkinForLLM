"""A site's settings are its own host's alone, and the administrator stays at the main address
(roadmap R44)."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_site_addresses import PASSWORD, served

from imageskin import admin
from imageskin.chatgpt_plan import ChatGptPlanClient
from imageskin.hosts import DEFAULT_SITE
from imageskin.llm_choice import ModelLists
from imageskin.sites import site_home

pytestmark = pytest.mark.real_hosts

ANN, BOB = "ann@example.com", "bob@example.com"  # site a's host, and the main address's


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def signed_in(sites: object, address: str, email: str) -> TestClient:
    browser = TestClient(sites, base_url=address)  # type: ignore[arg-type]
    answer = browser.post("/api/host/sign-in", json={"email": email, "password": PASSWORD})
    assert answer.is_success, answer.text
    return browser


def test_a_sites_settings_open_only_for_its_own_host(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path)
    ann = signed_in(sites, "http://a.localhost:8000", ANN)
    visitor = TestClient(sites, base_url="http://a.localhost:8000")
    # Bob, signed in at the main address, sends his cookie to site a by hand.
    bob = signed_in(sites, "http://localhost:8000", BOB)
    cookie = bob.cookies.get("imageskin_host")
    assert cookie
    stranger = TestClient(sites, base_url="http://a.localhost:8000")
    stranger.cookies.set("imageskin_host", cookie)
    for browser in (visitor, stranger):
        assert browser.get("/api/llm").status_code == 404
        assert browser.patch("/api/settings", json={"teach_me": True}).status_code == 404
        assert browser.post("/api/content/pdfs", files={"file": ("a.pdf", b"%PDF-1")}).is_error
        assert browser.get("/api/host/me").status_code == 401
    assert ann.get("/api/llm").status_code == 200
    assert ann.patch("/api/settings", json={"teach_me": True}).json()["teach_me"] is True


def test_a_change_on_one_site_leaves_another_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The key is taken as it is, without asking OpenRouter.
    monkeypatch.setattr(ModelLists, "models", lambda self, provider, key: ["a/model"])
    sites, _, _ = served(tmp_path)
    ann = signed_in(sites, "http://a.localhost:8000", ANN)
    bob = signed_in(sites, "http://localhost:8000", BOB)
    changed = ann.patch("/api/settings", json={"general_prompts": True})
    assert changed.json()["general_prompts"] is True
    picked = ann.put("/api/llm", json={"provider": "openrouter", "api_key": "sk-or-test"})
    assert picked.status_code == 200 and picked.json()["provider"] == "openrouter"
    assert bob.get("/api/settings").json()["general_prompts"] is False
    assert bob.get("/api/llm").json()["provider"] != "openrouter"
    assert ann.get("/api/settings").json()["general_prompts"] is True


def test_the_administrator_is_not_found_on_a_customers_site(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, _ = served(tmp_path)
    (tmp_path / "home" / "admin.toml").write_text('password = "secret"\n')
    # At the main address, Bob signs in as the administrator as before.
    bob = signed_in(sites, "http://localhost:8000", BOB)
    assert bob.post("/api/admin/sign-in", json={"password": "secret"}).is_success
    assert bob.get("/api/admin/session").json()["here"] is True
    assert bob.get("/api/admin/settings").status_code == 200
    admin_cookie = bob.cookies.get("imageskin_admin")
    assert admin_cookie

    ann = signed_in(sites, "http://a.localhost:8000", ANN)
    assert ann.get("/api/admin/session").json() == {
        "signed_in": False,
        "password_set": False,
        "timeout_minutes": 30,
        "ended": None,
        "here": False,
    }
    with caplog.at_level(logging.INFO):
        refused = ann.post("/api/admin/sign-in", json={"password": "secret"})
    assert refused.status_code == 404
    assert "Admin route refused on a customer's site" in caplog.messages
    assert ann.get("/api/admin/challenge").status_code == 404
    assert ann.post("/api/admin/laptop", json={}).status_code == 404
    # The administrator's sign-in, from the main address, counts as none here.
    ann.cookies.set("imageskin_admin", admin_cookie)
    assert ann.get("/api/admin/session").json()["signed_in"] is False
    for path in ("/api/admin/settings", "/api/admin/hosts", "/api/admin/resources"):
        assert ann.get(path).status_code == 404, path
    disk = ann.get("/api/host/disk", params={"email": BOB})
    assert disk.status_code == 403  # a host, not the administrator, asking for another's


def test_the_chatgpt_plan_is_not_offered_on_a_customers_site(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, _ = served(tmp_path)
    ann = signed_in(sites, "http://a.localhost:8000", ANN)
    providers = [p["id"] for p in ann.get("/api/llm").json()["providers"]]
    assert "chatgpt" not in providers and "openrouter" in providers
    with caplog.at_level(logging.INFO):
        assert ann.get("/api/chatgpt").status_code == 404
    assert "ChatGPT plan refused on a customer's site" in caplog.messages
    assert ann.get("/api/chatgpt/sign-in", follow_redirects=False).status_code == 404
    assert ann.put("/api/llm", json={"provider": "chatgpt"}).status_code == 404
    assert ann.post("/api/llm/models", json={"provider": "chatgpt"}).status_code == 404
    # At the main address, it is offered as before.
    bob = signed_in(sites, "http://localhost:8000", BOB)
    assert "chatgpt" in [p["id"] for p in bob.get("/api/llm").json()["providers"]]
    assert bob.get("/api/chatgpt").status_code == 200


def test_a_chatgpt_plan_chosen_before_is_turned_off_on_a_customers_site(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Codex's review of PR #284: a site that chose the plan before R44 doesn't keep using it."""
    home = tmp_path / "home"
    for site in ("a", None):
        folder = site_home(site, home) if site else home
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "llm.json").write_text(
            json.dumps({"provider": "chatgpt", "keys": {"openrouter": "sk-or"}, "models": {}})
        )
    sites, made, _ = served(tmp_path)
    ann = signed_in(sites, "http://a.localhost:8000", ANN)
    with caplog.at_level(logging.WARNING):
        assert ann.get("/api/llm").json()["provider"] == "local"
    assert "ChatGPT plan turned off on a customer's site" in caplog.messages
    assert made["a"].state.llm.settings.provider == "local"
    assert not isinstance(made["a"].state.llm._client, ChatGptPlanClient)
    assert json.loads((site_home("a", home) / "llm.json").read_text())["keys"] == {
        "openrouter": "sk-or"
    }
    # The main address keeps its choice.
    bob = signed_in(sites, "http://localhost:8000", BOB)
    assert bob.get("/api/llm").json()["provider"] == "chatgpt"
    assert isinstance(made[DEFAULT_SITE].state.llm._client, ChatGptPlanClient)
