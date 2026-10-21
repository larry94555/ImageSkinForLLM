"""Back to your own photo and voice from a ready-made avatar, once their sample is accepted
(Larry's test of PR #128)."""

import functools
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import test_start_now
from fastapi.testclient import TestClient
from test_start_now import CHOICE, Fetcher, packs_of, renderer

from imageskin import start_now as sn
from imageskin.app import OWN_NOT_ACCEPTED, create_app
from imageskin.uploads import PhotoResult, UploadStore, VoiceSample

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
