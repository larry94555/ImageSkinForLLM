import pytest

from imageskin.sentences import SentenceSplitter


def split(text: str, step: int) -> list[str]:
    """Feed the text in pieces of `step` characters, as the LLM would stream it."""
    splitter = SentenceSplitter()
    sentences: list[str] = []
    for i in range(0, len(text), step):
        sentences += splitter.feed(text[i : i + step])
    return sentences + splitter.flush()


CASES = [
    ("Hi Larry. How are you? Great!", ["Hi Larry.", "How are you?", "Great!"]),
    (
        "Dr. Smith and Mrs. Jones met e.g. here. Bye.",
        ["Dr. Smith and Mrs. Jones met e.g. here.", "Bye."],
    ),
    ("It costs 3.50 now. Pi is 3.14159.", ["It costs 3.50 now.", "Pi is 3.14159."]),
    ("I met J. R. Tolkien. The U.S. team won.", ["I met J. R. Tolkien.", "The U.S. team won."]),
    ("Born in 1990. Moved in 2001.", ["Born in 1990.", "Moved in 2001."]),
    ("It was 5. 6 came next.", ["It was 5. 6 came next."]),  # a number may go on
    ("Go to www.example.com. Then click.", ["Go to www.example.com.", "Then click."]),
    ('He said "Stop." Then he left.', ['He said "Stop."', "Then he left."]),
    ("(See above.) Next one.", ["(See above.)", "Next one."]),
    ("Wait... really? Hmm… Yes.", ["Wait... really?", "Hmm…", "Yes."]),
    ("A paragraph\n\nAnother one", ["A paragraph", "Another one"]),
    ("Two lines\nin one paragraph.", ["Two lines\nin one paragraph."]),
    (
        "Steps:\n1. First item\n2. Second item\n- A bullet\n# Heading\nText.",
        ["Steps:", "1. First item", "2. Second item", "- A bullet", "# Heading", "Text."],
    ),
    (
        "Here is code:\n```python\nx = 1. Then\nprint(x)\n```\nThat is it. Done.",
        ["Here is code:", "```python\nx = 1. Then\nprint(x)\n```", "That is it.", "Done."],
    ),
    ("Unclosed:\n```\nx = 1. Y\n", ["Unclosed:", "```\nx = 1. Y"]),
    ("No full stop at the end", ["No full stop at the end"]),
    ("A stray . Then more", ["A stray .", "Then more"]),
    ("", []),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
@pytest.mark.parametrize("step", [1, 3, 1000])
def test_replies_split_into_sentences_however_they_arrive(
    text: str, expected: list[str], step: int
) -> None:
    assert split(text, step) == expected


def test_a_sentence_is_handed_back_as_soon_as_the_next_one_starts() -> None:
    splitter = SentenceSplitter()
    assert splitter.feed("Hello there.") == []  # it may be "Dr." so far
    assert splitter.feed(" ") == []
    assert splitter.feed("How") == ["Hello there."]
    assert splitter.feed(" are you?") == []
    assert splitter.flush() == ["How are you?"]
    assert splitter.flush() == []
