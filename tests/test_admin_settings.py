"""The admin settings (roadmap R155)."""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from imageskin import admin_settings
from imageskin.admin_settings import (
    DEFAULTS,
    FILE_ONLY,
    FILENAME,
    ORDER,
    AdminSettings,
    AdminSettingsStore,
    checked,
)
from imageskin.app import create_app
from imageskin.delete_data import delete_my_data
from imageskin.resources import Thresholds, colour

# The real defaults, with hosts' own photo and voice turned off (R239).
pytestmark = pytest.mark.custom_defaults


def test_the_recommended_settings() -> None:
    assert DEFAULTS == AdminSettings(30, Thresholds(blue_above=60, orange_below=30, red_below=15))


def test_a_change_is_saved_and_read_after_a_restart(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = AdminSettingsStore(tmp_path)
    with caplog.at_level(logging.INFO):
        saved = store.change({"timeout_minutes": 10, "thresholds": {"blue_above": 70}})
    assert saved == AdminSettings(10, Thresholds(blue_above=70, orange_below=30, red_below=15))
    assert store.current == saved
    assert AdminSettingsStore(tmp_path).current == saved  # from the file
    changed = [r for r in caplog.records if r.message == "Admin settings changed"]
    assert changed[0].__dict__["before"]["timeout_minutes"] == 30
    assert changed[0].__dict__["after"]["timeout_minutes"] == 10


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"timeout_minutes": 4}, "a whole number from 5 to 240"),
        ({"timeout_minutes": 241}, "a whole number from 5 to 240"),
        ({"timeout_minutes": 30.5}, "a whole number from 5 to 240"),
        ({"timeout_minutes": True}, "a whole number from 5 to 240"),
        ({"thresholds": {"red_below": 40}}, "must go in order"),  # above orange's 30
        ({"thresholds": {"orange_below": 60}}, "must go in order"),  # equal to blue's
        ({"thresholds": {"red_below": 0}}, "must go in order"),
        ({"thresholds": {"blue_above": 100}}, "must go in order"),
        ({"thresholds": {"blue_above": "60"}}, "must go in order"),
        ({"thresholds": {"blue_above": False}}, "must go in order"),
        ({"thresholds": {"purple_above": 5}}, "must go in order"),
        ({"thresholds": [1, 2, 3]}, "must go in order"),
        ({"colours": 1}, "no admin setting called colours"),
    ],
)
def test_a_wrong_setting_is_refused_and_nothing_saved(
    tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    store = AdminSettingsStore(tmp_path)
    with pytest.raises(ValueError, match=message):
        store.change(changes)
    assert store.current == DEFAULTS
    assert not (tmp_path / FILENAME).exists()


def test_thresholds_can_be_decimals() -> None:
    thresholds = {"blue_above": 62.5, "orange_below": 25.5, "red_below": 10}
    assert checked(DEFAULTS, {"thresholds": thresholds}).thresholds == Thresholds(**thresholds)
    assert ORDER.startswith("The thresholds must go in order")


@pytest.mark.parametrize("text", ["{not json", "[]", '{"timeout_minutes": 1}'])
def test_a_file_that_cant_be_used_gives_the_recommended_settings(
    tmp_path: Path, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / FILENAME).write_text(text)
    assert AdminSettingsStore(tmp_path).current == DEFAULTS
    assert "Admin settings are not valid" in caplog.text


def signed_in(home: Path) -> TestClient:
    (home / "admin.toml").write_text('password = "secret"\n')
    browser = TestClient(create_app(home))
    browser.post("/api/admin/sign-in", json={"password": "secret"})
    return browser


def test_the_api_reads_and_changes_them_for_the_administrator_only(tmp_path: Path) -> None:
    browser = signed_in(tmp_path)
    read = browser.get("/api/admin/settings").json()
    recommended = read.pop("recommended")
    assert read == recommended == DEFAULTS.as_dict()
    changed = browser.put(
        "/api/admin/settings",
        json={"thresholds": {"blue_above": 80, "orange_below": 40, "red_below": 20}},
    )
    assert changed.status_code == 200
    assert changed.json()["thresholds"] == {"blue_above": 80, "orange_below": 40, "red_below": 20}
    assert changed.json()["recommended"]["thresholds"]["blue_above"] == 60
    refused = browser.put("/api/admin/settings", json={"thresholds": {"red_below": 50}})
    assert refused.status_code == 400 and refused.json()["detail"] == ORDER
    assert json.loads((tmp_path / FILENAME).read_text())["thresholds"]["blue_above"] == 80

    stranger = TestClient(create_app(tmp_path))
    assert stranger.get("/api/admin/settings").status_code == 401
    assert stranger.put("/api/admin/settings", json={"timeout_minutes": 5}).status_code == 401


def test_the_dashboard_uses_the_thresholds_at_once(tmp_path: Path) -> None:
    browser = signed_in(tmp_path)
    browser.put(
        "/api/admin/settings",
        json={"thresholds": {"blue_above": 99, "orange_below": 98, "red_below": 97}},
    )
    reading = browser.get("/api/admin/resources").json()
    assert reading["thresholds"] == {"blue_above": 99, "orange_below": 98, "red_below": 97}
    thresholds = Thresholds(**reading["thresholds"])
    for resource in reading["resources"]:
        assert resource["colour"] == colour(resource["percent_remaining"], thresholds)


def test_the_sign_out_uses_the_minutes_at_once(tmp_path: Path) -> None:
    browser = signed_in(tmp_path)
    browser.put("/api/admin/settings", json={"timeout_minutes": 5})
    assert browser.get("/api/admin/session").json()["timeout_minutes"] == 5


def test_delete_my_data_leaves_them(tmp_path: Path) -> None:
    # They are the site's, not a person's.
    store = AdminSettingsStore(tmp_path)
    store.change({"timeout_minutes": 10})
    delete_my_data(tmp_path)
    assert AdminSettingsStore(tmp_path).current.timeout_minutes == 10


# The test email (R264, Milestone 31): set only in the file, read again when it changes.


def write_settings(home: Path, data: dict[str, Any]) -> None:
    """The file changed by hand, with a new modification time even on a fast clock."""
    path = home / FILENAME
    path.write_text(json.dumps(data))
    stamp = path.stat().st_mtime_ns + 1_000_000
    os.utime(path, ns=(stamp, stamp))


def test_there_is_no_test_email_to_begin_with(tmp_path: Path) -> None:
    assert DEFAULTS.test_email == ""
    assert AdminSettingsStore(tmp_path).current.test_email == ""


def test_the_test_email_is_read_from_the_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_settings(tmp_path, {"test_email": " me@example.com ", "timeout_minutes": 10})
    with caplog.at_level(logging.INFO):
        settings = AdminSettingsStore(tmp_path).current
    assert settings.test_email == "me@example.com"
    assert settings.timeout_minutes == 10
    read = [r for r in caplog.records if r.message == "Admin test email read"]
    assert read[0].__dict__["test_email_set"] is True
    assert read[0].__dict__["again"] is False


@pytest.mark.parametrize("value", ["not-an-email", "a@b", 5, ["me@example.com"], "a b@c.d"])
def test_a_test_email_that_isnt_one_is_never_used(
    tmp_path: Path, value: object, caplog: pytest.LogCaptureFixture
) -> None:
    write_settings(tmp_path, {"test_email": value, "timeout_minutes": 10})
    settings = AdminSettingsStore(tmp_path).current
    assert settings.test_email == ""
    assert settings.timeout_minutes == 10  # the rest of the file is still used
    assert "Admin test email ignored" in caplog.text


@pytest.mark.parametrize("value", ["", None])
def test_an_empty_test_email_is_not_set(tmp_path: Path, value: object) -> None:
    write_settings(tmp_path, {"test_email": value})
    assert AdminSettingsStore(tmp_path).current.test_email == ""


def test_a_test_email_added_by_hand_works_with_no_restart(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = AdminSettingsStore(tmp_path)
    store.change({"timeout_minutes": 10})
    assert store.current.test_email == ""
    data = json.loads((tmp_path / FILENAME).read_text())
    write_settings(tmp_path, {**data, "test_email": "me@example.com"})
    with caplog.at_level(logging.INFO):
        assert store.current.test_email == "me@example.com"
    assert store.current.timeout_minutes == 10
    again = [r for r in caplog.records if r.message == "Admin test email read"]
    assert len(again) == 1 and again[0].__dict__["again"] is True  # read once, not each time
    write_settings(tmp_path, {**data, "test_email": ""})
    assert store.current.test_email == ""


def test_a_change_on_the_page_keeps_the_test_email(tmp_path: Path) -> None:
    write_settings(tmp_path, {"test_email": "me@example.com"})
    store = AdminSettingsStore(tmp_path)
    store.change({"timeout_minutes": 10})
    assert store.current.test_email == "me@example.com"
    assert json.loads((tmp_path / FILENAME).read_text())["test_email"] == "me@example.com"
    assert AdminSettingsStore(tmp_path).current.test_email == "me@example.com"


def test_a_change_keeps_a_test_email_just_added_by_hand(tmp_path: Path) -> None:
    store = AdminSettingsStore(tmp_path)
    store.change({"timeout_minutes": 10})
    data = json.loads((tmp_path / FILENAME).read_text())
    write_settings(tmp_path, {**data, "test_email": "me@example.com"})
    store.change({"timeout_minutes": 20})  # without reading the settings first
    assert json.loads((tmp_path / FILENAME).read_text())["test_email"] == "me@example.com"


def test_a_file_half_saved_while_edited_keeps_the_settings_in_use(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_settings(tmp_path, {"test_email": "me@example.com", "timeout_minutes": 10})
    store = AdminSettingsStore(tmp_path)
    assert store.current.test_email == "me@example.com"
    path = tmp_path / FILENAME
    path.write_text('{"test_email": "me@ex')
    stamp = path.stat().st_mtime_ns + 2_000_000
    os.utime(path, ns=(stamp, stamp))
    assert store.current.test_email == "me@example.com"
    assert store.current.timeout_minutes == 10
    assert "Admin settings are not valid; keeping the ones in use" in caplog.text


def test_the_file_removed_gives_the_recommended_settings(tmp_path: Path) -> None:
    write_settings(tmp_path, {"test_email": "me@example.com"})
    store = AdminSettingsStore(tmp_path)
    (tmp_path / FILENAME).unlink()
    assert store.current == DEFAULTS


def test_the_api_shows_the_test_email_but_never_changes_it(tmp_path: Path) -> None:
    write_settings(tmp_path, {"test_email": "me@example.com"})
    browser = signed_in(tmp_path)
    assert browser.get("/api/admin/settings").json()["test_email"] == "me@example.com"
    refused = browser.put("/api/admin/settings", json={"test_email": "other@example.com"})
    assert refused.status_code == 400 and refused.json()["detail"] == FILE_ONLY
    assert "admin-settings.json" in FILE_ONLY
    assert browser.get("/api/admin/settings").json()["test_email"] == "me@example.com"
    stranger = TestClient(create_app(tmp_path))
    assert stranger.get("/api/admin/settings").status_code == 401


def test_two_changes_at_once_both_survive(tmp_path: Path) -> None:
    """A change reads the settings and saves them under one lock (Codex's review of PR #315):
    the second of two overlapping changes starts from the first's result."""
    store = AdminSettingsStore(tmp_path)
    first_checked = threading.Event()
    second_started = threading.Event()
    real_checked = admin_settings.checked

    def slow_checked(settings: AdminSettings, changes: dict[str, Any]) -> AdminSettings:
        if "timeout_minutes" in changes:
            first_checked.set()
            second_started.wait(2)  # the other change is waiting for the lock now
        return real_checked(settings, changes)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(admin_settings, "checked", slow_checked)
        first = threading.Thread(target=store.change, args=({"timeout_minutes": 10},))
        first.start()
        first_checked.wait(2)

        def second_change() -> None:
            second_started.set()
            store.change({"days_before_deleting": 20})

        second = threading.Thread(target=second_change)
        second.start()
        first.join(5)
        second.join(5)
    assert (store.current.timeout_minutes, store.current.days_before_deleting) == (10, 20)
    again = AdminSettingsStore(tmp_path).current
    assert (again.timeout_minutes, again.days_before_deleting) == (10, 20)
