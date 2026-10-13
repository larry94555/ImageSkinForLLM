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
        ({"view": "admin"}, "view must be one of: teacher, student"),
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
    defaults = {"show_metrics": False, "view": "teacher"}
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


def test_the_student_view_is_saved_and_the_teacher_view_is_the_default(tmp_path: Path) -> None:
    assert load_ui_settings(tmp_path).view == "teacher"
    save_ui_settings(tmp_path, {"view": "student"})
    assert load_ui_settings(tmp_path) == UiSettings(show_metrics=False, view="student")
    assert set(CHOICES) == {f.name for f in fields(UiSettings)}  # every setting has its values


def test_changes_made_together_both_stay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Review on PR #77: two changes that both read the file before either wrote it lost one.
    load = ui_settings.load_ui_settings

    def slow_load(home: Path) -> UiSettings:
        settings = load(home)
        time.sleep(0.05)  # the other change reads now, unless it waits its turn
        return settings

    monkeypatch.setattr(ui_settings, "load_ui_settings", slow_load)
    changes: list[dict[str, object]] = [{"view": "student"}, {"show_metrics": True}]
    threads = [threading.Thread(target=save_ui_settings, args=(tmp_path, c)) for c in changes]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert load(tmp_path) == UiSettings(show_metrics=True, view="student")
    assert [f.name for f in tmp_path.iterdir()] == [FILENAME]  # no part-written file left
