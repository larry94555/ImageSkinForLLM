import pytest

from imageskin.speech_text import CODE, CODE_BLOCK, LINK, LINKS, PICTURE, TABLE, spoken_text


def spoken(display: str) -> str:
    return spoken_text(display)


def test_plain_text_is_spoken_as_is() -> None:
    assert spoken("Hello, Larry. How are you?") == "Hello, Larry. How are you?"


def test_empty_and_decorative_replies_say_nothing() -> None:
    assert spoken("") == ""
    assert spoken("👍 <br> 🎉") == ""


@pytest.mark.parametrize(
    ("display", "said"),
    [
        ("This is **bold**, *italic* and __strong__.", "This is bold, italic and strong."),
        ("It was _really_ ~~cheap~~ good.", "It was really cheap good."),
        ("Keep snake_case and 2 * 3 as they are.", "Keep snake_case and 2 * 3 as they are."),
        ("See [the guide](https://x.io/guide) first.", "See the guide first."),
        ("One<br>two", "One two"),
    ],
)
def test_markdown_markers_are_dropped_and_words_kept(display: str, said: str) -> None:
    assert spoken(display) == said


def test_a_code_block_is_a_sentence_pointing_to_the_text() -> None:
    reply = "Run this:\n\n```python\nprint('hi')\n```\n\nThen call it again."
    assert spoken(reply) == f"Run this: {CODE_BLOCK} Then call it again."
    assert spoken("Run this\n~~~\nx\n~~~\nDone") == f"Run this. {CODE_BLOCK} Done"
    assert spoken("```\nprint(1)\n```") == CODE_BLOCK


def test_a_longer_fence_can_hold_a_shorter_one() -> None:
    reply = "Like this:\n````md\n```py\nx = 1\n```\n````\nDone."
    assert spoken(reply) == f"Like this: {CODE_BLOCK} Done."


def test_an_unclosed_code_block_runs_to_the_end() -> None:
    assert spoken("Try:\n```\nx = 1\ny = `2`") == f"Try: {CODE_BLOCK}"


@pytest.mark.parametrize(
    ("display", "said"),
    [
        ("Then call `main()` again.", "Then call main() again."),
        ("Use `__init__` and `**kwargs`.", "Use __init__ and **kwargs."),
        ("So `x*y` and `x**2` stay.", "So x*y and x**2 stay."),
        ("Open `https://x.io` now.", f"Open {LINK} now."),
        ("Use ``code`` now.", "Use code now."),
        ("Type `` a`b `` here.", "Type a`b here."),
        ("Inline ```x y``` too.", "Inline x y too."),
        ("Run `pip install -e .` first.", f"Run {CODE} first."),
    ],
)
def test_short_inline_code_is_spoken_and_longer_code_is_pointed_to(display: str, said: str) -> None:
    assert spoken(display) == said


@pytest.mark.parametrize(
    ("display", "said"),
    [
        ("Go to https://example.com/a?b=1.", f"Go to {LINK}."),
        ("Or www.example.org, today.", f"Or {LINK}, today."),
        ("See [the guide](https://x.io) or https://x.io.", f"See the guide or {LINK}."),
        ("Read https://a.io, https://b.io and https://c.io now.", f"Read {LINKS} now."),
        ("Read https://a.io https://b.io.", f"Read {LINKS}."),
        ("Try https://a.io or https://b.io.", f"Try {LINK} or {LINK}."),
        ("https://x.io has it.", "The link in the text below has it."),
        ("Done.\n\n- https://x.io", "Done. The link in the text below"),
        ("Choose (https://a.io) or (https://b.io).", f"Choose {LINK} or {LINK}."),
        ("See <https://a.io>.", f"See {LINK}."),
        ("See [docs](https://a.io/x) and <b>more</b>.", "See docs and more."),
    ],
)
def test_a_url_is_replaced_by_a_phrase(display: str, said: str) -> None:
    assert spoken(display) == said


def test_a_picture_is_replaced_by_a_phrase() -> None:
    assert spoken("Look at ![a cat](cat.png) here.") == f"Look at {PICTURE} here."


def test_decorative_emoji_are_not_spoken() -> None:
    assert spoken("Great 👍🏽 job 🎉!") == "Great job!"
    assert spoken("Family 👨‍👩‍👧 and flag 🇺🇸 here") == "Family and flag here"


def test_an_emoji_standing_for_a_word_is_spoken() -> None:
    assert spoken("I ❤️ it, and I ♥ that.") == "I love it, and I love that."
    assert spoken("❤️ it. Thanks ❤️") == "it. Thanks"  # no word on one side: decoration
    assert spoken("See https://x.io ❤️ it") == f"See {LINK} it"  # the word before is not said


def test_lines_without_punctuation_end_a_sentence() -> None:
    reply = "## Shopping list\n\n- Eggs\n* Milk\n+ Bread.\n\n> Quoted line\nDone"
    assert spoken(reply) == "Shopping list. Eggs. Milk. Bread. Quoted line. Done"


def test_a_line_break_inside_a_paragraph_is_only_a_space() -> None:
    reply = "This is one sentence\ncontinued here.\nAnd\n\nNew paragraph\n\n1. First\n2) Second"
    said = "This is one sentence continued here. And. New paragraph. First. Second"
    assert spoken(reply) == said


def test_a_table_is_a_sentence_pointing_to_the_text() -> None:
    rows = "| Name | Age |\n|---|:---:|\n| Ann | `30 years old` |\n| [Bo](https://b.io) | 4 |"
    reply = f"Ages\n\n{rows}\n\nDone."
    assert spoken(reply) == f"Ages. {TABLE} Done."
    assert spoken("Name | Age\n--- | ---\nAnn | 30") == TABLE


def test_horizontal_rules_and_stray_borders_are_not_spoken() -> None:
    assert spoken("Text\n\n---\n\nMore | less") == "Text. More less"


@pytest.mark.parametrize(
    ("display", "said"),
    [
        ("Martin Luther King Jr. was a leader.", "Martin Luther King Junior was a leader."),
        ("He met Martin Luther King Jr.", "He met Martin Luther King Junior."),
        ("Ask Dr. Smith or Mrs. Jones.", "Ask Doctor Smith or Missus Jones."),
        (
            "Cats vs. dogs, fruit (e.g. apples), etc.",
            "Cats versus dogs, fruit (for example apples), et cetera.",
        ),
        ("It weighs approx. 3 kg, i.e. a lot.", "It weighs approximately 3 kg, that is a lot."),
        ("Mr. Sr. and Prof. Lee", "Mister Senior and Professor Lee"),
        ("Visit St. Louis.", "Visit St. Louis."),  # Saint or Street: left as written
        ("The DRY rule and JR.EXE stay.", "The DRY rule and JR.EXE stay."),  # not short forms
        ("Bring fruit, etc. Next topic.", "Bring fruit, et cetera. Next topic."),
        ("He is Jr.\nNext line", "He is Junior. Next line"),
        ("Ask Dr. Who.", "Ask Doctor Who."),  # a title never ends the sentence
        ("Run `dr.` now.", "Run dr. now."),  # short code is said as written
        ("See [Dr. Smith](https://a.io).", "See Doctor Smith."),
    ],
)
def test_short_forms_are_said_as_words(display: str, said: str) -> None:
    assert spoken_text(display) == said
