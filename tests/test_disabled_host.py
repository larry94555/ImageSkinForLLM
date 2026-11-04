"""A host the administrator disabled (roadmap R44c): their site is read-only for them, and only
the administrator acting as them changes it."""

import logging
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_acting_as_host import administrator, link_for, opened
from test_site_addresses import PASSWORD, served

from imageskin import admin
from imageskin.hosts import CHANGES, DISABLED_WORDS, STILL_OPEN

pytestmark = pytest.mark.real_hosts

ANN, BOB = "ann@example.com", "bob@example.com"  # site a's host, and the main address's
SITE_A = "http://a.localhost:8000"


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


def disable(boss: TestClient, email: str = ANN, disabled: bool = True) -> dict[str, object]:
    answer = boss.put("/api/admin/hosts/properties", json={"email": email, "disabled": disabled})
    assert answer.status_code == 200, answer.text
    return dict(answer.json())


def test_a_disabled_host_reads_but_changes_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path)
    ann = signed_in(sites, SITE_A, ANN)
    boss = administrator(sites, tmp_path)
    with caplog.at_level(logging.INFO):
        properties = disable(boss)
    assert properties["disabled"] is True and properties["custom_image"] is None
    assert "Host disabled" in caplog.messages
    assert service.host_accounts.is_disabled(ANN)
    assert boss.get("/api/admin/hosts/properties", params={"email": ANN}).json()["disabled"]
    # The admin view's list says so beside the email (R44d).
    assert boss.get("/api/admin/hosts").json() == {"hosts": [ANN, BOB], "disabled": [ANN]}

    # Still signed in, and reading as before.
    assert ann.get("/api/host/session").json()["disabled"] is True
    assert ann.get("/api/host/me").json()["disabled"] is True
    assert ann.get("/api/settings").status_code == 200
    assert ann.get("/api/llm").status_code == 200
    # Every change refused, and logged with why.
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        refused = ann.patch("/api/settings", json={"general_prompts": True})
    assert refused.status_code == 403 and refused.json()["detail"] == DISABLED_WORDS
    record = next(r for r in caplog.records if r.message == "Host change refused")
    assert record.__dict__["why"] == "disabled"
    assert (record.__dict__["method"], record.__dict__["path"]) == ("PATCH", "/api/settings")
    added = ann.post("/api/content", files={"file": ("a.pdf", b"%PDF-1.4 x")})
    assert added.status_code == 403
    assert ann.put("/api/llm", json={"provider": "local"}).json()["detail"] == DISABLED_WORDS
    assert ann.post("/api/host/email", json={"new_email": "x@example.com"}).status_code == 403
    photo = ann.post("/api/uploads/photos", files={"file": ("me.jpg", b"\xff\xd8x")})
    assert photo.status_code == 403 and photo.json()["detail"] == DISABLED_WORDS
    assert ann.delete("/api/data").json()["detail"] == DISABLED_WORDS
    # Visitors still use the site: the chat's level of detail is anyone's.
    visitor = TestClient(sites, base_url=SITE_A)
    assert visitor.patch("/api/settings", json={"detail": 2}).json()["detail"] == 2
    assert ann.patch("/api/settings", json={"detail": 3}).json()["detail"] == 3
    assert ann.get("/api/settings").json()["general_prompts"] is False

    # Signing out and in again stays open.
    assert ann.post("/api/host/sign-out").is_success
    answer = TestClient(sites, base_url=SITE_A).post(
        "/api/host/sign-in", json={"email": ANN, "password": PASSWORD}
    )
    assert answer.json()["disabled"] is True  # the pages are read-only at once (R44d)
    again = signed_in(sites, SITE_A, ANN)
    assert again.patch("/api/settings", json={"teach_me": True}).status_code == 403

    # Enabled again, the host changes their site as before.
    with caplog.at_level(logging.INFO):
        assert disable(boss, disabled=False)["disabled"] is False
    assert "Host enabled" in caplog.messages
    assert "disabled" not in again.get("/api/host/session").json()
    assert again.patch("/api/settings", json={"teach_me": True}).json()["teach_me"] is True


def test_the_administrator_acting_as_a_disabled_host_changes_the_site(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path)
    boss = administrator(sites, tmp_path)
    disable(boss)
    acting = opened(sites, link_for(boss))
    session = acting.get("/api/host/session").json()
    assert session["acting_as_admin"] is True and session["disabled"] is True
    changed = acting.patch("/api/settings", json={"general_prompts": True})
    assert changed.status_code == 200 and changed.json()["general_prompts"] is True
    added = acting.post("/api/content", files={"file": ("a.pdf", b"%PDF-1.4 x")})
    assert added.status_code == 200, added.text
    # The host, signed in themselves, sees the change but can't make one.
    ann = signed_in(sites, SITE_A, ANN)
    assert ann.get("/api/settings").json()["general_prompts"] is True
    assert ann.patch("/api/settings", json={"general_prompts": False}).status_code == 403


def test_disabling_one_host_leaves_the_others_and_the_administrator(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path)
    boss = administrator(sites, tmp_path)
    disable(boss, BOB)  # the main address's host, who is also signed in as the administrator
    assert boss.patch("/api/settings", json={"teach_me": True}).status_code == 403
    # The administrator's own calls stay open, so they can enable him again.
    assert boss.put("/api/admin/hosts/properties", json={"email": ANN}).status_code == 200
    ann = signed_in(sites, SITE_A, ANN)
    assert ann.patch("/api/settings", json={"teach_me": True}).status_code == 200
    disable(boss, BOB, disabled=False)
    assert boss.patch("/api/settings", json={"teach_me": True}).status_code == 200
    missing = boss.put("/api/admin/hosts/properties", json={"email": "no@example.com"})
    assert missing.status_code == 404


def changing_routes(app: FastAPI) -> list[tuple[str, str]]:
    """Every POST, PUT, PATCH and DELETE of the site's app, from its OpenAPI, which lists the
    included routers' routes with their prefixes (no route leaves itself out of it)."""
    found = []
    for path, operations in app.openapi()["paths"].items():
        for method in sorted(m.upper() for m in operations if m.upper() in CHANGES):
            found.append((method, re.sub(r"\{[^}]+\}", "x", path)))
    return found


# The changing routes a disabled host isn't refused, each named, as visitors use them too. Any
# other route must refuse a disabled host, so a new one is either guarded or added here on
# purpose (Codex's review of PR #287: a 422 for a missing body proves nothing).
VISITORS = {
    "POST /api/host/sign-up",  # signing up for an account of one's own
    "POST /api/host/restart",  # a deleted site's host, signed in nowhere, starting it (R69c)
    "POST /api/host/page",  # the log's note that a page opened
    "POST /api/chat",
    "POST /api/chat/ahead",
    "POST /api/chat/repeat",
    "POST /api/chat/clips/x/stop",
    "POST /api/chat/video",
    # The chat's level of detail is anyone's; every other field is refused, as
    # test_a_disabled_host_reads_but_changes_nothing checks with real changes.
    "PATCH /api/settings",
}


def test_every_changing_route_that_needs_the_host_is_refused(tmp_path: Path) -> None:
    """Each POST, PUT, PATCH and DELETE refuses a disabled host with 403 and the disabled
    message, before reading its body, unless it is in STILL_OPEN or VISITORS."""
    sites, made, service = served(tmp_path)
    ann = signed_in(sites, SITE_A, ANN)
    service.host_accounts.set_disabled(ANN, True)
    routes = changing_routes(made["a"])
    assert len(routes) > 40  # the site's whole API, not a few routes
    not_refused, still_open = set(), []
    for method, path in routes:
        if any(path.startswith(p) for p in STILL_OPEN):
            still_open.append(path)
            continue
        answer = ann.request(method, path)
        if not (answer.status_code == 403 and answer.json()["detail"] == DISABLED_WORDS):
            not_refused.add(f"{method} {path}")
    assert not_refused == VISITORS
    assert "/api/host/sign-in" in still_open and "/api/admin/hosts/properties" in still_open


def test_a_trial_sites_path_is_read_without_its_code() -> None:
    from fastapi import HTTPException

    from imageskin.hosts import Host, refuse_if_disabled

    host = Host(ANN, 0.0, "k7q2", disabled=True)
    refuse_if_disabled("POST", "/t/k7q2/api/host/sign-out", host)  # still open
    refuse_if_disabled("GET", "/t/k7q2/api/settings", host)  # reading
    refuse_if_disabled("PATCH", "/api/settings", Host(ANN, 0.0, acting=True, disabled=True))
    with pytest.raises(HTTPException) as refused:
        refuse_if_disabled("DELETE", "/t/k7q2/api/content/x", host)
    assert refused.value.status_code == 403
