import logging

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


def test_failed_requests_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="imageskin.app"):
        assert client.get("/boom").status_code == 500
    assert any(
        r.getMessage() == "Request failed" and vars(r)["path"] == "/boom" for r in caplog.records
    )
