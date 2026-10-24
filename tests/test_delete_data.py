"""Delete my data (roadmap R31): the person's files are removed and setup starts again; the PDFs
and all made from them go too (R31a)."""

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
from test_lessons_ahead import TopicLlm
from test_prepare_job import make_job
from test_topics import riemann_app
from test_uploads import PNG
from test_wiki_job import PDF, one_page_per_piece, settle, two_pages

from imageskin.app import DELETED_MEANWHILE, create_app
from imageskin.chat import CLEAR_FAILED, ClearFailed
from imageskin.delete_data import PERSONAL, Deleted, delete_my_data
from imageskin.lessons_ahead import LESSONS_FILE
from imageskin.pdf_reading import Progress, Reading
from imageskin.prepare_job import (
    SAMPLE_BEING_MADE,
    WAIT_TO_DELETE,
    ClipSteps,
    PrepareError,
    PrepareStatus,
)
from imageskin.review import Review

# What isn't the person's, and is kept.
KEPT = (
    "models/faces/face.task",
    "ui-settings.json",
    "default-people/animated_female_professor.png",  # made up, not the person's (R24c)
    "default-people/downloads/animated_female_professor.zip",
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
    "default-person.json",
    "default-person.saving.json",  # left by a save cut short
    "content/pdfs/a.pdf",  # the PDFs and all made from them (R31a)
    "content/read/a.json",
    "content/wiki/a.json",
    "content/wiki/a.edits.json",
    "content/wiki/a.history/1.json",
    "content/wiki/lessons.json",
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


def test_the_engines_forget_the_person_too(tmp_path: Path) -> None:
    """The learned voice and the loaded face held in memory go with the files, so the next
    setup learns and loads the new ones (reviews on PR #109)."""
    forgot: list[str] = []

    class Voice:
        def speak(self, voice: str, text: str) -> None:
            raise AssertionError("not spoken here")

        def forget_voice(self) -> None:
            forgot.append("voice")

    def steps(*args: Any, **kwargs: Any) -> ClipSteps:
        name = "reply face" if kwargs.get("progressive") else "sample face"
        return ClipSteps(
            lambda t, w: None, lambda p, w, o: None, forget=lambda: forgot.append(name)
        )

    with (
        patch("imageskin.app.clip_voice", return_value=(lambda: None, Voice(), "v", "clone")),
        patch("imageskin.app.photoreal_steps", steps),
    ):
        client = chatted(tmp_path)
    assert forgot == []
    assert client.delete("/api/data").json()["left"] == []
    assert sorted(forgot) == ["reply face", "sample face", "voice"]


def pdf_app(tmp_path: Path) -> tuple[Any, TestClient, str]:
    """An app with one PDF read, its wiki built and edited, and a lesson written ahead."""
    app = create_app(tmp_path, read_pdf=two_pages, build_wiki=one_page_per_piece)
    client = TestClient(app)
    pdf = client.post("/api/content", files={"file": ("w.pdf", PDF, "application/pdf")}).json()
    settle(app.state.readings, app.state.wiki)
    client.put(f"/api/wiki/{pdf['id']}-p1", json={"title": "Rain", "summary": "Rain falls."})
    (app.state.wiki.folder / LESSONS_FILE).write_text('{"format": 1, "lessons": {"Rain": {}}}')
    return app, client, pdf["id"]


def test_the_api_deletes_the_pdfs_and_all_made_from_them(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    app, client, pdf_id = pdf_app(tmp_path)
    assert client.get("/api/wiki").json() and (tmp_path / "content" / "read").is_dir()
    assert (app.state.wiki.folder / f"{pdf_id}.edits.json").is_file()
    assert (app.state.wiki.folder / f"{pdf_id}.history").is_dir()
    with caplog.at_level(logging.INFO):
        answer = client.delete("/api/data")
    assert answer.status_code == 200 and answer.json()["left"] == []
    assert "PDFs forgotten" in caplog.text and "PDF removed" in caplog.text
    # Nothing of the PDF is left, on disk or in what the app shows.
    assert not (tmp_path / "content").exists()
    assert client.get("/api/content").json() == []
    assert client.get("/api/wiki").json() == []
    assert client.get("/api/wiki/builds").json() == {}
    assert client.get(f"/api/wiki/{pdf_id}-p1").status_code == 404
    # A PDF added afterwards is read and built as before.
    client.post("/api/content", files={"file": ("x.pdf", PDF, "application/pdf")})
    settle(app.state.readings, app.state.wiki)
    assert len(client.get("/api/content").json()) == 1 and client.get("/api/wiki").json()


def test_a_pdf_that_cant_be_removed_is_listed_as_left(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _, client, pdf_id = pdf_app(tmp_path)
    stuck = tmp_path / "content" / "pdfs" / f"{pdf_id}.pdf"
    unlink = Path.unlink

    def open_elsewhere(self: Path, missing_ok: bool = False) -> None:
        if self == stuck:
            raise PermissionError("in use by another program")
        unlink(self, missing_ok)

    with patch.object(Path, "unlink", open_elsewhere), caplog.at_level(logging.WARNING):
        answer = client.delete("/api/data")
    assert answer.status_code == 200
    assert answer.json()["left"] == [f"content/pdfs/{pdf_id}.pdf"]
    assert "Could not remove the PDF" in caplog.text
    # Its wiki is gone already; clicking again, once it is closed, removes the PDF too.
    assert client.get("/api/wiki").json() == []
    assert client.delete("/api/data").json()["left"] == []
    assert not (tmp_path / "content").exists() and client.get("/api/content").json() == []


def test_a_prepare_refusing_the_delete_keeps_the_pdfs(tmp_path: Path) -> None:
    app, client, pdf_id = pdf_app(tmp_path)
    job = app.state.prepare_job
    with job._lock:
        job._rendering_again = True
    assert client.delete("/api/data").status_code == 409
    assert [p["id"] for p in client.get("/api/content").json()] == [pdf_id]
    assert client.get("/api/wiki").json()


def test_a_lesson_being_written_during_the_delete_saves_nothing_after_it(tmp_path: Path) -> None:
    """With Teach me on, a lesson part the LLM is writing when the data is deleted is not saved
    once it is done, so no content folder comes back (Codex's review)."""
    writing, release = threading.Event(), threading.Event()

    class SlowLlm(TopicLlm):
        def __call__(self, messages: list[Any]) -> str:
            if "main ideas of" in messages[-1]["content"]:
                writing.set()
                release.wait(5)
            return super().__call__(messages)

    client = riemann_app(tmp_path, SlowLlm(), lessons_ahead=True)
    lessons = client.app.state.lessons
    assert client.patch("/api/settings", json={"teach_me": True}).status_code == 200
    assert writing.wait(5)
    answer = client.delete("/api/data")
    release.set()
    lessons.wait()
    assert answer.status_code == 200 and answer.json()["left"] == []
    assert not (tmp_path / "content").exists()
    assert client.get("/api/lessons").json()["saved"] == []


def test_a_pdf_being_read_during_the_delete_stops_and_leaves_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A reading under way stops at its next page and lets its private copy go before the
    content folder is removed. The copy is kept open as Windows would, refusing to delete it
    while it is read (Codex's review)."""
    reading = threading.Event()
    open_copies: set[Path] = set()

    def slow_reader(path: Path, progress: Progress) -> Reading:
        open_copies.add(path)
        try:
            for page in range(1, 501):  # 10 s in all, unless stopped
                progress(page, 500)
                reading.set()
                threading.Event().wait(0.02)
            return two_pages(path, progress)
        finally:
            open_copies.discard(path)

    unlink = Path.unlink

    def as_on_windows(self: Path, missing_ok: bool = False) -> None:
        if self in open_copies:
            raise PermissionError("in use by another program")
        unlink(self, missing_ok)

    client = TestClient(create_app(tmp_path, read_pdf=slow_reader, build_wiki=one_page_per_piece))
    client.post("/api/content", files={"file": ("w.pdf", PDF, "application/pdf")})
    assert reading.wait(5)
    with patch.object(Path, "unlink", as_on_windows), caplog.at_level(logging.INFO):
        answer = client.delete("/api/data")
    assert answer.status_code == 200 and answer.json()["left"] == []
    assert not (tmp_path / "content").exists()
    assert "PDF reading stopped" in caplog.text
    assert client.get("/api/content/readings").json() == {}


def test_content_writes_and_the_delete_wait_for_each_other(tmp_path: Path) -> None:
    """A PDF upload under way when the data is deleted finishes first and is deleted with the
    rest; one that arrives during the delete waits for it and is refused, so nothing comes back;
    one sent afterwards is stored as usual (Codex's review)."""
    client = TestClient(create_app(tmp_path, read_pdf=two_pages, build_wiki=one_page_per_piece))
    store = client.app.state.readings.store  # type: ignore[attr-defined]
    adding, release_add = threading.Event(), threading.Event()
    real_add = store.add

    def slow_add(name: Any, data: Any) -> Any:
        adding.set()
        release_add.wait(5)
        return real_add(name, data)

    answers: dict[str, Any] = {}

    def send(name: str, call: Callable[[], Any]) -> threading.Thread:
        thread = threading.Thread(target=lambda: answers.__setitem__(name, call()))
        thread.start()
        return thread

    def upload(name: str) -> Any:
        return client.post("/api/content", files={"file": (name, PDF, "application/pdf")})

    # An upload already being stored: the delete waits for it, then deletes it.
    with patch.object(store, "add", slow_add):
        before = send("before", lambda: upload("before.pdf"))
        assert adding.wait(5)
        delete = send("delete", lambda: client.delete("/api/data"))
        delete.join(0.3)
        assert delete.is_alive()
        release_add.set()
        before.join(5)
        delete.join(5)
    assert answers["before"].status_code == 200 and answers["delete"].status_code == 200
    assert answers["delete"].json()["left"] == [] and not (tmp_path / "content").exists()

    # An upload, an edit and a rebuild sent while the files are deleted are refused after it.
    deleting, release = threading.Event(), threading.Event()
    real_delete = delete_my_data

    def slow_delete(home: Path) -> Deleted:
        deleting.set()
        release.wait(5)
        return real_delete(home)

    with patch("imageskin.app.delete_my_data", slow_delete):
        delete = send("delete", lambda: client.delete("/api/data"))
        assert deleting.wait(5)
        waiting = [
            send("during", lambda: upload("during.pdf")),
            send("edit", lambda: client.put("/api/wiki/x-p1", json={"title": "T", "summary": "S"})),
            send("rebuild", lambda: client.post(f"/api/content/{'f' * 32}/wiki/rebuild")),
        ]
        waiting[0].join(0.3)
        assert all(thread.is_alive() for thread in waiting)
        release.set()
        for thread in [delete, *waiting]:
            thread.join(5)
    for name in ("during", "edit", "rebuild"):
        assert answers[name].status_code == 409
        assert answers[name].json()["detail"] == DELETED_MEANWHILE
    assert not (tmp_path / "content" / "pdfs").exists() and client.get("/api/content").json() == []

    # Sent afterwards: stored, read and built as usual.
    assert upload("after.pdf").status_code == 200
    settle(client.app.state.readings, client.app.state.wiki)  # type: ignore[attr-defined]
    assert [p["name"] for p in client.get("/api/content").json()] == ["after.pdf"]
    assert client.get("/api/wiki").json()
