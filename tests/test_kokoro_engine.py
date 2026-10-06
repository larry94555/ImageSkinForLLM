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
    chunk_sounds,
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


class Steps:
    """Stands in for the pred_dur tensor: each phoneme's length in 25 ms steps."""

    def __init__(self, *steps: int) -> None:
        self.steps = list(steps)

    def tolist(self) -> list[int]:
        return self.steps


@dataclass
class Result:
    audio: Audio | None
    tokens: list[Token] = field(default_factory=list)
    phonemes: str = ""
    pred_dur: Steps | None = None


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


def test_speech_from_results_times_each_sound_across_chunks() -> None:
    results = [
        # "hi": padding, h, I (as in "my"), padding = 10 steps = 0.25 s
        Result(Audio(0.25), phonemes="hI", pred_dur=Steps(2, 3, 4, 1)),
        Result(Audio(0.5), phonemes="mˈi", pred_dur=Steps(1, 2, 1, 3, 1)),
    ]
    sounds = speech_from_results(results).sounds
    assert [(s.sound, s.start, s.end, s.shape) for s in sounds] == [
        (".", 0.0, 0.05, "rest"),
        ("h", 0.05, 0.125, "IH"),
        ("I", 0.125, 0.225, "AA"),
        (".", 0.225, 0.25, "rest"),
        (".", 0.25, 0.275, "rest"),
        ("m", 0.275, 0.35, "MBP"),  # the stress mark's step stays with m
        ("i", 0.35, 0.425, "EE"),
        (".", 0.425, 0.45, "rest"),
    ]


def test_chunk_sounds_drops_phonemes_the_model_has_no_token_for() -> None:
    sounds = chunk_sounds("h~i", [1, 1, 1, 1], 1.0, vocab={"h", "i"})
    assert [s.sound for s in sounds] == [".", "h", "i", "."]
    assert sounds[0].start == 1.0


def test_chunk_sounds_skips_a_chunk_whose_counts_do_not_match(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert chunk_sounds("hi", [1, 1], 0.0, vocab=None) == []
    assert "Sound timings skipped" in caplog.text


def test_speak_passes_the_models_phoneme_set() -> None:
    class Pipeline:
        model = type("Model", (), {"vocab": {"h": 1}})()

        def __call__(self, text: str, voice: str) -> Iterable[Any]:
            return iter([Result(Audio(0.1), phonemes="hx", pred_dur=Steps(1, 2, 1))])

    sounds = KokoroEngine(lambda: Pipeline()).speak("af_heart", "Hi").sounds
    assert [s.sound for s in sounds] == [".", "h", "."]


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
