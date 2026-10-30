"""The level of detail in an answer, set with the bar on the chat screen (roadmap R180)."""

import functools
import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from test_reply_video import REPLY_ID, stop_patches, video_app  # noqa: F401 (a fixture)

from imageskin.chat import (
    CONTENT_RULES,
    DEFAULT_DETAIL,
    DETAIL_LEVELS,
    REPLY_TOKENS,
    SUMMARY_PROMPT,
    Conversation,
    Message,
    Turn,
    at_length,
    detail_level,
    estimate,
    reply_tokens,
    system_message,
    system_prompt,
    tokens,
)
from imageskin.review import Review
from imageskin.ui_settings import load_ui_settings, save_ui_settings

# The system prompt before the bar: the middle of the bar must answer as it did.
BEFORE = (
    "You are talking with someone face to face, and your replies are spoken aloud. Keep each"
    " reply short and conversational: one to three sentences in plain words, without lists,"
    " headings or code unless you are asked for them."
    " Everything you say must agree with what was said earlier in this conversation: keep"
    " track of who said what, and get every name and fact right. Reply only with the words you"
    " would say out loud, never with notes about your reply."
)


def test_the_middle_of_the_bar_asks_as_before() -> None:
    assert DEFAULT_DETAIL == 3
    assert system_prompt() == BEFORE
    assert system_message(None)["content"] == f"{BEFORE} {CONTENT_RULES}"
    assert reply_tokens() == REPLY_TOKENS == 300


def test_each_level_asks_for_its_own_length_with_room_for_it() -> None:
    prompts = [system_prompt(level) for level in DETAIL_LEVELS]
    assert len(set(prompts)) == 5
    assert "a single short sentence" in system_prompt(1)
    assert "only the main point" in system_prompt(1)
    assert "a few paragraphs" in system_prompt(5) and "examples" in system_prompt(5)
    rooms = []
    for level in DETAIL_LEVELS:
        with detail_level(level):
            rooms.append(reply_tokens())
            assert system_message(None)["content"].startswith(system_prompt(level))
    assert rooms == sorted(rooms) and rooms[-1] > 3 * rooms[0]
    assert reply_tokens() == REPLY_TOKENS  # back to the middle after the block


def test_a_level_off_the_bar_is_asked_at_the_middle() -> None:
    with detail_level(9):
        assert reply_tokens() == REPLY_TOKENS
        assert system_message(None)["content"].startswith(BEFORE)


class Recorder:
    """An LLM that keeps what it was sent and the reply's room at the time."""

    def __init__(self) -> None:
        self.sent: list[list[Message]] = []
        self.rooms: list[int] = []

    def __call__(self, messages: list[Message]) -> str:
        self.sent.append(messages)
        self.rooms.append(reply_tokens())
        return "SUMMARY" if messages[-1]["content"] == SUMMARY_PROMPT else "Reply."


def test_a_change_applies_to_the_next_answer(caplog: pytest.LogCaptureFixture) -> None:
    llm = Recorder()
    level = {"now": 1}
    conversation = Conversation(llm, lambda: 4096, detail=lambda: level["now"])
    with caplog.at_level(logging.INFO, logger="imageskin.chat"):
        conversation.send("Why is the sky blue?")
        level["now"] = 5  # moved on the bar, with no restart
        conversation.send("Why is the sky blue?")
    assert llm.sent[0][0]["content"].startswith(system_prompt(1))
    assert llm.sent[1][0]["content"].startswith(system_prompt(5))
    assert llm.rooms == [DETAIL_LEVELS[1][1], DETAIL_LEVELS[5][1]]
    sent = [r for r in caplog.records if r.message == "Chat prompt sent"]
    assert [r.detail for r in sent] == [1, 5]  # type: ignore[attr-defined]


def test_the_warm_up_and_the_summary_use_the_level_set() -> None:
    llm = Recorder()
    warmed: list[str] = []
    conversation = Conversation(
        llm,
        lambda: 4096,
        warm_up=lambda: warmed.append(system_message(None)["content"]),
        detail=lambda: 4,
    )
    conversation.warm_up()
    assert warmed[0].startswith(system_prompt(4))
    for i in range(8):  # enough for the older turns to be summarized
        conversation.send(f"Question {i} " + "x" * 300)
        conversation.wait()
    summaries = [m for m in llm.sent if m[-1]["content"] == SUMMARY_PROMPT]
    assert summaries and summaries[0][0]["content"].startswith(system_prompt(4))


def test_the_level_is_saved_like_the_other_settings(tmp_path: Path) -> None:
    assert load_ui_settings(tmp_path).detail == DEFAULT_DETAIL
    save_ui_settings(tmp_path, {"detail": 5})
    assert load_ui_settings(tmp_path).detail == 5
    for wrong in (0, 6, "5", True):
        with pytest.raises(ValueError, match="must be one of"):
            save_ui_settings(tmp_path, {"detail": wrong})


def test_the_chat_answers_at_the_level_set_on_the_bar(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    asked: list[tuple[str, int]] = []

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        asked.append((messages[0]["content"], reply_tokens()))
        yield "Light scatters."

    client = video_app(tmp_path, written, stream)
    with (
        patch("imageskin.app.load_review", return_value=Review(accepted=True)),
        caplog.at_level(logging.INFO, logger="imageskin.app"),
    ):
        client.post("/api/chat", json={"prompt": "Why blue?", "reply_id": REPLY_ID})
        changed = client.patch("/api/settings", json={"detail": 5})
        assert changed.status_code == 200 and changed.json()["detail"] == 5
        client.post("/api/chat", json={"prompt": "Why blue?", "reply_id": "a" * 32})
    # after the identity and goals (R92)
    assert system_prompt(3) in asked[0][0] and asked[0][1] == DETAIL_LEVELS[3][1]
    assert system_prompt(5) in asked[-1][0] and asked[-1][1] == DETAIL_LEVELS[5][1]
    set_ = next(r for r in caplog.records if r.message == "Level of detail set")
    assert set_.detail == 5  # type: ignore[attr-defined]


def written(photo: Path, text: str, output: Path) -> None:
    output.write_text(text)


def test_more_detail_takes_its_room_from_the_history_not_the_prompt() -> None:
    long_prompt = "x" * 450  # fits at every level, counted a token a byte
    for level in DETAIL_LEVELS:
        llm = Recorder()
        Conversation(llm, lambda: 4096, detail=functools.partial(int, level)).send(long_prompt)
        assert long_prompt in llm.sent[0][-1]["content"]


def test_the_length_is_said_with_the_question_off_the_middle_or_when_asked_again() -> None:
    """Asked again after the bar moved, a small model said its earlier answer word for word,
    copied from the conversation (Larry, 2026-10-29), so the length goes with the question."""
    before = [Turn("user", "Tell me about rain."), Turn("assistant", "Rain falls.")]
    assert at_length("Q", "Tell me about snow.", before) == "Q"  # the middle, as before the bar
    again = at_length("Q", "Tell me about rain.", before)
    assert again == 'Q\n\n(Answer this question, "Tell me about rain.", in one to three sentences.)'
    with detail_level(5):
        assert at_length("Q", "Tell me about snow.", []).endswith(
            '(Answer this question, "Tell me about snow.", in a few paragraphs, complete and'
            " in depth.)"
        )


def test_a_question_asked_again_at_another_level_is_sent_with_its_length() -> None:
    llm = Recorder()
    level = {"now": 3}
    conversation = Conversation(llm, lambda: 4096, detail=lambda: level["now"])
    conversation.send("Tell me about rain.")
    level["now"] = 5
    conversation.send("Tell me about rain.")
    assert llm.sent[0][-1]["content"] == "Tell me about rain."
    assert llm.sent[1][-1]["content"].endswith(
        '(Answer this question, "Tell me about rain.", in a few paragraphs, complete and in depth.)'
    )
    # The conversation keeps the question as asked.
    assert [t.content for t in conversation.turns()][::2] == ["Tell me about rain."] * 2


def test_the_length_said_after_the_question_fits_the_window() -> None:
    """Review on PR #221: the note went after passages that already filled the room left for
    the prompt, so with the history at its budget the prompt and reply no longer fitted."""
    with detail_level(5):
        system = tokens(system_message(None), estimate)
    window = 2 * (550 + system)
    # What is left for the prompt once the history, the system prompt and the reply have
    # theirs: about 250 tokens, less than the passages could take.
    room = window - (window // 2 - (DETAIL_LEVELS[5][1] - REPLY_TOKENS))
    room -= DETAIL_LEVELS[5][1] + system
    sent: list[list[Message]] = []

    def llm(messages: list[Message]) -> str:
        sent.append(messages)
        return "Reply."

    conversation = Conversation(
        llm, lambda: window, find=lambda prompt: ["alpha " * 200], detail=lambda: 5
    )
    conversation.send("Which?")
    asked = sent[0][-1]
    assert "alpha" in asked["content"] and asked["content"].endswith("complete and in depth.)")
    assert tokens(asked, estimate) <= room


def test_a_long_question_is_named_cut_in_the_note() -> None:
    with detail_level(5):
        note = at_length("", "why " * 60, [])
    assert note.startswith('\n\n(Answer this question, "why why') and '…", in a few' in note
    assert len(note) < 200
