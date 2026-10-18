"""Delete my data (roadmap R31): the person's files are removed and setup starts again."""

import logging
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from test_chat import chat_app
from test_prepare_job import make_job

from imageskin.chat import CLEAR_FAILED, ClearFailed
from imageskin.delete_data import PERSONAL, Deleted, delete_my_data
from imageskin.prepare_job import SAMPLE_BEING_MADE, WAIT_TO_DELETE, PrepareError, PrepareStatus
from imageskin.review import Review

# What isn't the person's, and is kept.
KEPT = (
    "models/faces/face.task",
    "content/notes.pdf",
    "content/notes-wiki.json",
    "ui-settings.json",
)
PERSONS = (
    "uploads/photos/a.jpg",
    "uploads/sounds/b.wav",
    "uploads/chosen-photo.json",
    "uploads/voice-sample.wav",
    "photoreal/abc/frames/0001.png",
    "clips/sample.mp4",
    "clips/goodbye.mp4",
    "prepare.json",
    "replies/idle/a.mp4",
    "replies/3.mp4",
    "conversation.json",
    "review.json",
    "accent.json",
    "consent.json",
)


def fill(home: Path) -> None:
    for name in KEPT + PERSONS:
        path = home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x" * 10)


def test_the_persons_files_are_deleted_and_the_rest_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fill(tmp_path)
    with caplog.at_level(logging.INFO):
        deleted = delete_my_data(tmp_path)
    assert deleted == Deleted(files=len(PERSONS), bytes=10 * len(PERSONS), left=[])
    assert all((tmp_path / name).is_file() for name in KEPT)
    assert not any((tmp_path / name).exists() for name in PERSONAL)
    assert "Deleting my data" in caplog.text and "Deleted my data" in caplog.text
    # Again: nothing is left to delete.
    assert delete_my_data(tmp_path) == Deleted()


def test_a_file_that_cant_be_deleted_is_listed_and_the_rest_go(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fill(tmp_path)
    stuck = tmp_path / "replies" / "idle" / "a.mp4"
    unlink = Path.unlink

    def open_elsewhere(self: Path, missing_ok: bool = False) -> None:
        if self == stuck:
            raise PermissionError("in use by another program")
        unlink(self, missing_ok)

    with patch.object(Path, "unlink", open_elsewhere), caplog.at_level(logging.WARNING):
        deleted = delete_my_data(tmp_path)
    assert deleted.left == ["replies/idle/a.mp4"]
    assert deleted.files == len(PERSONS) - 1
    assert stuck.is_file() and not (tmp_path / "replies" / "3.mp4").exists()
    assert not (tmp_path / "uploads").exists()
    assert "Could not delete a file" in caplog.text
    # Once it is closed, trying again removes it.
    assert delete_my_data(tmp_path) == Deleted(files=1, bytes=10)
    assert not (tmp_path / "replies").exists()


def test_a_file_gone_meanwhile_is_skipped(tmp_path: Path) -> None:
    fill(tmp_path)
    with patch.object(Path, "unlink", side_effect=FileNotFoundError):
        assert delete_my_data(tmp_path) == Deleted()


def test_the_prepare_job_forgets_what_was_prepared(tmp_path: Path) -> None:
    job, _ = make_job(tmp_path)
    job.start()
    job.wait(5)
    assert job.status().state == "done"
    assert job.forget(lambda: "deleted") == "deleted"
    assert job.status() == PrepareStatus("idle")


def test_the_prepare_job_refuses_while_it_runs(tmp_path: Path) -> None:
    release = threading.Event()
    job, _ = make_job(tmp_path, voice=release.wait)
    job.start()
    called = []
    with pytest.raises(PrepareError, match=WAIT_TO_DELETE):
        job.forget(lambda: called.append(1))
    release.set()
    job.wait(5)
    assert called == [] and job.status().state == "done"


def test_the_prepare_job_refuses_while_the_sample_is_made_again(tmp_path: Path) -> None:
    job, _ = make_job(tmp_path)
    job._rendering_again = True
    with pytest.raises(PrepareError, match=SAMPLE_BEING_MADE):
        job.forget(lambda: None)


def test_the_api_deletes_my_data_and_setup_starts_again(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = chat_app(tmp_path, lambda messages: "Hello")
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "My name is Larry."})
    fill(tmp_path)
    with caplog.at_level(logging.INFO):
        answer = client.delete("/api/data")
    assert answer.status_code == 200
    # The reply video goes with the conversation, as Clear conversation removes it (R27b).
    assert answer.json()["left"] == [] and answer.json()["files"] == len(PERSONS) - 1
    assert "Conversation cleared" in caplog.text and "Deleted my data" in caplog.text
    assert not any((tmp_path / name).exists() for name in PERSONAL)
    assert all((tmp_path / name).is_file() for name in KEPT)
    # Setup starts at consent, and the conversation is gone.
    assert client.get("/api/consent").json()["agreed"] is False
    client.post("/api/consent", json={"agreed": True})
    assert client.get("/api/chat").json() == {"turns": []}
    assert client.get("/api/prepare").json()["state"] == "idle"
    assert client.get("/api/review").json()["accepted"] is False


def test_the_api_refuses_while_setup_prepares(tmp_path: Path) -> None:
    client = chat_app(tmp_path, lambda messages: "Hello")
    fill(tmp_path)
    job = client.app.state.prepare_job  # type: ignore[attr-defined]
    with patch.object(job, "status", return_value=PrepareStatus("running")):
        answer = client.delete("/api/data")
    assert answer.status_code == 409 and answer.json()["detail"] == WAIT_TO_DELETE
    assert all((tmp_path / name).exists() for name in PERSONS)


def test_the_api_says_when_the_job_refuses(tmp_path: Path) -> None:
    client = chat_app(tmp_path, lambda messages: "Hello")
    job = client.app.state.prepare_job  # type: ignore[attr-defined]
    with patch.object(job, "forget", side_effect=PrepareError(SAMPLE_BEING_MADE)):
        answer = client.delete("/api/data")
    assert answer.status_code == 409 and answer.json()["detail"] == SAMPLE_BEING_MADE


def test_the_api_deletes_nothing_when_the_conversation_cant_be_cleared(tmp_path: Path) -> None:
    client = chat_app(tmp_path, lambda messages: "Hello")
    fill(tmp_path)
    with patch("imageskin.app.Conversation.clear", side_effect=ClearFailed(CLEAR_FAILED)):
        answer = client.delete("/api/data")
    assert answer.status_code == 500 and answer.json()["detail"] == CLEAR_FAILED
    assert all((tmp_path / name).exists() for name in PERSONS)
