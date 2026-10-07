import json
import logging
import threading
from dataclasses import asdict
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin.app import create_app
from imageskin.prepare_job import (
    NO_PHOTO,
    PrepareError,
    PrepareJob,
    PrepareStatus,
    Progress,
    Step,
    fresh_steps,
    kokoro_voice,
    percent,
    photoreal_face,
)
from imageskin.uploads import PhotoChoice, PhotoResult, UploadStore, VoiceSample
from imageskin.video import VideoError

PHOTO_ID = "a" * 32


class FakeStore:
    """The parts of UploadStore the job uses: a chosen photo and a voice sample."""

    def __init__(self, folder: Path) -> None:
        self.photo = folder / "me.jpg"
        self.photo.write_bytes(b"photo")
        self.chosen: str | None = PHOTO_ID
        self.problem: str | None = None

    def photo_choice(self) -> PhotoChoice:
        return PhotoChoice(self.chosen)

    def voice_sample(self) -> VoiceSample:
        return VoiceSample(2, 40, 35, self.problem)

    def path(self, kind: str, upload_id: str) -> Path | None:
        return self.photo if upload_id == PHOTO_ID else None


def face_in_steps(photo: Path, progress: Progress) -> None:
    progress("models", 0, 1)
    progress("models", 1, 1)
    progress("shapes", 10, 10)
    progress("shapes", 10, 10)  # said twice, logged once
    for i in range(5):
        progress("loop", i, 4)
    progress("align", 0, 1)
    progress("align", 1, 1)


def make_job(
    tmp_path: Path, face: object = face_in_steps, voice: object = lambda: None
) -> tuple[PrepareJob, FakeStore]:
    store = FakeStore(tmp_path)
    job = PrepareJob(tmp_path, cast(UploadStore, store), voice, face)  # type: ignore[arg-type]
    return job, store


def test_prepares_the_voice_then_the_face_and_saves_the_result(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    job, _ = make_job(tmp_path)
    assert job.status().state == "idle"
    with caplog.at_level(logging.INFO):
        started = job.start()
        job.wait(5)
    assert started.state == "running" and started.photo_id == PHOTO_ID
    status = job.status()
    assert status.state == "done" and status.percent == 100 and status.error is None
    assert status.steps is not None
    assert [s.key for s in status.steps] == ["voice", "models", "shapes", "loop", "align"]
    assert all(s.done == s.total for s in status.steps)
    # Mouth shapes from before: done, with no time, since nothing was rendered.
    assert [s.seconds is None for s in status.steps] == [False, False, True, False, False]
    assert caplog.text.count("Prepare step finished") == 4
    assert caplog.text.count("Prepare step already done") == 1
    assert "Prepare job finished" in caplog.text
    saved = json.loads((tmp_path / "prepare.json").read_text())
    assert saved["state"] == "done" and saved["finished_at"]


def test_reports_progress_and_time_left_while_it_runs(tmp_path: Path) -> None:
    reached, release = threading.Event(), threading.Event()

    def slow_face(photo: Path, progress: Progress) -> None:
        progress("models", 1, 1)
        progress("shapes", 10, 10)
        progress("loop", 50, 200)  # resumed: 50 frames were there already
        progress("loop", 52, 200)
        reached.set()
        release.wait(5)

    job, _ = make_job(tmp_path, slow_face)
    job.start()
    assert reached.wait(5)
    assert job.start().state == "running"  # a second click just reports on it
    status = job.status()
    loop = next(s for s in (status.steps or []) if s.key == "loop")
    assert (loop.done, loop.total) == (52, 200) and loop.left_s is not None
    assert loop.seconds is None
    assert 0 < status.percent < 100
    release.set()
    job.wait(5)
    assert job.status().state == "done"


def test_needs_a_photo_and_enough_voice(tmp_path: Path) -> None:
    job, store = make_job(tmp_path)
    store.chosen = None
    with pytest.raises(PrepareError, match=NO_PHOTO):
        job.start()
    store.chosen = PHOTO_ID
    store.problem = "Add more recordings."
    with pytest.raises(PrepareError, match="Add more recordings."):
        job.start()
    assert job.status().state == "idle"


def test_a_failure_says_why(tmp_path: Path) -> None:
    def no_ffmpeg(photo: Path, progress: Progress) -> None:
        raise VideoError("ffmpeg was not found")

    job, _ = make_job(tmp_path, no_ffmpeg)
    job.start()
    job.wait(5)
    status = job.status()
    assert status.state == "failed" and status.error == "ffmpeg was not found"
    voice = (status.steps or [])[0]
    assert voice.done == 1  # the voice step had finished


def test_an_unexpected_error_is_reported_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken() -> None:
        raise RuntimeError("boom")

    job, _ = make_job(tmp_path, voice=broken)
    with caplog.at_level(logging.ERROR):
        job.start()
        job.wait(5)
    error = job.status().error or ""
    assert error.startswith("Something went wrong: boom.")
    assert "Traceback" in caplog.text


def test_a_removed_photo_fails_the_job(tmp_path: Path) -> None:
    job, store = make_job(tmp_path)
    store.photo = tmp_path / "gone.jpg"
    store.path = lambda kind, upload_id: None  # type: ignore[method-assign]
    job.start()
    job.wait(5)
    assert job.status().error == "The photo to prepare was removed. Choose another one."


def test_a_job_stopped_by_a_restart_carries_on(tmp_path: Path) -> None:
    steps = [asdict(s) for s in fresh_steps()]
    steps[3]["done"], steps[3]["total"] = 80, 200
    saved = {"state": "running", "photo_id": PHOTO_ID, "percent": 40, "steps": steps}
    (tmp_path / "prepare.json").write_text(json.dumps(saved))
    job, _ = make_job(tmp_path)
    status = job.status()  # how far it had got shows until the steps report again
    assert status.state == "running" and status.percent == 40
    assert status.steps is not None and status.steps[3].done == 80
    job.resume()
    job.wait(5)
    assert job.status().state == "done"


def test_resume_does_nothing_when_no_job_was_running(tmp_path: Path) -> None:
    job, _ = make_job(tmp_path)
    job.resume()
    job.wait(5)
    assert job.status().state == "idle"


def test_a_new_photo_needs_preparing_again(tmp_path: Path) -> None:
    job, store = make_job(tmp_path)
    job.start()
    job.wait(5)
    store.chosen = "b" * 32
    assert job.status().state == "idle"


def test_too_little_speech_after_preparing_needs_preparing_again(tmp_path: Path) -> None:
    job, store = make_job(tmp_path)
    job.start()
    job.wait(5)
    assert job.status().state == "done"
    store.problem = "Add more recordings."  # recordings removed afterwards
    assert job.status().state == "idle"
    store.problem = None
    assert job.status().state == "done"


def test_a_state_file_from_other_steps_loads_consistently(tmp_path: Path) -> None:
    old_steps = [{"key": "face", "label": "Old step", "done": 1, "total": 1}]
    saved = {"state": "done", "photo_id": PHOTO_ID, "percent": 100, "steps": old_steps}
    (tmp_path / "prepare.json").write_text(json.dumps(saved))
    job, _ = make_job(tmp_path)
    assert job.status() == PrepareStatus("idle")

    (tmp_path / "prepare.json").write_text(json.dumps({**saved, "state": "running"}))
    job, _ = make_job(tmp_path)
    running = job.status()
    assert running.state == "running" and running.percent == 0
    assert [s.done for s in running.steps or []] == [0] * 5
    job.resume()
    job.wait(5)
    assert job.status().state == "done"


def test_an_unreadable_state_file_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "prepare.json").write_text("{not json")
    with caplog.at_level(logging.ERROR):
        job, _ = make_job(tmp_path)
    assert job.status().state == "idle"
    assert "Could not read the prepare job state" in caplog.text


def test_percent_is_weighted_by_how_long_each_step_takes() -> None:
    steps = fresh_steps()
    assert percent(steps) == 0
    voice_done = [Step("voice", "", 1, 1)] + steps[1:]
    loop_half = steps[:3] + [Step("loop", "", 100, 200)] + steps[4:]
    assert percent(voice_done) < 2 < 40 < percent(loop_half) < 50


def test_default_voice_step_says_a_word() -> None:
    with patch("imageskin.kokoro_engine.KokoroEngine.speak") as speak:
        kokoro_voice()
    speak.assert_called_once_with("af_heart", "Hello.")


def test_default_face_step_builds_the_photoreal_library(tmp_path: Path) -> None:
    def progress(step: str, done: int, total: int) -> None:
        pass

    with (
        patch("imageskin.prepare_job.find_ffmpeg") as ffmpeg,
        patch("imageskin.photoreal_library.prepare_library") as prepare,
    ):
        photoreal_face(tmp_path)(tmp_path / "me.jpg", progress)
    ffmpeg.assert_called_once()
    prepare.assert_called_once_with(tmp_path / "me.jpg", tmp_path, progress=progress)


JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100


def test_the_api_starts_the_job_and_reports_on_it(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=face_in_steps,
        )
    )
    assert client.get("/api/prepare").status_code == 403  # consent first
    client.post("/api/consent", json={"agreed": True})
    assert client.get("/api/prepare").json()["state"] == "idle"
    refused = client.post("/api/prepare")
    assert refused.status_code == 409 and refused.json()["detail"] == NO_PHOTO

    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    with patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)):
        assert client.post("/api/prepare").json()["state"] == "running"
        client.app.state.prepare_job.wait(5)  # type: ignore[attr-defined]
        done = client.get("/api/prepare").json()
    assert done["state"] == "done" and done["percent"] == 100
    assert [s["done"] for s in done["steps"]] == [1, 1, 10, 4, 1]
