import pytest

from imageskin.sentences import LONG_CLIP_WORDS, SentenceSplitter, clips
from imageskin.speech_text import TABLE, spoken_text


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
    # Nor is a picture, link or HTML tag, which speech_text replaces whole: the clause ends
    # after it instead (a review finding on R22b), or the sentence stays whole when that would
    # pass eight words.
    (
        "Please see ![a detailed diagram of it](d.png) before we go on. Next.",
        ["Please see ![a detailed diagram of it](d.png)", "before we go on.", "Next."],
    ),
    (
        "Read [the long guide to it](https://a.io/g) first and then go. Next.",
        ["Read [the long guide to it](https://a.io/g)", "first and then go.", "Next."],
    ),
    (
        'One two <span class="a b c"> three four five six. Next.',
        ['One two <span class="a b c">', "three four five six.", "Next."],
    ),
    (
        "Please see ![a very detailed diagram showing the entire architecture clearly]"
        "(diagram.png) before continuing. Next.",
        [
            "Please see ![a very detailed diagram showing the entire architecture clearly]"
            "(diagram.png) before continuing.",
            "Next.",
        ],
    ),
    ("```\nx = f(a, b, c)\n```\nSo, that is it.", ["```\nx = f(a, b, c)\n```", "So, that is it."]),
    # Nor a line that may be a table's row, as a table is replaced whole (another finding).
    (
        "| Name of the person here | Age of them now | City |\n|---|---|---|\n| Ann | 3 | Rome |"
        "\n\nAfter that. Next.",
        [
            "| Name of the person here | Age of them now | City |\n|---|---|---|"
            "\n| Ann | 3 | Rome |",
            "After that.",
            "Next.",
        ],
    ),
]


@pytest.mark.parametrize(("text", "expected"), FIRST_CLAUSE_CASES)
@pytest.mark.parametrize("step", [1, 3, 1000])
def test_the_first_sentences_first_clause_is_a_sentence_of_its_own(
    text: str, expected: list[str], step: int
) -> None:
    assert clauses(text, step) == expected


def test_a_table_whose_first_line_is_long_is_still_spoken_as_a_table() -> None:
    table = (
        "| Name of the person here | Age of them now | City |\n|---|---|---|\n| Ann | 3 | Rome |"
    )
    for step in (1, 3, 1000):
        spoken = [spoken_text(s) for s in clauses(table + "\n\nAfter that.", step)]
        assert spoken == [TABLE, "After that."]


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


@pytest.mark.parametrize("step", [1, 3, 1000])
def test_math_is_not_cut_while_it_is_still_being_written(step: int) -> None:
    # Review on PR #79: the first clause's word count was reached inside the open $...$.
    zeta = r"$\zeta(s) = \sum_{n=1}^{\infty} \frac{1}{n^s}$"
    text = f"The formula is {zeta} for s above one. Next."
    sentences = clauses(text, step)
    assert all(s.count("$") % 2 == 0 for s in sentences)
    assert "Next." in sentences and "".join(sentences).replace(" ", "") == text.replace(" ", "")
    assert all("$" not in spoken_text(s) and "\\" not in spoken_text(s) for s in sentences)


@pytest.mark.parametrize("step", [1, 3, 1000])
def test_a_full_stop_inside_math_does_not_end_the_sentence(step: int) -> None:
    assert split("Use $A=1. B=2$ here. Next.", step) == ["Use $A=1. B=2$ here.", "Next."]
    assert split("Use \\(A=1. B\\) here. Next.", step) == ["Use \\(A=1. B\\) here.", "Next."]


def test_money_does_not_hold_back_the_first_clause() -> None:
    assert clauses("It costs $5 and more than that today. Bye.", 1000)[0] == "It costs $5"


@pytest.mark.parametrize("step", [1, 3, 1000])
@pytest.mark.parametrize(("opener", "closer"), [("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)")])
def test_math_over_several_lines_is_never_cut(opener: str, closer: str, step: int) -> None:
    # Review on PR #79: a cut on a later line than the opener split display math.
    math = f"{opener}\nA = 1. B = 2. And then c equals d plus e plus f\n{closer}"
    for first_clause in (False, True):
        splitter = SentenceSplitter(first_clause=first_clause)
        text = f"Here it is:\n{math}\nNext one. Done."
        sentences: list[str] = []
        for i in range(0, len(text), step):
            sentences += splitter.feed(text[i : i + step])
        sentences += splitter.flush()
        holding = [s for s in sentences if opener in s or closer in s]
        assert len(holding) == 1 and opener in holding[0] and closer in holding[0]
        assert all("$" not in spoken_text(s) and "\\" not in spoken_text(s) for s in sentences)


@pytest.mark.parametrize("step", [1, 3, 1000])
def test_a_dollar_in_code_or_a_url_does_not_hold_back_the_sentence(step: int) -> None:
    # Review on PR #79: a $ in inline code was taken as math still open.
    assert split("Use `$HOME`. Next.", step) == ["Use `$HOME`.", "Next."]
    assert split("Run `$$`. Next one.\nAnd more. Done.", step) == [
        "Run `$$`.",
        "Next one.",
        "And more.",
        "Done.",
    ]
    assert split("See https://a.io/$x here. Next.", step) == ["See https://a.io/$x here.", "Next."]
    code = "Run this:\n\n```\necho $$\n```\n\nThen go. Done."
    assert split(code, step)[-2:] == ["Then go.", "Done."]


class Voice:
    """Whether the voice is waiting, set by the test as the clips would be."""

    def __init__(self) -> None:
        self.waiting = False

    def __call__(self) -> bool:
        return self.waiting


def test_an_unfinished_sentence_is_cut_at_its_clause_while_the_voice_waits() -> None:
    voice = Voice()
    splitter = SentenceSplitter(first_clause=True, voice_waiting=voice)
    assert splitter.feed("Hello there Larry, it is") == ["Hello there Larry,"]
    # The voice is busy with the first clause: the rest waits for its full stop.
    assert splitter.feed(" a fine day, and the sun") == []
    voice.waiting = True  # the first clip is made and the LLM is still writing
    assert splitter.feed(" is") == ["it is a fine day,"]
    assert splitter.waiting_cuts == {2}
    voice.waiting = False
    assert splitter.feed(" out. Next") == ["and the sun is out."]
    assert splitter.flush() == ["Next"]
    assert splitter.waiting_cuts == {2}


def test_a_finished_sentence_is_handed_over_whole_even_while_the_voice_waits() -> None:
    voice = Voice()
    splitter = SentenceSplitter(first_clause=True, voice_waiting=voice)
    assert splitter.feed("Hello there Larry, it") == ["Hello there Larry,"]
    voice.waiting = True
    assert splitter.feed(" is a fine day, and the sun is out. Then") == [
        "it is a fine day, and the sun is out."
    ]
    assert splitter.waiting_cuts == set()


def test_a_clause_too_short_or_none_waits_for_more() -> None:
    splitter = SentenceSplitter(first_clause=True, voice_waiting=lambda: True)
    assert splitter.feed("Hello there Larry, how") == ["Hello there Larry,"]
    assert splitter.feed(" are you") == []  # too few words for a clause
    assert splitter.feed("?") == []
    assert splitter.feed(" Fine") == ["how are you?"]
    assert splitter.waiting_cuts == set()
    # Without `voice_waiting`, a sentence after the first clause waits for its full stop.
    plain = SentenceSplitter(first_clause=True)
    assert plain.feed("Hello there Larry, it is a fine day, and the sun") == ["Hello there Larry,"]


def test_a_known_reply_s_first_clause_and_long_sentences_are_clips_of_their_own() -> None:
    topics = (
        "I can talk about Prime Number Definition, The Sieve of Eratosthenes, The Zeta"
        " Function, Euler's Product Formula and 4 more on the Wiki page."
    )
    assert clips([topics, "You could start by asking me about The Zeta Function."]) == [
        "I can talk about Prime Number Definition,",
        "The Sieve of Eratosthenes, The Zeta Function,",
        "Euler's Product Formula and 4 more on the Wiki page.",
        "You could start by asking me about The Zeta Function.",
    ]


def test_short_known_sentences_are_spoken_whole() -> None:
    assert clips(["I can talk about Rain.", "Ask me anything about it."]) == [
        "I can talk about Rain.",
        "Ask me anything about it.",
    ]
    assert clips([]) == []
    assert clips(["  ", "Hi."]) == ["Hi."]


def test_a_known_sentence_is_never_cut_but_at_punctuation() -> None:
    # Not inside a title, though long: there is nowhere to cut it.
    sentence = "Sorry I can only answer questions about the material I was given just now today."
    assert clips([sentence, sentence]) == [sentence, sentence]
    # A first clause too short is joined to the next.
    assert clips(["Yes, it is, and the rest follows."]) == ["Yes, it is,", "and the rest follows."]
    # Later clauses are joined up to LONG_CLIP_WORDS words.
    long = ", ".join(["one two three"] * 6) + "."
    pieces = clips(["Hi.", long])
    four = ", ".join(["one two three"] * 4) + ","
    assert pieces == ["Hi.", four, "one two three, one two three."]
    assert all(len(p.split()) <= LONG_CLIP_WORDS for p in pieces)


def test_a_known_reply_with_a_code_block_is_left_whole() -> None:
    code = "Here is some code, which prints a number:\n```\nprint(1)\n```"
    assert clips([code]) == [code]


@pytest.mark.parametrize(
    "first",
    [
        "Is the value of $f(x, y)$, for every pair, the same as before",
        "Is the value of f(x, y), for every pair, the same as before",
        "Is the value of `f(x, y)`, for every pair, the same as before",
        "Is the value of [f, g](https://example.com/a,b), for every pair, the same as before",
        'Is the value of <span title="f, g">f</span>, for every pair, the same as before',
    ],
)
def test_a_known_sentence_is_not_cut_inside_math_code_brackets_or_markup(first: str) -> None:
    sentence = f"{first} or not?"
    head = first.split(", for every pair")[0] + ","
    assert clips([sentence]) == [head, "for every pair, the same as before or not?"]
    assert all(spoken_text(p) for p in clips([sentence]))


def test_a_title_with_a_comma_may_be_cut_at_it() -> None:
    assert clips(["I can talk about War, Peace and Politics and Rain."]) == [
        "I can talk about War,",
        "Peace and Politics and Rain.",
    ]
