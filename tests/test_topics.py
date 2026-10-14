import io
import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_question_scope import PDF, Llm, app_with_content

from imageskin.app import create_app
from imageskin.chat import NO_TOPICS_YET, Conversation, Message, Turn
from imageskin.lookup import named_topic
from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.review import Review
from imageskin.topics import (
    NO_CONTENT,
    ONLY_THESE,
    SPOKEN_TOPICS,
    asks_for_topics,
    decline_reply,
    main_entries,
    spoken_list,
    topics_reply,
)
from imageskin.uploads import PhotoResult
from imageskin.wiki import Progress as WikiProgress
from imageskin.wiki import Wiki, WikiPage


@pytest.mark.parametrize(
    "prompt",
    [
        "What topics can you talk about?",
        "what can you talk about",
        "What do you know about?",
        "What do you know?",
        "So, what can I ask you about?",
        "What can I ask?",
        "Which subjects do you cover?",
        "What can you tell me about?",
        "What can you help me with today?",
        "What are your topics?",
        "What topics are there?",
        "What topics do you have?",
        "What are you able to talk about?",
        "Topics?",
        "List your topics please",
        "OK what things can you teach me about?",
        "What topics could you discuss?",
        "WHAT CAN YOU TALK ABOUT?!",
    ],
)
def test_questions_about_what_it_can_talk_about_are_recognized(prompt: str) -> None:
    assert asks_for_topics(prompt)


@pytest.mark.parametrize(
    "prompt",
    [
        "What do you know about volcanoes?",
        "What can you tell me about the zeta function?",
        "Which topics in chapter 2 are hardest?",
        "Talk about rain.",
        "What is a topic sentence?",
        "Can you talk about prime numbers?",
        "",
    ],
)
def test_other_questions_are_not_taken_for_it(prompt: str) -> None:
    assert not asks_for_topics(prompt)


def entry(title: str, *parts: str) -> dict[str, Any]:
    return {"title": title, "entries": [{"title": p, "entries": []} for p in parts]}


def test_the_topics_are_each_pdfs_main_entries_once_each() -> None:
    contents = [
        {
            "pdf_name": "a.pdf",
            "entries": [entry("Prime Numbers", "Sieves"), entry("Zeta  Function")],
        },
        {"pdf_name": "b.pdf", "entries": [entry("prime numbers"), entry("Rain"), entry(" ")]},
    ]
    assert main_entries(contents) == ["Prime Numbers", "Zeta Function", "Rain"]


def test_lists_are_said_with_and_or_or() -> None:
    assert spoken_list([]) == ""
    assert spoken_list(["A"]) == "A"
    assert spoken_list(["A", "B"]) == "A and B"
    assert spoken_list(["A", "B", "C"], "or") == "A, B or C"


def first(items: Any) -> str:
    return str(items[0])


def test_the_reply_names_the_topics_and_suggests_one() -> None:
    assert topics_reply(["Rain", "Snow"], False, first) == [
        "I can talk about Rain and Snow.",
        "You could start by asking me about Rain.",
    ]


def test_when_general_prompts_are_off_it_says_only_these_are_answered() -> None:
    assert topics_reply(["Rain"], True, first) == [
        "I can talk about Rain.",
        ONLY_THESE,
        "Ask me anything about it.",
    ]


def test_a_long_list_is_cut_short_and_points_to_the_wiki() -> None:
    topics = [f"Topic {n}" for n in range(1, SPOKEN_TOPICS + 3)]
    said = topics_reply(topics, False, first)[0]
    assert said.startswith("I can talk about Topic 1, Topic 2,")
    assert said.endswith(f"Topic {SPOKEN_TOPICS} and 2 more on the Wiki page.")


def test_before_any_pdf_it_can_talk_about_anything() -> None:
    assert topics_reply([], False) == [NO_CONTENT]


def test_the_decline_names_a_few_topics() -> None:
    def three(items: Any, k: int) -> list[str]:
        return list(items[:k])

    assert decline_reply(["Rain", "Snow"])[1] == "You could ask me about Rain or Snow."
    assert decline_reply(["A", "B", "C", "D"], three)[1] == "You could ask me about A, B or C."


class Stream:
    def __call__(self, messages: list[Message]) -> Any:
        raise AssertionError("the LLM isn't asked")


def test_the_topics_are_answered_without_the_llm_and_kept_for_later(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = Llm()
    said: list[str | None] = []
    conversation = Conversation(
        llm,
        lambda: 4096,
        stream=Stream(),
        find=lambda prompt: [],
        content_only=lambda: True,
        topics=lambda: ["Rain"],
    )
    with caplog.at_level(logging.INFO):
        reply, place = conversation.send("What can you talk about?", said.append)
    assert said == [None, "I can talk about Rain.", ONLY_THESE, "Ask me anything about it."]
    assert (reply, place) == (Turn("assistant", " ".join(s for s in said if s)), 1)
    assert "Topics asked for" in caplog.text
    # Not declined though nothing matches it, and sent with the next prompt.
    conversation = Conversation(
        llm, lambda: 4096, find=lambda p: ["Rain falls."], topics=lambda: ["Rain"]
    )
    conversation.send("What topics can you talk about?")
    conversation.send("Tell me about the first one.")
    assert [m["content"] for m in llm.sent[0][1:3]] == [
        "What topics can you talk about?",
        "I can talk about Rain. Ask me anything about it.",
    ]


def test_while_the_pdfs_are_read_it_says_to_ask_again() -> None:
    conversation = Conversation(Llm(), lambda: 4096, content_only=lambda: True)
    assert conversation.send("What can you talk about?")[0].content == NO_TOPICS_YET


def test_topics_that_cant_be_read_are_left_out(caplog: pytest.LogCaptureFixture) -> None:
    def broken() -> list[str]:
        raise OSError("disk gone")

    conversation = Conversation(
        Llm(), lambda: 4096, find=lambda p: [], content_only=lambda: True, topics=broken
    )
    assert conversation.send("Tell me a joke.")[0].content.endswith("something in it.")
    assert "Could not read the content's topics" in caplog.text


@pytest.mark.parametrize("general_prompts", [False, True])
def test_the_app_answers_with_the_wikis_topics(tmp_path: Path, general_prompts: bool) -> None:
    llm = Llm()
    client = app_with_content(tmp_path, llm, general_prompts, add_pdf=True)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        reply = client.post("/api/chat", json={"prompt": "What topics can you talk about?"})
    assert reply.status_code == 200
    assert reply.json()["content"].startswith("I can talk about Moons of Mars.")
    assert (ONLY_THESE in reply.json()["content"]) is not general_prompts
    assert llm.sent == []


def riemann_app(tmp_path: Path, llm: Llm) -> Any:
    """A Riemann-like PDF whose words don't include "tell", as in Larry's test (2026-10-14)."""

    def paper(path: Path, progress: Progress) -> Reading:
        pieces = [
            Piece(1, "paragraph", "The number of primes below a given size is counted."),
            Piece(2, "paragraph", "The zeta function is given by an integral over x."),
        ]
        return Reading("text", 2, pieces, [])

    def topics(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, w: Any) -> Wiki:
        return Wiki(
            2,
            [
                WikiPage(f"{pdf_id}-primes", "Prime Number Basics", "Primes are counted.", [1]),
                WikiPage(
                    f"{pdf_id}-zeta",
                    "Zeta Function Integral",
                    "The zeta function as an integral.",
                    [2],
                ),
            ],
        )

    app = create_app(
        tmp_path,
        check_photo=lambda p: PhotoResult([], 80),
        prepare_voice=lambda: None,
        prepare_face=lambda photo, progress: None,
        render_clip=lambda photo, text, output: None,
        ask_llm=llm,
        read_pdf=paper,
        build_wiki=topics,
    )
    client = TestClient(app)
    client.post("/api/consent", json={"agreed": True})
    client.post("/api/content", files={"file": ("riemann.pdf", io.BytesIO(PDF))})
    app.state.readings.wait()
    app.state.wiki.wait()
    return client


def test_a_suggested_topic_is_answered_when_asked_about(tmp_path: Path) -> None:
    """Larry's exchange (2026-10-14): the topic suggested was then declined when asked about."""
    llm = Llm()
    client = riemann_app(tmp_path, llm)
    with (
        patch("imageskin.app.load_review", return_value=Review(accepted=True)),
        patch("imageskin.topics.random.choice", lambda topics: "Zeta Function Integral"),
    ):
        told = client.post("/api/chat", json={"prompt": "What topics can you talk about?"})
        asked = client.post(
            "/api/chat", json={"prompt": "What can you tell me about the zeta function integral?"}
        )
    assert told.json()["content"].endswith("asking me about Zeta Function Integral.")
    assert asked.json()["content"] == "Two moons."  # the LLM's answer, not the decline
    assert "The zeta function as an integral." in llm.sent[-1][-1]["content"]


@pytest.mark.parametrize(
    "prompt",
    [
        "Tell me about Prime Number Basics.",
        "I'd like to learn about the zeta function integral",
        "Please explain Zeta Function Integral",
        # A word the content doesn't have outweighs the rest; the topic it names is looked up.
        "What's so fascinating about the Zeta Function Integral?",
    ],
)
def test_asking_about_a_named_topic_is_never_declined(tmp_path: Path, prompt: str) -> None:
    llm = Llm()
    client = riemann_app(tmp_path, llm)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        reply = client.post("/api/chat", json={"prompt": prompt})
    assert reply.json()["content"] == "Two moons."
    assert "Reference text" in llm.sent[-1][-1]["content"]


def test_the_topic_named_is_the_longest_one_whose_words_are_all_there() -> None:
    contents = [{"entries": [entry("Zeta Function"), entry("Zeta Function Integral"), entry("x")]}]
    asked = "about the integral of the zeta function"
    assert named_topic(asked, contents) == "Zeta Function Integral"
    assert named_topic("about the zeta function", contents) == "Zeta Function"
    assert named_topic("about primes", contents) is None
