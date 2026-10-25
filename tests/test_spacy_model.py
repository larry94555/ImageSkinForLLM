"""spaCy's English model, which Kokoro's English pipeline loads through misaki (roadmap R134a).

Runs where the voice extra is installed, such as a laptop or the Docker image; skipped otherwise.
"""

import pytest

spacy = pytest.importorskip("spacy")


def test_spacys_english_model_loads_and_tokenizes() -> None:
    # preshed 3.0.14 made this raise OverflowError in the tokenizer, so prepare failed.
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        pytest.skip("en_core_web_sm is not installed")
    assert [t.text for t in nlp("Hello, I'm here.")] == ["Hello", ",", "I", "'m", "here", "."]
