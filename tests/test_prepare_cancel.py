"""Cancel Prepare (roadmap R134c): a running prepare stops at once, or once the part it is on is
finished (at most 10 seconds), and Resume Preparation carries on from where it stopped."""

import json
import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_prepare_job import JPG, PHOTO_ID, first_voice_id, make_job, write_clip

from imageskin import prepare_job
from imageskin.app import create_app
from imageskin.prepare_job import STOPPING, PrepareError, Progress, fresh_steps, interrupt
from imageskin.ui_settings import DEFAULTS
from imageskin.uploads import PhotoResult, UploadStore, VoiceSample


def held_face(reached: threading.Event, release: threading.Event, after: list[str]) -> object:
    """A face step that waits part-way, then reports again: where Stop after this part takes
    effect. It waits in Python, as an engine's frame loop does, so Stop now can cut it short."""

    def face(photo: Path, progress: Progress) -> None:
        progress("models", 0, 1, "Checking the face models")
        reached.set()
        end = time.monotonic() + 5
        while not release.is_set() and time.monotonic() < end:
            time.sleep(0.01)
        progress("models", 1, 1)
        after.append("models done")

    return face


def messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records]


def test_stop_after_this_part_stops_at_the_next_report_and_resume_carries_on(
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
            job.start()  # Resume waits until it has stopped
        release.set()
        job.wait(5)
    status = job.status()
    assert status.state == "cancelled" and not status.cancelling
    assert status.steps is not None and status.steps[0].done == 1  # how far it got
    assert all(s.activity is None and s.left_s is None for s in status.steps)
    assert after == []  # the face step's next report stopped it
    assert not list((tmp_path / "clips").glob("*.mp4"))
    assert "Prepare cancelling" in messages(caplog) and "Prepare cancelled" in messages(caplog)
    assert job.cancel().state == "cancelled"  # nothing to stop now

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="imageskin.prepare_job"):
        release.clear()
        reached.clear()
        assert job.start().state == "running"  # Resume Preparation
        assert reached.wait(5)
        release.set()
        job.wait(5)
    assert job.status().state == "done"
    resumed = next(r for r in caplog.records if r.getMessage() == "Prepare resumed")
    assert getattr(resumed, "percent", None) == status.percent


def test_stop_now_cuts_the_part_short(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    reached, release = threading.Event(), threading.Event()
    after: list[str] = []
    job, _ = make_job(tmp_path, held_face(reached, release, after))
    with caplog.at_level(logging.INFO, logger="imageskin.prepare_job"):
        job.start()
        assert reached.wait(5)
        start = time.monotonic()
        job.cancel(now=True)
        job.wait(2)
    assert time.monotonic() - start < 2  # not the 5 s the part would take
    assert job.status().state == "cancelled" and after == []
    interrupted = next(r for r in caplog.records if r.getMessage() == "Prepare interrupted")
    assert getattr(interrupted, "found", None) is True


def test_stop_after_this_part_stops_at_once_when_the_part_runs_long(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    reached, release = threading.Event(), threading.Event()
    after: list[str] = []
    job, _ = make_job(tmp_path, held_face(reached, release, after))
    with (
        patch.object(prepare_job, "STOP_AFTER_PART_MAX_S", 0.2),
        caplog.at_level(logging.INFO, logger="imageskin.prepare_job"),
    ):
        job.start()
        assert reached.wait(5)
        start = time.monotonic()
        job.cancel()
        job.wait(3)
    assert time.monotonic() - start < 3
    assert job.status().state == "cancelled" and after == []
    assert "Prepare part still running; stopping it now" in messages(caplog)


def test_a_cancel_while_the_last_clip_is_made_still_stops(tmp_path: Path) -> None:
    job, _ = make_job(tmp_path)

    def clip(photo: Path, text: str, output: Path) -> None:
        write_clip(photo, text, output)
        if text != "Goodbye.":
            job.cancel()  # confirmed while the clip is made; no report comes after the last one

    job._render_clip = clip
    job.start()
    job.wait(5)
    assert job.status().state == "cancelled"


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
    assert status.state == "cancelled" and status.failure is None
    assert "Prepare failed while cancelling" in messages(caplog)


def test_cancel_with_nothing_running_changes_nothing(tmp_path: Path) -> None:
    job, _ = make_job(tmp_path)
    assert job.cancel().state == "idle"
    job.start()
    job.wait(5)
    assert job.cancel(now=True).state == "done"
    assert job.status().state == "done"


def cancelled_job(tmp_path: Path) -> tuple[prepare_job.PrepareJob, object]:
    reached, release = threading.Event(), threading.Event()
    job, store = make_job(tmp_path, held_face(reached, release, []))
    job.start()
    assert reached.wait(5)
    job.cancel(now=True)
    job.wait(5)
    assert job.status().state == "cancelled"
    release.set()  # a later run goes straight through
    return job, store


def test_a_changed_setting_means_preparing_over_again(tmp_path: Path) -> None:
    job, store = cancelled_job(tmp_path)
    store.chosen = "b" * 32  # type: ignore[attr-defined]
    assert job.status().state == "idle"  # nothing to resume


def test_discard_starts_again_from_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    job, _ = cancelled_job(tmp_path)
    times = job.status().times
    with caplog.at_level(logging.INFO, logger="imageskin.prepare_job"):
        status = job.discard()
    assert status.state == "idle" and status.times == times
    assert "Stopped prepare discarded" in messages(caplog)
    assert json.loads((tmp_path / "prepare.json").read_text())["state"] == "idle"
    job.start()
    job.wait(5)
    assert job.discard().state == "done"  # only a cancelled job is discarded


def saved_running(tmp_path: Path, cancelling: bool) -> None:
    saved = {
        "state": "running",
        "photo_id": PHOTO_ID,
        "percent": 40,
        "steps": [asdict(s) for s in fresh_steps()],
        "times": {"voice": 12.0},
        "cancelling": cancelling,
        # What it was made from, as now, so it can be resumed.
        "voice_id": first_voice_id(tmp_path),
        "face_movement": DEFAULTS.face_movement,
    }
    (tmp_path / "prepare.json").write_text(json.dumps(saved))


def test_a_stopped_job_is_cancelled_at_once(tmp_path: Path) -> None:
    saved_running(tmp_path, cancelling=False)
    job, _ = make_job(tmp_path)
    assert job.status().stopped  # no thread works on it
    status = job.cancel()
    assert status.state == "cancelled" and status.percent == 40
    assert json.loads((tmp_path / "prepare.json").read_text())["state"] == "cancelled"


def test_a_cancel_cut_short_by_a_restart_is_finished_at_start(tmp_path: Path) -> None:
    saved_running(tmp_path, cancelling=True)
    job, _ = make_job(tmp_path)
    job.resume()
    job.wait(5)
    assert job.status().state == "cancelled"


def test_interrupt_needs_a_started_thread() -> None:
    assert interrupt(threading.Thread(target=lambda: None)) is False


def test_the_api_cancels_resumes_and_discards(tmp_path: Path) -> None:
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
    job = client.app.state.prepare_job  # type: ignore[attr-defined]
    with patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)):
        client.post("/api/prepare")
        assert reached.wait(5)
        cancelling = client.post("/api/prepare/cancel", json={"now": True}).json()
        assert cancelling["cancelling"] is True
        job.wait(5)
        assert client.get("/api/prepare").json()["state"] == "cancelled"
        # Resume Preparation, then Stop after this part.
        reached.clear()
        assert client.post("/api/prepare").json()["state"] == "running"
        assert reached.wait(5)
        client.post("/api/prepare/cancel")
        refused = client.post("/api/prepare")
        assert refused.status_code == 409 and refused.json()["detail"] == STOPPING
        release.set()
        job.wait(5)
        assert client.post("/api/prepare/discard").json()["state"] == "idle"


def test_a_stop_landing_just_as_the_steps_end_still_stops(tmp_path: Path) -> None:
    saved_running(tmp_path, cancelling=True)
    job, _ = make_job(tmp_path)

    def interrupted() -> None:
        raise prepare_job.PrepareCancelled()

    job._run_steps = interrupted  # type: ignore[method-assign]
    job._run()
    assert job.status().state == "cancelled"
