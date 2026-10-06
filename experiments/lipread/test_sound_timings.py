import pytest
from sound_timings import split_sentences, steps_to_seconds


def test_split_sentences() -> None:
    text = "Hello, my name is Mary. Would you like some more popcorn? Go"
    assert split_sentences(text) == [
        "Hello, my name is Mary.",
        "Would you like some more popcorn?",
        "Go",
    ]
    assert split_sentences("  ") == []


def test_steps_are_25_ms() -> None:
    assert steps_to_seconds([1.0, 4.0]) == [pytest.approx(0.025), pytest.approx(0.1)]
