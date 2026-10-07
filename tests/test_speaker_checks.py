import logging
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
from numpy.typing import NDArray
from sound_fakes import RATE, speechlike, wav_of

from imageskin import sound_checks, speaker_checks
from imageskin.download import DownloadError
from imageskin.speaker_checks import (
    MODEL_RATE,
    TWO_VOICES,
    SpeakerChecker,
    SpeakerCheckError,
    VoiceMeasure,
    fbank,
    problems,
    speech_stretches,
    to_model_rate,
    two_groups,
)


def test_two_voices_are_flagged_only_when_the_other_talks_for_a_while() -> None:
    assert problems(VoiceMeasure(stretches=40, other=10, alike=0.2)) == [TWO_VOICES]
    assert problems(VoiceMeasure(stretches=40, other=2, alike=0.2)) == []  # a cough or a laugh
    assert problems(VoiceMeasure(stretches=40, other=20, alike=0.8)) == []  # one voice
    assert problems(VoiceMeasure(stretches=0)) == []


def test_resampling_keeps_length_and_pitch() -> None:
    t = np.arange(RATE) / RATE
    out = to_model_rate(np.sin(2 * np.pi * 440 * t), RATE)
    assert len(out) == MODEL_RATE
    assert np.argmax(np.abs(np.fft.rfft(out))) == 440  # 1 Hz per bin for one second
    assert np.max(np.abs(out)) == pytest.approx(1, abs=0.01)
    same = np.zeros(10)
    assert to_model_rate(same, MODEL_RATE) is same
    assert len(to_model_rate(np.zeros(0), RATE)) == 0


def test_fbank_matches_kaldi() -> None:
    t = np.arange(8000) / MODEL_RATE
    x = 0.3 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.sin(2 * np.pi * 3000 * t)
    features = fbank(x)
    assert features.shape == (48, 80)  # 25 ms frames every 10 ms in half a second
    # From kaldi-native-fbank 1.21 with the same settings (dither off), frame 10.
    kaldi = [-12.575, -5.595, -8.3577, -15.9424, -14.0677, -15.9424]
    assert features[10, [0, 10, 20, 40, 60, 79]] == pytest.approx(kaldi, abs=0.01)
    assert fbank(np.zeros(100)).shape == (0, 80)


def test_only_stretches_of_speech_are_used() -> None:
    speech = to_model_rate(speechlike(10), RATE)
    stretches = speech_stretches(speech)
    assert stretches.shape == (12, 150, 80)  # every 0.75 s over 10 s
    assert np.allclose(stretches.mean(axis=1), 0, atol=1e-4)  # each band's average taken away
    pause = np.zeros(MODEL_RATE * 5)
    assert len(speech_stretches(np.concatenate([pause, speech, pause]))) == 12
    assert speech_stretches(pause).shape == (0, 150, 80)
    assert speech_stretches(np.zeros(100)).shape == (0, 150, 80)  # shorter than a frame


def unit(v: list[float]) -> NDArray[np.float64]:
    a = np.array(v, dtype=np.float64)
    return a / np.linalg.norm(a)


def test_two_groups_split_by_voice() -> None:
    rng = np.random.default_rng(0)
    me, other = unit([1, 0, 0, 0]), unit([0, 1, 0, 0])

    def prints(voice: NDArray[np.float64], count: int) -> NDArray[np.float64]:
        p = voice + rng.normal(0, 0.1, (count, 4))
        return p / np.linalg.norm(p, axis=1, keepdims=True)

    one = two_groups(prints(me, 30))
    assert one.stretches == 30 and one.alike > 0.9 and problems(one) == []
    two = two_groups(np.concatenate([prints(me, 30), prints(other, 5)]))
    assert two.other == 5 and two.alike < 0.2 and problems(two) == [TWO_VOICES]
    assert two_groups(prints(me, 1)) == VoiceMeasure(stretches=1)


class FakeSession:
    """Gives each stretch the band where it changes most as its voice print, so a high and a
    low voice get different prints."""

    runs: list[int] = []

    def __init__(self, path: str, options: object, providers: list[str]) -> None:
        self.path = path

    def run(self, outputs: None, feeds: dict[str, NDArray[np.float32]]) -> list[Any]:
        x = feeds["x"]
        FakeSession.runs.append(len(x))
        prints = np.zeros((len(x), 80), np.float32)
        prints[np.arange(len(x)), np.argmax(x.std(axis=1), axis=1)] = 3.0
        return [prints]


def fake_onnxruntime() -> dict[str, Any]:
    module = types.ModuleType("onnxruntime")
    module.SessionOptions = types.SimpleNamespace  # type: ignore[attr-defined]
    module.InferenceSession = FakeSession  # type: ignore[attr-defined]
    FakeSession.runs = []
    return {"onnxruntime": module}


def test_checker_flags_a_second_voice(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    checker = SpeakerChecker(tmp_path / "models")
    alone = speechlike(40)
    together = np.concatenate([speechlike(30), speechlike(10, pitch=1000, seed=1)])
    with (
        patch.dict(sys.modules, fake_onnxruntime()),
        patch.object(speaker_checks, "download") as download,
        patch.object(speaker_checks, "BATCH", 16),
        caplog.at_level(logging.INFO),
    ):
        assert checker.check(alone, RATE) == []
        assert checker.check(together, RATE) == [TWO_VOICES]
        assert checker.check(np.zeros(RATE), RATE) == []  # no speech, nothing to compare
    download.assert_called_once()  # loaded once
    assert max(FakeSession.runs) == 16 and FakeSession.runs[3] < 16  # 52 stretches in batches
    assert "Speaker model ready" in caplog.text
    flagged = [r for r in caplog.records if r.message == "Speaker checked"][1]
    assert flagged.problems == 1 and flagged.other >= 10  # type: ignore[attr-defined]


def test_a_failed_download_turns_the_check_off_until_restart(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    checker = SpeakerChecker(tmp_path / "models")
    failing = patch.object(speaker_checks, "download", side_effect=DownloadError("offline"))
    with patch.dict(sys.modules, fake_onnxruntime()), failing as download:
        with caplog.at_level(logging.ERROR):
            checker.prepare()  # logged, doesn't raise
        with pytest.raises(SpeakerCheckError, match="offline"):
            checker.check(speechlike(20), RATE)
    assert download.call_count == 1  # not retried on every recording
    assert "Speaker checks are off until restart" in caplog.text


def test_prepare_loads_the_model(tmp_path: Path) -> None:
    checker = SpeakerChecker(tmp_path / "models")
    with patch.dict(sys.modules, fake_onnxruntime()), patch.object(speaker_checks, "download"):
        checker.prepare()
        checker.prepare()
    assert isinstance(checker._session, FakeSession)
    assert checker._session.path == str(tmp_path / "models" / "campplus_voxceleb_16k.onnx")


def test_sound_checks_add_the_voice_check(tmp_path: Path) -> None:
    path = tmp_path / "two.wav"
    path.write_bytes(wav_of(speechlike(40)))
    seen: list[int] = []

    def voices(samples: NDArray[np.float64], rate: int) -> list[str]:
        seen.append(rate)
        return [TWO_VOICES]

    result = sound_checks.check(path, voices)
    assert result.problems == [TWO_VOICES] and seen == [RATE]
    assert sound_checks.check(path).problems == []
