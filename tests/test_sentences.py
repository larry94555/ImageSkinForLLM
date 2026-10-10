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
    (  # a ```` block holds ```, and only a fence of the same character closes a block
        "Code:\n````md\n```\nA. B\n```\n````\nAfter. Done.",
        ["Code:", "````md\n```\nA. B\n```\n````", "After.", "Done."],
    ),
    (
        "Code:\n```\nA. B\n~~~\nC. D\n```\nAfter.",
        ["Code:", "```\nA. B\n~~~\nC. D\n```", "After."],
    ),
    (
        'Use `print("Hi. Bye")` here. Next.',
        ['Use `print("Hi. Bye")` here.', "Next."],
    ),
    ("Run ``a`. b`` now. Then go.", ["Run ``a`. b`` now.", "Then go."]),
    # A backtick that starts no code splits once its line is complete.
    ("A stray ` mark. Then more.\nNew line.", ["A stray ` mark.", "Then more.", "New line."]),
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


def test_a_sentence_waits_while_inline_code_may_still_close() -> None:
    splitter = SentenceSplitter()
    assert splitter.feed("Type `exit. Now") == []  # the ` may close later on this line
    assert splitter.feed("` to stop. Then") == ["Type `exit. Now` to stop."]


# --- The first clause, cut short for the first clip (R22b) ---


def clauses(text: str, step: int = 3) -> list[str]:
    splitter = SentenceSplitter(first_clause=True)
    sentences: list[str] = []
    for i in range(0, len(text), step):
        sentences += splitter.feed(text[i : i + step])
    return sentences + splitter.flush()


FIRST_CLAUSE_CASES = [
    # At a comma, semicolon, colon or dash, once there are three words and the next has started.
    ("Hi Larry, how are you today? Fine.", ["Hi Larry, how are you today?", "Fine."]),
    ("Well now Larry, how are you? Fine.", ["Well now Larry,", "how are you?", "Fine."]),
    ("He was a leader; he led. Next.", ["He was a leader;", "he led.", "Next."]),
    ("Here is the thing: it works. Next.", ["Here is the thing:", "it works.", "Next."]),
    ("He was a leader — a great one. Next.", ["He was a leader", "— a great one.", "Next."]),
    ("He was a leader—a great one. Next.", ["He was a leader", "—a great one.", "Next."]),
    # Before a joining word.
    (
        "He led the movement because he had to. Next.",
        ["He led the movement", "because he had to.", "Next."],
    ),
    ('She said "yes, we can" and left. Next.', ['She said "yes,', 'we can" and left.', "Next."]),
    # After five words when there is no clause (R22e), but not on a word that leads into the
    # next: then on the last word before it that doesn't lead into the next...
    (
        "One two three four five six seven of the big old house. Next.",
        ["One two three four five", "six seven of the big old house.", "Next."],
    ),
    (
        "Martin Luther King Jr. was a really important leader in the Civil Rights Movement. Next.",
        [
            "Martin Luther King Jr.",
            "was a really important leader in the Civil Rights Movement.",
            "Next.",
        ],
    ),
    (
        "He said yes (quickly) the big old house. Next.",
        ["He said yes (quickly)", "the big old house.", "Next."],
    ),
    # ...or, when every word so far leads into the next, on the first after that doesn't.
    ("The of the in the big old house. Next.", ["The of the in the big", "old house.", "Next."]),
    (  # eight words at most, whatever the eighth is
        "The of the in the of a the an cat. Next.",
        ["The of the in the of a the", "an cat.", "Next."],
    ),
    # A short first sentence, or one that ends before a clause, is kept whole.
    ("Hello there, Larry.", ["Hello there, Larry."]),
    ("I am fine. And you, Larry, how are you?", ["I am fine.", "And you, Larry, how are you?"]),
    ("One two three four five.", ["One two three four five."]),
    ("One two three four five six.", ["One two three four five six."]),
    ("The capital of France is Paris.", ["The capital of France is Paris."]),
    ("One two three four five", ["One two three four five"]),
    # Only the first sentence is cut; a comma inside inline code isn't a clause.
    (
        "Use `a, b, c` now, please. Then, go on, and stop.",
        ["Use `a, b, c` now,", "please.", "Then, go on, and stop."],
    ),
    # Looking back for a word to end on skips code and dashes too.
    (
        "Try `x, y` is the a big old house. Next.",
        ["Try `x, y` is the a big", "old house.", "Next."],
    ),
    ("He was – the of old house now. Next.", ["He was – the of old", "house now.", "Next."]),
    ("Steps:\n1. First, do this\n2. Then, that", ["Steps:", "1. First, do this", "2. Then, that"]),
    ("```\nx = f(a, b, c)\n```\nSo, that is it.", ["```\nx = f(a, b, c)\n```", "So, that is it."]),
]


@pytest.mark.parametrize(("text", "expected"), FIRST_CLAUSE_CASES)
@pytest.mark.parametrize("step", [1, 3, 1000])
def test_the_first_sentences_first_clause_is_a_sentence_of_its_own(
    text: str, expected: list[str], step: int
) -> None:
    assert clauses(text, step) == expected


def test_the_first_clause_waits_for_the_next_word() -> None:
    splitter = SentenceSplitter(first_clause=True)
    assert splitter.feed("Well now Larry,") == []  # the sentence may end here
    assert splitter.feed(" ") == []
    assert splitter.feed("how") == ["Well now Larry,"]
    assert splitter.flush() == ["how"]


def test_a_cut_by_word_count_waits_for_the_word_after_the_next() -> None:
    splitter = SentenceSplitter(first_clause=True)
    assert splitter.feed("One two three four five six") == []  # the sentence may end on "six"
    assert splitter.feed(" s") == ["One two three four five"]
    assert splitter.flush() == ["six s"]
