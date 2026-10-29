"""Back to your own photo and voice from a ready-made avatar, once their sample is accepted
(Larry's test of PR #128)."""

import functools
import logging
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
import test_start_now
from fastapi.testclient import TestClient
from test_start_now import CHOICE, Fetcher, packs_of, renderer

from imageskin import start_now as sn
from imageskin.app import OWN_NOT_ACCEPTED, WAIT_FOR_AVATAR, create_app
from imageskin.uploads import PhotoResult, UploadStore, VoiceSample
from imageskin.warm_up_time import last_warm_up_s, save_warm_up_s

pack = test_start_now.pack  # the fixture: a real, small pack of the person CHOICE names
JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100


@pytest.fixture
def client(tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        "imageskin.app.StartNow",
        functools.partial(sn.StartNow, packs=packs_of(pack), fetch=Fetcher(pack)),
    )
    return TestClient(
        create_app(
            tmp_path,
            check_photo=lambda photo: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=renderer([]),
            ask_llm=lambda messages: "Hello there",
        )
    )


def choose(client: TestClient) -> None:
    assert client.post("/api/start-now", json=vars(CHOICE)).status_code == 200
    client.app.state.start_now.wait(10)  # type: ignore[attr-defined]


def test_your_own_accepted_sample_is_used_again_at_once(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    client.post("/api/consent", json={"agreed": True})
    photo = client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)}).json()
    with patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)):
        # Before their sample is accepted, there is nothing to switch to.
        choose(client)
        refused = client.delete("/api/start-now")
        assert refused.status_code == 409 and refused.json()["detail"] == OWN_NOT_ACCEPTED
        assert client.get("/api/review").json()["own_sample_accepted"] is False

        # 1. Their own photo and voice, prepared and accepted.
        client.post("/api/prepare")
        client.app.state.prepare_job.wait(10)  # type: ignore[attr-defined]
        assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
        assert client.get("/api/start-now").json()["chosen"] is None
        # 2. A ready-made avatar in the chat: their own sample stays accepted.
        choose(client)
        review = client.get("/api/review").json()
        assert review["default_person"] is True and review["own_sample_accepted"] is True
        # 3. Use your own photo and voice: at once, with nothing prepared again.
        with caplog.at_level(logging.INFO):
            back = client.delete("/api/start-now")
        assert back.status_code == 200 and back.json()["accepted"] is True
        assert any(r.getMessage() == "Switched to your own photo and voice" for r in caplog.records)
        assert client.get("/api/start-now").json()["chosen"] is None
        assert client.get("/api/chat/photo").json()["url"] == f"/api/uploads/photos/{photo['id']}"
        assert client.app.state.start_now.voice() is None  # type: ignore[attr-defined]
        assert client.get("/api/review").json()["accepted"] is True


def test_switching_back_needs_consent(client: TestClient) -> None:
    assert client.delete("/api/start-now").status_code == 403


def test_switching_back_waits_for_an_avatar_being_got_ready(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Review on PR #129: switching back while an avatar was downloaded was undone once it was
    ready, as it was chosen then. Now it is refused until then, and works after."""
    client.post("/api/consent", json={"agreed": True})
    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    saving, go = threading.Event(), threading.Event()
    save = sn.StartNow._save

    def held(self: sn.StartNow, choice: sn.Choice) -> None:
        saving.set()
        go.wait(10)
        save(self, choice)

    with (
        patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)),
        patch.object(sn.StartNow, "_save", held),
    ):
        client.post("/api/prepare")
        client.app.state.prepare_job.wait(10)  # type: ignore[attr-defined]
        assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
        assert client.post("/api/start-now", json=vars(CHOICE)).status_code == 200
        assert saving.wait(10)  # about to choose it
        with caplog.at_level(logging.WARNING):
            refused = client.delete("/api/start-now")
        assert refused.status_code == 409 and refused.json()["detail"] == WAIT_FOR_AVATAR
        assert any("while a person is got ready" in r.getMessage() for r in caplog.records)
        go.set()
        client.app.state.start_now.wait(10)  # type: ignore[attr-defined]
        assert client.get("/api/start-now").json()["chosen"] is not None  # as the page said
        back = client.delete("/api/start-now")
        assert back.status_code == 200
        assert client.get("/api/start-now").json()["chosen"] is None


def test_the_chat_waits_while_your_own_voice_and_face_are_got_ready(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Larry, 2026-10-29: back on his own photo and voice from an avatar, a prompt showed
    Thinking for minutes, while their voice and idle video were got ready again. The chat now
    asks whether it is ready, and says so until it is (R181)."""
    from imageskin.reply_video import ReplyVideos

    client.post("/api/consent", json={"agreed": True})
    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    with patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)):
        client.post("/api/prepare")
        client.app.state.prepare_job.wait(10)  # type: ignore[attr-defined]
        assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
        choose(client)
        client.app.state.reply_warm_up.join(10)  # type: ignore[attr-defined]
        assert client.get("/api/chat/ready").json() == {"ready": True}

        warming, go = threading.Event(), threading.Event()
        warm_up = ReplyVideos.warm_up

        def held(self: ReplyVideos, photo: Path) -> None:
            warming.set()
            go.wait(10)
            warm_up(self, photo)

        with patch.object(ReplyVideos, "warm_up", held), caplog.at_level(logging.INFO):
            assert client.delete("/api/start-now").status_code == 200
            assert warming.wait(10)
            waiting = client.get("/api/chat/ready").json()
            # The last warm-up, after the avatar was chosen, was timed (R183): a few seconds
            # left at most, or None once this one takes longer.
            assert waiting["ready"] is False and "left_s" in waiting
            go.set()
            client.app.state.reply_warm_up.join(10)  # type: ignore[attr-defined]
        assert client.get("/api/chat/ready").json() == {"ready": True}
        done = [r for r in caplog.records if r.getMessage() == "Reply warm-up done"]
        assert done and isinstance(done[-1].__dict__["duration_ms"], float)


def test_the_chat_says_how_many_seconds_are_left_from_the_last_warm_up(
    client: TestClient, tmp_path: Path
) -> None:
    """R183: after a rebuild, the chat said only that it was getting ready, for over a minute.
    Each warm-up's length is kept, and while the next runs the chat is told the seconds left."""
    from imageskin.reply_video import ReplyVideos

    client.post("/api/consent", json={"agreed": True})
    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    with patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)):
        client.post("/api/prepare")
        client.app.state.prepare_job.wait(10)  # type: ignore[attr-defined]
        assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
        client.app.state.reply_warm_up.join(10)  # type: ignore[attr-defined]
        assert last_warm_up_s(tmp_path) is not None  # the warm-up after the accept was timed
        choose(client)
        client.app.state.reply_warm_up.join(10)  # type: ignore[attr-defined]
        save_warm_up_s(tmp_path, 75)  # as if the last one took 75 s

        warming, go = threading.Event(), threading.Event()
        warm_up = ReplyVideos.warm_up

        def held(self: ReplyVideos, photo: Path) -> None:
            warming.set()
            go.wait(10)
            warm_up(self, photo)

        with patch.object(ReplyVideos, "warm_up", held):
            assert client.delete("/api/start-now").status_code == 200
            assert warming.wait(10)
            waiting = client.get("/api/chat/ready").json()
            assert waiting["ready"] is False and 70 <= waiting["left_s"] <= 75
            go.set()
            client.app.state.reply_warm_up.join(10)  # type: ignore[attr-defined]
        assert client.get("/api/chat/ready").json() == {"ready": True}
        assert last_warm_up_s(tmp_path) < 75  # type: ignore[operator]  # this one's, kept for next


def test_the_chat_ready_needs_a_person(client: TestClient) -> None:
    assert client.get("/api/chat/ready").status_code == 403  # before consent
