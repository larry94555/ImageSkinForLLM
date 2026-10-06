import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin import __version__
from imageskin.app import create_app


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
    assert '<script type="module" src="/js/main.js">' in page.text
    for asset in ("/js/main.js", "/js/router.js", "/js/api.js", "/styles.css"):
        assert client.get(asset).status_code == 200, asset
