"""Cancel Prepare (roadmap R134c): a running prepare stops at its next progress report once Cancel
is confirmed, and is then idle; nothing else is changed."""

import json
import logging
import threading
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_prepare_job import JPG, PHOTO_ID, make_job, write_clip

from imageskin.app import create_app
from imageskin.prepare_job import STOPPING, PrepareError, Progress, fresh_steps
from imageskin.uploads import PhotoResult, UploadStore, VoiceSample


def held_face(reached: threading.Event, release: threading.Event, after: list[str]) -> object:
    """A face step that waits part-way, then reports again: where a cancel takes effect."""

    def face(photo: Path, progress: Progress) -> None:
        progress("models", 0, 1, "Checking the face models")
        reached.set()
        release.wait(5)
        progress("models", 1, 1)
        after.append("models done")

    return face


def test_a_cancelled_job_stops_at_its_next_report_and_is_idle(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    reached, release = threading.Event(), threading.Event()
    after: list[str] = []
    job, _ = make_job(tmp_path, held_face(reached, release, after))
    with caplog.at_level(logging.INFO, logger="imageskin.prepare_job"):
        job.start()
        assert reached.wait(5)
        cancelling = job.cancel()
        assert cancelling.state == "running" and cancelling.cancelling
        assert json.loads((tmp_path / "prepare.json").read_text())["cancelling"]
        assert job.cancel().cancelling  # asked twice: still just cancelling
        with pytest.raises(PrepareError, match=STOPPING):
            job.start()  # Prepare waits until it has stopped
        release.set()
        job.wait(5)
    status = job.status()
    assert status.state == "idle" and not status.cancelling and status.steps is None
    assert status.times is not None and "voice" in status.times  # kept for the time left
    assert after == []  # the face step's next report stopped it
    assert not list((tmp_path / "clips").glob("*.mp4"))
    messages = [r.getMessage() for r in caplog.records]
    assert "Prepare cancelling" in messages and "Prepare cancelled" in messages
    stopped = next(r for r in caplog.records if r.getMessage() == "Prepare job stopped")
    assert getattr(stopped, "duration_s", None) is not None
    # And it can be prepared again from the start.
    job.start()
    job.wait(5)
    assert job.status().state == "done"


def test_a_cancel_while_the_last_clip_is_made_still_stops(tmp_path: Path) -> None:
    job, _ = make_job(tmp_path)

    def clip(photo: Path, text: str, output: Path) -> None:
        write_clip(photo, text, output)
        if text != "Goodbye.":
            job.cancel()  # confirmed while the clip is made; no report comes after the last one

    job._render_clip = clip
    job.start()
    job.wait(5)
    assert job.status().state == "idle"


def test_an_engine_failing_while_it_is_stopped_is_still_a_cancel(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    reached, release = threading.Event(), threading.Event()

    def face(photo: Path, progress: Progress) -> None:
        reached.set()
        release.wait(5)
        raise RuntimeError("cut off")

    job, _ = make_job(tmp_path, face)
    with caplog.at_level(logging.WARNING, logger="imageskin.prepare_job"):
        job.start()
        assert reached.wait(5)
        job.cancel()
        release.set()
        job.wait(5)
    status = job.status()
    assert status.state == "idle" and status.failure is None
    assert "Prepare failed while cancelling" in [r.getMessage() for r in caplog.records]


def test_cancel_with_nothing_running_changes_nothing(tmp_path: Path) -> None:
    job, _ = make_job(tmp_path)
    assert job.cancel().state == "idle"
    job.start()
    job.wait(5)
    assert job.cancel().state == "done"
    assert job.status().state == "done"


def saved_running(tmp_path: Path, cancelling: bool) -> None:
    saved = {
        "state": "running",
        "photo_id": PHOTO_ID,
        "percent": 40,
        "steps": [asdict(s) for s in fresh_steps()],
        "times": {"voice": 12.0},
        "cancelling": cancelling,
    }
    (tmp_path / "prepare.json").write_text(json.dumps(saved))


def test_a_stopped_job_is_cancelled_at_once(tmp_path: Path) -> None:
    saved_running(tmp_path, cancelling=False)
    job, _ = make_job(tmp_path)
    assert job.status().stopped  # no thread works on it
    status = job.cancel()
    assert status.state == "idle" and status.times == {"voice": 12.0}
    assert json.loads((tmp_path / "prepare.json").read_text())["state"] == "idle"


def test_a_cancel_cut_short_by_a_restart_is_finished_at_start(tmp_path: Path) -> None:
    saved_running(tmp_path, cancelling=True)
    job, _ = make_job(tmp_path)
    job.resume()
    job.wait(5)
    assert job.status().state == "idle"


def test_the_api_cancels_the_job(tmp_path: Path) -> None:
    reached, release = threading.Event(), threading.Event()
    after: list[str] = []
    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=held_face(reached, release, after),  # type: ignore[arg-type]
            render_clip=write_clip,
        )
    )
    assert client.post("/api/prepare/cancel").status_code == 403  # consent first
    client.post("/api/consent", json={"agreed": True})
    assert client.post("/api/prepare/cancel").json()["state"] == "idle"
    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    with patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)):
        client.post("/api/prepare")
        assert reached.wait(5)
        cancelling = client.post("/api/prepare/cancel").json()
        assert cancelling["state"] == "running" and cancelling["cancelling"] is True
        refused = client.post("/api/prepare")
        assert refused.status_code == 409 and refused.json()["detail"] == STOPPING
        release.set()
        client.app.state.prepare_job.wait(5)  # type: ignore[attr-defined]
        assert client.get("/api/prepare").json()["state"] == "idle"
