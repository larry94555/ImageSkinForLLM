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
    ],
)
def test_a_broken_file_starts_a_new_conversation(
    tmp_path: Path, content: str, caplog: pytest.LogCaptureFixture
) -> None:
    saved = tmp_path / "conversation.json"
    saved.write_text(content, encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        assert load_saved(saved) == ([], [], None)
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
