import logging
import wave
from pathlib import Path

import numpy as np
import pytest
from sound_fakes import RATE, speechlike, wav_of

from imageskin import sound_checks
from imageskin.sound_checks import CLIPPED, NOISY, SoundMeasure, measure, problems


def test_a_clean_recording_passes() -> None:
    m = measure(speechlike(40), RATE)
    assert 23 < m.speech_s < 27  # 250 ms of every 400 ms; the pauses don't count
    assert m.clipped == 0
    assert m.snr_db > 40
    assert problems(m) == []


def test_a_short_recording_says_how_much_speech_it_has() -> None:
    m = measure(speechlike(10), RATE)
    assert problems(m) == [
        "This recording has only 6 seconds of speech. Each recording needs at least 15 seconds:"
        " read the whole section from the recording guide."
    ]


def test_a_clipped_recording_is_too_loud() -> None:
    m = measure(np.clip(speechlike(40, level=2.0), -1, 1), RATE)
    assert m.clipped > sound_checks.MAX_CLIPPED
    assert problems(m) == [CLIPPED]


def test_a_loud_recording_that_peaks_just_below_the_top_passes() -> None:
    assert problems(measure(speechlike(40, level=0.95), RATE)) == []


def test_background_noise_is_flagged() -> None:
    m = measure(speechlike(40, noise=0.05), RATE)
    assert m.snr_db < sound_checks.MIN_SNR_DB
    assert problems(m) == [NOISY]


def test_a_quiet_but_clean_recording_passes() -> None:
    assert problems(measure(speechlike(40, level=0.01, noise=0.00003), RATE)) == []


def test_silence_is_too_short_and_not_noisy() -> None:
    for samples in (np.zeros(RATE * 30), np.random.default_rng(0).normal(0, 0.01, RATE * 30)):
        m = measure(samples, RATE)
        assert m.speech_s == 0
        assert problems(m) == [sound_checks.TOO_SHORT.format(speech=0)]


def test_pauses_of_digital_silence_count_as_quiet() -> None:
    # Noise suppression in some recorders makes the pauses between words exactly zero.
    samples = speechlike(30, noise=0)
    m = measure(samples, RATE)
    assert m.speech_s == measure(speechlike(30), RATE).speech_s
    assert problems(m) == []


def test_an_empty_recording_has_no_speech() -> None:
    assert measure(np.zeros(10), RATE) == SoundMeasure(speech_s=0, clipped=0, snr_db=0)


def test_noise_is_not_judged_without_speech() -> None:
    assert problems(SoundMeasure(speech_s=0, clipped=0, snr_db=3)) == [
        sound_checks.TOO_SHORT.format(speech=0)
    ]


def test_check_reads_the_stored_wav_and_logs_the_result(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "a.wav"
    path.write_bytes(wav_of(speechlike(30)))
    with caplog.at_level(logging.INFO):
        result = sound_checks.check(path)
    assert result.problems == [] and 17 < result.speech_s < 20
    logged = [r for r in caplog.records if r.message == "Sound checked"]
    assert logged and logged[0].problems == 0  # type: ignore[attr-defined]


def test_only_16_bit_mono_is_read(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"\0\0\0\0" * 100)
    with pytest.raises(ValueError, match="16-bit mono"):
        sound_checks.read_wav(path)
