import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin.app import create_app
from imageskin.delete_data import delete_my_data
from imageskin.wizard import FILENAME, STEPS, load_step, save_step


def test_no_file_means_the_first_step(tmp_path: Path) -> None:
    assert load_step(tmp_path) == "start"


def test_saved_step_is_loaded_and_logged_with_time_spent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="imageskin.wizard"):
        save_step(tmp_path / "home", "photo")
        with patch("imageskin.wizard.time.time", return_value=10**10):
            save_step(tmp_path / "home", "voice")
    assert load_step(tmp_path / "home") == "voice"
    first, second = (vars(r) for r in caplog.records if r.getMessage() == "Wizard step")
    assert first["step"] == "photo" and first["spent_on_previous_s"] is None
    assert second["step"] == "voice" and second["from"] == "photo"
    assert second["spent_on_previous_s"] > 0


def test_unknown_step_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No wizard step"):
        save_step(tmp_path, "camera")
    assert not (tmp_path / FILENAME).exists()


@pytest.mark.parametrize("text", ["not json", "[]", json.dumps({"step": "nowhere"})])
def test_unreadable_file_means_the_first_step(
    tmp_path: Path, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / FILENAME).write_text(text)
    with caplog.at_level(logging.ERROR, logger="imageskin.wizard"):
        assert load_step(tmp_path) == "start"
    assert caplog.records
    save_step(tmp_path, "accent")  # an unreadable file is replaced
    assert load_step(tmp_path) == "accent"


def test_steps_are_in_order() -> None:
    assert STEPS == ("start", "photo", "voice", "accent", "prepare", "review")


def test_wizard_api_saves_the_step_across_a_restart(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/wizard").json() == {"step": "start"}
    assert client.put("/api/wizard", json={"step": "prepare"}).json() == {"step": "prepare"}
    assert TestClient(create_app(tmp_path)).get("/api/wizard").json() == {"step": "prepare"}


def test_wizard_api_refuses_an_unknown_step(tmp_path: Path) -> None:
    response = TestClient(create_app(tmp_path)).put("/api/wizard", json={"step": "camera"})
    assert response.status_code == 400
    assert "No wizard step" in response.json()["detail"]


def test_wizard_api_says_when_the_step_cannot_be_saved(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    with patch("imageskin.app.save_step", side_effect=OSError("disk full")):
        response = client.put("/api/wizard", json={"step": "photo"})
    assert response.status_code == 500
    assert response.json()["detail"] == "The step could not be saved."


def test_delete_my_data_starts_the_wizard_again(tmp_path: Path) -> None:
    save_step(tmp_path, "review")
    delete_my_data(tmp_path)
    assert load_step(tmp_path) == "start"


def test_camera_photo_taken_is_logged_with_its_size(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = TestClient(create_app(tmp_path))
    with caplog.at_level(logging.INFO, logger="imageskin.wizard"):
        response = client.post(
            "/api/wizard/camera",
            json={"taken": True, "width": 1280, "height": 720, "camera": "Integrated Camera"},
        )
    assert response.json() == {"logged": True}
    record = next(r for r in caplog.records if r.getMessage() == "Camera photo taken")
    assert (vars(record)["width"], vars(record)["height"]) == (1280, 720)
    assert vars(record)["camera"] == "Integrated Camera"


@pytest.mark.parametrize("reason", ["insecure", "unsupported", "refused", "no-camera", "failed"])
def test_camera_not_used_is_logged_with_the_reason(
    tmp_path: Path, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    client = TestClient(create_app(tmp_path))
    with caplog.at_level(logging.INFO, logger="imageskin.wizard"):
        assert client.post("/api/wizard/camera", json={"taken": False, "reason": reason}).is_success
    record = next(r for r in caplog.records if r.getMessage() == "Camera not used")
    assert vars(record)["reason"] == reason


def test_camera_report_with_an_unknown_reason_is_refused(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/wizard/camera", json={"taken": False, "reason": "bored"})
    assert response.status_code == 400
    assert "No camera reason" in response.json()["detail"]
