import pytest

from imageskin.speech_text import spoken_text


def spoken(display: str) -> str:
    return spoken_text(display)


def test_plain_text_is_spoken_as_is() -> None:
    assert spoken("Hello, Larry. How are you?") == "Hello, Larry. How are you?"


def test_empty_and_unspeakable_replies_say_nothing() -> None:
    assert spoken("") == ""
    assert spoken("```\nprint(1)\n```") == ""
    assert spoken("👍 https://example.com") == ""


@pytest.mark.parametrize(
    ("display", "said"),
    [
        ("This is **bold**, *italic* and __strong__.", "This is bold, italic and strong."),
        ("It was _really_ ~~cheap~~ good.", "It was really cheap good."),
        ("Keep snake_case and 2 * 3 as they are.", "Keep snake_case and 2 * 3 as they are."),
        ("See [the guide](https://x.io/guide) first.", "See the guide first."),
        ("Look ![a cat](cat.png) here.", "Look here."),
        ("One<br>two", "One two"),
    ],
)
def test_markdown_markers_are_dropped_and_words_kept(display: str, said: str) -> None:
    assert spoken(display) == said


def test_code_is_not_spoken() -> None:
    reply = "Run this:\n\n```python\nprint('hi')\n```\n\nThen call `main()` again."
    assert spoken(reply) == "Run this: Then call again."


def test_a_longer_fence_can_hold_a_shorter_one() -> None:
    reply = "Like this:\n````md\n```py\nx = 1\n```\n````\nDone."
    assert spoken(reply) == "Like this: Done."


def test_inline_code_ends_at_the_same_number_of_backticks() -> None:
    assert spoken("Use ``code`` now.") == "Use now."
    assert spoken("Type `` a`b `` here.") == "Type here."
    assert spoken("Inline ```x``` too.") == "Inline too."


def test_an_unclosed_code_block_runs_to_the_end() -> None:
    assert spoken("Try:\n```\nx = 1\ny = 2") == "Try:"


@pytest.mark.parametrize(
    ("display", "said"),
    [
        ("Go to https://example.com/a?b=1.", "Go to."),
        ("Or www.example.org, today.", "Or, today."),
        ("Docs (http://a.io/x) help.", "Docs help."),
    ],
)
def test_urls_are_not_spoken_but_punctuation_after_them_is(display: str, said: str) -> None:
    assert spoken(display) == said


def test_emoji_are_not_spoken() -> None:
    assert spoken("Great 👍🏽 job 🎉!") == "Great job!"
    assert spoken("Family 👨‍👩‍👧 and flag 🇺🇸 and ❤️ love") == "Family and flag and love"


def test_lines_without_punctuation_end_a_sentence() -> None:
    reply = "## Shopping list\n\n- Eggs\n* Milk\n+ Bread.\n\n> Quoted line\nDone"
    assert spoken(reply) == "Shopping list. Eggs. Milk. Bread. Quoted line. Done"


def test_a_line_break_inside_a_paragraph_is_only_a_space() -> None:
    reply = "This is one sentence\ncontinued here.\nAnd\n\nNew paragraph\n\n1. First\n2) Second"
    said = "This is one sentence continued here. And. New paragraph. First. Second"
    assert spoken(reply) == said


def test_tables_are_read_cell_by_cell() -> None:
    reply = "| Name | Age |\n|---|:---:|\n| Ann | 30 |"
    assert spoken(reply) == "Name Age. Ann 30"
