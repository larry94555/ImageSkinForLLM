import logging
from pathlib import Path

import numpy as np
import pytest

from imageskin.accent import (
    ACCENTS,
    KOKORO_VOICES,
    PASSAGE,
    PROBE,
    AccentEngine,
    convert_fitted,
    kept_path,
    load_accent,
    pcm16_to_float,
    pick_base,
    save_accent,
)
from imageskin.kokoro_engine import to_pcm16
from imageskin.visemes import SoundTiming
from imageskin.voice import Speech, VoiceError, WordTiming

RATE = 24000


def tone(level: float, n: int = RATE // 2) -> np.ndarray:
    return np.full(n, level, dtype=np.float32)


def test_the_accent_is_the_persons_own_until_one_is_chosen(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert load_accent(tmp_path) == "own"
    with caplog.at_level(logging.INFO):
        save_accent(tmp_path / "home", "british")
    assert load_accent(tmp_path / "home") == "british"
    assert "Accent chosen" in caplog.text


@pytest.mark.parametrize("saved", ["not json", '["british"]', '{"accent": "martian"}'])
def test_a_broken_accent_file_means_the_persons_own(
    tmp_path: Path, saved: str, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "accent.json").write_text(saved)
    with caplog.at_level(logging.ERROR):
        assert load_accent(tmp_path) == "own"
    assert caplog.records


def test_every_other_accent_has_voices_of_men_and_women() -> None:
    assert set(KOKORO_VOICES) == set(ACCENTS) - {"own"}
    for lang, voices in KOKORO_VOICES.values():
        assert lang in ("a", "b")
        assert any(v[1] == "m" for v in voices) and any(v[1] == "f" for v in voices)


def test_convert_fitted_keeps_the_length() -> None:
    longer = convert_fitted(tone(0.1), lambda s: tone(0.4, len(s) + 77))
    shorter = convert_fitted(tone(0.1), lambda s: tone(0.4, len(s) - 77))
    assert len(longer) == len(shorter) == RATE // 2 and longer.dtype == np.float32
    assert shorter[-1] == 0 and longer[0] == pytest.approx(0.4)


def test_pick_base_converts_every_voice_and_picks_the_closest_after() -> None:
    levels = {"a": 0.1, "b": 0.5, "c": 0.4, "d": 0.3}
    converted: list[float] = []

    def convert(samples: np.ndarray) -> np.ndarray:
        converted.append(float(samples[0]))
        # After conversion the ranking flips: the base furthest from the person converts best.
        return tone(0.9 if samples[0] == pytest.approx(0.1) else 0.2)

    best, scores = pick_base(
        list(levels), lambda v: tone(levels[v]), convert, lambda s: float(s[0])
    )
    assert best == "a" and len(converted) == 4
    assert scores == [("a", 0.9), ("b", 0.2), ("c", 0.2)]


class FakeClone:
    """The parts of ChatterboxEngine the accent engine uses."""

    name = "Fake clone"

    def __init__(self) -> None:
        self.learned: list[str] = []

    def check_voice_sample(self, voice: str) -> None:
        self.learned.append(f"checked {voice}")

    def learn_voice(self, voice: str) -> None:
        self.learned.append(voice)

    def learn_speech(self, voice: str, speech: np.ndarray) -> None:
        self.learned.append(f"{voice} from speech at {speech[0]:.3f}")

    def reference(self, voice: str, fresh: bool = False) -> np.ndarray:
        self.learned.append(f"read {voice} afresh" if fresh else f"read {voice}")
        return tone(0.5)

    def speak(self, voice: str, text: str) -> Speech:
        return Speech(b"clone", RATE, [])

    def forget_voice(self) -> None:
        self.learned.append("forgot")


class FakeKokoro:
    """Each voice speaks at its own level; Larry's own voice is 0.5."""

    def __init__(self, lang: str) -> None:
        self.lang = lang
        self.said: list[tuple[str, str]] = []

    def speak(self, voice: str, text: str) -> Speech:
        self.said.append((voice, text))
        level = {"bm_lewis": 0.45, "bm_george": 0.3}.get(voice, 0.1)
        return Speech(
            to_pcm16(tone(level).tolist()),
            RATE,
            [WordTiming("Hi", 0.0, 0.3)],
            [SoundTiming("h", 0.0, 0.1)],
        )


class FakeConverter:
    def __init__(self) -> None:
        self.voice: np.ndarray | None = None
        self.broken = False

    def set_voice(self, reference: np.ndarray) -> None:
        if self.broken:
            raise RuntimeError("bad reference")
        self.voice = reference

    def __call__(self, samples: np.ndarray) -> np.ndarray:
        if self.broken:
            raise RuntimeError("out of memory")
        # Moves the level halfway to the person's, and runs a little long.
        return np.full(len(samples) + 10, (samples[0] + 0.5) / 2, dtype=np.float32)


def accent_engine(
    clone_keeps_accent: bool = False,
) -> tuple[AccentEngine, FakeClone, dict[str, FakeKokoro], FakeConverter]:
    clone, converter = FakeClone(), FakeConverter()
    kokoros: dict[str, FakeKokoro] = {}

    def kokoro(lang: str) -> FakeKokoro:
        kokoros[lang] = FakeKokoro(lang)
        return kokoros[lang]

    # A voice print where closeness is closeness of level to the person's 0.5.
    def voice_print(samples: np.ndarray) -> np.ndarray:
        angle = abs(float(samples[0]) - 0.5)
        return np.array([np.cos(angle), np.sin(angle)])

    engine = AccentEngine(
        clone,  # type: ignore[arg-type]
        kokoro,
        lambda: converter,
        voice_print,
        clone_keeps_accent=clone_keeps_accent,
    )
    return engine, clone, kokoros, converter


def test_with_the_persons_own_accent_the_clone_speaks() -> None:
    engine, clone, kokoros, _ = accent_engine()
    engine.prepare("voice-sample.wav", "own")
    engine.check_voice_sample("voice-sample.wav")
    assert engine.speak("voice-sample.wav", "Hi").pcm == b"clone"
    assert clone.learned == ["voice-sample.wav", "checked voice-sample.wav"]
    assert kokoros == {} and engine.base is None  # nothing else is loaded


def test_another_accent_picks_a_base_voice_and_converts_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine, clone, kokoros, converter = accent_engine()
    with caplog.at_level(logging.INFO):
        engine.prepare("voice-sample.wav", "british")
        speech = engine.speak("voice-sample.wav", "Hi")
    # Kokoro's timings are kept: the clone's voice and aligner are not loaded, only the sample read.
    assert engine.base == "bm_lewis" and clone.learned == ["read voice-sample.wav afresh"]
    assert converter.voice is not None and converter.voice[0] == 0.5
    british = kokoros["b"]
    assert len([t for v, t in british.said if t == PROBE]) == len(KOKORO_VOICES["british"][1])
    assert british.said[-1] == ("bm_lewis", "Hi")
    samples = pcm16_to_float(speech.pcm)
    assert len(samples) == RATE // 2 and samples[0] == pytest.approx(0.475, abs=1e-3)
    assert speech.words == [WordTiming("Hi", 0.0, 0.3)]  # Kokoro's timings are kept
    picked = next(r for r in caplog.records if r.getMessage() == "Picked base voice")
    assert vars(picked)["voice"] == "bm_lewis" and len(vars(picked)["scores"]) == 3
    assert "Converted speech to the person's voice" in caplog.text
    assert "Loaded voice converter" in caplog.text
    engine.prepare("voice-sample.wav", "own")  # back to the person's own accent
    assert engine.speak("voice-sample.wav", "Hi").pcm == b"clone"


def test_a_clone_that_keeps_accents_learns_the_accent_once_and_speaks_every_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine, clone, kokoros, converter = accent_engine(clone_keeps_accent=True)
    with caplog.at_level(logging.INFO):
        engine.prepare("voice-sample.wav", "british")
    british = kokoros["b"]
    # The picked base voice reads the passage; converted, it is what the clone learns from.
    assert engine.base == "bm_lewis" and british.said[-1] == ("bm_lewis", PASSAGE)
    assert clone.learned == [
        "read voice-sample.wav afresh",
        "voice-sample.wav from speech at 0.475",
    ]
    assert engine._converter is None  # freed: no line is converted
    said = len(british.said)
    assert engine.speak("voice-sample.wav", "Hi").pcm == b"clone"
    assert len(british.said) == said  # the clone spoke, not Kokoro
    learned = next(
        r for r in caplog.records if r.getMessage() == "Clone learned the voice with the accent"
    )
    assert vars(learned)["accent"] == "british" and vars(learned)["base"] == "bm_lewis"
    assert vars(learned)["passage_s"] == 0.5
    assert "Converted speech to the person's voice" not in caplog.text
    engine.prepare("voice-sample.wav", "own")  # the own accent learns from the voice sample again
    assert clone.learned[-1] == "voice-sample.wav"


def test_a_converter_that_fails_on_the_passage_says_so() -> None:
    engine, _, _, converter = accent_engine(clone_keeps_accent=True)
    calls = 0

    def convert_probes_only(samples: np.ndarray) -> np.ndarray:
        nonlocal calls
        calls += 1
        if calls > len(KOKORO_VOICES["american"][1]):
            raise RuntimeError("out of memory")
        return samples

    with (
        pytest.MonkeyPatch.context() as m,
        pytest.raises(VoiceError, match="could not convert the voice: out of memory"),
    ):
        m.setattr(FakeConverter, "__call__", lambda self, s: convert_probes_only(s))
        engine.prepare("voice-sample.wav", "american")


def test_a_converter_that_fails_says_so() -> None:
    engine, _, _, converter = accent_engine()
    engine.prepare("voice-sample.wav", "american")
    converter.broken = True
    with pytest.raises(VoiceError, match="could not convert the voice: out of memory"):
        engine.speak("voice-sample.wav", "Hi")
    with pytest.raises(VoiceError, match="could not learn the voice for the accent"):
        engine.prepare("voice-sample.wav", "american")


def test_a_converter_that_cannot_load_says_so() -> None:
    def broken() -> FakeConverter:
        raise OSError("no space left")

    def refused() -> FakeConverter:
        raise VoiceError("not installed")

    for load, message in (
        (broken, "could not load Chatterbox's voice converter"),
        (refused, "^not installed$"),
    ):
        engine = AccentEngine(FakeClone(), FakeKokoro, load, lambda s: s)  # type: ignore[arg-type]
        with pytest.raises(VoiceError, match=message):
            engine.prepare("voice-sample.wav", "british")


def test_a_forgotten_voice_drops_the_clones_and_the_converters() -> None:
    """R31: after Delete my data neither the clone nor the converter keeps the person's voice."""
    engine, clone, _, converter = accent_engine()
    engine.prepare("voice-sample.wav", "british")
    assert engine._converter is converter and engine.base is not None
    engine.forget_voice()
    assert clone.learned[-1] == "forgot" and engine._converter is None
    assert engine.accent == "own" and engine.base is None


def recorded(tmp_path: Path, sound: bytes = b"Larry speaking") -> str:
    sample = tmp_path / "uploads" / "voice-sample.wav"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_bytes(sound)
    return str(sample)


def test_the_accent_is_learned_again_from_the_kept_speech_after_a_restart(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """R183: after a rebuild, the chat waited minutes while the British accent was converted
    again; the speech converted last time is kept beside the voice sample and learned from."""
    voice = recorded(tmp_path)
    engine, _, _, _ = accent_engine(clone_keeps_accent=True)
    with caplog.at_level(logging.INFO):
        engine.prepare(voice, "british")
    assert kept_path(voice) == tmp_path / "uploads" / "voice-sample.accent.npz"
    assert kept_path(voice).is_file() and "Kept the accent speech for the next start" in caplog.text
    assert not list((tmp_path / "uploads").glob("*.writing"))

    restarted, clone, kokoros, converter = accent_engine(clone_keeps_accent=True)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        restarted.prepare(voice, "british")
    # Nothing converted, no Kokoro voice spoken, the converter never loaded.
    assert kokoros == {} and converter.voice is None and restarted._converter is None
    assert restarted.base == "bm_lewis" and restarted.accent == "british"
    assert clone.learned == [f"{voice} from speech at 0.475"]
    learned = next(
        r
        for r in caplog.records
        if r.getMessage() == "Clone learned the voice with the accent from the kept speech"
    )
    assert vars(learned)["base"] == "bm_lewis" and vars(learned)["duration_ms"] >= 0


@pytest.mark.parametrize("change", ["recordings", "accent"])
def test_kept_speech_for_other_recordings_or_another_accent_is_not_used(
    tmp_path: Path, change: str, caplog: pytest.LogCaptureFixture
) -> None:
    voice = recorded(tmp_path)
    accent_engine(clone_keeps_accent=True)[0].prepare(voice, "british")
    if change == "recordings":
        recorded(tmp_path, b"Larry speaking again")
    restarted, _, kokoros, _ = accent_engine(clone_keeps_accent=True)
    with caplog.at_level(logging.INFO):
        restarted.prepare(voice, "british" if change == "recordings" else "american")
    assert kokoros  # converted anew
    assert "Kept accent speech is for another voice or accent" in caplog.text
    restarted, _, kokoros, _ = accent_engine(clone_keeps_accent=True)
    restarted.prepare(voice, "british" if change == "recordings" else "american")
    assert kokoros == {}  # and kept again for the next start


def test_a_clone_that_keeps_accents_learns_anew_when_only_the_base_voice_was_kept(
    tmp_path: Path,
) -> None:
    voice = recorded(tmp_path)
    engine, _, _, _ = accent_engine(clone_keeps_accent=True)
    engine.base, engine.accent = "bm_george", "british"
    engine._keep(voice, np.zeros(0, dtype=np.float32))
    restarted, clone, kokoros, _ = accent_engine(clone_keeps_accent=True)
    restarted.prepare(voice, "british")
    # The kept base voice reads the passage; no probe is spoken.
    assert kokoros["b"].said == [("bm_george", PASSAGE)]
    assert clone.learned[-1] == f"{voice} from speech at 0.400"


def test_broken_kept_speech_is_converted_anew(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    voice = recorded(tmp_path)
    kept_path(voice).write_bytes(b"not an npz")
    engine, _, kokoros, _ = accent_engine(clone_keeps_accent=True)
    with caplog.at_level(logging.WARNING):
        engine.prepare(voice, "british")
    assert "Could not read the kept accent speech" in caplog.text
    assert engine.base == "bm_lewis" and kokoros


def test_a_truncated_kept_archive_is_converted_anew(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Codex's review: an archive cut short raises BadZipFile, which must not fail prepare."""
    voice = recorded(tmp_path)
    accent_engine(clone_keeps_accent=True)[0].prepare(voice, "british")
    kept_path(voice).write_bytes(kept_path(voice).read_bytes()[:100])
    engine, _, kokoros, _ = accent_engine(clone_keeps_accent=True)
    with caplog.at_level(logging.WARNING):
        engine.prepare(voice, "british")
    assert "Could not read the kept accent speech" in caplog.text
    assert engine.base == "bm_lewis" and kokoros  # worked out again, and kept again
    assert accent_engine(clone_keeps_accent=True)[0]._read_kept(voice, "british") is not None


def test_speech_that_cannot_be_kept_is_logged_and_prepare_carries_on(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    voice = recorded(tmp_path)
    kept_path(voice).mkdir()  # a folder in the way: the kept file can't replace it
    engine, clone, _, _ = accent_engine(clone_keeps_accent=True)
    with caplog.at_level(logging.WARNING):
        engine.prepare(voice, "british")
    assert "Could not keep the accent speech" in caplog.text
    assert clone.learned[-1] == f"{voice} from speech at 0.475"
    assert not list((tmp_path / "uploads").glob("*.writing"))


def test_without_a_readable_voice_sample_nothing_is_kept(tmp_path: Path) -> None:
    engine, _, kokoros, _ = accent_engine(clone_keeps_accent=True)
    voice = str(tmp_path / "voice-sample.wav")  # the fake clone reads no file
    engine.prepare(voice, "british")
    assert kokoros and not kept_path(voice).exists()


def test_a_clone_that_does_not_keep_accents_keeps_the_base_voice(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """R183, with Chatterbox: every line is converted, so the converter still loads after a
    restart, but the base voice isn't picked again from every voice of the accent."""
    voice = recorded(tmp_path)
    accent_engine()[0].prepare(voice, "british")
    assert kept_path(voice).is_file()
    restarted, clone, kokoros, converter = accent_engine()
    with caplog.at_level(logging.INFO):
        restarted.prepare(voice, "british")
        speech = restarted.speak(voice, "Hi")
    assert restarted.base == "bm_lewis" and "Base voice kept from last time" in caplog.text
    assert "Picked base voice" not in caplog.text
    assert [t for _, t in kokoros["b"].said] == ["Hi"]  # no probe spoken
    assert converter.voice is not None and clone.learned == [f"read {voice} afresh"]
    assert pcm16_to_float(speech.pcm)[0] == pytest.approx(0.475, abs=1e-3)
