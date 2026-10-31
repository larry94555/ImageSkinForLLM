"""Guidelines for the topics (roadmap R195)."""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from test_question_scope import Llm, app_with_content

from imageskin.chat import TOPIC_GUIDELINES, Conversation, Message, detail_level, topic_guided
from imageskin.customization import (
    FEATURES,
    SHIPPED,
    TOPICS,
    Read,
    features,
    guidelines_of,
    is_edited,
    with_guidelines,
)
from imageskin.lookup import subject_named
from imageskin.review import Review

EDITED = "When talking about a topic, start with why it matters."
GUIDED = f"{TOPIC_GUIDELINES} {EDITED}"
SUBJECTS = ["Water Cycle", "Evaporation", "Moons of Mars"]


def test_they_ship_describing_todays_replies_and_are_listed_after_answering_questions() -> None:
    assert FEATURES["topics"].shipped == TOPICS == guidelines_of(SHIPPED, "topics")
    assert [f["key"] for f in features(SHIPPED)][:2] == ["questions", "topics"]
    assert not is_edited(SHIPPED, "topics")
    assert is_edited(with_guidelines(SHIPPED, "topics", EDITED), "topics")


@pytest.mark.parametrize(
    ("prompt", "subject"),
    [
        ("Tell me about the Water Cycle.", "Water Cycle"),
        ("What can you tell me about the water cycle?", "Water Cycle"),
        ("Can you explain evaporation?", "Evaporation"),  # an example question's part
        ("Moons of Mars", "Moons of Mars"),
        ("Why does the water cycle matter?", None),  # something more about it
        ("Tell me about the history of the water cycle.", None),
        ("Tell me about photosynthesis.", None),  # not one of the topics
        ("Tell me about it.", None),
    ],
)
def test_a_prompt_asks_about_a_topic_as_a_whole(prompt: str, subject: str | None) -> None:
    assert subject_named(prompt, SUBJECTS) == subject


def test_as_shipped_nothing_is_added_so_the_prompt_is_as_before() -> None:
    with detail_level(3, SHIPPED):
        assert topic_guided("Tell me about the Water Cycle.", "Water Cycle") == (
            "Tell me about the Water Cycle."
        )
    edited = with_guidelines(SHIPPED, "topics", EDITED)
    with detail_level(3, edited):
        assert topic_guided("Why?", None) == "Why?"  # not about a topic
        assert topic_guided("Tell me about it.", "Water Cycle") == f"Tell me about it.\n{GUIDED}"
    assert topic_guided("Tell me about it.", "Water Cycle") == "Tell me about it."  # no identity


def conversation(llm: Llm, now: list[Read], **more: object) -> Conversation:
    return Conversation(
        llm,
        lambda: 4096,
        topics=lambda: SUBJECTS[::2],
        customization=lambda: now[0],
        subject_of=lambda prompt: subject_named(prompt, SUBJECTS),
        **more,  # type: ignore[arg-type]
    )


def test_replies_about_a_topic_are_asked_with_them_and_other_answers_are_not(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = Llm()
    now = [Read(SHIPPED, True, 0.1)]
    chat = conversation(llm, now)
    with caplog.at_level(logging.INFO, logger="imageskin.chat"):
        chat.send("Tell me about the Water Cycle.")
        now[0] = Read(with_guidelines(SHIPPED, "topics", EDITED), False, 0.1)
        chat.send("Tell me about the Water Cycle.")
        chat.send("Why does the water cycle matter?")
        chat.send("What can you talk about?")  # answered by the code, no LLM call
        chat.send("Tell me about the first one.")
        chat.send("Can you give me an example of evaporation?")
    shipped, edited, question, first, example = (sent[-1]["content"] for sent in llm.sent)
    assert shipped == "Tell me about the Water Cycle."
    assert edited.startswith("Tell me about the Water Cycle.\n") and GUIDED in edited
    assert GUIDED not in question and GUIDED not in example
    assert GUIDED in first  # the first topic named, "Water Cycle"
    # Asked with the user message, not the system message, so the instructions stay cached.
    assert all(sent[0] == llm.sent[0][0] for sent in llm.sent)
    used = [
        (r.feature, r.edited)  # type: ignore[attr-defined]
        for r in caplog.records
        if r.message == "Guidelines used"
    ]
    assert used == [
        ("questions", False),
        ("topics", False),
        ("questions", False),
        ("topics", True),
        ("questions", False),
        ("questions", False),
        ("topics", True),
        ("questions", False),
    ]
    # Only the prompt as typed is kept in the conversation.
    assert GUIDED not in str(chat.turns())


def test_a_topic_read_ahead_is_read_as_it_will_be_sent() -> None:
    read: list[list[Message]] = []

    def ahead(messages: list[Message]) -> str:
        read.append(messages)
        return "x"

    now = [Read(with_guidelines(SHIPPED, "topics", EDITED), False, 0.1)]
    chat = conversation(Llm(), now, read_ahead=ahead)
    assert chat.read_ahead("Tell me about the Water Cycle") == "read"
    assert chat.read_ahead("Why does the water cycle matter") == "read"
    assert GUIDED in read[0][-1]["content"] and GUIDED not in read[1][-1]["content"]


def test_a_broken_topic_check_is_answered_as_any_question(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(prompt: str) -> str | None:
        raise OSError("wiki unreadable")

    llm = Llm()
    now = [Read(with_guidelines(SHIPPED, "topics", EDITED), False, 0.1)]
    chat = Conversation(llm, lambda: 4096, customization=lambda: now[0], subject_of=broken)
    with caplog.at_level(logging.ERROR, logger="imageskin.chat"):
        chat.send("Tell me about the Water Cycle.")
    assert GUIDED not in llm.sent[0][-1]["content"]
    assert "Could not tell whether the prompt asks about a topic" in caplog.text


def test_the_host_edits_them_and_a_picked_example_question_is_asked_with_them(
    tmp_path: Path,
) -> None:
    llm = Llm()
    client = app_with_content(tmp_path, llm, general_prompts=False, add_pdf=True)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        examples = client.get("/api/chat/hints").json()["examples"]
        saved = client.put("/api/customization/guidelines/topics", json={"text": EDITED})
        client.post("/api/chat", json={"prompt": examples[0]})
        client.post("/api/chat", json={"prompt": "Tell me about the moons of Mars."})
        client.post("/api/chat", json={"prompt": "Which moons circle Mars?"})
        topics = client.post("/api/chat", json={"prompt": "What can you talk about?"}).json()
        client.put("/api/customization/guidelines/topics", json={"text": None})
        client.post("/api/chat", json={"prompt": examples[0]})
    assert examples and saved.json()["features"][1]["edited"] is True
    picked, told, question, back = (sent[-1]["content"] for sent in llm.sent)
    assert GUIDED in picked and GUIDED in told
    assert GUIDED not in question and GUIDED not in back
    assert "Moons of Mars" in topics["content"]  # still the code's reply, without the LLM


def test_guidelines_that_dont_fit_are_left_out_rather_than_overflowing_the_window(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Codex's review on PR #248: the room is checked for the question as typed, so the
    guidelines added after it must fit that room too, near their longest."""
    longest = "Start with why it matters. " * 70  # about 1,900 characters
    now = [Read(with_guidelines(SHIPPED, "topics", longest), False, 0.1)]
    prompt = "Tell me about the Water Cycle" + ", and then some more of it" * 20 + "."
    read: list[list[Message]] = []

    def ahead(messages: list[Message]) -> str:
        read.append(messages)
        return "x"

    def chat_in(window: int, llm: Llm) -> Conversation:
        return Conversation(
            llm,
            lambda: window,
            customization=lambda: now[0],
            subject_of=lambda p: "Water Cycle",
            read_ahead=ahead,
        )

    # The smallest window the question as typed fits in, without the guidelines.
    window = next(w for w in range(1024, 8192, 8) if fits(chat_in(w, Llm()), prompt))
    llm = Llm()
    chat = chat_in(window, llm)
    caplog.clear()  # of the windows tried
    with caplog.at_level(logging.WARNING, logger="imageskin.chat"):
        chat.send(prompt)
    assert chat_in(window, Llm()).read_ahead(prompt) == "read"  # before anything was said
    assert llm.sent[0][-1]["content"] == prompt and read[-1][-1]["content"] == prompt
    warned = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert warned == ["Topics guidelines left out"]
    # With room for them, they are sent.
    roomy = Llm()
    chat_in(4 * window, roomy).send(prompt)
    assert roomy.sent[0][-1]["content"].endswith(longest.strip())


def fits(chat: Conversation, prompt: str) -> bool:
    try:
        chat.send(prompt)
    except ValueError:
        return False
    return True
