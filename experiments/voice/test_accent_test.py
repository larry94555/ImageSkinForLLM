"""Unit tests for the R26a accent test, with fake voice tools (no models needed)."""

import logging
from pathlib import Path

import numpy as np
import pytest
from accent_test import (
    CLONE,
    KOKORO_ACCENTS,
    convert_fitted,
    parse_donors,
    pick_base,
    run,
    voice_descriptions,
)
from page import Clip, Line, build_page
from voice_tools import SAMPLE_RATE

HALF_SECOND = SAMPLE_RATE // 2


def tone(level: float, n: int = HALF_SECOND) -> np.ndarray:
    return np.full(n, level, dtype=np.float32)


def level_of(path: Path) -> float:
    """A fake similarity: the loudness of the clip, read back from its WAV."""
    from imageskin.video import read_pcm16

    samples, _ = read_pcm16(path)
    return round(abs(samples[0]) / 32768, 2)


def test_convert_fitted_keeps_the_length() -> None:
    out = convert_fitted(tone(0.1), lambda s: tone(0.4, len(s) + 77))
    assert len(out) == HALF_SECOND and out.dtype == np.float32
    assert out[0] == pytest.approx(0.4)


def test_pick_base_converts_every_voice_and_picks_the_closest_after(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    levels = {"a": 0.1, "b": 0.5, "c": 0.4, "d": 0.3}
    converted: list[float] = []

    def convert(samples: np.ndarray) -> np.ndarray:
        converted.append(float(samples[0]))
        # After conversion the ranking flips: the base furthest from the person converts best.
        return tone(0.9 if samples[0] == pytest.approx(0.1) else 0.2)

    caplog.set_level(logging.INFO, logger="accent_test")
    best, scores = pick_base(
        list(levels), lambda v, text: tone(levels[v]), convert, level_of, tmp_path
    )
    assert best == "a" and len(converted) == 4
    assert scores[0] == {"voice": "a", "base": 0.1, "converted": 0.9}
    assert (tmp_path / "a.wav").exists() and (tmp_path / "d_converted.wav").exists()
    record = next(r for r in caplog.records if r.getMessage() == "Picked base voice")
    assert record.voice == "a" and record.duration_ms >= 0  # type: ignore[attr-defined]


def test_run_makes_clone_bases_and_conversions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="accent_test")
    bases = {"British": lambda text: tone(0.3), "Slavic donor": lambda text: tone(0.5)}
    lines = run(
        ["Hi there.", "Bye now."],
        tmp_path,
        lambda text: tone(0.1),
        bases,
        lambda s: tone(0.7, len(s) - 5),
        level_of,
        lambda path: "us 0.90",
    )
    assert len(lines) == 2
    clips = lines[0].clips
    assert list(clips) == [CLONE, "British base", "British", "Slavic donor base", "Slavic donor"]
    assert clips["Slavic donor base"].wav == "line1_slavic-donor_base.wav"
    assert clips["British"].similarity == 0.7 and clips["British base"].similarity == 0.3
    # A changed accent's time counts the base voice speaking too, not only the conversion.
    assert clips["British"].added_ms >= clips["British base"].added_ms
    assert clips[CLONE].speech_s == 0.5 and clips[CLONE].heard_as == "us 0.90"
    assert (tmp_path / "line2_british.wav").exists()
    made = [r for r in caplog.records if r.getMessage() == "Made line"]
    assert len(made) == 10


def test_run_without_similarity(tmp_path: Path) -> None:
    lines = run(["Hi."], tmp_path, lambda t: tone(0.1), {}, lambda s: s)
    assert lines[0].clips[CLONE].similarity is None


def test_descriptions_and_page_title() -> None:
    columns = voice_descriptions({"British": "Kokoro bm_george"})
    assert list(columns) == [CLONE, "British base", "British"]
    assert "bm_george converted" in columns["British"]
    line = Line("Hi.", {"British": Clip("b.wav", 1.0, 500.0, 0.6, heard_as="england 0.80")})
    page = build_page("me.wav", columns, [line], "Accent test")
    assert "<title>Accent test</title>" in page and "<h1>Accent test</h1>" in page
    assert "heard as england 0.80" in page and "similarity 0.60" in page


def test_parse_donors() -> None:
    assert parse_donors(["Slavic=a b.wav", "Indian=c.wav"]) == {
        "Slavic": Path("a b.wav"),
        "Indian": Path("c.wav"),
    }
    with pytest.raises(ValueError, match="NAME=recording.wav"):
        parse_donors(["just.wav"])


def test_every_accent_has_men_and_women() -> None:
    for lang, voices in KOKORO_ACCENTS.values():
        assert lang in ("a", "b")
        assert any(v[1] == "m" for v in voices) and any(v[1] == "f" for v in voices)


DONORS = sorted(p.name for p in (Path(__file__).parent / "donors").glob("*.wav"))


@pytest.mark.parametrize("name", DONORS)
def test_donor_recordings_are_voice_samples(name: str) -> None:
    from voice_tools import reference_clip

    from imageskin.chatterbox_engine import REFERENCE_S, read_voice_sample

    assert len(DONORS) == 6
    samples = read_voice_sample(Path(__file__).parent / "donors" / name)
    assert len(reference_clip(samples)) == int(REFERENCE_S * SAMPLE_RATE)  # 10 s to learn from
