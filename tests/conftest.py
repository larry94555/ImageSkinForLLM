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


@pytest.fixture(autouse=True)
def signed_in_host(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every browser in the tests is a signed-in host (R190), as the host pages' calls refuse
    anyone else; tests marked `real_hosts` sign in, or don't, for themselves."""
    if request.node.get_closest_marker("real_hosts"):
        return
    from imageskin.hosts import Host

    monkeypatch.setattr(
        "imageskin.hosts.HostAccounts.host", lambda self, token: Host("host@example.com", 0.0)
    )


@pytest.fixture(autouse=True)
def custom_photo_and_voice_allowed(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hosts may use their own photo and voice in the tests, which set up with them throughout,
    though Admin settings turns both off by default (R239, R240); tests marked
    `custom_defaults` keep the real defaults."""
    if request.node.get_closest_marker("custom_defaults"):
        return
    from imageskin import admin_settings

    monkeypatch.setattr(
        admin_settings,
        "DEFAULTS",
        admin_settings.AdminSettings(disable_custom_image=False, disable_custom_voice=False),
    )
