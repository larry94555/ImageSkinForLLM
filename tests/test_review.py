import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin.app import create_app
from imageskin.prepare_job import PrepareStatus
from imageskin.review import NOT_READY, accept, load_review, withdraw
from imageskin.uploads import PhotoResult, UploadStore, VoiceSample

DONE = PrepareStatus(
    "done", "photo1", voice_id="clone:abc", percent=100, finished_at="2026-10-09T15:00:00+00:00"
)


def test_a_sample_is_not_accepted_until_it_is(tmp_path: Path) -> None:
    assert load_review(tmp_path, DONE).accepted is False


def test_accepting_the_ready_sample_is_saved(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        review = accept(tmp_path / "home", DONE)
    assert review.accepted and review.accepted_at
    assert load_review(tmp_path / "home", DONE) == review
    assert "Sample accepted" in caplog.text


def test_there_is_nothing_to_accept_before_prepare_finishes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Prepare"):
        accept(tmp_path, PrepareStatus("running", "photo1"))
    assert not (tmp_path / "review.json").exists()


@pytest.mark.parametrize(
    "later",
    [
        PrepareStatus("idle"),  # the photo or the recordings changed
        PrepareStatus("running", "photo1"),  # preparing again
        PrepareStatus("done", "photo2", voice_id="clone:abc", finished_at=DONE.finished_at),
        PrepareStatus("done", "photo1", voice_id="clone-british:abc", finished_at=DONE.finished_at),
        PrepareStatus("done", "photo1", voice_id="clone:abc", finished_at="2026-10-09T16:00:00"),
    ],
)
def test_a_sample_made_again_needs_reviewing_again(tmp_path: Path, later: PrepareStatus) -> None:
    accept(tmp_path, DONE)
    assert load_review(tmp_path, later).accepted is False


def test_rejecting_withdraws_the_acceptance(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    accept(tmp_path, DONE)
    with caplog.at_level(logging.INFO):
        assert withdraw(tmp_path, "reject-voice").accepted is False
        withdraw(tmp_path, "reject-voice")  # nothing left to withdraw: still fine
    assert load_review(tmp_path, DONE).accepted is False
    assert "withdrawn" in caplog.text and "nothing to withdraw" in caplog.text


@pytest.mark.parametrize("saved", ["not json", '["accepted"]'])
def test_a_broken_review_file_means_not_accepted(
    tmp_path: Path, saved: str, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "review.json").write_text(saved)
    assert load_review(tmp_path, DONE).accepted is False


def test_an_unreadable_review_file_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "review.json").mkdir()  # a folder can't be read as a file
    with caplog.at_level(logging.ERROR):
        assert load_review(tmp_path, DONE).accepted is False
    assert "Could not read the review" in caplog.text


def test_an_acceptance_without_a_time_still_counts(tmp_path: Path) -> None:
    key = {"photo_id": "photo1", "voice_id": "clone:abc", "finished_at": DONE.finished_at}
    (tmp_path / "review.json").write_text(json.dumps({"sample": key}))
    assert load_review(tmp_path, DONE).accepted is True


JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100


def write_clip(photo: Path, text: str, output: Path) -> None:
    output.write_text(text)


def test_the_api_accepts_the_sample_and_rejects_it(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=write_clip,
        )
    )
    assert client.get("/api/review").status_code == 403  # consent first
    client.post("/api/consent", json={"agreed": True})
    assert client.get("/api/review").json() == {"accepted": False, "accepted_at": None}
    refused = client.post("/api/review", json={"decision": "accept"})
    assert refused.status_code == 409 and refused.json()["detail"] == NOT_READY
    assert client.post("/api/review", json={"decision": "maybe"}).status_code == 422

    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    with patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)):
        client.post("/api/prepare")
        client.app.state.prepare_job.wait(5)  # type: ignore[attr-defined]
        accepted = client.post("/api/review", json={"decision": "accept"}).json()
        assert accepted["accepted"] is True
        assert client.get("/api/review").json() == accepted
        rejected = client.post("/api/review", json={"decision": "reject-image"}).json()
        assert rejected == {"accepted": False, "accepted_at": None}
        assert client.get("/api/review").json()["accepted"] is False
