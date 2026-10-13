import json
import logging
import urllib.error
from dataclasses import asdict
from typing import Any

import pytest

from imageskin.chat import TOKENS_PER_MESSAGE, EmptyReply, LlmError, Message, estimate
from imageskin.wiki import WikiPage
from imageskin.wiki_outline import (
    DETAIL_PROMPT,
    DETAIL_SCHEMA,
    MAX_DEPTH,
    OUTLINE_REPLY_TOKENS,
    SECTIONS_SCHEMA,
    SIMPLE_CHARS,
    SUMMARY_PROMPT,
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
    units,
)

PDF_ID = "a" * 32
WINDOW = 4096
LONG = " ".join(f"Sentence {n} says something." for n in range(1, 9))  # 8 sentences


def topic(n: int, text: str = "Short.") -> WikiPage:
    return WikiPage(f"{PDF_ID}-t{n}", f"Topic {n}", text, [n])


def sections(*found: tuple[str, str, list[int]]) -> str:
    return json.dumps({"sections": [{"title": t, "summary": s, "topics": n} for t, s, n in found]})


def detail(summary: str, *parts: tuple[str, list[int]]) -> str:
    found = [{"title": t, "paragraphs": n} for t, n in parts]
    return json.dumps({"summary": summary, "parts": found})


def piece(page: int, text: str) -> dict[str, Any]:
    return {"page": page, "kind": "paragraph", "text": text, "rows": None}


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
    assert not simple("x" * 601)  # one long "sentence", such as a list with no full stops
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
    progress: list[tuple[int, int]] = []
    found = outliner(llm, progress=lambda *p: progress.append(p)).outline(
        [topic(n) for n in range(1, 5)]
    )

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
    assert progress == [(1, 1)]


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


def test_a_topic_the_pdf_says_more_about_gets_a_detail_page_of_the_pdfs_paragraphs() -> None:
    llm = Llm(detail("A summary.", ("First", [1]), ("Second", [2, 3, 9])))
    page = WikiPage(f"{PDF_ID}-t1", "Topic 1", "The LLM's few sentences.", [1, 2])
    pieces = [piece(1, LONG), piece(2, "More."), piece(3, "Another topic.")]
    found = outliner(llm).outline([page], pieces)

    messages, schema = llm.asked[0]
    assert schema is DETAIL_SCHEMA
    first, rest = LONG.split(" Sentence 6")
    rest = "Sentence 6" + rest
    assert messages[1]["content"] == f"Topic 1\n\n1. {first}\n\n2. {rest}\n\n3. More."
    entry = found[0]
    assert (entry.id, entry.detail) == (f"{PDF_ID}-t1", True)
    assert entry.summary == "The LLM's few sentences."  # the topic keeps its own
    assert [(e.id, e.title, e.summary, e.pages, e.detail) for e in entry.entries] == [
        (f"{PDF_ID}-first", "First", first, [1], False),  # in the PDF's own words
        (f"{PDF_ID}-second", "Second", f"{rest} More.", [1, 2], False),
    ]


def test_a_topic_the_pdf_says_little_about_is_shown_as_it_is() -> None:
    llm = Llm()
    found = outliner(llm).outline([topic(1, "Few.")], [piece(1, "Short. Text.")])
    assert llm.asked == [] and found[0].summary == "Few." and not found[0].detail


def test_paragraphs_are_sent_in_batches_that_fit_and_a_batch_with_no_parts_adds_none() -> None:
    pieces = [piece(1, f"{n}" * 100 + ".") for n in range(1, 7)]  # 6 paragraphs, 1 sentence each
    room = estimate(DETAIL_PROMPT) + estimate("Topic 1") + 2 * TOKENS_PER_MESSAGE + 230
    llm = Llm(
        "nothing here",  # paragraphs 1 and 2, asked twice
        "still nothing",
        detail("S.", ("A", [3, 1]), ("B", [4])),  # 1 is not in this batch
        detail("S3.", ("C", [6, 5]), ("Again", [5])),  # 5 is in C already
        json.dumps({"summary": "Unused: a topic keeps its own."}),  # the batches' summaries
    )
    found = outliner(llm, window=OUTLINE_REPLY_TOKENS + room).outline([topic(1, "Few.")], pieces)
    assert llm.asked[-1][0][0]["content"] == SUMMARY_PROMPT
    assert llm.asked[-1][0][1]["content"] == "Topic 1\n\nS.\n\nS3."
    batches = [m[1]["content"].split("\n\n")[1:] for m, _ in llm.asked[:-1]]
    assert [[line.split(".")[0] for line in b] for b in batches] == [
        ["1", "2"],
        ["1", "2"],
        ["3", "4"],
        ["5", "6"],
    ]
    entry = found[0]
    assert entry.summary == "Few." and entry.detail
    assert [(e.title, e.summary) for e in entry.entries] == [
        ("A", pieces[2]["text"]),
        ("B", pieces[3]["text"]),
        ("C", f"{pieces[4]['text']} {pieces[5]['text']}"),
    ]


def test_a_long_part_opens_up_again_down_to_the_last_level() -> None:
    pieces = [piece(1, f"{n}" * 129 + ".") for n in range(1, 8)]  # 7 paragraphs of 130
    llm = Llm(
        detail("Level 2.", ("Deep", [1, 2, 3, 4, 5, 6]), ("Flat", [7])),
        detail("Level 3.", ("Deeper", [1, 2, 3, 4, 5]), ("Other", [6])),
    )
    progress: list[tuple[int, int]] = []
    found = outliner(llm, progress=lambda *p: progress.append(p)).outline(
        [topic(1, "Few.")], pieces
    )
    assert progress == [(1, 1), (2, 2)]  # the long part's request is planned once it is found
    deep = found[0].entries[0]
    assert deep.detail and deep.summary == "Level 3."  # the LLM's summary of the part
    deeper = deep.entries[0]
    assert MAX_DEPTH == 4 and not deeper.detail  # the last level, though not simple
    assert deeper.summary == " ".join(p["text"] for p in pieces[:5])
    assert len(llm.asked) == 2


def test_a_long_topic_that_cannot_be_split_is_kept_whole() -> None:
    one_part = detail("Summary.", ("Only", [1]))
    found = outliner(Llm(one_part, "")).outline([topic(1, LONG)])
    assert found[0].summary == LONG and not found[0].detail and found[0].entries == []


def test_an_empty_reply_counts_as_unusable() -> None:
    def ask(messages: list[Message], schema: dict[str, Any]) -> str:
        raise EmptyReply("The LLM sent an empty reply.")

    found = Outliner(PDF_ID, ask, estimate, WINDOW).outline([topic(1, LONG)])
    assert found[0].summary == LONG


def test_an_unreachable_llm_is_waited_for_and_a_refusal_passed_on() -> None:
    error = LlmError("Could not reach the LLM")
    error.__cause__ = urllib.error.URLError("refused")
    llm = Llm(error, detail("Summary.", ("A", [1]), ("B", [2])))
    waits: list[int] = []
    found = outliner(llm, wait_for_llm=lambda e, n, of: waits.append(n)).outline([topic(1, LONG)])
    assert waits == [1] and found[0].detail

    with pytest.raises(LlmError):
        outliner(Llm(error)).outline([topic(1, LONG)])  # no wait_for_llm
    refused = LlmError("The LLM refused the prompt (400)")
    with pytest.raises(LlmError, match="refused"):
        outliner(Llm(refused), wait_for_llm=lambda e, n, of: None).outline([topic(1, LONG)])


def test_a_long_paragraph_is_cut_into_pieces_short_enough_to_show() -> None:
    assert units(3, LONG) == [
        (3, LONG.split(" Sentence 6")[0]),
        (3, "Sentence 6" + LONG.split(" Sentence 6")[1]),
    ]
    cut_up = units(1, "word " * 140)  # one sentence of 700 characters
    assert len(cut_up) == 2 and all(len(t) <= SIMPLE_CHARS for _, t in cut_up)
    assert units(1, "  ") == []


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
        '{"summary": " ", "parts": [{"title": "T", "paragraphs": [1]}]}',
        '{"summary": "s", "parts": [1, {"title": "T", "paragraphs": [2, "1"]}]}',
        '{"summary": "s", "parts": [{"title": 2, "paragraphs": [1]}]}',
        '{"summary": "s", "parts": [{"title": "T", "paragraphs": "1"}]}',
    ],
)
def test_unusable_detail_is_none(raw: str) -> None:
    assert read_detail(raw, {1}) is None


def test_detail_keeps_each_paragraph_once() -> None:
    raw = detail(" S. ", ("T", [1, 1, 2]))
    assert read_detail(raw, {1, 2}) == ("S.", [("T", [1, 2])])


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


def test_the_table_of_contents_keeps_the_documents_order_whatever_the_llm_answers() -> None:
    llm = Llm(sections(("Later", "S.", [3, 2]), ("Gappy", "S.", [4, 6])))
    found = outliner(llm).outline([topic(n) for n in range(1, 7)])
    # Topic 1, left out, stays first; the section's topics are in order; a section whose
    # topics aren't next to each other is not kept.
    assert [e.title for e in found] == ["Topic 1", "Later", "Topic 4", "Topic 5", "Topic 6"]
    assert [e.title for e in found[1].entries] == ["Topic 2", "Topic 3"]


def test_a_part_split_in_several_batches_gets_one_summary_of_them_all() -> None:
    def count(text: str) -> int:  # a paragraph's line is 100, "Deep" 200, anything else 1
        return 200 if text == "Deep" else 100 if text[:1].isdigit() else 1

    # The topic's 5 paragraphs fit in one batch; the part "Deep" takes 3 at a time.
    window = OUTLINE_REPLY_TOKENS + 2 * TOKENS_PER_MESSAGE + 2 + 5 * 102
    pieces = [piece(1, f"{n}" * 159 + ".") for n in range(1, 6)]  # 160 characters each
    llm = Llm(
        detail("Topic.", ("Deep", [1, 2, 3, 4]), ("Flat", [5])),
        detail("First half.", ("A", [1]), ("B", [2])),
        detail("Second half.", ("C", [4])),
        json.dumps({"summary": "The whole part."}),
    )
    found = Outliner(PDF_ID, llm, count, window).outline([topic(1, "Few.")], pieces)
    deep = found[0].entries[0]
    assert deep.detail and deep.summary == "The whole part."
    assert [e.title for e in deep.entries] == ["A", "B", "C"]
    messages, _ = llm.asked[-1]
    assert messages[0]["content"] == SUMMARY_PROMPT
    assert messages[1]["content"] == "Deep\n\nFirst half.\n\nSecond half."


def test_summaries_too_many_for_one_request_are_summarized_in_rounds() -> None:
    def count(text: str) -> int:  # a summary is 100 tokens, anything else 1
        return 100 if text.startswith("Summary") else 1

    window = OUTLINE_REPLY_TOKENS + 2 * TOKENS_PER_MESSAGE + 2 + 2 * 102  # 2 summaries a request
    answers = ['{"summary": "Summary AB."}', '{"summary": "Summary CD."}', '{"summary": "All."}']
    llm = Llm(*answers)
    outline = Outliner(PDF_ID, llm, count, window, planned=1)
    progress: list[tuple[int, int]] = []
    outline.progress = lambda *p: progress.append(p)
    assert (
        outline.summarize("T", ["Summary A.", "Summary B.", "Summary C.", "Summary D."]) == "All."
    )
    sent = [m[1]["content"] for m, _ in llm.asked]
    assert sent == [
        "T\n\nSummary A.\n\nSummary B.",
        "T\n\nSummary C.\n\nSummary D.",
        "T\n\nSummary AB.\n\nSummary CD.",
    ]
    assert progress == [(1, 3), (2, 3), (3, 3)]  # the round is planned for once it is found

    one_each = Outliner(PDF_ID, Llm(), count, window - 102, planned=1)
    assert one_each.summarize("T", ["Summary A.", "Summary B."]) == "Summary A. Summary B."
    assert one_each.planned == 0


def test_the_batches_summaries_are_joined_when_the_llm_cannot_summarize_them() -> None:
    outline = outliner(Llm("no", "no"))
    assert outline.summarize("T", ["One.", "Two."]) == "One. Two."
    outline.planned = 1
    assert outline.summarize("T", ["Only."]) == "Only." and outline.planned == 0


def test_a_single_long_paragraph_gets_a_detail_page() -> None:
    llm = Llm(detail("About it.", ("Start", [1]), ("End", [2])))
    found = outliner(llm).outline([topic(1, "Few.")], [piece(1, "word " * 140)])
    assert found[0].detail and [e.title for e in found[0].entries] == ["Start", "End"]
