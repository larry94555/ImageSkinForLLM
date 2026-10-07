import numpy as np
import pytest
from numpy.typing import NDArray


@pytest.fixture(autouse=True)
def no_model_downloads(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every app a test makes would fetch the speaker model, and where MediaPipe is installed
    the face models, at startup. Recordings then sound like one person. test_face_checks and
    test_speaker_checks test the models themselves, with fakes."""
    if not request.module.__name__.endswith("test_face_checks"):
        monkeypatch.setattr("imageskin.face_checks.FaceChecker.prepare", lambda self: None)
    if not request.module.__name__.endswith("test_speaker_checks"):

        def one_voice(self: object, stretches: NDArray[np.float32]) -> NDArray[np.float64]:
            return np.ones((len(stretches), 4)) / 2

        monkeypatch.setattr("imageskin.speaker_checks.SpeakerChecker.prepare", lambda self: None)
        monkeypatch.setattr("imageskin.speaker_checks.SpeakerChecker.voice_prints", one_voice)
