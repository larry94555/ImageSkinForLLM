"""A ready-made avatar in your own voice (roadmap R24d): the avatar's picture, prepared and
reviewed with the user's recordings, and its ready-made voice until that sample is accepted."""

import functools
import logging
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
import test_start_now
from fastapi.testclient import TestClient
from test_start_now import CHOICE, Fetcher, packs_of

from imageskin import start_now as sn
from imageskin.app import (
    NO_AVATAR,
    OWN_NOT_ACCEPTED,
    VOICE_CONSENT_NEEDED,
    WAIT_FOR_PREPARE_AVATAR,
    create_app,
)
from imageskin.prepare_job import AVATAR_PREFIX, PrepareError, PrepareStatus
from imageskin.uploads import NO_VOICE, PhotoResult, UploadStore, VoiceSample

pack = test_start_now.pack  # the fixture: a real, small pack of the person CHOICE names
RECORDINGS = VoiceSample(2, 40, 35, None)  # recordings that passed the checks
JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100


@pytest.fixture
def rendered() -> list[tuple[str, str]]:
    """The picture each clip was rendered from, by file name, and what it said."""
    return []


class Gate:
    """Holds Prepare's voice step, when closed, until opened: Prepare is then running."""

    def __init__(self) -> None:
        self.reached = threading.Event()
        self.opened = threading.Event()
        self.opened.set()

    def __call__(self) -> None:
        self.reached.set()
        assert self.opened.wait(10)


@pytest.fixture
def gate() -> Gate:
    return Gate()


@pytest.fixture
def client(
    tmp_path: Path,
    pack: Path,
    rendered: list[tuple[str, str]],
    gate: Gate,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setattr(
        "imageskin.app.StartNow",
        functools.partial(sn.StartNow, packs=packs_of(pack), fetch=Fetcher(pack)),
    )

    def render(picture: Path, text: str, output: Path) -> None:
        assert picture.is_file()
        rendered.append((picture.name, text))
        output.write_bytes(b"mp4")

    return TestClient(
        create_app(
            tmp_path,
            check_photo=lambda photo: PhotoResult([], 80),
            prepare_voice=gate,
            prepare_face=lambda photo, progress: None,
            render_clip=render,
            ask_llm=lambda messages: "Hello there",
        )
    )


def choose(client: TestClient) -> None:
    assert client.post("/api/start-now", json=vars(CHOICE)).status_code == 200
    client.app.state.start_now.wait(10)  # type: ignore[attr-defined]


def prepare(client: TestClient) -> PrepareStatus:
    assert client.post("/api/prepare").status_code == 200
    job = client.app.state.prepare_job  # type: ignore[attr-defined]
    job.wait(10)
    status: PrepareStatus = job.status()
    return status


def ready_made(client: TestClient) -> bool:
    """Whether the replies need no voice prepared: they speak in a ready-made one."""
    voice_ready = client.app.state.prepare_job._prepare_voice  # type: ignore[attr-defined]
    return bool(voice_ready._ready_made())


def test_avatar_speaks_in_your_voice_once_its_sample_is_accepted(
    client: TestClient, rendered: list[tuple[str, str]], caplog: pytest.LogCaptureFixture
) -> None:
    choose(client)
    picture = client.app.state.start_now.picture()  # type: ignore[attr-defined]
    rendered.clear()
    with caplog.at_level(logging.INFO):
        review = client.put("/api/start-now/own-voice", json={"agreed": True})
    assert review.status_code == 200
    assert review.json()["own_voice"] is True and review.json()["voice_accepted"] is False
    assert any(r.getMessage() == "Avatar's voice chosen" for r in caplog.records)
    # Until the sample is accepted, the chat stays open in the ready-made voice.
    assert review.json()["accepted"] is True and ready_made(client)

    with patch.object(UploadStore, "voice_sample", return_value=RECORDINGS):
        status = prepare(client)
        assert status.state == "done", status.error
        assert status.photo_id == f"{AVATAR_PREFIX}{picture.stem}"
        # The sample and the lines are the avatar's picture, not an uploaded photo.
        assert {name for name, _ in rendered} == {picture.name}
        assert ready_made(client)
        with caplog.at_level(logging.INFO):
            accepted = client.post("/api/review", json={"decision": "accept"})
        assert accepted.status_code == 200
        assert any(
            r.getMessage() == "The avatar speaks in your own voice now" for r in caplog.records
        )

        # Still the avatar in the chat, now in the user's own voice.
        assert client.get("/api/start-now").json()["chosen"] is not None
        review = client.get("/api/review").json()
        assert review["voice_accepted"] is True and review["own_sample_accepted"] is False
        assert not ready_made(client)
        photo = client.get("/api/chat/photo").json()
        assert photo["url"].startswith("/api/start-now/picture")
        # Goodbye is the one Prepare made in the user's voice.
        job = client.app.state.prepare_job  # type: ignore[attr-defined]
        line = client.get("/api/start-now/lines/goodbye")
        assert line.status_code == 200 and line.content == job.clip("goodbye").read_bytes()

        # There is no sample of their own photo to switch to.
        refused = client.delete("/api/start-now")
        assert refused.status_code == 409 and refused.json()["detail"] == OWN_NOT_ACCEPTED

        # The ready-made voice again: what was prepared no longer counts.
        back = client.delete("/api/start-now/own-voice")
        assert back.status_code == 200 and back.json()["own_voice"] is False
        assert ready_made(client)
        assert client.get("/api/prepare").json()["state"] == "idle"


def test_prepare_needs_recordings_for_the_avatar(client: TestClient) -> None:
    """Without recordings the avatar's own ready-made voice is not kept as the user's photo's
    would be (item 59): Prepare asks for them."""
    choose(client)
    client.put("/api/start-now/own-voice", json={"agreed": True})
    with patch.object(UploadStore, "voice_sample", return_value=VoiceSample(0, 0, 0, NO_VOICE)):
        refused = client.post("/api/prepare")
    assert refused.status_code == 409 and refused.json()["detail"] == NO_VOICE


def test_consent_is_needed(client: TestClient) -> None:
    choose(client)
    refused = client.put("/api/start-now/own-voice", json={"agreed": False})
    assert refused.status_code == 400 and refused.json()["detail"] == VOICE_CONSENT_NEEDED
    assert client.get("/api/consent").json()["agreed"] is False
    assert client.put("/api/start-now/own-voice", json={"agreed": True}).status_code == 200
    assert client.get("/api/consent").json()["agreed"] is True  # the recordings can be added


def test_an_avatar_is_needed(client: TestClient) -> None:
    refused = client.put("/api/start-now/own-voice", json={"agreed": True})
    assert refused.status_code == 409 and refused.json()["detail"] == NO_AVATAR


def test_ready_voice_waits_for_the_avatar_being_prepared(
    client: TestClient, gate: Gate, rendered: list[tuple[str, str]]
) -> None:
    """Codex's review of PR #131: switching back mid-Prepare left the job without its picture.
    Now it is refused until Prepare has finished, with the avatar still in the user's voice."""
    choose(client)
    client.put("/api/start-now/own-voice", json={"agreed": True})
    picture = client.app.state.start_now.picture()  # type: ignore[attr-defined]
    rendered.clear()
    gate.opened.clear()
    with patch.object(UploadStore, "voice_sample", return_value=RECORDINGS):
        assert client.post("/api/prepare").json()["state"] == "running"
        assert gate.reached.wait(10)  # Prepare holds in its voice step
        refused = client.delete("/api/start-now/own-voice")
        assert refused.status_code == 409 and refused.json()["detail"] == WAIT_FOR_PREPARE_AVATAR
        assert client.app.state.start_now.own_voice() is True  # type: ignore[attr-defined]
        gate.opened.set()
        job = client.app.state.prepare_job  # type: ignore[attr-defined]
        job.wait(10)
        assert job.status().state == "done"  # for the avatar, as it was asked
        assert {name for name, _ in rendered} == {picture.name}
        assert client.delete("/api/start-now/own-voice").status_code == 200


def test_own_voice_waits_for_your_own_photo_being_prepared(client: TestClient, gate: Gate) -> None:
    """A Prepare of the user's own photo started first is not switched to the avatar midway."""
    client.post("/api/consent", json={"agreed": True})
    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    choose(client)
    gate.opened.clear()
    with patch.object(UploadStore, "voice_sample", return_value=RECORDINGS):
        assert client.post("/api/prepare").json()["state"] == "running"
        assert gate.reached.wait(10)
        refused = client.put("/api/start-now/own-voice", json={"agreed": True})
        assert refused.status_code == 409 and refused.json()["detail"] == WAIT_FOR_PREPARE_AVATAR
        assert client.app.state.start_now.own_voice() is False  # type: ignore[attr-defined]
        gate.opened.set()
        client.app.state.prepare_job.wait(10)  # type: ignore[attr-defined]
        assert client.put("/api/start-now/own-voice", json={"agreed": True}).status_code == 200


def test_the_change_is_refused_while_a_sample_is_made_again(client: TestClient) -> None:
    choose(client)
    job = client.app.state.prepare_job  # type: ignore[attr-defined]
    with patch.object(type(job), "change_voice", side_effect=PrepareError("busy")):
        refused = client.put("/api/start-now/own-voice", json={"agreed": True})
    assert refused.status_code == 409 and refused.json()["detail"] == "busy"


def test_choosing_an_avatar_again_brings_its_ready_made_voice(client: TestClient) -> None:
    choose(client)
    client.put("/api/start-now/own-voice", json={"agreed": True})
    assert client.app.state.start_now.own_voice() is True  # type: ignore[attr-defined]
    choose(client)
    assert client.app.state.start_now.own_voice() is False  # type: ignore[attr-defined]


def test_ready_voice_again_without_an_avatar_does_nothing(client: TestClient) -> None:
    client.post("/api/consent", json={"agreed": True})
    back = client.delete("/api/start-now/own-voice")
    assert back.status_code == 200 and back.json()["accepted"] is False


def test_own_voice_without_a_choice(tmp_path: Path) -> None:
    start_now = sn.StartNow(tmp_path, lambda picture, text, output: None, packs={})
    assert start_now.own_voice() is False
    with pytest.raises(ValueError):
        start_now.set_own_voice(True)
    (tmp_path / sn.CHOICE_FILE).write_text("not json", encoding="utf-8")
    assert start_now.own_voice() is False
