import builtins
import struct
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import pytest

from imageskin.kokoro_engine import (
    SAMPLE_RATE,
    KokoroEngine,
    _load_pipeline,
    speech_from_results,
    to_pcm16,
)
from imageskin.voice import VoiceError


@dataclass
class Token:
    text: str
    start_ts: float | None
    end_ts: float | None


class Audio:
    """Stands in for the torch tensor Kokoro returns."""

    def __init__(self, seconds: float) -> None:
        self.samples = [0.5] * int(seconds * SAMPLE_RATE)

    def tolist(self) -> list[float]:
        return self.samples


@dataclass
class Result:
    audio: Audio | None
    tokens: list[Token] = field(default_factory=list)


def fake_pipeline(results: list[Result]) -> Callable[..., Iterable[Any]]:
    def pipeline(text: str, voice: str) -> Iterable[Any]:
        return iter(results)

    return pipeline


def test_to_pcm16_scales_and_clips() -> None:
    pcm = to_pcm16([0.0, 1.0, -1.0, 2.0, -2.0, 0.5])
    assert struct.unpack("<6h", pcm) == (0, 32767, -32767, 32767, -32767, 16384)


def test_speech_from_results_offsets_later_chunks_and_skips_punctuation() -> None:
    results = [
        Result(Audio(1.0), [Token("Hello", 0.1, 0.5), Token(",", 0.5, 0.6)]),
        Result(None),
        Result(Audio(0.5), [Token("there", 0.0, 0.4), Token("x", None, None)]),
    ]
    speech = speech_from_results(results)
    assert len(speech.pcm) == 2 * int(1.5 * SAMPLE_RATE)
    assert [(w.word, w.start, w.end) for w in speech.words] == [
        ("Hello", 0.1, 0.5),
        ("there", 1.0, 1.4),
    ]


def test_speak_loads_model_once() -> None:
    loads = []

    def load() -> Callable[..., Iterable[Any]]:
        loads.append(1)
        return lambda text, voice: iter([Result(Audio(0.1), [Token("Hi", 0.0, 0.1)])])

    engine = KokoroEngine(load)
    assert engine.speak("af_heart", "Hi").words[0].word == "Hi"
    engine.speak("af_heart", "Hi")
    assert len(loads) == 1


def test_speak_rejects_empty_text() -> None:
    with pytest.raises(VoiceError, match="no text"):
        KokoroEngine(lambda: fake_pipeline([])).speak("af_heart", " ")


def test_speak_with_no_audio_reports_no_real_time_factor() -> None:
    assert KokoroEngine(lambda: fake_pipeline([])).speak("af_heart", "Hi").pcm == b""


def test_model_errors_become_voice_errors() -> None:
    def pipeline(text: str, voice: str) -> Iterable[Any]:
        raise RuntimeError("voices/zz_nobody.pt not found")

    with pytest.raises(VoiceError, match="zz_nobody"):
        KokoroEngine(lambda: pipeline).speak("zz_nobody", "Hi")


def test_load_errors_become_voice_errors() -> None:
    def load() -> Callable[..., Iterable[Any]]:
        raise OSError("no network")

    with pytest.raises(VoiceError, match="could not load the Kokoro model: no network"):
        KokoroEngine(load).speak("af_heart", "Hi")


def test_missing_kokoro_explains_how_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def no_kokoro(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "kokoro":
            raise ImportError(name, name="kokoro")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_kokoro)
    with pytest.raises(VoiceError, match=r'pip install -e "\.\[voice\]"'):
        _load_pipeline()
    with pytest.raises(VoiceError, match="not installed"):
        KokoroEngine().speak("af_heart", "Hi")


def test_broken_dependency_reports_the_real_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def broken_torch(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "kokoro":
            raise ImportError("DLL load failed while importing _C", name="torch._C")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_torch)
    with pytest.raises(VoiceError, match="installed but could not be loaded: DLL load failed"):
        _load_pipeline()
