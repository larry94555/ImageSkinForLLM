import io
import logging
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_question_scope import PDF, Llm, app_with_content

from imageskin.app import create_app
from imageskin.chat import EARLIER, SUMMARY_PROMPT, Conversation, Message, Turn
from imageskin.lookup import named_topic
from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.review import Review
from imageskin.topics import (
    ASK_ABOUT_IT,
    ASK_AGAIN,
    ASK_AGAIN_FOR_ALL,
    NO_CONTENT,
    NO_TOPICS,
    ONLY_THESE,
    SPOKEN_TOPICS,
    STILL_READING,
    STILL_READING_REST,
    asks_for_topics,
    decline_reply,
    main_entries,
    referred_topic,
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
    assert topics_reply(["Rain", "Snow"], False, choose=first) == [
        "I can talk about Rain and Snow.",
        "You could start by asking me about Rain.",
    ]


def test_when_general_prompts_are_off_it_says_only_these_are_answered() -> None:
    assert topics_reply(["Rain"], True, choose=first) == [
        "I can talk about Rain.",
        ONLY_THESE,
        "Ask me anything about it.",
    ]


def test_a_long_list_is_cut_short_and_points_to_the_wiki() -> None:
    topics = [f"Topic {n}" for n in range(1, SPOKEN_TOPICS + 3)]
    said = topics_reply(topics, False, choose=first)[0]
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


def test_a_long_list_of_topics_is_spoken_a_clause_at_a_time(
    caplog: pytest.LogCaptureFixture,
) -> None:
    topics = ["Prime Number Definition", "The Sieve of Eratosthenes", "The Zeta Function"]
    said: list[str | None] = []
    conversation = Conversation(
        Llm(), lambda: 4096, stream=Stream(), find=lambda prompt: [], topics=lambda: topics
    )
    with caplog.at_level(logging.INFO):
        reply, _ = conversation.send("What can you talk about?", said.append)
    # The first clip is short, so the first word is heard sooner (R100); the reply is kept whole.
    assert said[:3] == [
        None,
        "I can talk about Prime Number Definition,",
        "The Sieve of Eratosthenes and The Zeta Function.",
    ]
    assert reply.content == (
        "I can talk about Prime Number Definition, The Sieve of Eratosthenes and The Zeta"
        f" Function. {said[3]}"
    )
    assert "Made reply cut into clips" in caplog.text


def test_while_the_pdfs_are_read_it_says_to_ask_again() -> None:
    conversation = Conversation(
        Llm(), lambda: 4096, content_only=lambda: True, topics_complete=lambda: False
    )
    assert (
        conversation.send("What can you talk about?")[0].content == f"{STILL_READING} {ASK_AGAIN}"
    )


def test_the_topics_so_far_are_not_given_as_all_of_them() -> None:
    assert topics_reply(["Rain"], True, complete=False) == [
        "So far I can talk about Rain.",
        STILL_READING_REST,
        ASK_AGAIN_FOR_ALL,
    ]


def test_when_no_wiki_could_be_built_it_says_so() -> None:
    assert topics_reply([], True) == [NO_TOPICS, ASK_ABOUT_IT]


def test_if_it_cant_tell_whether_all_is_read_it_says_to_ask_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken() -> bool:
        raise OSError("disk gone")

    conversation = Conversation(
        Llm(), lambda: 4096, topics=lambda: ["Rain"], topics_complete=broken
    )
    assert conversation.send("Topics?")[0].content.startswith("So far I can talk about Rain.")
    assert "Could not tell whether the content is all read" in caplog.text


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


def riemann_app(tmp_path: Path, llm: Llm, lessons_ahead: bool | None = None, **more: Any) -> Any:
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
        lessons_ahead=lessons_ahead,
        **more,
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
        "Why is everyone so fascinated and baffled by the Zeta Function Integral?",
    ],
)
def test_asking_about_a_named_topic_is_never_declined(tmp_path: Path, prompt: str) -> None:
    llm = Llm()
    client = riemann_app(tmp_path, llm)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        reply = client.post("/api/chat", json={"prompt": prompt})
    assert reply.json()["content"] == "Two moons."
    assert "Reference text" in llm.sent[-1][-1]["content"]


def test_the_topic_named_is_the_longest_whose_words_are_there_in_order() -> None:
    contents = [{"entries": [entry("Zeta Function"), entry("Zeta Function Integral"), entry("x")]}]
    assert named_topic("about the zeta function integral", contents) == "Zeta Function Integral"
    # Its words in another order don't name it; "zeta function" together still names that one.
    assert named_topic("about the integral of the zeta function", contents) == "Zeta Function"
    assert named_topic("about the zeta function", contents) == "Zeta Function"
    assert named_topic("about primes", contents) is None


def app_with_topics(
    tmp_path: Path,
    llm: Llm,
    titles: list[str],
    text: str,
    pdfs: int = 1,
    hold: threading.Event | None = None,
    unreadable: bool = False,
    hold_first: bool = False,
) -> Any:
    """An app with `pdfs` PDFs, each a wiki of `titles` (made unique per PDF after the first)
    over one paragraph of `text`. With `hold`, every wiki after the first waits for it; with
    `unreadable`, every PDF after the first can't be read. With `hold_first` too, the first
    waits as well."""
    built: list[str] = []
    read_so_far: list[Path] = []

    def read(path: Path, progress: Progress) -> Reading:
        read_so_far.append(path)
        if unreadable and len(read_so_far) > 1:
            raise ValueError("This PDF can't be read.")
        return Reading("text", 1, [Piece(1, "paragraph", text)], [])

    def topics(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, w: Any) -> Wiki:
        built.append(pdf_id)
        n = len(built)
        if hold is not None and (n > 1 or hold_first):
            hold.wait(10)
        suffix = "" if n == 1 else f" {n}"
        pages = [
            WikiPage(f"{pdf_id}-{i}", f"{t}{suffix}", f"About {t}.", [1])
            for i, t in enumerate(titles)
        ]
        return Wiki(1, pages)

    app = create_app(
        tmp_path,
        check_photo=lambda p: PhotoResult([], 80),
        prepare_voice=lambda: None,
        prepare_face=lambda photo, progress: None,
        render_clip=lambda photo, text, output: None,
        ask_llm=llm,
        read_pdf=read,
        build_wiki=topics,
    )
    client = TestClient(app)
    client.post("/api/consent", json={"agreed": True})
    for n in range(pdfs):
        client.post("/api/content", files={"file": (f"{n}.pdf", io.BytesIO(PDF))})
        app.state.readings.wait()
        if hold is None or (n == 0 and not hold_first):
            app.state.wiki.wait()
    return client


def ask(client: Any, prompt: str) -> str:
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        return str(client.post("/api/chat", json={"prompt": prompt}).json()["content"])


def test_a_topic_named_with_an_asking_word_can_be_asked_about(tmp_path: Path) -> None:
    """A topic called "Learning" is suggested, so it must be answerable (review on PR #85)."""
    llm = Llm()
    client = app_with_topics(tmp_path, llm, ["Learning"], "Learning takes practice.")
    assert ask(client, "What can you talk about?").startswith("I can talk about Learning.")
    assert ask(client, "Tell me about Learning") == "Two moons."
    assert "About Learning." in llm.sent[-1][-1]["content"]


def test_a_topic_s_words_scattered_in_an_unrelated_question_dont_name_it(tmp_path: Path) -> None:
    """Review on PR #85: this must still be declined, not answered from the Water Cycle."""
    llm = Llm()
    client = app_with_topics(tmp_path, llm, ["Water Cycle"], "Rain falls and flows to the sea.")
    reply = ask(client, "Is water safe to drink during my cycle?")
    assert reply.startswith("Sorry, I can only answer questions about the material")
    assert llm.sent == []
    contents = [{"entries": [entry("Water Cycle")]}]
    assert named_topic("Is water safe to drink during my cycle?", contents) is None
    assert named_topic("Why does the water cycle matter?", contents) == "Water Cycle"


def test_while_a_second_pdf_is_built_the_first_s_topics_are_not_all_of_them(
    tmp_path: Path,
) -> None:
    """Review on PR #85: one PDF ready and one still being built."""
    hold = threading.Event()
    client = app_with_topics(tmp_path, Llm(), ["Rain"], "Rain falls.", pdfs=2, hold=hold)
    try:
        reply = ask(client, "What topics can you talk about?")
        assert reply == f"So far I can talk about Rain. {STILL_READING_REST} {ASK_AGAIN_FOR_ALL}"
        assert ONLY_THESE not in reply
    finally:
        hold.set()
    client.app.state.wiki.wait()
    assert ask(client, "What topics can you talk about?").startswith(
        "I can talk about Rain and Rain 2."
    )


def test_a_pdf_that_cant_be_read_doesnt_keep_the_topics_waiting(tmp_path: Path) -> None:
    client = app_with_topics(tmp_path, Llm(), ["Rain"], "Rain falls.", pdfs=2, unreadable=True)
    assert ask(client, "What topics can you talk about?").startswith("I can talk about Rain.")


def test_the_topics_listed_can_be_referred_to_through_the_app(tmp_path: Path) -> None:
    """Review on PR #85: with general prompts off, "the second one" after the list is answered
    from that topic, with the list in the history, rather than declined."""
    llm = Llm()
    client = app_with_topics(tmp_path, llm, ["Rain", "Snow", "Hail"], "Weather falls.")
    with patch("imageskin.chat.random.choice", lambda topics: "Hail"):
        listed = ask(client, "What topics can you talk about?")
    assert listed.startswith("I can talk about Rain, Snow and Hail.")
    assert ask(client, "Tell me about the second one") == "Two moons."
    sent = llm.sent[-1]
    assert "About Snow." in sent[-1]["content"]
    assert sent[-1]["content"].endswith("Tell me about the second one")
    assert {"role": "assistant", "content": listed} in sent
    assert ask(client, "OK, and that one?") == "Two moons."
    assert "About Hail." in llm.sent[-1][-1]["content"]
    # Not a reference: still declined.
    assert ask(client, "Who won the first world cup?").startswith("Sorry")


@pytest.mark.parametrize(
    ("prompt", "topic"),
    [
        ("Tell me about the second one", "Snow"),
        ("What about the last one?", "Hail"),
        ("And the third", "Hail"),
        ("topic 2 please", "Snow"),
        ("Tell me more about that one", "Rain"),
        ("What did the one you suggested mean?", "Rain"),
        ("What was the first prime number?", None),
        ("Tell me about the fourth one", None),
        ("Tell me a joke", None),
    ],
)
def test_a_prompt_can_refer_to_a_listed_topic(prompt: str, topic: str | None) -> None:
    assert referred_topic(prompt, ["Rain", "Snow", "Hail"], "Rain") == topic


def test_a_topics_reply_that_passes_the_history_budget_starts_a_summary() -> None:
    """Review on PR #85: the reply made here is kept like the LLM's, summary and all."""
    sent: list[list[Message]] = []

    def llm(messages: list[Message]) -> str:
        sent.append(messages)
        return "OK."

    conversation = Conversation(llm, lambda: 4096, topics=lambda: ["Rain"])  # budget 2048
    for i in range(3):
        conversation.send(f"Prompt {i} " + "x" * 640)
        conversation.wait()
    assert not any(m[-1]["content"] == SUMMARY_PROMPT for m in sent)
    conversation.send("What topics can you talk about?")
    conversation.wait()
    assert any(m[-1]["content"] == SUMMARY_PROMPT for m in sent)
    conversation.send("Tell me about the first one")
    assert sent[-1][0]["content"].endswith(f"{EARLIER}\nOK.")
