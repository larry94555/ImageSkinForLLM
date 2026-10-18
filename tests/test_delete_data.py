"""Delete my data (roadmap R31): the person's files are removed and setup starts again."""

import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_chat import chat_app
from test_prepare_job import make_job
from test_uploads import PNG

from imageskin.app import DELETED_MEANWHILE
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
    unlink = Path.unlink

    def removed_meanwhile(self: Path, missing_ok: bool = False) -> None:
        unlink(self)
        raise FileNotFoundError(self)

    with patch.object(Path, "unlink", removed_meanwhile):
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


def chatted(tmp_path: Path) -> TestClient:
    """An app with a conversation and the person's files in its home."""
    client = chat_app(tmp_path, lambda messages: "Hello")
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "My name is Larry."})
    fill(tmp_path)
    (tmp_path / "consent.json").write_text('{"agreed_at": "2026-10-18T00:00:00+00:00"}')
    return client


def test_a_prepare_started_before_the_delete_reserves_the_job_refuses_it(tmp_path: Path) -> None:
    client = chatted(tmp_path)
    job = client.app.state.prepare_job  # type: ignore[attr-defined]

    class PrepareStartsNow:
        """The delete's wait for the warm-up, just before it reserves the job: a Prepare
        starts then (review on PR #109)."""

        def is_alive(self) -> bool:
            with job._lock:
                job._status = PrepareStatus("running")
            return False

    client.app.state.reply_warm_up = PrepareStartsNow()  # type: ignore[attr-defined]
    answer = client.delete("/api/data")
    assert answer.status_code == 409 and answer.json()["detail"] == WAIT_TO_DELETE
    # Nothing was cleared or removed: the conversation, its videos and the files are there.
    assert len(client.get("/api/chat").json()["turns"]) == 2
    assert all((tmp_path / name).exists() for name in PERSONS)


def test_a_prepare_started_during_the_delete_waits_for_it(tmp_path: Path) -> None:
    client = chatted(tmp_path)
    job = client.app.state.prepare_job  # type: ignore[attr-defined]
    deleting, release = threading.Event(), threading.Event()
    real_delete = delete_my_data

    def slow_delete(home: Path) -> Deleted:
        deleting.set()
        release.wait(5)
        deleted = real_delete(home)
        order.append("deleted")
        return deleted

    order: list[str] = []
    answers: list[int] = []
    with patch("imageskin.app.delete_my_data", slow_delete):
        delete = threading.Thread(
            target=lambda: answers.append(client.delete("/api/data").status_code)
        )
        delete.start()
        assert deleting.wait(5)

        def prepare() -> None:
            try:
                job.start()
            except PrepareError:  # nothing to prepare once the delete is done
                pass
            order.append("prepare")

        start = threading.Thread(target=prepare)
        start.start()
        start.join(0.3)
        assert start.is_alive()  # waiting for the delete
        release.set()
        delete.join(5)
        start.join(5)
    assert answers == [200] and order == ["deleted", "prepare"]
    assert not any((tmp_path / name).exists() for name in PERSONAL)


def test_the_api_says_when_the_job_refuses(tmp_path: Path) -> None:
    client = chatted(tmp_path)
    job = client.app.state.prepare_job  # type: ignore[attr-defined]
    with job._lock:
        job._rendering_again = True
    answer = client.delete("/api/data")
    assert answer.status_code == 409 and answer.json()["detail"] == SAMPLE_BEING_MADE
    assert len(client.get("/api/chat").json()["turns"]) == 2
    assert all((tmp_path / name).exists() for name in PERSONS)


def test_the_api_deletes_nothing_when_the_conversation_cant_be_cleared(tmp_path: Path) -> None:
    client = chat_app(tmp_path, lambda messages: "Hello")
    fill(tmp_path)
    with patch("imageskin.app.Conversation.clear", side_effect=ClearFailed(CLEAR_FAILED)):
        answer = client.delete("/api/data")
    assert answer.status_code == 500 and answer.json()["detail"] == CLEAR_FAILED
    assert all((tmp_path / name).exists() for name in PERSONS)


def test_a_folder_that_cant_be_read_is_left_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fill(tmp_path)
    walk = os.walk

    def unreadable_uploads(top: Path, onerror: Any = None) -> Any:
        if Path(top) == tmp_path / "uploads":
            if onerror:
                onerror(PermissionError(13, "Permission denied", str(top)))
            return iter([])
        return walk(top, onerror=onerror)

    with (
        patch("imageskin.delete_data.os.walk", unreadable_uploads),
        caplog.at_level(logging.WARNING),
    ):
        deleted = delete_my_data(tmp_path)
    # Never reported as complete: the folder it couldn't read is left.
    assert deleted.left == ["uploads"]
    assert (tmp_path / "uploads" / "photos" / "a.jpg").is_file()
    assert not (tmp_path / "clips").exists()
    assert "Could not read a folder" in caplog.text and "Could not delete a folder" in caplog.text


def test_requests_that_arrive_during_the_delete_write_nothing_after_it(tmp_path: Path) -> None:
    """A prompt, a clear, a consent, a photo and an accent sent while the files are deleted wait
    for the delete and are then refused, so nothing comes back (reviews on PR #109)."""
    client = chatted(tmp_path)
    deleting, release = threading.Event(), threading.Event()
    real_delete = delete_my_data

    def slow_delete(home: Path) -> Deleted:
        deleting.set()
        release.wait(5)
        return real_delete(home)

    answers: dict[str, Any] = {}

    def send(name: str, call: Callable[[], Any]) -> threading.Thread:
        thread = threading.Thread(target=lambda: answers.__setitem__(name, call()))
        thread.start()
        return thread

    with (
        patch("imageskin.app.delete_my_data", slow_delete),
        patch("imageskin.app.load_review", return_value=Review(accepted=True)),
    ):
        delete = send("delete", lambda: client.delete("/api/data"))
        assert deleting.wait(5)
        waiting = [
            send("chat", lambda: client.post("/api/chat", json={"prompt": "Remember me."})),
            send("clear", lambda: client.delete("/api/chat")),
            send("consent", lambda: client.post("/api/consent", json={"agreed": True})),
            send(
                "upload",
                lambda: client.post("/api/uploads/photos", files={"file": ("me.png", PNG)}),
            ),
            send("accent", lambda: client.put("/api/accent", json={"accent": "own"})),
        ]
        waiting[0].join(0.3)
        assert all(thread.is_alive() for thread in waiting)
        release.set()
        for thread in [delete, *waiting]:
            thread.join(5)
    assert answers["delete"].json()["left"] == []
    for name in ("chat", "clear", "consent", "upload", "accent"):
        assert answers[name].status_code == 409, name
        assert answers[name].json()["detail"] == DELETED_MEANWHILE
    assert not any((tmp_path / name).exists() for name in PERSONAL)
    # A request sent after the delete is the new setup's, and is let through.
    assert client.post("/api/consent", json={"agreed": True}).status_code == 200
    assert client.post("/api/uploads/photos", files={"file": ("me.png", PNG)}).status_code == 200
