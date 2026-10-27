import logging
import sys
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from imageskin import pocket_engine
from imageskin.alignment import Aligner
from imageskin.chatterbox_engine import SAMPLE_RATE
from imageskin.kokoro_engine import to_pcm16
from imageskin.visemes import SoundTiming
from imageskin.voice import VoiceError, WordTiming


class FakeCloner:
    def __init__(self) -> None:
        self.voices: list[np.ndarray] = []
        self.texts: list[str] = []

    def set_voice(self, reference: np.ndarray) -> None:
        self.voices.append(reference)

    def __call__(self, text: str) -> np.ndarray:
        self.texts.append(text)
        return np.full(SAMPLE_RATE // 2, 0.25, dtype=np.float32)  # half a second


class FakeAligner(Aligner):
    def load(self) -> None:
        pass

    def align(
        self, samples: np.ndarray, rate: int, text: str
    ) -> tuple[list[WordTiming], list[SoundTiming]]:
        seconds = len(samples) / rate
        return [WordTiming(text, 0.0, seconds)], [SoundTiming("a", 0.0, seconds)]


@pytest.fixture
def voice_sample(tmp_path: Path) -> Path:
    samples = np.concatenate([np.zeros(SAMPLE_RATE), np.full(SAMPLE_RATE * 12, 0.5)])
    path = tmp_path / "voice-sample.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(to_pcm16(samples.tolist()))
    return path


def test_pocket_speaks_through_the_clone_steps_under_its_own_name(
    voice_sample: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cloner = FakeCloner()
    with (
        patch.object(pocket_engine, "_load_cloner", return_value=cloner),
        patch.object(pocket_engine, "check_installed"),
    ):
        engine = pocket_engine.pocket_engine()
        engine._aligner = FakeAligner()
        with caplog.at_level(logging.INFO, logger="imageskin.chatterbox_engine"):
            speech = engine.speak(str(voice_sample), "Hello")
    assert engine.name == "Pocket TTS" and cloner.texts == ["Hello"]
    # Learned from the same 10 seconds of the voice sample as Chatterbox.
    assert len(cloner.voices[0]) == 10 * SAMPLE_RATE
    assert speech.sample_rate == SAMPLE_RATE and len(speech.pcm) == SAMPLE_RATE
    messages = [r.getMessage() for r in caplog.records]
    assert messages == ["Loaded Pocket TTS", "Learned voice", "Spoke text in cloned voice"]
    assert vars(caplog.records[-1])["model"] == "Pocket TTS"


def test_pocket_load_failures_name_pocket(voice_sample: Path) -> None:
    def gated() -> FakeCloner:
        raise VoiceError(pocket_engine.GATED)

    with patch.object(pocket_engine, "_load_cloner", side_effect=gated):
        engine = pocket_engine.pocket_engine()
        engine._aligner = FakeAligner()
        engine._check = lambda: None
        with pytest.raises(VoiceError) as e:
            engine.speak(str(voice_sample), "Hi")
    assert str(e.value).startswith("could not load Pocket TTS: its weights that clone a voice")
    assert pocket_engine.TERMS_URL in str(e.value) and "hf auth login" in str(e.value)
    # The engine is picked when the server starts, so going back to Chatterbox needs a restart.
    assert "uninstall pocket-tts and restart imageskin serve" in str(e.value)


def test_signed_in_is_a_hugging_face_token(monkeypatch: pytest.MonkeyPatch) -> None:
    with patch("huggingface_hub.get_token", return_value="hf_x"):
        assert pocket_engine.signed_in()
    with patch("huggingface_hub.get_token", return_value=None):
        assert not pocket_engine.signed_in()
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)  # not installed
    assert not pocket_engine.signed_in()


def test_usable_needs_it_installed_and_signed_in() -> None:
    with patch.object(pocket_engine, "installed", return_value=False):
        assert not pocket_engine.usable()
    with (
        patch.object(pocket_engine, "installed", return_value=True),
        patch.object(pocket_engine, "signed_in", return_value=True),
    ):
        assert pocket_engine.usable()


def test_installed_and_check_installed_look_for_the_packages() -> None:
    def spec(found: set[str]):  # type: ignore[no-untyped-def]
        return lambda name: object() if name in found else None

    with patch("importlib.util.find_spec", spec({"transformers", "kokoro"})):
        assert not pocket_engine.installed()
        with pytest.raises(VoiceError, match="pocket_tts not installed; see 'Your own voice'"):
            pocket_engine.check_installed()
    with patch("importlib.util.find_spec", spec({"pocket_tts", "transformers", "kokoro"})):
        assert pocket_engine.installed()
        pocket_engine.check_installed()


def test_pocket_s_two_worker_threads_share_the_engines_threads() -> None:
    class FakeTorch:
        threads = 4

        def get_num_threads(self) -> int:
            return self.threads

        def set_num_threads(self, n: int) -> None:
            self.threads = n

    torch = FakeTorch()
    with pocket_engine.worker_threads(torch):
        assert torch.threads == 2
    assert torch.threads == 4
    torch.threads = 1
    with pytest.raises(RuntimeError), pocket_engine.worker_threads(torch):
        assert torch.threads == 1  # never none
        raise RuntimeError("the model failed")
    assert torch.threads == 1


def test_the_gated_reason_is_hugging_faces_own_error() -> None:
    class GatedRepoError(Exception):
        pass

    def refused(path: str) -> object:
        raise GatedRepoError(
            f"403 Client Error. (Request ID: Root=1-6acb)\n\n"
            f"Cannot access gated repo for url {path}."
        )

    reason = pocket_engine.gated_reason(refused, "hf://kyutai/pocket-tts/model.safetensors")
    assert reason == (
        "GatedRepoError: 403 Client Error. Cannot access gated repo for url"
        " hf://kyutai/pocket-tts/model.safetensors."
    )

    def silent(path: str) -> object:
        raise OSError()

    assert pocket_engine.gated_reason(silent, "x") == "OSError"
    assert pocket_engine.gated_reason(lambda path: path, "x") == "the download works now; try again"
    assert "no weights that clone" in pocket_engine.gated_reason(refused, None)
