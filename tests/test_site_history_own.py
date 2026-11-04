"""Each site's own history and progress (roadmap R65): what one site's host and visitors do is
kept in that site's folder, and no page or API call of another site shows it."""

import hashlib
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_chat import FakeLlm2
from test_site_addresses import PASSWORD, served

from imageskin import admin
from imageskin.chat import Conversation
from imageskin.hosts import DEFAULT_SITE
from imageskin.sites import site_home

pytestmark = pytest.mark.real_hosts

ANN, BOB, CY = "ann@example.com", "bob@example.com", "cy@example.com"
PDF = b"%PDF-1.4 a lesson"
# Calls that change with time alone (or reach ChatGPT), not with anything a site does; the test
# also leaves out any call that answers differently when nothing has been done.
MOVING = {"/api/startup", "/api/admin/challenge", "/api/chatgpt/sign-in"}


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def signed_in(sites: object, address: str, email: str, path: str = "") -> TestClient:
    browser = TestClient(sites, base_url=address)  # type: ignore[arg-type]
    answer = browser.post(f"{path}/api/host/sign-in", json={"email": email, "password": PASSWORD})
    assert answer.is_success, answer.text
    return browser


def readings(app: object, browser: TestClient, path: str = "") -> dict[str, object]:
    """Every GET of the site's API that takes no part of its address, as this browser sees it."""
    seen: dict[str, object] = {}
    for route, operations in app.openapi()["paths"].items():  # type: ignore[attr-defined]
        if "get" not in operations or "{" in route or route in MOVING:
            continue
        answer = browser.get(f"{path}{route}", follow_redirects=False)
        try:
            body: object = answer.json()
        except ValueError:
            body = hashlib.sha256(answer.content).hexdigest()
        seen[route] = (answer.status_code, body)
    return seen


def files(folder: Path, leave_out: Path) -> dict[str, str]:
    """Each file under the folder with a hash of what is in it, but those under `leave_out`."""
    return {
        str(f.relative_to(folder)): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(folder.rglob("*"))
        if f.is_file() and leave_out not in f.parents
    }


def ok(answer: object) -> dict[str, object]:
    assert answer.is_success, answer.text  # type: ignore[attr-defined]
    return dict(answer.json())  # type: ignore[attr-defined]


def changes_on(browser: TestClient, path: str = "") -> None:
    """What a site's host does, each checked to have happened (Codex's review of PR #289):
    consent, the settings, a PDF, the customization's identity and goals, the setup wizard's step,
    and Clear conversation."""
    ok(browser.post(f"{path}/api/consent", json={"agreed": True}))
    ok(browser.patch(f"{path}/api/settings", json={"general_prompts": True, "detail": 5}))
    ok(browser.post(f"{path}/api/content", files={"file": ("mars.pdf", io.BytesIO(PDF))}))
    ok(browser.put(f"{path}/api/customization/identity", json={"name": "Ada"}))
    ok(browser.put(f"{path}/api/customization/goals", json={"goals": ["Love the night sky."]}))
    ok(browser.put(f"{path}/api/wizard", json={"step": "photo"}))
    assert browser.delete(f"{path}/api/chat").is_success
    # Read back on the site itself.
    assert browser.get(f"{path}/api/settings").json()["general_prompts"] is True
    customization = ok(browser.get(f"{path}/api/customization"))
    assert customization["identity"]["name"] == "Ada"  # type: ignore[index]
    assert customization["goals"] == ["Love the night sky."]
    assert ok(browser.get(f"{path}/api/wizard"))["step"] == "photo"


def a_conversation(folder: Path) -> None:
    """A saved conversation of one exchange, as the chat keeps it."""
    folder.mkdir(parents=True, exist_ok=True)
    Conversation(FakeLlm2(), lambda: 4096, saved=folder / "conversation.json").send("Hello")


def test_nothing_one_site_does_shows_on_another(tmp_path: Path) -> None:
    sites, made, service = served(tmp_path, sign_up_makes_site=True)
    service.host_accounts.sign_up(CY, PASSWORD, "test")
    code, _ = service.sites.add_trial(CY)
    home = tmp_path / "home"
    # Each site has a conversation before: Clear conversation on site a clears its own only.
    a_conversation(home)
    a_conversation(site_home("a", home))
    bob = signed_in(sites, "http://localhost:8000", BOB)
    visitor = TestClient(sites, base_url="http://localhost:8000")
    cy = signed_in(sites, "http://localhost:8000", CY, f"/t/{code}")
    main_app = made[DEFAULT_SITE]  # each site's app is made at its first call
    browsers = {"bob": bob, "visitor": visitor}
    before = {who: readings(main_app, b) for who, b in browsers.items()}
    again = {who: readings(main_app, b) for who, b in browsers.items()}
    steady = {who: {r for r in before[who] if before[who][r] == again[who][r]} for who in before}
    assert len(steady["bob"]) > 30  # most of the main address's API, as its host sees it
    trial_before = readings(made[code], cy, f"/t/{code}")
    kept = files(home, home / "sites")

    # Ann's site a, a subdomain, is used by its host and a visitor.
    ann = signed_in(sites, "http://a.localhost:8000", ANN)
    changes_on(ann)
    made["a"].state.readings.wait()
    assert [p["name"] for p in ann.get("/api/content").json()] == ["mars.pdf"]
    assert json.loads((site_home("a", home) / "conversation.json").read_text())["turns"] == []
    assert len(json.loads((home / "conversation.json").read_text())["turns"]) == 2  # the main's

    after = {who: readings(main_app, b) for who, b in browsers.items()}
    for who in before:
        moved = [r for r in steady[who] if before[who][r] != after[who][r]]
        assert moved == [], f"{who} sees site a's changes at {moved}"
    assert readings(made[code], cy, f"/t/{code}") == trial_before
    # Nothing written outside site a's folder but Ann's sign-in, kept with every site's hosts.
    # And her PDFs, kept in her own folder beside her sites (R258).
    shared = {"hosts.json"}
    written = files(home, home / "sites")
    assert {f: h for f, h in written.items() if f not in shared and not f.startswith("hosts")} == {
        f: h for f, h in kept.items() if f not in shared
    }
    a_home = site_home("a", home)
    assert json.loads((a_home / "consent.json").read_text())["agreed_at"]
    assert not (site_home(code, home) / "consent.json").exists()
