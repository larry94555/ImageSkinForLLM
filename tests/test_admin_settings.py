"""The admin settings (roadmap R155)."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from imageskin.admin_settings import (
    DEFAULTS,
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
