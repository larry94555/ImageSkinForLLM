import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from imageskin.alignment import (
    ALIGNER_FILES,
    ALIGNER_REVISION,
    END_PAD_S,
    Aligner,
    Word,
    ctc_frames,
    ensure_aligner,
    hf_cache,
    letter_tokens,
    sound_timings_for,
    to_rate,
    widened,
    word_sounds,
    word_timings,
    words_from_tokens,
)
from imageskin.visemes import SoundTiming
from imageskin.voice import VoiceError, WordTiming

VOCAB = {"<pad>": 0, "|": 1, "A": 2, "B": 3, "'": 4, "M": 5, "I": 6}


def emissions_for(path: str) -> np.ndarray:
    """Log-probabilities that make the recognizer hear one token per frame; "-" is blank and "x"
    is speech that matches no letter of the text (as when a number is said)."""
    tokens = {"-": 0, "x": VOCAB["M"], **VOCAB}
    out = np.full((len(path), len(VOCAB)), np.log(0.01))
    for t, ch in enumerate(path):
        out[t, tokens[ch]] = np.log(0.9)
    return out


def test_ctc_frames_follow_the_most_likely_path() -> None:
    frames = ctc_frames(emissions_for("--AA-|-BB--"), [2, 1, 3])
    assert frames == [range(2, 4), range(5, 6), range(7, 9)]


def test_ctc_frames_keep_repeated_letters_apart() -> None:
    # "AA" needs a blank between the two A's, so each A gets its own frame.
    frames = ctc_frames(emissions_for("A-A"), [2, 2])
    assert frames == [range(0, 1), range(2, 3)]


def test_ctc_frames_ends_on_a_letter_or_blank() -> None:
    assert ctc_frames(emissions_for("-A"), [2]) == [range(1, 2)]
    assert ctc_frames(emissions_for("A-"), [2]) == [range(0, 1)]


def test_ctc_frames_too_short_raises() -> None:
    with pytest.raises(ValueError, match="too short"):
        ctc_frames(emissions_for("A-"), [2, 2])


def test_letter_tokens_skip_unknown_characters_and_digits() -> None:
    assert letter_tokens("a-b!", VOCAB) == [2, 3]
    assert letter_tokens("|", VOCAB) == []
    assert letter_tokens("3pm", VOCAB) == []


def test_word_timings_from_letter_frames() -> None:
    # 10 frames over 1 second: "A" at frames 1-2, "B" at frames 6-7.
    words = [Word("a", "ɐ"), Word("b", "b")]
    timings = word_timings(words, emissions_for("-AA|--BB--"), VOCAB, 1.0)
    assert timings == [WordTiming("a", 0.1, 0.3 + END_PAD_S), WordTiming("b", 0.6, 1.0)]


def test_joined_words_have_no_gap_token() -> None:
    # "I'm" as "I" + "'m": no word gap between them, so the path fits in 4 frames.
    words = [Word("I", "I", joined=True), Word("'m", "m")]
    timings = word_timings(words, emissions_for("I'M-"), VOCAB, 0.4)
    assert [t.word for t in timings] == ["I", "'m"]
    assert timings[0].start == 0.0 and timings[1].start == pytest.approx(0.1)


def test_words_without_letters_get_their_own_stretch() -> None:
    # 0.1 s frames: "a" is heard at 0.0, the number from 0.2 to 0.5, "b" at 0.6.
    words = [Word("a", "ɐ"), Word("45", "fɔɹTi fIv"), Word("b", "b")]
    timings = word_timings(words, emissions_for("A|xxx|B-"), VOCAB, 0.8)
    assert timings[0] == WordTiming("a", 0.0, 0.2)  # it does not swallow the number
    assert timings[1] == WordTiming("45", 0.2, 0.6)
    assert timings[2].start == 0.6


def test_all_numeric_text_is_found_in_the_audio() -> None:
    words = [Word("2026", "twˈɛnti twˈɛnti sˈɪks")]
    timings = word_timings(words, emissions_for("--xxxx----"), VOCAB, 1.0)
    assert timings == [WordTiming("2026", 0.2, 0.8)]


def test_adjacent_words_without_letters_share_their_stretch_by_sounds() -> None:
    # "A 45 67 B": the numbers are heard from 0.2 to 0.8 s; "45" has 8 sounds and "67" 6.
    words = [Word("A", "A"), Word("45", "fɔɹti fIv"), Word("67", "sɪksti"), Word("B", "b")]
    timings = word_timings(words, emissions_for("A|xxxxxx|B-"), VOCAB, 1.1)
    assert timings[1].start == 0.2
    assert timings[2].start == timings[1].end
    assert timings[2].end == timings[3].start == 0.9
    assert timings[1].end == pytest.approx(0.2 + 0.6 * 8 / 14, abs=0.001)


def test_widened_runs_into_the_next_word_or_a_short_way_into_a_pause() -> None:
    timings = [WordTiming("a", 0.0, 0.2), WordTiming("b", 0.25, 0.4), WordTiming("c", 2.0, 2.1)]
    out = widened(timings, 2.15)
    assert out == [
        WordTiming("a", 0.0, 0.25),
        WordTiming("b", 0.25, round(0.4 + END_PAD_S, 3)),
        WordTiming("c", 2.0, 2.15),
    ]


def test_word_sounds_share_the_time_and_skip_stress_marks() -> None:
    sounds = word_sounds("ˈhˈæt", 1.0, 1.3)
    assert [s.sound for s in sounds] == ["h", "æ", "t"]
    assert sounds[0].start == 1.0 and sounds[-1].end == pytest.approx(1.3)
    assert sounds[1].end - sounds[1].start == pytest.approx(0.1, abs=0.002)


def test_word_sounds_without_phonemes() -> None:
    assert word_sounds("", 1.0, 1.5) == [SoundTiming("ə", 1.0, 1.5)]
    assert word_sounds("", 1.0, 1.0) == []


def test_sound_timings_rest_between_words_and_at_both_ends() -> None:
    words = [Word("a", "ɐ"), Word("b", "b")]
    timings = [WordTiming("a", 0.1, 0.3), WordTiming("b", 0.5, 0.6)]
    sounds = sound_timings_for(words, timings, 1.0)
    assert [(s.sound, s.start, s.end) for s in sounds] == [
        (".", 0.0, 0.1),
        ("ɐ", 0.1, 0.3),
        (".", 0.3, 0.5),
        ("b", 0.5, 0.6),
        (".", 0.6, 1.0),
    ]


def test_to_rate() -> None:
    samples = np.arange(24, dtype=np.float32)
    assert to_rate(samples, 16000, 16000) is samples
    out = to_rate(samples, 24000, 16000)
    assert len(out) == 16 and out.dtype == np.float32
    assert out[3] == pytest.approx(4.5)


def test_words_from_tokens_drop_punctuation_and_mark_joins() -> None:
    tokens = [
        SimpleNamespace(text="Hi", phonemes="hI", whitespace=""),
        SimpleNamespace(text=",", phonemes=",", whitespace=" "),
        SimpleNamespace(text="I", phonemes="I", whitespace=""),
        SimpleNamespace(text="'m", phonemes="m", whitespace=" "),
        SimpleNamespace(text="$", phonemes=None, whitespace=""),
        SimpleNamespace(text="5", phonemes="fIv", whitespace=""),
    ]
    assert words_from_tokens(tokens) == [
        Word("Hi", "hI", False),
        Word("I", "I", True),
        Word("'m", "m", False),
        Word("5", "fIv", False),
    ]


def fake_aligner(path: str = "--A|-B--") -> Aligner:
    def load() -> tuple[object, dict[str, int]]:
        return (lambda samples: emissions_for(path)), VOCAB

    def g2p() -> object:
        return lambda text: [Word(w, w.lower()) for w in text.split()]

    return Aligner(load=load, g2p=g2p)  # type: ignore[arg-type]


def test_aligner_logs_and_returns_timings(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="imageskin.alignment"):
        words, sounds = fake_aligner().align(np.zeros(24000, dtype=np.float32), 24000, "A B")
    assert [w.word for w in words] == ["A", "B"]
    assert words[0].start == pytest.approx(0.25)
    assert sounds[0] == SoundTiming(".", 0.0, 0.25)
    messages = [r.getMessage() for r in caplog.records]
    assert messages == ["Loaded aligner", "Aligned words"]
    assert vars(caplog.records[-1])["words"] == 2


def test_aligner_with_no_words_raises() -> None:
    with pytest.raises(VoiceError, match="no words"):
        fake_aligner().align(np.zeros(100, dtype=np.float32), 24000, "")


def test_aligner_audio_too_short_raises() -> None:
    with pytest.raises(VoiceError, match="could not find the words"):
        fake_aligner("A").align(np.zeros(100, dtype=np.float32), 24000, "A B")


def test_aligner_load_errors_become_voice_errors() -> None:
    def broken() -> tuple[object, dict[str, int]]:
        raise OSError("no network")

    def missing() -> tuple[object, dict[str, int]]:
        raise ImportError("No module named 'transformers'")

    with pytest.raises(VoiceError, match="could not load the aligner.*no network"):
        Aligner(load=broken).align(np.zeros(1), 16000, "a")  # type: ignore[arg-type]
    with pytest.raises(VoiceError, match="could not be loaded.*README"):
        Aligner(load=missing).align(np.zeros(1), 16000, "a")  # type: ignore[arg-type]


def test_aligner_without_kokoro_explains_install() -> None:
    def no_kokoro() -> object:
        raise ImportError("No module named 'kokoro'")

    aligner = fake_aligner()
    aligner._load_g2p = no_kokoro  # type: ignore[assignment]
    with pytest.raises(VoiceError, match=r"\.\[voice\]"):
        aligner.align(np.zeros(1), 16000, "a")


def test_ensure_aligner_downloads_each_file_into_the_models_folder(tmp_path: Path) -> None:
    calls: list[tuple[str, Path, int, str]] = []
    folder = ensure_aligner(tmp_path, lambda *args: calls.append(args))
    assert folder == tmp_path / "models" / "wav2vec2-base-960h"
    assert [c[1] for c in calls] == [folder / name for name, _, _ in ALIGNER_FILES]
    assert calls[2][0] == (
        f"https://huggingface.co/facebook/wav2vec2-base-960h/resolve/{ALIGNER_REVISION}"
        "/model.safetensors"
    )
    assert calls[2][2] == 377607901


def test_load_loads_the_model_and_pronunciation_once() -> None:
    loads: list[str] = []

    def load() -> tuple[object, dict[str, int]]:
        loads.append("model")
        return (lambda samples: emissions_for("A")), VOCAB

    def g2p() -> object:
        loads.append("g2p")
        return lambda text: []

    aligner = Aligner(load=load, g2p=g2p)  # type: ignore[arg-type]
    aligner.load()
    aligner.load()
    assert loads == ["g2p", "model"]  # the quick one first, so a missing Kokoro fails fast


def test_ensure_aligner_copies_from_the_hugging_face_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    snapshot = hf_cache() / "models--facebook--wav2vec2-base-960h" / "snapshots" / ALIGNER_REVISION
    snapshot.mkdir(parents=True)
    (snapshot / "vocab.json").write_text("{}")
    folder = ensure_aligner(tmp_path / "home", lambda *args: None)
    assert (folder / "vocab.json").read_text() == "{}"
    assert not (folder / "config.json").exists()


def test_hf_cache_follows_hugging_face_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert hf_cache() == tmp_path / "hub"
    monkeypatch.delenv("HF_HOME")
    assert hf_cache() == Path.home() / ".cache" / "huggingface" / "hub"
