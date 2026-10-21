"""Use my own photo with a default person's voice (roadmap R24d, features.md item 59)."""

import functools
import logging
from pathlib import Path
from typing import Any

import pytest
import test_start_now
from fastapi.testclient import TestClient
from test_start_now import CHOICE, Fetcher, packs_of, renderer, started

from imageskin import start_now as sn
from imageskin.app import create_app
from imageskin.consent import load_consent, save_consent
from imageskin.uploads import PhotoResult

pack = test_start_now.pack  # the fixture: a real, small pack of the person CHOICE names
JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100


def no_problems(photo: Path) -> PhotoResult:
    return PhotoResult([], 80)


# The default person's choice


def test_own_photo_keeps_the_default_voice_until_another_person_is_chosen(
    tmp_path: Path, pack: Path
) -> None:
    person = started(tmp_path, pack)
    with pytest.raises(ValueError, match="No ready-made avatar"):
        person.set_own_photo(True)
    person.start(CHOICE)
    person.wait(10)
    assert person.own_photo() is False and person.kept_voice() is None
    assert person.rendering_voice() is None
    person.set_own_photo(True)
    assert person.own_photo() is True and person.chosen() == CHOICE
    # Prepare speaks the user's own photo in the default voice.
    assert person.kept_voice() == ("b", "bf_emma") == person.rendering_voice()
    person.set_own_photo(False)
    assert person.own_photo() is False
    person.set_own_photo(True)
    person.start(CHOICE)  # chosen again: the default picture again
    assert person.own_photo() is False


def test_own_photo_needs_a_readable_choice(tmp_path: Path, pack: Path) -> None:
    person = started(tmp_path, pack)
    (tmp_path / sn.CHOICE_FILE).write_text("[1]", encoding="utf-8")
    assert person.own_photo() is False and person.chosen() is None


# Consent for the photos only


def test_consent_for_the_photos_only_is_saved_and_never_replaces_consent_for_both(
    tmp_path: Path,
) -> None:
    assert save_consent(tmp_path, photo_only=True).photo_only is True
    assert load_consent(tmp_path).photo_only is True
    assert save_consent(tmp_path).photo_only is False  # consent for both replaces it
    kept = save_consent(tmp_path, photo_only=True)
    assert kept.photo_only is False and load_consent(tmp_path).photo_only is False


# The app


@pytest.fixture
def client(tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        "imageskin.app.StartNow",
        functools.partial(sn.StartNow, packs=packs_of(pack), fetch=Fetcher(pack)),
    )
    voices: list[str] = []
    client = TestClient(
        create_app(
            tmp_path / "home",
            check_photo=no_problems,
            prepare_voice=lambda: voices.append("own voice prepared"),
            prepare_face=lambda photo, progress: None,
            render_clip=renderer([]),
            ask_llm=lambda messages: "Hello there",
        )
    )
    client.app.state.voices = voices  # type: ignore[attr-defined]
    return client


def choose(client: TestClient) -> None:
    assert client.post("/api/start-now", json=vars(CHOICE)).status_code == 200
    client.app.state.start_now.wait(10)  # type: ignore[attr-defined]


def prepared(client: TestClient) -> dict[str, Any]:
    assert client.post("/api/prepare").status_code == 200
    client.app.state.prepare_job.wait(10)  # type: ignore[attr-defined]
    status: dict[str, Any] = client.get("/api/prepare").json()
    return status


def test_own_photo_is_refused_without_a_default_person(client: TestClient) -> None:
    refused = client.put("/api/start-now/own-photo", json={"own": True})
    assert refused.status_code == 409 and refused.json()["detail"] == sn.NOT_CHOSEN


def test_your_own_photo_speaks_in_the_default_voice_once_accepted(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    choose(client)
    with caplog.at_level(logging.INFO):
        status = client.put("/api/start-now/own-photo", json={"own": True}).json()
    assert status["own_photo"] is True and status["own_photo_in_use"] is False
    assert any(r.getMessage() == "Own photo chosen" for r in caplog.records)

    # Consent for the photos only: enough for a photo, not for a recording.
    assert client.post("/api/consent", json={"agreed": True, "photo_only": True}).status_code == 200
    photo = client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)}).json()
    sound = client.post("/api/uploads/sounds", files={"file": ("me.wav", b"RIFF")})
    assert sound.status_code == 403 and "photos only" in sound.json()["detail"]

    # Prepared with no recordings, in the default voice: the own voice is never prepared.
    with caplog.at_level(logging.INFO):
        done = prepared(client)
    assert done["state"] == "done" and done["voice_id"] == "preset:bf_emma"
    assert client.app.state.voices == []  # type: ignore[attr-defined]
    assert any(r.getMessage() == "Keeping the ready-made voice" for r in caplog.records)

    # Under review: the chat stays open with the default person meanwhile.
    review = client.get("/api/review").json()
    assert review == {
        "accepted": True,
        "accepted_at": None,
        "sample_accepted": False,
        "default_person": True,
        "own_photo": True,
    }
    assert client.get("/api/chat/photo").json()["url"].startswith("/api/start-now/picture")

    with caplog.at_level(logging.INFO):
        assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
    assert any(r.getMessage() == "Own photo in use with the default voice" for r in caplog.records)
    assert client.get("/api/review").json()["sample_accepted"] is True
    now = client.get("/api/start-now").json()
    assert now["chosen"] == vars(CHOICE) and now["own_photo_in_use"] is True
    # The chat shows the photo, says the lines Prepare made with it, and speaks in the default
    # person's voice.
    assert client.get("/api/chat/photo").json()["url"] == f"/api/uploads/photos/{photo['id']}"
    assert client.get("/api/start-now/lines/goodbye").content == b"mp4"
    assert client.app.state.start_now.voice() == ("b", "bf_emma")  # type: ignore[attr-defined]
    assert client.post("/api/chat", json={"prompt": "Hi"}).json()["content"] == "Hello there"

    # Back to the default picture: the sample in the default voice no longer counts.
    back = client.put("/api/start-now/own-photo", json={"own": False}).json()
    assert back["own_photo"] is False and back["own_photo_in_use"] is False
    assert client.get("/api/chat/photo").json()["url"].startswith("/api/start-now/picture")
    assert client.get("/api/prepare").json()["state"] == "idle"
