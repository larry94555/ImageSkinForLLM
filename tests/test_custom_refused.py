"""The host's own photo and voice refused where Admin settings turns them off (roadmap R240)."""

import functools
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import test_start_now
from fastapi.testclient import TestClient
from test_start_now import CHOICE, Fetcher, packs_of, renderer

from imageskin import start_now as sn
from imageskin.admin_settings import AdminSettings, CustomUse
from imageskin.app import OWN_TURNED_OFF, create_app
from imageskin.custom_access import (
    IMAGE_REFUSED,
    VOICE_REFUSED,
    own_person_blocked,
    refuse_unless_allowed,
)
from imageskin.uploads import NO_VOICE, PhotoResult, UploadStore, VoiceSample

pack = test_start_now.pack  # the fixture: a real, small pack of the person CHOICE names
JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100
WAV = b"RIFF" + b"\0" * 100
RECORDINGS = VoiceSample(2, 40, 35, None)  # recordings that passed: the own voice is used


@pytest.fixture
def client(tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        "imageskin.app.StartNow",
        functools.partial(sn.StartNow, packs=packs_of(pack), fetch=Fetcher(pack)),
    )
    browser = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda photo: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=renderer([]),
            ask_llm=lambda messages: "Hello there",
        )
    )
    browser.post("/api/consent", json={"agreed": True})
    return browser


def turn_off(client: TestClient, image: bool, voice: bool) -> None:
    client.app.state.admin_settings.change(  # type: ignore[attr-defined]
        {"disable_custom_image": image, "disable_custom_voice": voice}
    )


def own_person_accepted(client: TestClient) -> None:
    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    client.post("/api/prepare")
    client.app.state.prepare_job.wait(10)  # type: ignore[attr-defined]
    assert client.post("/api/review", json={"decision": "accept"}).status_code == 200


@pytest.mark.parametrize(
    ("use", "image", "voice", "refused"),
    [
        (CustomUse(True, True), True, True, None),
        (CustomUse(False, True), True, False, IMAGE_REFUSED),
        (CustomUse(False, False), True, True, IMAGE_REFUSED),  # the photo is said first
        (CustomUse(True, False), True, True, VOICE_REFUSED),
        (CustomUse(False, False), False, False, None),  # nothing of their own asked for
    ],
)
def test_refuse_unless_allowed(
    use: CustomUse, image: bool, voice: bool, refused: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    from fastapi import HTTPException

    with caplog.at_level(logging.WARNING):
        if refused is None:
            refuse_unless_allowed(use, image, voice, "h@example.com", "/api/x")
            assert not caplog.records
            return
        with pytest.raises(HTTPException) as e:
            refuse_unless_allowed(use, image, voice, "h@example.com", "/api/x")
    assert e.value.status_code == 403 and e.value.detail == refused
    record = caplog.records[0]
    kind = "image" if refused == IMAGE_REFUSED else "voice"
    assert record.getMessage() == f"Custom {kind} refused"
    assert (record.__dict__["host"], record.__dict__["route"]) == ("h@example.com", "/api/x")


def test_own_person_blocked() -> None:
    assert own_person_blocked(CustomUse(False, True), True, True)
    assert own_person_blocked(CustomUse(True, False), True, True)
    assert not own_person_blocked(CustomUse(True, False), True, False)  # a ready-made voice
    assert not own_person_blocked(CustomUse(False, False), False, False)


def test_uploads_are_refused_by_kind(client: TestClient) -> None:
    turn_off(client, image=True, voice=False)
    photo = client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    assert photo.status_code == 403 and photo.json()["detail"] == IMAGE_REFUSED
    assert client.put("/api/uploads/photos/chosen", json={"id": "0" * 32}).status_code == 403
    assert client.post(f"/api/uploads/photos/{'0' * 32}/check").status_code == 403
    assert client.put("/api/ready-voice", json={"voice": "af_heart"}).status_code == 403
    # A recording is still allowed.
    sound = client.post("/api/uploads/sounds", files={"file": ("me.wav", WAV)})
    assert sound.status_code != 403

    turn_off(client, image=False, voice=True)
    sound = client.post("/api/uploads/sounds", files={"file": ("me.wav", WAV)})
    assert sound.status_code == 403 and sound.json()["detail"] == VOICE_REFUSED
    assert client.put("/api/accent", json={"accent": "own"}).status_code == 403
    assert client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)}).status_code == 200


def test_prepare_with_own_photo_or_voice_is_refused(client: TestClient) -> None:
    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    turn_off(client, image=True, voice=False)
    refused = client.post("/api/prepare")
    assert refused.status_code == 403 and refused.json()["detail"] == IMAGE_REFUSED

    turn_off(client, image=False, voice=True)
    with patch.object(UploadStore, "voice_sample", return_value=RECORDINGS):
        refused = client.post("/api/prepare")
    assert refused.status_code == 403 and refused.json()["detail"] == VOICE_REFUSED
    # With no recordings the photo speaks in a ready-made voice (item 59): that is allowed.
    with patch.object(UploadStore, "voice_sample", return_value=VoiceSample(0, 0, 0, NO_VOICE)):
        assert client.post("/api/prepare").status_code == 200


def test_the_avatars_own_voice_is_refused(client: TestClient) -> None:
    assert client.post("/api/start-now", json=vars(CHOICE)).status_code == 200
    client.app.state.start_now.wait(10)  # type: ignore[attr-defined]
    turn_off(client, image=False, voice=True)
    refused = client.put("/api/start-now/own-voice", json={"agreed": True})
    assert refused.status_code == 403 and refused.json()["detail"] == VOICE_REFUSED
    # A default person with neither turned off needs nothing of the host's own.
    turn_off(client, image=True, voice=True)
    assert client.post("/api/start-now", json=vars(CHOICE)).status_code == 200


def test_an_accepted_own_person_waits_for_a_default_one(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with patch.object(UploadStore, "voice_sample", return_value=RECORDINGS):
        own_person_accepted(client)
        assert client.get("/api/review").json()["accepted"] is True

        turn_off(client, image=True, voice=False)
        review = client.get("/api/review").json()
        assert review["accepted"] is False and review["own_turned_off"] is True
        with caplog.at_level(logging.WARNING):
            chat = client.post("/api/chat", json={"message": "Hello"})
        assert chat.status_code == 403 and chat.json()["detail"] == OWN_TURNED_OFF
        assert "Chat refused: the own photo or voice is turned off" in caplog.text
        assert client.post("/api/review", json={"decision": "accept"}).status_code == 403

        # Choosing a default person opens the chat again; the own files are kept.
        assert client.post("/api/start-now", json=vars(CHOICE)).status_code == 200
        client.app.state.start_now.wait(10)  # type: ignore[attr-defined]
        assert client.get("/api/review").json()["accepted"] is True
        assert len(client.get("/api/uploads/photos").json()) == 1
        refused = client.delete("/api/start-now")
        assert refused.status_code == 403 and refused.json()["detail"] == IMAGE_REFUSED

        # Turned on again, the host's own is back as it was.
        turn_off(client, image=False, voice=False)
        assert client.delete("/api/start-now").status_code == 200
        assert client.get("/api/review").json()["accepted"] is True


def test_the_avatar_speaks_in_a_ready_made_voice_when_own_voices_are_off(
    client: TestClient,
) -> None:
    app = client.app
    job = app.state.prepare_job  # type: ignore[attr-defined]
    assert client.post("/api/start-now", json=vars(CHOICE)).status_code == 200
    app.state.start_now.wait(10)  # type: ignore[attr-defined]
    with patch.object(UploadStore, "voice_sample", return_value=RECORDINGS):
        assert client.put("/api/start-now/own-voice", json={"agreed": True}).status_code == 200
        client.post("/api/prepare")
        job.wait(10)
        assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
        assert client.get("/api/review").json()["voice_accepted"] is True
        voice_ready = job._prepare_voice
        assert not voice_ready._ready_made()  # the replies speak in the host's voice

        turn_off(client, image=True, voice=True)
        # Still a default person, so the chat stays open, in its ready-made voice.
        assert client.get("/api/review").json()["accepted"] is True
        assert voice_ready._ready_made()


def test_defaults_turn_both_off(tmp_path: Path) -> None:
    assert AdminSettings().disable_custom_image and AdminSettings().disable_custom_voice
