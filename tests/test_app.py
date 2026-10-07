import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin import __version__
from imageskin.app import STATIC_DIR, create_app, face_checker


def test_health_returns_ok_and_version() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_requests_are_logged_with_duration(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="imageskin.app"):
        TestClient(create_app()).get("/health")
    record = next(r for r in caplog.records if r.getMessage() == "Request handled")
    fields = vars(record)
    assert fields["path"] == "/health"
    assert fields["status"] == 200
    assert fields["duration_ms"] >= 0


def test_failed_requests_are_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)
    with (
        patch("imageskin.app.load_consent", side_effect=RuntimeError("boom")),
        caplog.at_level(logging.ERROR, logger="imageskin.app"),
    ):
        assert client.get("/api/consent").status_code == 500
    assert any(
        r.getMessage() == "Request failed" and vars(r)["path"] == "/api/consent"
        for r in caplog.records
    )


def test_consent_starts_unconfirmed_and_is_saved(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/consent").json() == {"agreed": False, "agreed_at": None}

    saved = client.post("/api/consent", json={"agreed": True})
    assert saved.status_code == 200
    assert saved.json()["agreed"] is True

    # A new app (a restart) still sees it.
    again = TestClient(create_app(tmp_path)).get("/api/consent").json()
    assert again == saved.json()


def test_consent_must_be_ticked(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/consent", json={"agreed": False})
    assert response.status_code == 400
    assert not (tmp_path / "consent.json").exists()


def test_browser_app_is_served(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    page = client.get("/")
    assert page.status_code == 200
    assert 'src="/assets/app.js"' in page.text
    for asset in ("/assets/app.js", "/assets/preact.js", "/assets/index.css"):
        assert client.get(asset).status_code == 200, asset


def test_browser_files_are_sent_compressed(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    with client.stream("GET", "/assets/preact.js", headers={"Accept-Encoding": "gzip"}) as response:
        assert response.headers["content-encoding"] == "gzip"
        sent = sum(len(chunk) for chunk in response.iter_raw())
    assert 0 < sent < (STATIC_DIR / "assets" / "preact.js").stat().st_size / 2


def test_preact_license_ships_with_the_app() -> None:
    # Preact is MIT licensed: its notice must go wherever its code goes, the wheel included.
    notice = (STATIC_DIR / "preact-LICENSE.txt").read_text(encoding="utf-8")
    assert "The MIT License" in notice and "Jason Miller" in notice


JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100


def no_problems(photo: Path) -> list[str]:
    return []


def consented_client(home: Path) -> TestClient:
    client = TestClient(create_app(home, check_photo=no_problems))
    client.post("/api/consent", json={"agreed": True})
    return client


def test_uploads_are_refused_before_consent(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    sent = client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    assert sent.status_code == 403
    assert sent.json()["detail"].startswith("Consent is needed before uploading.")
    assert client.get("/api/uploads/photos").status_code == 403
    assert not (tmp_path / "uploads").exists()


def test_photo_can_be_uploaded_listed_fetched_and_removed(tmp_path: Path) -> None:
    client = consented_client(tmp_path)
    sent = client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG, "text/plain")})
    assert sent.status_code == 200
    upload = sent.json()
    assert upload["name"] == "me.jpg" and upload["format"] == "jpg"
    assert upload["problems"] == []

    assert client.get("/api/uploads/photos").json() == [upload]
    fetched = client.get(f"/api/uploads/photos/{upload['id']}")
    assert fetched.content == JPG
    assert fetched.headers["content-type"] == "image/jpeg"
    assert fetched.headers["x-content-type-options"] == "nosniff"

    assert client.delete(f"/api/uploads/photos/{upload['id']}").json() == {"removed": True}
    assert client.get("/api/uploads/photos").json() == []
    assert client.get(f"/api/uploads/photos/{upload['id']}").status_code == 404
    assert client.delete(f"/api/uploads/photos/{upload['id']}").status_code == 404


def test_upload_errors_are_plain_messages(tmp_path: Path) -> None:
    client = consented_client(tmp_path)
    renamed = client.post("/api/uploads/photos", files={"file": ("me.jpg", b"hello")})
    assert renamed.status_code == 415
    assert renamed.json()["detail"].startswith("This is not a JPG, PNG or HEIC photo.")


def test_unknown_upload_kind_is_rejected(tmp_path: Path) -> None:
    client = consented_client(tmp_path)
    assert client.get("/api/uploads/videos").status_code == 422


def test_face_checks_are_off_without_mediapipe(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with patch("importlib.util.find_spec", return_value=None), caplog.at_level(logging.WARNING):
        assert face_checker(tmp_path) is None
    assert "Face checks are off" in caplog.text


def test_face_checks_are_on_with_mediapipe(tmp_path: Path) -> None:
    with patch("importlib.util.find_spec", return_value=object()):
        check = face_checker(tmp_path)
    assert check is not None
