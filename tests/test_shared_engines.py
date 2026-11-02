"""The models loaded once for every site (R61c)."""

import logging
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from imageskin.accent import AccentEngine
from imageskin.app import create_app, make_engines
from imageskin.prepare_job import clip_voice
from imageskin.sites import make_service
from imageskin.start_now import KokoroVoices
from imageskin.uploads import PhotoResult
from imageskin.voice import Speech, VoiceError


class Kokoro:
    """A Kokoro engine that says which language spoke, and how many speak at once."""

    def __init__(self, lang: str, counts: dict[str, int]) -> None:
        self.lang = lang
        self.counts = counts

    def speak(self, voice: str, text: str) -> Speech:
        self.counts["now"] += 1
        self.counts["most"] = max(self.counts["most"], self.counts["now"])
        time.sleep(0.02)
        self.counts["now"] -= 1
        return Speech(f"{self.lang}:{voice}:{text}".encode(), 24000, [], [])


def test_two_sites_share_one_set_of_models(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    service = make_service(tmp_path / "service")
    with caplog.at_level(logging.INFO):
        engines = make_engines(tmp_path / "service", face_checks=False)
    assert "Engines made" in caplog.text and engines.check_photo is None
    apps = [
        create_app(
            tmp_path / name,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            ask_llm=MagicMock(),
            service=service,
            engines=engines,
        )
        for name in "ab"
    ]
    assert all(app.state.engines is engines for app in apps)
    # The speaker model's folder is the shared one, not a site's.
    assert engines.speakers._model_file.parent == tmp_path / "service" / "models" / "speakers"
    for app in apps:
        assert TestClient(app).get("/health").status_code == 200
        # Each site waits for the shared models' loading, and adds its own later.
        assert app.state.loading[: len(engines.loading)] == list(engines.loading)


def test_an_app_given_no_engines_loads_its_own(tmp_path: Path) -> None:
    app = create_app(tmp_path, check_photo=lambda p: PhotoResult([], 80), ask_llm=MagicMock())
    assert app.state.engines.speakers._model_file.parent == tmp_path / "models" / "speakers"
    assert app.state.engines.check_photo is None  # photos are checked the test's way


def test_a_language_of_the_shared_kokoro_is_loaded_once_and_speaks_one_at_a_time() -> None:
    counts = {"now": 0, "most": 0}
    made: list[str] = []

    def kokoro(lang: str) -> Kokoro:
        made.append(lang)
        return Kokoro(lang, counts)

    voices = KokoroVoices(kokoro)
    site_a, site_b, british = voices.engine("a"), voices.engine("a"), voices.engine("b")
    spoken: list[bytes] = []

    def say(engine: object, text: str) -> None:
        spoken.append(engine.speak("af_heart", text).pcm)  # type: ignore[attr-defined]

    threads = [
        threading.Thread(target=say, args=(e, t))
        for e, t in ((site_a, "one"), (site_b, "two"), (british, "three"))
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(made) == ["a", "b"]  # two sites, one American engine
    assert sorted(spoken) == [b"a:af_heart:one", b"a:af_heart:two", b"b:af_heart:three"]
    assert counts["most"] == 1


def test_without_the_clone_the_ready_made_voice_is_the_shared_kokoro(tmp_path: Path) -> None:
    missing = VoiceError("chatterbox not installed")
    asked: list[str] = []
    ready = MagicMock()

    def kokoro(lang: str) -> MagicMock:
        asked.append(lang)
        return ready

    with patch("imageskin.chatterbox_engine.check_installed", side_effect=missing):
        step, engine, voice, kind = clip_voice(
            tmp_path / "voice-sample.wav", lambda: "own", MagicMock(), kokoro
        )
    assert asked == ["a"] and kind == "kokoro"
    step()
    assert engine is ready
    ready.speak.assert_called_once_with(voice, "Hello.")


def test_another_accent_speaks_its_base_voice_with_the_shared_kokoro(tmp_path: Path) -> None:
    def kokoro(lang: str) -> MagicMock:
        return MagicMock(name=f"kokoro-{lang}")

    with (
        patch("imageskin.chatterbox_engine.check_installed"),
        patch("imageskin.pocket_engine.installed", return_value=False),
    ):
        _, engine, _, kind = clip_voice(
            tmp_path / "voice-sample.wav", lambda: "british", MagicMock(), kokoro
        )
    assert isinstance(engine, AccentEngine) and kind == "clone"
    assert engine._kokoro is kokoro
