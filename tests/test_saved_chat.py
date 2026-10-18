"""The conversation is saved in the data folder and restored after a restart (roadmap R30)."""

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from test_chat import FakeLlm2, chat_app

from imageskin.chat import SUMMARY_PROMPT, Conversation, Message, Turn, load_saved, system_message
from imageskin.review import Review


def test_the_conversation_is_saved_and_restored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    saved = tmp_path / "conversation.json"
    with caplog.at_level(logging.INFO):
        first = Conversation(FakeLlm2(), lambda: 4096, saved=saved)
        first.send("My name is Larry.")
    assert "No saved conversation; starting a new one" in caplog.text
    assert "Conversation saved" in caplog.text
    llm = FakeLlm2()
    with caplog.at_level(logging.INFO):
        again = Conversation(llm, lambda: 4096, saved=saved)
    assert again.turns() == [Turn("user", "My name is Larry."), Turn("assistant", "Reply 1")]
    assert "Conversation restored" in caplog.text
    # The restored turns are sent with the next prompt, so the LLM remembers them.
    again.send("What is my name?")
    assert llm.sent[-1] == [
        system_message(None),
        {"role": "user", "content": "My name is Larry."},
        {"role": "assistant", "content": "Reply 1"},
        {"role": "user", "content": "What is my name?"},
    ]


def test_the_summary_is_saved_and_sent_after_a_restart(tmp_path: Path) -> None:
    saved = tmp_path / "conversation.json"
    first = Conversation(FakeLlm2(), lambda: 4096, saved=saved)
    for i in range(5):
        first.send(f"Prompt {i} " + "x" * 590)  # passes the budget: summarized
    first.wait()
    summary = json.loads(saved.read_text(encoding="utf-8"))["summary"]
    assert summary is not None and summary.startswith("SUMMARY")
    llm = FakeLlm2()
    again = Conversation(llm, lambda: 4096, saved=saved)
    assert len(again.turns()) == 10  # the chat still shows everything
    again.send("Hello")
    assert llm.sent[-1][0] == system_message(summary)
    assert all(m[0]["content"] != SUMMARY_PROMPT for m in llm.sent)


def test_clearing_saves_an_empty_conversation(tmp_path: Path) -> None:
    saved = tmp_path / "conversation.json"
    first = Conversation(FakeLlm2(), lambda: 4096, saved=saved)
    first.send("Hi")
    first.clear()
    assert Conversation(FakeLlm2(), lambda: 4096, saved=saved).turns() == []


def test_without_a_file_nothing_is_saved(tmp_path: Path) -> None:
    Conversation(FakeLlm2(), lambda: 4096).send("Hi")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        '{"transcript": []}',  # no turns
        '{"transcript": "x", "turns": []}',
        '{"transcript": [{"role": "system", "content": "x"}], "turns": []}',
        '{"transcript": [{"role": "user", "content": 1}], "turns": []}',
        '{"transcript": [], "turns": [], "summary": 3}',
        '{"transcript": [], "turns": [], "told": []}',
        '{"transcript": [], "turns": [], "told": {"named": [1], "suggested": null}}',
        '{"transcript": [], "turns": [], "told": {"named": [], "suggested": 2}}',
    ],
)
def test_a_broken_file_starts_a_new_conversation(
    tmp_path: Path, content: str, caplog: pytest.LogCaptureFixture
) -> None:
    saved = tmp_path / "conversation.json"
    saved.write_text(content, encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        assert load_saved(saved) == ([], [], None, ([], None))
    assert "Could not read the saved conversation; starting a new one" in caplog.text


def test_a_save_that_fails_is_logged_and_the_chat_goes_on(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    saved = tmp_path / "conversation.json"
    conversation = Conversation(FakeLlm2(), lambda: 4096, saved=saved)
    with (
        patch("imageskin.chat.save", side_effect=OSError("disk full")),
        caplog.at_level(logging.ERROR),
    ):
        assert conversation.send("Hi") == (Turn("assistant", "Reply 1"), 1)
    assert "Could not save the conversation" in caplog.text
    assert len(conversation.turns()) == 2


def test_the_saved_file_keeps_any_language(tmp_path: Path) -> None:
    saved = tmp_path / "conversation.json"

    def reply(messages: list[Message]) -> str:
        return "你好 🐶"

    Conversation(reply, lambda: 4096, saved=saved).send("Grüß dich")
    restored = Conversation(reply, lambda: 4096, saved=saved).turns()
    assert restored == [Turn("user", "Grüß dich"), Turn("assistant", "你好 🐶")]


def test_the_app_keeps_the_conversation_after_a_restart(tmp_path: Path) -> None:
    client = chat_app(tmp_path, lambda messages: "Hello")
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi"})
    assert (tmp_path / "conversation.json").is_file()
    restarted = chat_app(tmp_path, lambda messages: "Hello")
    assert restarted.get("/api/chat").json() == {
        "turns": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]
    }


TOPICS = ["Rain", "Snow", "Hail"]


def topics_conversation(saved: Path, looked_up: list[str]) -> Conversation:
    """Only the content is answered, and each topic has a passage (as in test_topics)."""

    def find(prompt: str) -> list[str]:
        looked_up.append(prompt)
        return [f"About {prompt}."] if prompt in TOPICS else []

    return Conversation(
        lambda messages: "Two moons.",
        lambda: 4096,
        find=find,
        content_only=lambda: True,
        topics=lambda: TOPICS,
        saved=saved,
    )


def test_the_topics_named_still_count_after_a_restart(tmp_path: Path) -> None:
    """Review on PR #108: "the second one" and "that one" after a restart still mean the topics
    named and suggested before it, rather than being declined."""
    saved = tmp_path / "conversation.json"
    with patch("imageskin.chat.random.choice", lambda topics: "Hail"):
        topics_conversation(saved, []).send("What topics can you talk about?")
    looked_up: list[str] = []
    again = topics_conversation(saved, looked_up)
    assert again.send("Tell me about the second one")[0].content == "Two moons."
    assert again.send("OK, and that one?")[0].content == "Two moons."
    assert looked_up == ["Snow", "Hail"]
    # Clearing forgets them, after a restart too.
    again.clear()
    cleared = topics_conversation(saved, looked_up)
    assert cleared.send("Tell me about the second one")[0].content.startswith("Sorry")


def test_a_file_saved_before_topics_were_kept_still_restores(tmp_path: Path) -> None:
    saved = tmp_path / "conversation.json"
    saved.write_text(
        '{"transcript": [{"role": "user", "content": "Hi"}], "turns": [], "summary": null}',
        encoding="utf-8",
    )
    assert load_saved(saved) == ([Turn("user", "Hi")], [], None, ([], None))


def test_new_conversations_never_share_their_turns(tmp_path: Path) -> None:
    """Two conversations started with nothing saved keep their own turns."""
    first = Conversation(FakeLlm2(), lambda: 4096, saved=tmp_path / "a.json")
    first.send("Hi")
    second = Conversation(FakeLlm2(), lambda: 4096, saved=tmp_path / "b.json")
    assert second.turns() == []
