import pytest


@pytest.fixture(autouse=True)
def no_model_downloads(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Where MediaPipe is installed, every app a test makes would fetch the face models at
    startup. test_face_checks tests that download itself, with fakes."""
    if request.module.__name__.endswith("test_face_checks"):
        return
    monkeypatch.setattr("imageskin.face_checks.FaceChecker.prepare", lambda self: None)
