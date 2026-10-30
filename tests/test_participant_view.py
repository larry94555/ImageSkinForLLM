"""The participant view until a host signs in (roadmap R190)."""

import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from imageskin import admin
from imageskin.app import create_app
from imageskin.host_api import NOT_SIGNED_IN

pytestmark = pytest.mark.real_hosts

HOST = {"email": "host@example.com", "password": "a long secret"}

# A call from each host page: setup, the wizard, Start now, Manage Content and wiki editing.
HOST_CALLS: list[tuple[str, str, dict[str, Any]]] = [
    ("post", "/api/consent", {"json": {"agreed": True}}),
    ("put", "/api/wizard", {"json": {"step": "photo"}}),
    ("get", "/api/uploads/photos", {}),
    ("post", "/api/prepare", {}),
    ("put", "/api/accent", {"json": {"accent": "american"}}),
    ("post", "/api/review", {"json": {"accepted": True}}),
    ("post", "/api/start-now", {"json": {}}),
    ("get", "/api/content/readings", {}),
    ("delete", "/api/content/some-pdf", {}),
    ("put", "/api/wiki/some-page", {"json": {"title": "t", "body": "b"}}),
    ("post", "/api/content/some-pdf/wiki/rebuild", {}),
    ("get", "/api/content/some-pdf/wiki/history", {}),
]

# What the participant view reads: the chat's state, the wiki and the PDFs.
OPEN_CALLS = ["/api/consent", "/api/settings", "/api/content", "/api/wiki"]


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    caplog.set_level(logging.INFO)


def test_anyone_not_signed_in_is_refused_the_host_pages_calls(tmp_path: Path) -> None:
    browser = TestClient(create_app(tmp_path))
    for method, path, kwargs in HOST_CALLS:
        answer = getattr(browser, method)(path, **kwargs)
        assert (path, answer.status_code) == (path, 401)
        assert answer.json() == {"detail": NOT_SIGNED_IN}
    for path in OPEN_CALLS:
        assert (path, browser.get(path).status_code) == (path, 200)


def test_a_signed_in_host_gets_past_the_check(tmp_path: Path) -> None:
    browser = TestClient(create_app(tmp_path))
    assert browser.post("/api/host/sign-up", json=HOST).status_code == 200
    for method, path, kwargs in HOST_CALLS:
        answer = getattr(browser, method)(path, **kwargs)
        # Past the host check: whatever the call itself answers, never the sign-in refusal.
        assert answer.status_code != 401 or answer.json() != {"detail": NOT_SIGNED_IN}, path
    browser.post("/api/host/sign-out")
    assert browser.get("/api/uploads/photos").status_code == 401


def test_the_view_follows_who_is_signed_in(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    browser = TestClient(create_app(tmp_path))
    assert browser.get("/api/settings").json()["view"] == "participant"
    browser.post("/api/host/sign-up", json=HOST)
    assert browser.get("/api/settings").json()["view"] == "host"
    # A host can still look at the app as a participant sees it.
    browser.patch("/api/settings", json={"view": "participant"})
    assert browser.get("/api/settings").json()["view"] == "participant"
    browser.patch("/api/settings", json={"view": "host"})
    browser.post("/api/host/sign-out")
    # The saved view is the host's: anyone else still gets the participant view.
    assert browser.get("/api/settings").json()["view"] == "participant"
    lines = [r for r in caplog.records if r.getMessage() == "View chosen"]
    assert [(r.view, r.why) for r in lines] == [  # type: ignore[attr-defined]
        ("participant", "no host signed in"),
        ("host", "host signed in"),
        ("participant", "host signed in"),
        ("participant", "no host signed in"),
    ]
