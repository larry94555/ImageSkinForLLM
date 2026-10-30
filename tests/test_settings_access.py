"""Settings only for a signed-in host or a listed admin laptop (roadmap R191)."""

import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_admin_laptops import Laptop, listing, write

from imageskin import admin
from imageskin.app import create_app
from imageskin.settings_access import PASSES_KEPT, SettingsAccess

pytestmark = pytest.mark.real_hosts

HOST = {"email": "host@example.com", "password": "a long secret"}

# A call from each part of the Settings page.
SETTINGS_CALLS: list[tuple[str, str, dict[str, Any]]] = [
    ("patch", "/api/settings", {"json": {"show_metrics": True}}),
    ("get", "/api/llm", {}),
    ("put", "/api/llm", {"json": {"provider": "local"}}),
    ("post", "/api/llm/models", {"json": {"provider": "openai", "key": "k"}}),
    ("get", "/api/chatgpt", {}),
    ("get", "/api/chatgpt/sign-in", {"follow_redirects": False}),
    ("post", "/api/chatgpt/use", {"json": {"use": False}}),
    ("post", "/api/chatgpt/sign-out", {}),
    ("delete", "/api/chat", {}),
    ("delete", "/api/data", {}),
    ("post", "/api/admin/sign-in", {"json": {"password": "first secret"}}),
]


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    caplog.set_level(logging.INFO)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    write(tmp_path / "admin.toml", 'password = "first secret"\n')
    return tmp_path


def access(browser: TestClient, laptop: Laptop | None = None) -> dict[str, object]:
    body = {}
    if laptop:
        challenge = browser.get("/api/admin/challenge").json()["challenge"]
        body = {"laptop": laptop.body(challenge)}
    answer = browser.post("/api/settings/access", json=body)
    assert answer.status_code == 200
    return dict(answer.json())


def shown_lines(caplog: pytest.LogCaptureFixture) -> list[tuple[str, bool, str | None]]:
    return [
        (r.getMessage(), r.host, r.laptop)  # type: ignore[attr-defined]
        for r in caplog.records
        if r.getMessage() in ("Settings shown", "Settings hidden")
    ]


def test_settings_are_hidden_from_anyone_not_a_host_and_its_calls_not_found(
    home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    browser = TestClient(create_app(home))
    assert access(browser) == {"shown": False, "as": None}
    for method, path, kwargs in SETTINGS_CALLS:
        answer = getattr(browser, method)(path, **kwargs)
        assert (path, answer.status_code, answer.json()) == (path, 404, {"detail": "Not Found"})
    assert "Settings call refused" in caplog.messages
    # Every page follows the settings, and the chat's own bar sets the level of detail.
    assert browser.get("/api/settings").status_code == 200
    assert browser.patch("/api/settings", json={"detail": 2}).status_code == 200
    assert shown_lines(caplog) == [("Settings hidden", False, None)]


def test_a_signed_in_host_sees_settings_and_gets_past_the_check(
    home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    browser = TestClient(create_app(home))
    browser.post("/api/host/sign-up", json=HOST)
    assert access(browser) == {"shown": True, "as": "host"}
    # Not the ChatGPT sign-in, which would go on to ask OpenAI.
    for method, path, kwargs in [c for c in SETTINGS_CALLS if c[1] != "/api/chatgpt/sign-in"]:
        answer = getattr(browser, method)(path, **kwargs)
        assert answer.status_code != 404 or answer.json() != {"detail": "Not Found"}, path
    assert browser.patch("/api/settings", json={"show_metrics": True}).json()["show_metrics"]
    browser.post("/api/host/sign-out")
    assert access(browser)["shown"] is False
    assert shown_lines(caplog) == [
        ("Settings shown", True, None),
        ("Settings hidden", False, None),
    ]


def test_a_listed_laptop_sees_settings_and_the_administrator_signs_in_there(
    home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    listed, other = Laptop(), Laptop()
    write(home / "admin-laptops.toml", listing(listed))
    browser = TestClient(create_app(home))
    stranger = TestClient(browser.app)
    assert access(stranger, other) == {"shown": False, "as": None}
    assert access(browser, listed) == {"shown": True, "as": "laptop"}
    # The pass in its cookie serves the Settings calls, with no proof each time.
    assert access(browser) == {"shown": True, "as": "laptop"}
    assert browser.get("/api/llm").status_code != 404
    challenge = browser.get("/api/admin/challenge").json()["challenge"]
    signed_in = browser.post(
        "/api/admin/sign-in",
        json={"password": "first secret", "laptop": listed.body(challenge)},
    )
    assert signed_in.json() == {"signed_in": True}
    assert shown_lines(caplog) == [
        ("Settings hidden", False, None),
        ("Settings shown", False, listed.id),
        ("Settings shown", False, listed.id),
    ]

    # Taken out of the file, the laptop's pass no longer works.
    write(home / "admin-laptops.toml", listing(other))
    assert access(browser) == {"shown": False, "as": None}
    assert browser.get("/api/llm").status_code == 404


def test_with_no_laptops_file_no_laptop_is_listed(home: Path) -> None:
    browser = TestClient(create_app(home))
    assert access(browser, Laptop()) == {"shown": False, "as": None}
    assert browser.post("/api/admin/sign-in", json={"password": "first secret"}).status_code == 404


def test_the_passes_kept_are_limited(home: Path) -> None:
    from imageskin.admin_laptops import AdminLaptops
    from imageskin.hosts import HostAccounts

    laptop = Laptop()
    write(home / "admin-laptops.toml", listing(laptop))
    kept = SettingsAccess(HostAccounts(home), AdminLaptops(home / "admin-laptops.toml"))
    first = kept.give_pass(laptop.id)
    for _ in range(PASSES_KEPT):
        last = kept.give_pass(laptop.id)
    assert kept.laptop(first) is None
    assert kept.laptop(last) == laptop.id
    assert kept.who(None, last) == "laptop"
    assert kept.who(None, "made up") is None
