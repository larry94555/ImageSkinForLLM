import logging
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

from imageskin.alignment import Aligner
from imageskin.chatterbox_engine import (
    INSTALL_HINT,
    SAMPLE_RATE,
    ChatterboxEngine,
    provide_pkg_resources,
    read_voice_sample,
    reference_clip,
    start_of_speech,
)
from imageskin.kokoro_engine import to_pcm16
from imageskin.visemes import SoundTiming
from imageskin.voice import VoiceError, WordTiming


def write_wav(path: Path, samples: np.ndarray, rate: int = SAMPLE_RATE, channels: int = 1) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(to_pcm16(np.repeat(samples, channels).tolist()))
    return path


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
    def align(
        self, samples: np.ndarray, rate: int, text: str
    ) -> tuple[list[WordTiming], list[SoundTiming]]:
        seconds = len(samples) / rate
        return [WordTiming(text, 0.0, seconds)], [SoundTiming("a", 0.0, seconds)]


@pytest.fixture
def voice_sample(tmp_path: Path) -> Path:
    samples = np.concatenate([np.zeros(SAMPLE_RATE), np.full(SAMPLE_RATE * 12, 0.5)])
    return write_wav(tmp_path / "voice-sample.wav", samples.astype(np.float32))


def engine(cloner: FakeCloner) -> ChatterboxEngine:
    return ChatterboxEngine(load=lambda: cloner, aligner=FakeAligner())


def test_speak_returns_audio_and_timings(
    voice_sample: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cloner = FakeCloner()
    with caplog.at_level(logging.INFO, logger="imageskin.chatterbox_engine"):
        speech = engine(cloner).speak(str(voice_sample), "Hello")
    assert speech.sample_rate == SAMPLE_RATE
    assert len(speech.pcm) == SAMPLE_RATE  # half a second of 16-bit samples
    assert speech.words == [WordTiming("Hello", 0.0, 0.5)]
    assert speech.sounds == [SoundTiming("a", 0.0, 0.5)]
    assert cloner.texts == ["Hello"]
    # Learned from 10 seconds of speech, after the leading second of silence.
    assert len(cloner.voices[0]) == 10 * SAMPLE_RATE and cloner.voices[0][0] == 0.5
    messages = [r.getMessage() for r in caplog.records]
    assert messages == ["Loaded Chatterbox Turbo", "Learned voice", "Spoke text in cloned voice"]
    spoke = vars(caplog.records[-1])
    assert spoke["audio_s"] == 0.5 and "clone_ms" in spoke and "align_ms" in spoke


def test_voice_is_learned_once_per_sample(voice_sample: Path, tmp_path: Path) -> None:
    cloner = FakeCloner()
    eng = engine(cloner)
    eng.speak(str(voice_sample), "One")
    eng.speak(str(voice_sample), "Two")
    assert len(cloner.voices) == 1
    other = write_wav(tmp_path / "other.wav", np.full(SAMPLE_RATE, 0.3, dtype=np.float32))
    eng.speak(str(other), "Three")
    assert len(cloner.voices) == 2


def test_empty_text_is_rejected(voice_sample: Path) -> None:
    with pytest.raises(VoiceError, match="no text"):
        engine(FakeCloner()).speak(str(voice_sample), "  ")


def test_model_errors_become_voice_errors(voice_sample: Path) -> None:
    class Broken(FakeCloner):
        def __call__(self, text: str) -> np.ndarray:
            raise RuntimeError("out of memory")

    with pytest.raises(VoiceError, match="could not speak the text: out of memory"):
        engine(Broken()).speak(str(voice_sample), "Hi")


def test_learning_errors_become_voice_errors(voice_sample: Path) -> None:
    class Broken(FakeCloner):
        def set_voice(self, reference: np.ndarray) -> None:
            raise RuntimeError("bad reference")

    with pytest.raises(VoiceError, match="could not learn the voice.*bad reference"):
        engine(Broken()).speak(str(voice_sample), "Hi")


def test_not_installed_explains_install(voice_sample: Path) -> None:
    def missing() -> FakeCloner:
        raise ModuleNotFoundError("No module named 'chatterbox'", name="chatterbox")

    with pytest.raises(VoiceError) as exc:
        ChatterboxEngine(load=missing, aligner=FakeAligner()).speak(str(voice_sample), "Hi")
    assert str(exc.value) == INSTALL_HINT


def test_broken_install_and_load_failures(
    voice_sample: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken_import() -> FakeCloner:
        raise ModuleNotFoundError("No module named 'perth'", name="perth")

    def no_network() -> FakeCloner:
        raise OSError("connection reset")

    with pytest.raises(VoiceError, match="installed but could not be loaded"):
        ChatterboxEngine(load=broken_import, aligner=FakeAligner()).speak(str(voice_sample), "Hi")
    assert "Could not import Chatterbox" in caplog.text
    with pytest.raises(VoiceError, match="could not load Chatterbox Turbo: connection reset"):
        ChatterboxEngine(load=no_network, aligner=FakeAligner()).speak(str(voice_sample), "Hi")


def test_read_voice_sample_checks_the_format(tmp_path: Path) -> None:
    loud = np.full(100, 0.5, dtype=np.float32)
    assert read_voice_sample(write_wav(tmp_path / "ok.wav", loud))[0] == pytest.approx(0.5, 1e-3)
    with pytest.raises(VoiceError, match="not a 24 kHz mono"):
        read_voice_sample(write_wav(tmp_path / "44k.wav", loud, rate=44100))
    with pytest.raises(VoiceError, match="not a 24 kHz mono"):
        read_voice_sample(write_wav(tmp_path / "stereo.wav", loud, channels=2))
    with pytest.raises(VoiceError, match="is silent"):
        read_voice_sample(write_wav(tmp_path / "silent.wav", np.zeros(100, dtype=np.float32)))
    with pytest.raises(VoiceError, match="could not read the voice sample"):
        read_voice_sample(tmp_path / "missing.wav")


def test_reference_clip_skips_leading_silence() -> None:
    samples = np.concatenate([np.zeros(5), np.full(SAMPLE_RATE * 11, 0.5)]).astype(np.float32)
    assert start_of_speech(samples) == 5
    assert start_of_speech(np.zeros(3, dtype=np.float32)) == 0
    clip = reference_clip(samples)
    assert len(clip) == 10 * SAMPLE_RATE and clip[0] == 0.5


def test_provide_pkg_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def no_pkg_resources(name: str, *args: object, **kwargs: object) -> object:
        if name == "pkg_resources":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.delitem(sys.modules, "pkg_resources", raising=False)
    monkeypatch.setattr(builtins, "__import__", no_pkg_resources)
    provide_pkg_resources()
    monkeypatch.setattr(builtins, "__import__", real_import)
    shim = sys.modules["pkg_resources"]
    path = shim.resource_filename("imageskin", "voice.py")
    assert Path(path).name == "voice.py"
