import json
import logging
import threading
import time
from dataclasses import fields
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from imageskin import ui_settings
from imageskin.app import create_app
from imageskin.ui_settings import (
    CHOICES,
    FILENAME,
    UiSettings,
    checked,
    load_ui_settings,
    save_ui_settings,
)


def test_metrics_are_hidden_until_turned_on_and_stay_on(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert load_ui_settings(tmp_path) == UiSettings(show_metrics=False)
    with caplog.at_level(logging.INFO):
        assert save_ui_settings(tmp_path, {"show_metrics": True}).show_metrics is True
    assert load_ui_settings(tmp_path).show_metrics is True  # saved, so after a restart too
    assert "Settings changed" in caplog.text


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"colour": True}, "no setting called colour"),
        ({"show_metrics": "yes"}, "show_metrics must be one of: True, False"),
        ({"show_metrics": 1}, "show_metrics must be one of"),
        ({"view": "admin"}, "view must be one of: host, participant"),
    ],
)
def test_an_unknown_setting_or_a_wrong_value_is_refused(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        save_ui_settings(tmp_path, changes)
    assert not (tmp_path / FILENAME).exists()


@pytest.mark.parametrize(
    "text", ["{not json", "[1]", '{"show_metrics": 1}', '{"old": true}', '{"view": "admin"}']
)
def test_an_unreadable_settings_file_gives_the_defaults(
    tmp_path: Path, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / FILENAME).write_text(text)
    assert load_ui_settings(tmp_path) == UiSettings()


def test_the_settings_api_reads_and_changes_them(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    defaults = {
        "show_metrics": False,
        "view": "host",
        "teach_me": False,
        "quiz_me": False,
        "assessment": False,
        "debug": False,
        "general_prompts": False,
        "face_movement": "normal",
        "show_thinking": True,
    }
    assert client.get("/api/settings").json() == defaults  # no consent needed
    changed = client.patch("/api/settings", json={"show_metrics": True})
    assert changed.status_code == 200 and changed.json() == {**defaults, "show_metrics": True}
    assert TestClient(create_app(tmp_path)).get("/api/settings").json()["show_metrics"] is True

    refused = client.patch("/api/settings", json={"show_metrics": "on"})
    assert refused.status_code == 400 and "must be one of" in refused.json()["detail"]


def test_a_settings_file_that_cannot_be_written_is_reported(tmp_path: Path) -> None:
    (tmp_path / FILENAME).mkdir()  # a folder where the file should be
    response = TestClient(create_app(tmp_path)).patch("/api/settings", json={"show_metrics": True})
    assert response.status_code == 500
    assert response.json()["detail"] == "The settings could not be saved."


def test_the_participant_view_is_saved_and_the_host_view_is_the_default(tmp_path: Path) -> None:
    assert load_ui_settings(tmp_path).view == "host"
    save_ui_settings(tmp_path, {"view": "participant"})
    assert load_ui_settings(tmp_path) == UiSettings(show_metrics=False, view="participant")
    assert set(CHOICES) == {f.name for f in fields(UiSettings)}  # every setting has its values


@pytest.mark.parametrize(("old", "new"), [("teacher", "host"), ("student", "participant")])
def test_a_view_saved_under_its_old_name_is_read_as_the_new_one(
    tmp_path: Path, old: str, new: str, caplog: pytest.LogCaptureFixture
) -> None:
    # The views were called teacher and student until 2026-10-19.
    (tmp_path / FILENAME).write_text(json.dumps({"view": old, "show_metrics": True}))
    with caplog.at_level(logging.INFO):
        assert load_ui_settings(tmp_path) == UiSettings(show_metrics=True, view=new)
    assert "Old view name read as the new one" in caplog.text
    save_ui_settings(tmp_path, {"debug": True})  # the next save writes the new name
    assert json.loads((tmp_path / FILENAME).read_text())["view"] == new


def test_an_old_view_name_sent_by_a_browser_is_saved_as_the_new_one(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    assert client.patch("/api/settings", json={"view": "student"}).json()["view"] == "participant"
    assert json.loads((tmp_path / FILENAME).read_text()) == {"view": "participant"}


def test_changes_made_together_both_stay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Review on PR #77: two changes that both read the file before either wrote it lost one.
    load = ui_settings.saved_changes

    def slow_load(home: Path) -> dict[str, object]:
        saved = load(home)
        time.sleep(0.05)  # the other change reads now, unless it waits its turn
        return saved

    monkeypatch.setattr(ui_settings, "saved_changes", slow_load)
    changes: list[dict[str, object]] = [{"view": "participant"}, {"show_metrics": True}]
    threads = [threading.Thread(target=save_ui_settings, args=(tmp_path, c)) for c in changes]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert load_ui_settings(tmp_path) == UiSettings(show_metrics=True, view="participant")
    assert [f.name for f in tmp_path.iterdir()] == [FILENAME]  # no part-written file left


def test_only_the_settings_changed_are_saved_so_the_rest_follow_their_defaults(
    tmp_path: Path,
) -> None:
    # R27: the question scope follows the config file until it is changed on the Settings page.
    allowed = UiSettings(general_prompts=True)
    save_ui_settings(tmp_path, {"show_metrics": True}, allowed)
    assert json.loads((tmp_path / FILENAME).read_text()) == {"show_metrics": True}
    assert load_ui_settings(tmp_path, allowed).general_prompts is True
    assert load_ui_settings(tmp_path).general_prompts is False  # the config file says otherwise

    save_ui_settings(tmp_path, {"general_prompts": False}, allowed)
    assert load_ui_settings(tmp_path, allowed) == UiSettings(show_metrics=True)


def test_a_change_replaces_a_settings_file_that_cannot_be_used(tmp_path: Path) -> None:
    (tmp_path / FILENAME).write_text('{"show_metrics": 1}')
    assert save_ui_settings(tmp_path, {"debug": True}) == UiSettings(debug=True)
    assert json.loads((tmp_path / FILENAME).read_text()) == {"debug": True}


def test_the_question_scope_defaults_to_the_config_file(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path, general_prompts=True))
    assert client.get("/api/settings").json()["general_prompts"] is True
    changed = client.patch("/api/settings", json={"general_prompts": False})
    assert changed.json()["general_prompts"] is False
    again = TestClient(create_app(tmp_path, general_prompts=True))
    assert again.get("/api/settings").json()["general_prompts"] is False  # the change stays


def test_a_face_movement_saved_as_more_is_read_as_normal(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # "more" was taken out on 2026-10-26 (Larry); the file's other settings are kept.
    (tmp_path / FILENAME).write_text(json.dumps({"face_movement": "more", "debug": True}))
    with caplog.at_level(logging.INFO):
        assert load_ui_settings(tmp_path) == UiSettings(face_movement="normal", debug=True)
    assert "Face movement more read as normal" in caplog.messages
    with pytest.raises(ValueError, match="must be one of: off, slight, normal"):
        checked(UiSettings(), {"face_movement": "wild"})
