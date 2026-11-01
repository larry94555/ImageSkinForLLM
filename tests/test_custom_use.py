"""Whether hosts may use a custom image and voice: Admin settings' two checkboxes (roadmap R239)."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from imageskin import admin
from imageskin.admin_settings import (
    DEFAULTS,
    FILENAME,
    AdminSettings,
    AdminSettingsStore,
    Choice,
    CustomUse,
    checked,
    custom_use,
)
from imageskin.app import create_app

pytestmark = pytest.mark.real_hosts  # these tests sign in as a host for themselves

HOST = {"email": "host@example.com", "password": "a long secret"}


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def test_both_are_checked_by_default() -> None:
    assert DEFAULTS.disable_custom_image and DEFAULTS.disable_custom_voice
    assert custom_use(DEFAULTS) == CustomUse(image=False, voice=False)


def test_a_file_from_before_gets_both_checked(tmp_path: Path) -> None:
    (tmp_path / FILENAME).write_text(json.dumps({"timeout_minutes": 10}))
    current = AdminSettingsStore(tmp_path).current
    assert current.timeout_minutes == 10
    assert current.disable_custom_image and current.disable_custom_voice


@pytest.mark.parametrize("value", [1, 0, "true", None, [True]])
def test_a_checkbox_must_be_true_or_false(value: object) -> None:
    with pytest.raises(ValueError, match="disable_custom_voice must be true or false"):
        checked(DEFAULTS, {"disable_custom_voice": value})


def test_a_change_is_saved_and_logged_with_old_and_new(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = AdminSettingsStore(tmp_path)
    with caplog.at_level(logging.INFO):
        store.change({"disable_custom_voice": False})
    assert AdminSettingsStore(tmp_path).current.disable_custom_voice is False
    assert AdminSettingsStore(tmp_path).current.disable_custom_image is True
    record = next(r for r in caplog.records if r.message == "Admin settings changed")
    assert record.__dict__["disable_custom_voice_change"] == [True, False]
    assert record.__dict__["disable_custom_image_change"] == [True, True]


# Every mix of the checkbox and the host's own choice (R242): the choice wins when there is one.
@pytest.mark.parametrize(
    ("disabled", "choice", "allowed"),
    [
        (True, None, False),
        (False, None, True),
        (True, "allow", True),
        (False, "allow", True),
        (True, "deny", False),
        (False, "deny", False),
    ],
)
def test_the_rule_for_one_host(disabled: bool, choice: Choice, allowed: bool) -> None:
    settings = AdminSettings(disable_custom_image=disabled, disable_custom_voice=disabled)
    assert custom_use(settings, image_choice=choice) == CustomUse(image=allowed, voice=not disabled)
    assert custom_use(settings, voice_choice=choice) == CustomUse(image=not disabled, voice=allowed)


def test_host_me_says_what_the_host_may_use_at_once(tmp_path: Path) -> None:
    (tmp_path / "admin.toml").write_text('password = "secret"\n')
    app = create_app(tmp_path)
    host = TestClient(app)
    host.post("/api/host/sign-up", json=HOST)
    me = host.get("/api/host/me").json()
    assert (me["email"], me["custom_image"], me["custom_voice"]) == (HOST["email"], False, False)

    # The admin sign-in is only for a signed-in host or a listed laptop (R191).
    administrator = TestClient(app)
    administrator.post("/api/host/sign-in", json=HOST)
    administrator.post("/api/admin/sign-in", json={"password": "secret"})
    changed = administrator.put("/api/admin/settings", json={"disable_custom_voice": False})
    assert changed.status_code == 200
    assert changed.json()["disable_custom_voice"] is False
    assert changed.json()["recommended"]["disable_custom_voice"] is True
    me = host.get("/api/host/me").json()
    assert (me["custom_image"], me["custom_voice"]) == (False, True)

    refused = administrator.put("/api/admin/settings", json={"disable_custom_image": "no"})
    assert refused.status_code == 400
    assert host.put("/api/admin/settings", json={"disable_custom_image": False}).status_code == 401
    assert not AdminSettingsStore(tmp_path).current.disable_custom_voice
