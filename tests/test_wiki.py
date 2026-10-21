import json
import logging
import urllib.error

import pytest

from imageskin.chat import EmptyReply, LlmError, Message, estimate
from imageskin.wiki import (
    KNOWN_PROMPT,
    TITLES_TOKENS,
    WIKI_REPLY_TOKENS,
    Part,
    WikiError,
    ask_part,
    build_wiki,
    cut,
    latest_titles,
    normalize,
    parse,
    prompt_tokens,
    slug,
    split,
    unique,
)

PDF_ID = "a" * 32
# A window that leaves 1000 tokens (bytes, with `estimate`) for each part.
WINDOW = WIKI_REPLY_TOKENS + prompt_tokens(estimate) + 1000


def piece(page: int, text: str) -> dict[str, object]:
    return {"page": page, "kind": "paragraph", "text": text, "rows": None}


def answer(*topics: tuple[str, list[int], str]) -> str:
    return json.dumps({"topics": [{"title": t, "pages": p, "text": x} for t, p, x in topics]})


def test_pieces_are_marked_with_their_page_and_kept_together_while_they_fit() -> None:
    parts = split([piece(1, "a" * 40), piece(2, "b" * 40), piece(3, "c" * 40)], 110, estimate)
    assert parts == [
        Part(f"[page 1] {'a' * 40}\n\n[page 2] {'b' * 40}", [1, 2]),
        Part(f"[page 3] {'c' * 40}", [3]),
    ]


def test_a_piece_too_long_for_one_part_is_cut_at_spaces() -> None:
    text = " ".join(["word"] * 300)  # 1499 characters
    pieces = cut(text, 500, estimate)
    assert len(pieces) == 4 and all(len(p) <= 500 for p in pieces)
    assert " ".join(pieces) == text
    assert cut("short", 500, estimate) == ["short"]
    assert cut("x" * 900, 300, estimate) == ["x" * 270, "x" * 270, "x" * 270, "x" * 90]


def test_parse_keeps_usable_topics_and_only_the_parts_pages() -> None:
    raw = answer(("  The   Water Cycle ", [2, 9], " Water moves. "), ("No pages", [], "Text."))
    assert parse(raw, [1, 2, 3]) == [
        ("The Water Cycle", [2], "Water moves."),
        ("No pages", [1, 2, 3], "Text."),
    ]


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON at all",
        "[]",
        '{"topics": "none"}',
        '{"topics": [1, {"title": "", "text": "x"}, {"title": "T", "text": 3}]}',
        '{"topics": [{"title": "T", "text": "  "}]}',
        "{ broken",
    ],
)
def test_parse_finds_nothing_in_an_unusable_answer(raw: str) -> None:
    assert parse(raw, [1]) == []


def test_parse_finds_json_wrapped_in_other_words() -> None:
    raw = 'Here you go:\n```json\n{"topics": [{"title": "T", "pages": ["2", 1], "text": "x"}]}\n```'
    assert parse(raw, [1, 2]) == [("T", [1], "x")]


def test_a_part_is_asked_again_when_the_first_answer_cannot_be_used(
    caplog: pytest.LogCaptureFixture,
) -> None:
    answers = iter(["Sorry, I can't.", answer(("Topic", [1], "Text."))])
    asked: list[list[Message]] = []

    def ask(messages: list[Message]) -> str:
        asked.append(messages)
        return next(answers)

    with caplog.at_level(logging.WARNING):
        assert ask_part(Part("[page 1] x", [1]), ["Earlier"], ask) == [("Topic", [1], "Text.")]
    assert len(asked) == 2
    assert asked[0][0]["content"].endswith(f"{KNOWN_PROMPT} Earlier")
    assert asked[0][1] == {"role": "user", "content": "[page 1] x"}
    assert "The LLM's wiki answer could not be used" in caplog.text


def test_an_empty_reply_counts_as_unusable_but_a_failed_request_is_passed_on() -> None:
    def empty(messages: list[Message]) -> str:
        raise EmptyReply("The LLM sent an empty reply.")

    assert ask_part(Part("x", [1]), [], empty) is None

    def refuse(messages: list[Message]) -> str:
        raise LlmError("The LLM refused the prompt (400): too long")

    with pytest.raises(LlmError, match="refused"):
        ask_part(Part("x", [1]), [], refuse)

    def down(messages: list[Message]) -> str:
        raise LlmError("Could not reach the LLM") from urllib.error.URLError("refused")

    with pytest.raises(LlmError):
        ask_part(Part("x", [1]), [], down)


def test_a_refused_request_fails_the_build_even_with_a_wait_for_the_llm() -> None:
    def refuse(messages: list[Message]) -> str:
        raise LlmError("The LLM refused the prompt (400)")

    waited: list[int] = []
    with pytest.raises(LlmError, match="refused"):
        build_wiki(
            PDF_ID,
            [piece(1, "a")],
            refuse,
            estimate,
            WINDOW,
            None,
            lambda e, n, of: waited.append(n),
        )
    assert waited == []


def test_every_cut_of_a_long_piece_keeps_its_page() -> None:
    text = " ".join(["word"] * 300)  # far more than one part
    parts = split([piece(1, text), piece(2, "next")], 500, estimate)
    assert len(parts) >= 3
    for part in parts[:-1]:
        assert part.text.startswith("[page 1] ") and part.pages == [1]
        assert estimate(part.text) <= 500
    assert parts[-1].text.endswith("[page 2] next") and parts[-1].text.startswith("[page 1] ")


def test_only_the_latest_titles_that_fit_are_passed_on() -> None:
    titles = [f"Title {n:03}" for n in range(100)]  # 9 characters each
    kept = latest_titles(titles, estimate)
    assert kept == titles[-len(kept) :] and len(kept) == TITLES_TOKENS // 10


def test_the_wiki_has_one_page_per_topic_merged_across_parts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    answers = iter(
        [
            answer(("The Water Cycle", [1], "Water evaporates."), ("Clouds", [2], "They form.")),
            answer(("the water cycle.", [3], "Rain."), ("Clouds", [3], "Rain clouds.")),
        ]
    )
    asked: list[list[Message]] = []

    def ask(messages: list[Message]) -> str:
        asked.append(messages)
        return next(answers)

    progress: list[tuple[int, int]] = []
    pieces = [piece(1, "a" * 400), piece(2, "b" * 400), piece(3, "c" * 400)]
    with caplog.at_level(logging.INFO):
        wiki = build_wiki(PDF_ID, pieces, ask, estimate, WINDOW, lambda *p: progress.append(p))

    assert wiki.parts == 2 and wiki.skipped_parts == []
    assert [(p.id, p.title, p.pages, p.text) for p in wiki.pages] == [
        (f"{PDF_ID}-the-water-cycle", "The Water Cycle", [1, 3], "Water evaporates.\n\nRain."),
        (f"{PDF_ID}-clouds", "Clouds", [2, 3], "They form.\n\nRain clouds."),
    ]
    assert progress == [(0, 2), (1, 2), (2, 2)]  # the count first, before any part is asked
    assert asked[1][0]["content"].endswith(f"{KNOWN_PROMPT} The Water Cycle; Clouds")
    done = [r for r in caplog.records if r.message == "Wiki part done"]
    assert [r.__dict__["topics"] for r in done] == [2, 2]
    assert all(r.__dict__["duration_ms"] >= 0 for r in done)


def test_parts_with_no_usable_answer_are_skipped_and_listed() -> None:
    answers = iter(["no", "still no", answer(("Clouds", [2], "They form."))])
    pieces = [piece(1, "a" * 900), piece(2, "b" * 900)]
    wiki = build_wiki(PDF_ID, pieces, lambda m: next(answers), estimate, WINDOW)
    assert wiki.parts == 2 and wiki.skipped_parts == [1]
    assert [p.title for p in wiki.pages] == ["Clouds"]


def test_the_build_fails_when_no_part_has_a_usable_answer() -> None:
    with pytest.raises(WikiError, match="couldn't be used"):
        build_wiki(PDF_ID, [piece(1, "a")], lambda m: "no", estimate, WINDOW)


def test_a_pdf_with_no_text_has_no_pages() -> None:
    wiki = build_wiki(PDF_ID, [], lambda m: "unused", estimate, WINDOW)
    assert wiki.parts == 0 and wiki.pages == []


def test_a_window_too_small_for_the_wiki_is_refused() -> None:
    with pytest.raises(WikiError, match="can.t take in enough"):
        build_wiki(PDF_ID, [piece(1, "a")], lambda m: "", estimate, 1500)


def test_titles_become_unique_ids() -> None:
    assert normalize("The Water-Cycle!") == normalize("the water cycle")
    assert slug("Écoles & Rules (2024)") == "coles-rules-2024"
    assert slug("日本") == "topic"
    used: set[str] = set()
    assert [unique("p-a", used), unique("p-a", used), unique("p-a", used)] == [
        "p-a",
        "p-a-2",
        "p-a-3",
    ]


def test_an_unreachable_llm_is_waited_for_and_the_same_part_asked_again() -> None:
    def down() -> LlmError:
        error = LlmError("Could not reach the LLM")
        error.__cause__ = urllib.error.URLError("refused")
        return error

    answers: list[str | LlmError] = [answer(("A", [1], "x")), down(), answer(("B", [2], "y"))]
    asked: list[str] = []

    def ask(messages: list[Message]) -> str:
        asked.append(messages[1]["content"])
        next_answer = answers.pop(0)
        if isinstance(next_answer, LlmError):
            raise next_answer
        return next_answer

    waits: list[tuple[int, int]] = []
    pieces = [piece(1, "a" * 900), piece(2, "b" * 900)]
    wiki = build_wiki(
        PDF_ID, pieces, ask, estimate, WINDOW, wait_for_llm=lambda e, n, of: waits.append((n, of))
    )
    assert waits == [(2, 2)]
    assert asked[1] == asked[2] and len(asked) == 3
    assert [p.title for p in wiki.pages] == ["A", "B"]
    with pytest.raises(LlmError):
        build_wiki(PDF_ID, pieces[:1], lambda m: (_ for _ in ()).throw(down()), estimate, WINDOW)
