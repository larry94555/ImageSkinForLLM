import json
import logging
import urllib.error
from dataclasses import asdict
from typing import Any

import pytest

from imageskin.chat import EmptyReply, LlmError, Message, estimate
from imageskin.wiki import WikiPage
from imageskin.wiki_outline import (
    DETAIL_SCHEMA,
    MAX_DEPTH,
    OUTLINE_REPLY_TOKENS,
    SECTIONS_SCHEMA,
    Entry,
    Outliner,
    find,
    first_sentence,
    from_saved,
    plain_outline,
    read_detail,
    read_sections,
    sentences,
    shown,
    simple,
)

PDF_ID = "a" * 32
WINDOW = 4096
LONG = " ".join(f"Sentence {n} says something." for n in range(1, 9))  # 8 sentences


def topic(n: int, text: str = "Short.") -> WikiPage:
    return WikiPage(f"{PDF_ID}-t{n}", f"Topic {n}", text, [n])


def sections(*found: tuple[str, str, list[int]]) -> str:
    return json.dumps({"sections": [{"title": t, "summary": s, "topics": n} for t, s, n in found]})


def detail(summary: str, *parts: tuple[str, str]) -> str:
    return json.dumps({"summary": summary, "parts": [{"title": t, "text": x} for t, x in parts]})


class Llm:
    """Answers each request in turn; records what was asked and with which schema."""

    def __init__(self, *answers: str | LlmError) -> None:
        self.answers = list(answers)
        self.asked: list[tuple[list[Message], dict[str, Any]]] = []

    def __call__(self, messages: list[Message], schema: dict[str, Any]) -> str:
        self.asked.append((messages, schema))
        answer = self.answers.pop(0)
        if isinstance(answer, LlmError):
            raise answer
        return answer


def outliner(llm: Llm, **kw: Any) -> Outliner:
    return Outliner(PDF_ID, llm, estimate, kw.pop("window", WINDOW), **kw)


def test_simple_texts_are_shown_as_they_are() -> None:
    assert sentences("One. Two? Three!") == 3 and sentences("") == 0
    assert simple("One. Two. Three. Four. Five.") and not simple(LONG)
    assert first_sentence(" First one. Second.") == "First one."


def test_a_few_simple_topics_are_the_table_of_contents_without_asking(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = Llm()
    with caplog.at_level(logging.INFO):
        found = outliner(llm).outline([topic(1), topic(2)])
    assert llm.asked == []
    assert found == [
        Entry(f"{PDF_ID}-t1", "Topic 1", "Short.", [1]),
        Entry(f"{PDF_ID}-t2", "Topic 2", "Short.", [2]),
    ]
    done = [r for r in caplog.records if r.message == "Wiki outline built"][0]
    assert done.__dict__["entries"] == 2 and done.__dict__["detail_pages"] == 0
    assert done.__dict__["requests"] == 0 and done.__dict__["duration_ms"] >= 0


def test_many_topics_are_grouped_into_sections_in_order() -> None:
    llm = Llm(
        sections(
            ("Water", "About water.", [1, 2, 9]),
            ("Air", "About air.", [3, 2]),
            ("Again", "Only topics already placed.", [1]),
        )
    )
    progress: list[int] = []
    found = outliner(llm, progress=progress.append).outline([topic(n) for n in range(1, 5)])

    messages, schema = llm.asked[0]
    assert schema is SECTIONS_SCHEMA
    assert messages[1]["content"].splitlines() == [f"{n}. Topic {n}: Short." for n in range(1, 5)]
    assert [(e.title, e.summary, e.pages) for e in found] == [
        ("Water", "About water.", [1, 2]),
        ("Air", "About air.", [3]),  # topic 2 is in Water already
        ("Topic 4", "Short.", [4]),  # left out by the LLM: kept on its own
    ]
    assert [e.id for e in found[0].entries] == [f"{PDF_ID}-t1", f"{PDF_ID}-t2"]
    assert found[0].id == f"{PDF_ID}-water" and not found[0].detail
    assert progress == [1]


def test_topics_are_kept_as_they_are_when_no_sections_can_be_found(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = Llm("no", "still no")
    with caplog.at_level(logging.INFO):
        found = outliner(llm).outline([topic(n) for n in range(1, 5)])
    assert [e.title for e in found] == [f"Topic {n}" for n in range(1, 5)]
    assert len(llm.asked) == 2
    assert "The LLM's wiki outline answer could not be used" in caplog.text
    step = [r for r in caplog.records if r.message == "Wiki outline step done"][0]
    assert step.__dict__["step"] == "sections" and step.__dict__["used"] is False


def test_a_long_topic_gets_a_summary_and_a_detail_page_of_its_parts() -> None:
    llm = Llm(detail("A summary.", ("First", "One. Two."), ("Second", "Three.")))
    found = outliner(llm).outline([topic(1, LONG)])

    messages, schema = llm.asked[0]
    assert schema is DETAIL_SCHEMA and messages[1]["content"] == f"Topic 1\n\n{LONG}"
    entry = found[0]
    assert (entry.id, entry.summary, entry.detail) == (f"{PDF_ID}-t1", "A summary.", True)
    assert [(e.id, e.title, e.summary, e.pages, e.detail) for e in entry.entries] == [
        (f"{PDF_ID}-first", "First", "One. Two.", [1], False),
        (f"{PDF_ID}-second", "Second", "Three.", [1], False),
    ]


def test_a_long_part_opens_up_again_down_to_the_last_level() -> None:
    llm = Llm(
        detail("Level 2.", ("Deep", LONG), ("Flat", "Flat.")),
        detail("Level 3.", ("Deeper", LONG), ("Other", "Other.")),
    )
    found = outliner(llm).outline([topic(1, LONG)])
    deep = found[0].entries[0]
    assert deep.detail and deep.summary == "Level 3."
    deeper = deep.entries[0]
    assert MAX_DEPTH == 4 and not deeper.detail and deeper.summary == LONG  # the last level
    assert len(llm.asked) == 2


def test_a_long_topic_that_cannot_be_split_is_kept_whole() -> None:
    one_part = detail("Summary.", ("Only", "Text."))
    found = outliner(Llm(one_part, "")).outline([topic(1, LONG)])
    assert found[0].summary == LONG and not found[0].detail and found[0].entries == []


def test_an_empty_reply_counts_as_unusable() -> None:
    def ask(messages: list[Message], schema: dict[str, Any]) -> str:
        raise EmptyReply("The LLM sent an empty reply.")

    found = Outliner(PDF_ID, ask, estimate, WINDOW).outline([topic(1, LONG)])
    assert found[0].summary == LONG


def test_a_long_text_is_split_in_batches_that_fit() -> None:
    paragraphs = "\n\n".join(LONG for _ in range(6))  # about 1200 characters
    window = OUTLINE_REPLY_TOKENS + 900  # leaves room for 2 paragraphs at a time
    llm = Llm(
        detail("First half.", ("A", "a."), ("B", "b.")),
        detail("Second half.", ("C", "c.")),
        detail("Third.", ("D", "d.")),
    )
    found = outliner(llm, window=window).outline([topic(1, paragraphs)])
    assert len(llm.asked) == 3
    assert all(estimate(m[1]["content"]) < 500 for m, _ in llm.asked)
    assert found[0].summary == "First half."
    assert [e.title for e in found[0].entries] == ["A", "B", "C", "D"]


def test_an_unreachable_llm_is_waited_for_and_a_refusal_passed_on() -> None:
    error = LlmError("Could not reach the LLM")
    error.__cause__ = urllib.error.URLError("refused")
    llm = Llm(error, detail("Summary.", ("A", "a."), ("B", "b.")))
    waits: list[int] = []
    found = outliner(llm, wait_for_llm=lambda e, n, of: waits.append(n)).outline([topic(1, LONG)])
    assert waits == [1] and found[0].detail

    with pytest.raises(LlmError):
        outliner(Llm(error)).outline([topic(1, LONG)])  # no wait_for_llm
    refused = LlmError("The LLM refused the prompt (400)")
    with pytest.raises(LlmError, match="refused"):
        outliner(Llm(refused), wait_for_llm=lambda e, n, of: None).outline([topic(1, LONG)])


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON",
        "[]",
        '{"sections": "x"}',
        '{"sections": [1, {"title": "", "summary": "s", "topics": [1]}]}',
        '{"sections": [{"title": "T", "summary": " ", "topics": [1]}]}',
        '{"sections": [{"title": "T", "summary": "s", "topics": [7, "1", true]}]}',
        '{"sections": [{"title": "T", "summary": "s", "topics": "1"}]}',
    ],
)
def test_unusable_sections_are_none(raw: str) -> None:
    assert read_sections(raw, {1, 2}) is None


def test_sections_keep_each_topic_once() -> None:
    raw = sections(("  Two\n words ", " S. ", [2, 1, 2]))
    assert read_sections(f"Sure: {raw}", {1, 2}) == [("Two words", "S.", [2, 1])]


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON",
        "[]",
        '{"summary": "s", "parts": []}',
        '{"summary": " ", "parts": [{"title": "T", "text": "x"}]}',
        '{"summary": "s", "parts": [1, {"title": "T", "text": " "}, {"title": 2, "text": "x"}]}',
    ],
)
def test_unusable_detail_is_none(raw: str) -> None:
    assert read_detail(raw) is None


def test_saved_entries_are_read_back_and_shown_down_to_the_next_detail_page() -> None:
    leaf = Entry("l", "Leaf", "Leaf.", [1])
    inner = Entry("i", "Inner", "Inner.", [1], [leaf], detail=True)
    topic_entry = Entry("t", "Topic", "Topic.", [1], [inner, leaf], detail=True)
    section = Entry("s", "Section", "Section.", [1], [topic_entry])
    assert from_saved([asdict(section)]) == [section]
    assert find([section], "i") is inner and find([section], "nope") is None
    page = shown(topic_entry)
    assert [e["id"] for e in page["entries"]] == ["i", "l"]
    assert page["entries"][0]["entries"] == []  # on its own detail page
    assert shown(section)["entries"][0]["entries"] == []  # the topic's own detail page
    assert plain_outline([topic(1)]) == [Entry(f"{PDF_ID}-t1", "Topic 1", "Short.", [1])]


def test_a_window_too_small_still_asks_and_the_llm_says_if_it_is_refused() -> None:
    llm = Llm("no", "no")
    found = outliner(llm, window=10).outline([topic(n) for n in range(1, 5)])
    assert len(llm.asked) == 2 and len(found) == 4
