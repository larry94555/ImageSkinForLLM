"""Tests for R147's check of a question asked during a summary, without a llama-server."""

import threading
from collections.abc import Iterator
from typing import Any

import during_summary
import pytest

from imageskin import chat, reply_times
from imageskin.chat import Message


class SlowSummaries:
    """Answers at once, except a summary, which waits until released."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.asked: list[list[Message]] = []

    def ask(self, messages: list[Message], max_tokens: int = 300, schema: Any = None) -> str:
        self.asked.append(messages)
        assert self.release.wait(5)
        return "A summary."

    def stream(self, messages: list[Message]) -> Iterator[str]:
        self.asked.append(messages)
        reply_times.note_llm({"prompt_n": 20, "cache_n": 900})
        yield "Pi squared over six."

    def count(self, text: str) -> int:
        return chat.estimate(text)

    def context_tokens(self) -> int:
        return 4096


def test_a_question_asked_during_the_summary_is_answered_before_it_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(during_summary, "wait_until_idle", lambda url: 0.0)
    llm = SlowSummaries()
    talk = during_summary.conversation(llm, "http://x/v1", lambda q: [])
    threading.Timer(0.5, llm.release.set).start()
    result = during_summary.run(llm, talk)
    assert result["summary_started"] is True
    row = result["question_during_summary"]
    assert row["right"] is True and row["cache_n"] == 900
    assert result["summary_finished_after_ms"] > 0
    assert [m[-1]["content"] for m in llm.asked].count(chat.SUMMARY_PROMPT) == 1


def test_main_prints_the_times(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    llm = SlowSummaries()
    llm.release.set()
    monkeypatch.setattr(during_summary, "LlmClient", lambda settings: llm)
    monkeypatch.setattr(during_summary, "wait_until_idle", lambda url: 0.0)
    monkeypatch.setattr("sys.argv", ["during_summary"])
    during_summary.main()
    assert '"question_during_summary"' in capsys.readouterr().out
