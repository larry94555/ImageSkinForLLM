import logging
import sys
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from imageskin.alignment import Aligner
from imageskin.chatterbox_engine import (
    INSTALL_HINT,
    SAMPLE_RATE,
    ChatterboxEngine,
    check_installed,
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
    loads = 0

    def load(self) -> None:
        self.loads += 1

    def align(
        self, samples: np.ndarray, rate: int, text: str
    ) -> tuple[list[WordTiming], list[SoundTiming]]:
        seconds = len(samples) / rate
        return [WordTiming(text, 0.0, seconds)], [SoundTiming("a", 0.0, seconds)]


@pytest.fixture
def voice_sample(tmp_path: Path) -> Path:
    samples = np.concatenate([np.zeros(SAMPLE_RATE), np.full(SAMPLE_RATE * 12, 0.5)])
    return write_wav(tmp_path / "voice-sample.wav", samples.astype(np.float32))


def engine_with(load: Callable[[], FakeCloner]) -> ChatterboxEngine:
    return ChatterboxEngine(load=load, aligner=FakeAligner(), check=lambda: None)


def engine(cloner: FakeCloner) -> ChatterboxEngine:
    return engine_with(lambda: cloner)


def test_speak_returns_audio_and_timings(
    voice_sample: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cloner = FakeCloner()
    aligner = FakeAligner()
    with caplog.at_level(logging.INFO, logger="imageskin.chatterbox_engine"):
        speech = ChatterboxEngine(lambda: cloner, aligner, lambda: None).speak(
            str(voice_sample), "Hello"
        )
    assert aligner.loads == 1  # loaded up front, before the slow clone
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


def test_learn_voice_loads_the_models_and_relearns_a_changed_sample(
    voice_sample: Path,
) -> None:
    cloner = FakeCloner()
    aligner = FakeAligner()
    eng = ChatterboxEngine(lambda: cloner, aligner, lambda: None)
    eng.learn_voice(str(voice_sample))
    assert aligner.loads == 1 and len(cloner.voices) == 1 and cloner.texts == []
    # New recordings: the sample is joined again under the same name.
    write_wav(voice_sample, np.full(SAMPLE_RATE * 12, 0.25, dtype=np.float32))
    eng.learn_voice(str(voice_sample))
    assert len(cloner.voices) == 2 and cloner.voices[1][0] == 0.25
    eng.speak(str(voice_sample), "Hello")
    assert len(cloner.voices) == 2  # speaking keeps the voice just learned


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


def test_check_installed_names_what_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: None if name in ("chatterbox", "kokoro") else object(),
    )
    with pytest.raises(VoiceError) as exc:
        check_installed()
    assert str(exc.value) == f"chatterbox, kokoro not installed; {INSTALL_HINT}"
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    check_installed()


def test_bad_voice_sample_fails_before_any_model_loads(tmp_path: Path) -> None:
    loads: list[str] = []

    class CountingAligner(FakeAligner):
        def load(self) -> None:
            loads.append("aligner")

    def load_cloner() -> FakeCloner:
        loads.append("cloner")
        return FakeCloner()

    eng = ChatterboxEngine(load_cloner, CountingAligner(), check=lambda: None)
    with pytest.raises(VoiceError, match="could not read the voice sample"):
        eng.check_voice_sample(str(tmp_path / "missing.wav"))
    with pytest.raises(VoiceError, match="not a 24 kHz mono"):
        eng.speak(str(write_wav(tmp_path / "44k.wav", np.ones(9), rate=44100)), "Hi")
    assert loads == []


def test_not_installed_fails_before_reading_the_sample(tmp_path: Path) -> None:
    def missing() -> None:
        raise VoiceError("chatterbox not installed")

    eng = ChatterboxEngine(aligner=FakeAligner(), check=missing)
    with pytest.raises(VoiceError, match="not installed"):
        eng.speak(str(tmp_path / "missing.wav"), "Hi")


def test_checked_voice_sample_is_read_once(
    voice_sample: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import imageskin.chatterbox_engine as engine_module

    reads: list[Path] = []
    real = engine_module.read_voice_sample

    def counting(path: Path) -> np.ndarray:
        reads.append(path)
        return real(path)

    monkeypatch.setattr(engine_module, "read_voice_sample", counting)
    eng = engine(FakeCloner())
    eng.check_voice_sample(str(voice_sample))
    eng.speak(str(voice_sample), "One")
    eng.speak(str(voice_sample), "Two")
    assert reads == [voice_sample]


def test_broken_install_and_load_failures(
    voice_sample: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken_import() -> FakeCloner:
        raise ModuleNotFoundError("No module named 'perth'", name="perth")

    def no_network() -> FakeCloner:
        raise OSError("connection reset")

    with pytest.raises(VoiceError, match="installed but could not be loaded"):
        engine_with(broken_import).speak(str(voice_sample), "Hi")
    assert "Could not import Chatterbox" in caplog.text
    with pytest.raises(VoiceError, match="could not load Chatterbox Turbo: connection reset"):
        engine_with(no_network).speak(str(voice_sample), "Hi")


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


def test_provide_pkg_resources_keeps_the_real_module(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    real = types.ModuleType("pkg_resources")
    monkeypatch.setitem(sys.modules, "pkg_resources", real)
    provide_pkg_resources()
    assert sys.modules["pkg_resources"] is real


def test_reference_and_cloner_are_shared_with_the_accent_converter(voice_sample: Path) -> None:
    cloner = FakeCloner()
    loads: list[int] = []

    def load() -> FakeCloner:
        loads.append(1)
        return cloner

    eng = engine_with(load)
    expected = reference_clip(read_voice_sample(voice_sample))
    assert np.array_equal(eng.reference(str(voice_sample)), expected)
    assert eng.cloner() is cloner and eng.cloner() is cloner and len(loads) == 1
    # The recordings changed: the sample is joined again under the same name, so read it afresh.
    write_wav(voice_sample, np.full(SAMPLE_RATE * 12, 0.3, dtype=np.float32))
    assert eng.reference(str(voice_sample))[0] == expected[0]  # kept from before
    assert eng.reference(str(voice_sample), fresh=True)[0] == pytest.approx(0.3, abs=1e-3)
