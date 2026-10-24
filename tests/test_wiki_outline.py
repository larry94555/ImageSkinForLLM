import json
import logging
import urllib.error
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from imageskin.chat import TOKENS_PER_MESSAGE, EmptyReply, LlmError, Message, estimate
from imageskin.pdf_reading import read_pdf
from imageskin.wiki import WikiPage, build_wiki
from imageskin.wiki_outline import (
    DETAIL_PROMPT,
    DETAIL_SCHEMA,
    MAX_DEPTH,
    OUTLINE_REPLY_TOKENS,
    PARTS_PROMPT,
    PARTS_SCHEMA,
    SECTIONS_SCHEMA,
    SIMPLE_CHARS,
    SUMMARY_PROMPT,
    Entry,
    Outliner,
    Unit,
    ancestors,
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


def parts(*found: tuple[str, list[int]]) -> str:
    return json.dumps({"parts": [{"title": t, "paragraphs": n} for t, n in found]})


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
    llm = Llm(parts(("First", [1]), ("Second", [2, 3, 9])))
    page = WikiPage(f"{PDF_ID}-t1", "Topic 1", "The LLM's few sentences.", [1, 2])
    pieces = [piece(1, LONG), piece(2, "More."), piece(3, "Another topic.")]
    found = outliner(llm).outline([page], pieces)

    # A topic keeps the summary it was found with, so only its parts are asked for (R98).
    messages, schema = llm.asked[0]
    assert schema is PARTS_SCHEMA and messages[0]["content"] == PARTS_PROMPT
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
    # Page 3 is no topic's, so it is put back in an entry of its own (R98b).
    assert [(e.title, e.summary, e.pages) for e in found[1:]] == [("Page 3", "Another topic.", [3])]


def test_a_topic_the_pdf_says_little_about_is_shown_as_it_is() -> None:
    llm = Llm()
    found = outliner(llm).outline([topic(1, "Few.")], [piece(1, "Short. Text.")])
    assert llm.asked == [] and found[0].summary == "Few." and not found[0].detail


def test_paragraphs_are_sent_in_batches_that_fit_and_a_batch_with_no_parts_is_put_back() -> None:
    pieces = [piece(1, f"{n}" * 100 + ".") for n in range(1, 7)]  # 6 paragraphs, 1 sentence each
    room = estimate(PARTS_PROMPT) + estimate("Topic 1") + 2 * TOKENS_PER_MESSAGE + 230
    llm = Llm(
        "nothing here",  # paragraphs 1 and 2, asked twice
        "still nothing",
        parts(("A", [3, 1]), ("B", [4])),  # 1 is not in this batch
        parts(("C", [6, 5]), ("Again", [5])),  # 5 is in C already
    )
    progress: list[tuple[int, int]] = []
    found = outliner(
        llm, window=OUTLINE_REPLY_TOKENS + room, progress=lambda *p: progress.append(p)
    ).outline([topic(1, "Few.")], pieces)
    # A topic keeps its own summary, so the batches' are neither asked for nor summarized (R98).
    assert {m[0]["content"] for m, _ in llm.asked} == {PARTS_PROMPT}
    assert progress == [(1, 3), (2, 3), (3, 3)]  # no request planned for a summary
    batches = [m[1]["content"].split("\n\n")[1:] for m, _ in llm.asked]
    assert [[line.split(".")[0] for line in b] for b in batches] == [
        ["1", "2"],
        ["1", "2"],
        ["3", "4"],
        ["5", "6"],
    ]
    entry = found[0]
    assert entry.summary == "Few." and entry.detail
    assert [(e.title, e.summary) for e in entry.entries] == [
        # The batch with no usable answer adds no parts, so its paragraphs are put back (R98b).
        ("More from page 1", f"{pieces[0]['text']} {pieces[1]['text']}"),
        ("A", pieces[2]["text"]),
        ("B", pieces[3]["text"]),
        ("C", f"{pieces[4]['text']} {pieces[5]['text']}"),
    ]


def test_a_long_part_opens_up_again_down_to_the_last_level() -> None:
    pieces = [piece(1, f"{n}" * 129 + ".") for n in range(1, 8)]  # 7 paragraphs of 130
    llm = Llm(
        parts(("Deep", [1, 2, 3, 4, 5, 6]), ("Flat", [7])),
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
    # The topic keeps its summary, so only its parts are asked for; a part has none, so its
    # summary is asked for with its parts.
    assert [(m[0]["content"], schema) for m, schema in llm.asked] == [
        (PARTS_PROMPT, PARTS_SCHEMA),
        (DETAIL_PROMPT, DETAIL_SCHEMA),
    ]


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


def test_parts_alone_need_no_summary_and_give_none() -> None:
    assert read_detail(parts(("T", [2, 1])), {1, 2}, summarized=False) == ("", [("T", [2, 1])])
    assert read_detail(parts(), {1}, summarized=False) is None  # still no parts


def test_each_outline_step_is_logged_with_what_it_asked_for(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pieces = [piece(1, f"{n}" * 129 + ".") for n in range(1, 8)]
    llm = Llm(
        parts(("Deep", [1, 2, 3, 4, 5, 6]), ("Flat", [7])),
        detail("Level 3.", ("Deeper", [1, 2, 3, 4, 5]), ("Other", [6])),
    )
    with caplog.at_level(logging.INFO):
        outliner(llm).outline([topic(1, "Few.")], pieces)
    steps = [r for r in caplog.records if r.message == "Wiki outline step done"]
    assert [r.__dict__["step"] for r in steps] == ["parts", "detail"]


def test_saved_entries_are_read_back_and_shown_down_to_the_next_detail_page() -> None:
    leaf = Entry("l", "Leaf", "Leaf.", [1])
    inner = Entry("i", "Inner", "Inner.", [1], [leaf], detail=True)
    topic_entry = Entry("t", "Topic", "Topic.", [1], [inner, leaf], detail=True)
    section = Entry("s", "Section", "Section.", [1], [topic_entry])
    assert from_saved([asdict(section)]) == [section]
    assert find([section], "i") is inner and find([section], "nope") is None
    assert ancestors([section], "i") == [section, topic_entry]  # the levels above it
    assert ancestors([section], "s") == [] and ancestors([section], "nope") is None
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


def leaves(entries: list[Entry]) -> list[Entry]:
    return [leaf for e in entries for leaf in (leaves(e.entries) if e.entries else [e])]


def lost(found: list[Entry], topics: list[WikiPage], pieces: list[dict[str, Any]]) -> list[Unit]:
    """The PDF's paragraphs in no entry: neither in an entry's own words nor on the pages of a
    topic shown as it is (the PDF says little there)."""
    ids = {t.id for t in topics}
    words = "\n".join(e.summary for e in leaves(found) if e.id not in ids)
    whole = {p for e in leaves(found) if e.id in ids for p in e.pages}
    every = [u for p in pieces for u in units(p["page"], p["text"])]
    return [(page, text) for page, text in every if text not in words and page not in whole]


def test_paragraphs_left_out_are_put_back_at_their_place_in_the_pdf(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pieces = [piece(1, f"{n}" * 129 + ".") for n in range(1, 7)] + [piece(2, "Page two.")]
    pieces.append(piece(4, "Nobody's page."))
    llm = Llm(
        parts(("A", [1]), ("B", [4, 5])),  # leaves out 2, 3 and 6, and page 2
        sections(("First", "S.", [1, 2]), ("Second", "S.", [3, 4])),
    )
    topics = [WikiPage(f"{PDF_ID}-t1", "Topic 1", "Few.", [1, 2])]
    topics += [topic(n) for n in (3, 5, 6)]
    with caplog.at_level(logging.INFO):
        found = outliner(llm).outline(topics, pieces)
    assert lost(found, topics, pieces) == []
    one = found[0].entries[0]
    assert [(e.title, e.summary) for e in one.entries] == [
        ("A", pieces[0]["text"]),
        ("More from page 1", f"{pieces[1]['text']} {pieces[2]['text']}"),
        ("B", f"{pieces[3]['text']} {pieces[4]['text']}"),
        ("More from page 1", pieces[5]["text"]),  # a new id: the title is used already
        ("More from page 2", "Page two."),  # the next page: an entry of its own
    ]
    assert len({e.id for e in one.entries}) == 5
    # Page 4 is no topic's: between the sections of topics 1 to 3 (pages 1 to 3) and 5 and 6.
    assert [e.title for e in found] == ["First", "Page 4", "Second"]
    done = [r for r in caplog.records if r.message == "Wiki paragraphs put back"][0]
    assert done.__dict__["paragraphs"] == 5 and done.__dict__["pages"] == [1, 2, 4]


def test_a_topic_that_cannot_be_split_gets_its_pdf_paragraphs_back() -> None:
    pieces = [piece(1, LONG), piece(1, "Last.")]
    found = outliner(Llm("no", "no")).outline([topic(1, "Few.")], pieces)
    entry = found[0]
    assert entry.summary == "Few." and entry.detail
    assert [e.summary for e in entry.entries] == [f"{LONG} Last."]  # one page: one entry


def test_nothing_is_put_back_when_every_paragraph_is_in_the_wiki(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = Llm(parts(("A", [1]), ("B", [2])))
    pieces = [piece(1, LONG)]
    with caplog.at_level(logging.INFO):
        found = outliner(llm).outline([topic(1, "Few.")], pieces)
    assert [e.title for e in found[0].entries] == ["A", "B"]
    done = [r for r in caplog.records if r.message == "Wiki paragraphs put back"][0]
    assert done.__dict__["paragraphs"] == 0 and done.__dict__["pages"] == []


SPEED = Path(__file__).parent.parent / "experiments" / "speed"


def test_the_sample_pdfs_wiki_keeps_every_paragraph_of_the_pdf(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R98's cloud run of the sample PDF, built again from the LLM's recorded answers: it left 37
    of the PDF's 366 paragraphs in no entry, and now every one of them is in the wiki."""
    run = json.loads((SPEED / "wiki-r98-cloud-2026-10-23.json").read_text())["after"]
    answers = [r["answer"] for r in run["requests"]]
    topic_answers = iter(answers[: run["parts"]])
    outline_answers = iter(answers[run["parts"] :])
    pieces = [asdict(p) for p in read_pdf(SPEED / "sample.pdf").pieces]

    # The run counted tokens with llama-server's tokenizer; this estimate's count, scaled down to
    # it, splits the PDF the same way: the same topics, with every recorded answer used.
    def count(text: str) -> int:
        return int(estimate(text) * 0.3)

    wiki = build_wiki(PDF_ID, pieces, lambda m: next(topic_answers), count, 4096)
    assert [p.title for p in wiki.pages] == run["topics"]
    with caplog.at_level(logging.INFO):
        found = Outliner(PDF_ID, lambda m, s: next(outline_answers), count, 4096).outline(
            wiki.pages, pieces
        )
    assert next(outline_answers, None) is None

    every = [u for p in pieces for u in units(p["page"], p["text"])]
    put_back = [e for e in leaves(found) if e.title.startswith(("More from page", "Page "))]
    assert len(every) == 366 and lost(found, wiki.pages, pieces) == []
    done = [r for r in caplog.records if r.message == "Wiki paragraphs put back"][0]
    assert done.__dict__["paragraphs"] == 37 and len(put_back) == 8

    # Without the paragraphs put back, the outline is the run's own.
    def lines(entries: list[Entry], depth: int = 0) -> list[str]:
        return [
            line
            for e in entries
            if e not in put_back
            for line in ["  " * depth + e.title + " *" * e.detail, *lines(e.entries, depth + 1)]
        ]

    assert lines(found) == run["outline"]


def test_a_part_that_cannot_be_split_keeps_its_own_words_and_nothing_is_put_back() -> None:
    pieces = [piece(1, f"{n}" * 129 + ".") for n in range(1, 8)]
    llm = Llm(parts(("Deep", [1, 2, 3, 4, 5, 6]), ("Flat", [7])), "no", "no")
    found = outliner(llm).outline([topic(1, "Few.")], pieces)
    assert [e.title for e in found[0].entries] == ["Deep", "Flat"]
    assert found[0].entries[0].summary == " ".join(p["text"] for p in pieces[:6])
