"""A ready-made voice until recordings are added (features.md item 59)."""

import logging
import threading
from pathlib import Path
from typing import Any

import pytest
import test_start_now
from fastapi.testclient import TestClient
from test_start_now import CHOICE, started

from imageskin.app import WAIT_FOR_PREPARE_VOICE, create_app
from imageskin.ready_voice import DEFAULT, FILENAME, load_ready_voice, preset, save_ready_voice
from imageskin.uploads import PhotoResult

pack = test_start_now.pack  # the fixture: a real, small pack of the person CHOICE names
JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100


def test_the_ready_voice_is_saved_and_has_a_default(tmp_path: Path) -> None:
    assert load_ready_voice(tmp_path) == DEFAULT == "af_heart"
    assert save_ready_voice(tmp_path, "bm_george") == "bm_george"
    assert load_ready_voice(tmp_path) == "bm_george"
    assert preset("bm_george") == ("b", "bm_george")
    with pytest.raises(ValueError, match="'nobody' is not one of"):
        save_ready_voice(tmp_path, "nobody")
    # A nonbinary avatar's blended voice (R24b3) is a ready-made voice like the others.
    assert save_ready_voice(tmp_path, "bf_emma,bm_george") == "bf_emma,bm_george"
    assert load_ready_voice(tmp_path) == "bf_emma,bm_george"
    assert preset("af_heart,am_michael") == ("a", "af_heart,am_michael")


def test_a_broken_or_unknown_ready_voice_is_the_default(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / FILENAME).write_text('{"voice": "nobody"}', encoding="utf-8")
    assert load_ready_voice(tmp_path) == DEFAULT
    (tmp_path / FILENAME).write_text("not json", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        assert load_ready_voice(tmp_path) == DEFAULT
    assert any(r.getMessage() == "Could not read the ready-made voice" for r in caplog.records)


def test_choosing_an_avatar_makes_its_voice_the_ready_one(tmp_path: Path, pack: Path) -> None:
    person = started(tmp_path, pack)
    person.start(CHOICE)
    person.wait(10)
    assert load_ready_voice(tmp_path) == "bf_emma"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    voices: list[str] = []
    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda photo: PhotoResult([], 80),
            prepare_voice=lambda: voices.append("own voice prepared"),
            prepare_face=lambda photo, progress: None,
            render_clip=test_start_now.renderer([]),
            ask_llm=lambda messages: "Hello there",
        )
    )
    client.app.state.voices = voices  # type: ignore[attr-defined]
    return client


def prepared(client: TestClient) -> dict[str, Any]:
    assert client.post("/api/prepare").status_code == 200
    client.app.state.prepare_job.wait(10)  # type: ignore[attr-defined]
    status: dict[str, Any] = client.get("/api/prepare").json()
    return status


def test_without_recordings_your_photo_speaks_in_the_ready_voice(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    assert client.get("/api/ready-voice").status_code == 403  # consent first
    client.post("/api/consent", json={"agreed": True})
    assert client.get("/api/ready-voice").json() == {"voice": "af_heart", "in_use": True}
    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})

    # Prepare no longer waits for recordings: it keeps the ready-made voice.
    with caplog.at_level(logging.INFO):
        done = prepared(client)
    assert done["state"] == "done" and done["voice_id"] == "preset:af_heart"
    assert client.app.state.voices == []  # type: ignore[attr-defined]
    assert any(r.getMessage() == "Keeping the ready-made voice" for r in caplog.records)
    assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
    reply = client.post("/api/chat", json={"prompt": "Hi"})
    assert reply.status_code == 200 and reply.json()["content"] == "Hello there"

    # Another ready-made voice makes the sample again, in it.
    chosen = client.put("/api/ready-voice", json={"voice": "bm_george"})
    assert chosen.json() == {"voice": "bm_george", "in_use": True}
    client.app.state.prepare_job.wait(10)  # type: ignore[attr-defined]
    again = client.get("/api/prepare").json()
    assert again["state"] == "done" and again["voice_id"] == "preset:bm_george"


def test_the_ready_voice_waits_for_a_running_prepare(tmp_path: Path) -> None:
    release = threading.Event()

    def prepare_face(photo: Path, progress: object) -> None:
        release.wait(10)

    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda photo: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=prepare_face,
            render_clip=test_start_now.renderer([]),
            ask_llm=lambda messages: "Hello there",
        )
    )
    client.post("/api/consent", json={"agreed": True})
    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    assert client.post("/api/prepare").status_code == 200
    try:
        refused = client.put("/api/ready-voice", json={"voice": "bm_george"})
        assert refused.status_code == 409
        assert refused.json()["detail"] == WAIT_FOR_PREPARE_VOICE
        assert load_ready_voice(tmp_path) == DEFAULT
    finally:
        release.set()
    client.app.state.prepare_job.wait(10)  # type: ignore[attr-defined]
    done = client.get("/api/prepare").json()
    assert done["state"] == "done" and done["voice_id"] == "preset:af_heart"


def test_an_unknown_ready_voice_is_refused(client: TestClient) -> None:
    client.post("/api/consent", json={"agreed": True})
    refused = client.put("/api/ready-voice", json={"voice": "nobody"})
    assert refused.status_code == 400 and "is not a ready-made voice" in refused.json()["detail"]
