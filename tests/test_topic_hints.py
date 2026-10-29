"""The topic hints under the prompt box (roadmap R41g, item 53)."""

import logging
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_question_scope import Llm, app_with_content
from test_topics import app_with_topics, ask, entry, riemann_app

from imageskin.lookup import EXAMPLES, ContentLookup, example_subjects
from imageskin.topics import HINT_TOPICS, STILL_READING, STILL_READING_REST, hint_line


def test_without_example_links_the_hint_names_a_few_topics_and_says_how_many_more() -> None:
    assert hint_line([], content_only=True) is None
    assert hint_line(["Rain"], content_only=False) == "You can ask me about Rain."
    topics = ["Rain", "Snow", "Hail", "Fog", "Wind"]
    assert hint_line(topics, content_only=True) == (
        "Questions must be about these topics: Rain, Snow, Hail and 2 more on the Wiki page."
    )
    assert hint_line(topics[:HINT_TOPICS], content_only=False) == (
        "You can ask me about Rain, Snow and Hail."
    )


def test_with_example_links_the_hint_only_leads_into_them() -> None:
    """Larry (2026-10-29): naming the topics and then linking the same ones said them twice."""
    topics = ["Rain", "Snow", "Hail", "Fog", "Wind"]
    assert hint_line(topics, content_only=False, linked=True) == "You can ask me about:"
    assert hint_line(topics, content_only=True, linked=True) == (
        "Questions must be about these topics:"
    )
    assert hint_line([], content_only=False, linked=True) is None
    assert hint_line(topics, content_only=True, complete=False, linked=True) == (
        f"{STILL_READING_REST} So far you can ask me about:"
    )
    assert hint_line([], content_only=True, complete=False, linked=True) == STILL_READING


def test_examples_ask_about_each_topic_s_first_part_then_the_topics() -> None:
    contents = [
        {"entries": [entry("Prime Numbers.", "Sieves:", "Gaps"), entry("Zeta  Function")]},
        {"entries": [entry("zeta function"), entry("Rain", "sieves")]},
    ]
    assert example_subjects(contents) == ["Sieves", "Zeta Function", "Prime Numbers", "Rain"]
    assert example_subjects([]) == []


def lookup_over(contents: list[dict[str, Any]]) -> ContentLookup:
    """A lookup over these tables of contents and no PDF text."""
    wiki = SimpleNamespace(contents=lambda pdf=None: contents, store=SimpleNamespace(list=list))
    return ContentLookup(wiki, SimpleNamespace())  # type: ignore[arg-type]


def page(title: str, text: str, *parts: dict[str, Any]) -> dict[str, Any]:
    return {"id": title, "title": title, "summary": text, "pages": [1], "entries": list(parts)}


def test_examples_are_asked_in_turn_and_only_those_that_find_something() -> None:
    contents = [
        {
            "pdf_id": "p",
            "pdf_name": "weather.pdf",
            "entries": [
                page("Rain", "Rain falls."),
                # Only words the lookup leaves out: nothing would be found, so it isn't shown.
                page("What It Is", "Is what it is."),
                page("Snow", "Snow is frozen."),
                page("Hail", "Hail is ice."),
                page("Fog", "Fog is low cloud."),
            ],
        }
    ]
    assert lookup_over(contents).examples(limit=3) == [
        "What can you tell me about Rain?",
        "Can you explain Snow?",
        "Tell me about Hail.",
    ]
    assert lookup_over(contents).examples() == [
        "What can you tell me about Rain?",
        "Can you explain Snow?",
        "Tell me about Hail.",
        "What can you tell me about Fog?",
    ]


def test_up_to_EXAMPLES_examples_are_given_for_other_topics_to_cycle_through() -> None:
    """R182: the chat shows three at a time, so it is given more for "other topics..."."""
    contents = [
        {
            "pdf_id": "p",
            "pdf_name": "many.pdf",
            "entries": [page(f"Topic{n}", f"Topic{n} text.") for n in range(EXAMPLES + 5)],
        }
    ]
    assert len(lookup_over(contents).examples()) == EXAMPLES


def hints(client: Any) -> dict[str, Any]:
    response = client.get("/api/chat/hints")
    assert response.status_code == 200
    return dict(response.json())


def test_before_any_pdf_there_are_no_hints(tmp_path: Path) -> None:
    client = app_with_content(tmp_path, Llm(), general_prompts=False, add_pdf=False)
    assert hints(client) == {"line": None, "examples": []}


@pytest.mark.parametrize(
    ("general_prompts", "line"),
    [
        (False, "Questions must be about these topics:"),
        (True, "You can ask me about:"),
    ],
)
def test_the_hint_says_questions_must_be_about_the_topics_when_general_prompts_are_off(
    tmp_path: Path, general_prompts: bool, line: str
) -> None:
    client = app_with_content(tmp_path, Llm(), general_prompts=general_prompts, add_pdf=True)
    examples = ["What can you tell me about Moons of Mars?"]
    assert hints(client) == {"line": line, "examples": examples}


def test_a_clicked_example_question_is_answered_from_the_content(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Each example is sent as typed, so it must be answered, never declined (Larry on #85: "If
    I ask about a topic that I am told to ask about, I should get an answer")."""
    llm = Llm()
    client = riemann_app(tmp_path, llm)
    with caplog.at_level(logging.INFO, logger="imageskin.app"):
        shown = hints(client)
    assert shown == {
        "line": "Questions must be about these topics:",
        "examples": [
            "What can you tell me about Prime Number Basics?",
            "Can you explain Zeta Function Integral?",
        ],
    }
    logged = next(r for r in caplog.records if r.message == "Topic hints")
    assert (logged.topics, logged.examples) == (2, 2)  # type: ignore[attr-defined]
    assert logged.duration_ms >= 0  # type: ignore[attr-defined]
    for question, passage in zip(
        shown["examples"], ["Primes are counted.", "The zeta function as an integral."], strict=True
    ):
        assert ask(client, question) == "Two moons."
        assert passage in llm.sent[-1][-1]["content"]


def test_the_hints_follow_the_pdfs(tmp_path: Path) -> None:
    client = app_with_topics(tmp_path, Llm(), ["Rain", "Snow"], "Rain and snow fall.", pdfs=2)
    shown = hints(client)
    assert shown["line"] == "Questions must be about these topics:"
    assert len(shown["examples"]) == 4  # Rain, Snow, Rain 2 and Snow 2: all for "other topics..."
    for pdf in client.get("/api/content").json():
        client.delete(f"/api/content/{pdf['id']}")
    assert hints(client) == {"line": None, "examples": []}


def test_while_a_pdf_is_still_read_the_hint_says_so_far() -> None:
    """Review on PR #86: the topics so far are never given as all that can be asked about."""
    assert hint_line([], content_only=True, complete=False) == STILL_READING
    assert hint_line(["Rain"], content_only=True, complete=False) == (
        f"So far I can talk about Rain. {STILL_READING_REST}"
    )


def test_with_one_pdf_ready_and_one_pending_the_hints_are_only_so_far(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    hold = threading.Event()
    client = app_with_topics(tmp_path, Llm(), ["Rain"], "Rain falls.", pdfs=2, hold=hold)
    try:
        with caplog.at_level(logging.INFO, logger="imageskin.app"):
            shown = hints(client)
        assert shown["line"] == f"{STILL_READING_REST} So far you can ask me about:"
        assert "must be about" not in shown["line"]
        assert shown["examples"] == ["What can you tell me about Rain?"]  # still answerable
        logged = next(r for r in caplog.records if r.message == "Topic hints")
        assert logged.complete is False  # type: ignore[attr-defined]
    finally:
        hold.set()
    client.app.state.wiki.wait()
    assert hints(client)["line"] == "Questions must be about these topics:"
