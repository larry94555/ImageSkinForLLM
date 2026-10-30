"""The question read ahead while it is typed (roadmap R148)."""

import functools
import json
import logging
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, TypeVar
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin import reply_times
from imageskin.app import create_app
from imageskin.chat import (
    CONTENT_RULES,
    Conversation,
    EmptyReply,
    LlmCancelled,
    LlmClient,
    LlmError,
    LlmSettings,
    Message,
    ask_stop,
    system_message,
)
from imageskin.replies_first import RepliesFirst
from imageskin.review import Review
from imageskin.uploads import PhotoResult

T = TypeVar("T")

QUESTION = "How many moons does Mars have?"
PASSAGE = "Mars has two moons, Phobos and Deimos."


class Reader:
    """A read ahead that keeps what it was asked and notes llama-server's timings, as
    `LlmClient.ask` does."""

    def __init__(self, answer: Any = "The") -> None:
        self.asked: list[list[Message]] = []
        self.answer = answer

    def __call__(self, messages: list[Message]) -> str | None:
        self.asked.append(messages)
        reply_times.note_request({"prompt_n": 12, "cache_n": 180}, 50.0)
        if isinstance(self.answer, BaseException):
            raise self.answer
        answer: str | None = self.answer
        return answer


def keep(seen: list[Any], item: Any, answer: T) -> T:
    """Keeps what was asked, and answers."""
    seen.append(item)
    return answer


def chatting(reader: Reader | None, **kwargs: Any) -> Conversation:
    return Conversation(
        lambda messages: "Two.",
        lambda: 4096,
        find=lambda prompt: [PASSAGE],
        read_ahead=reader,
        **kwargs,
    )


def records(caplog: pytest.LogCaptureFixture, message: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.message == message]


# --- What is read ahead ---


def test_the_question_is_read_as_send_would_send_it(caplog: pytest.LogCaptureFixture) -> None:
    reader = Reader()
    conversation = chatting(reader)
    conversation.send("Hello there.")
    sent: list[list[Message]] = []
    conversation._ask = lambda messages: keep(sent, messages, "Two.")
    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert conversation.read_ahead(f"  {QUESTION} ") == "read"
    assert "Content sent with the prompt" not in caplog.messages  # not sent, so not logged
    conversation.send(QUESTION)
    assert reader.asked == sent  # the same messages, so llama-server reuses all it read
    asked = reader.asked[0]
    assert asked[0] == system_message(None)
    assert [m["content"] for m in asked[1:3]] == ["Hello there.", "Two."]
    assert PASSAGE in asked[-1]["content"] and asked[-1]["content"].endswith(QUESTION)
    [read] = records(caplog, "Prompt read ahead")
    assert read.tokens_read == 12 and read.tokens_reused == 180  # type: ignore[attr-defined]
    assert read.turns_sent == 2 and read.duration_ms >= 0  # type: ignore[attr-defined]


def test_nothing_read_ahead_is_kept() -> None:
    conversation = chatting(Reader())
    conversation.read_ahead(QUESTION)
    assert conversation.turns() == []


def test_a_topic_referred_to_is_what_is_looked_up() -> None:
    looked_up: list[str] = []
    conversation = Conversation(
        lambda messages: "Two.",
        lambda: 4096,
        find=lambda prompt: keep(looked_up, prompt, [PASSAGE]),
        topics=lambda: ["Mars", "Venus"],
        read_ahead=Reader(),
    )
    conversation.send("What can you talk about?")
    looked_up.clear()
    assert conversation.read_ahead("Tell me about the second one") == "read"
    assert looked_up == ["Venus"]


@pytest.mark.parametrize(
    ("draft", "reason"),
    [
        ("Mars moons", "too short"),
        ("What can you talk about?", "not asked as typed"),
        ("Can you give me an example?", "not asked as typed"),
        ("moon " * 4000, "too long"),
    ],
)
def test_some_questions_are_not_read_ahead(
    draft: str, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    reader = Reader()
    with caplog.at_level(logging.INFO):
        assert chatting(reader).read_ahead(draft) == reason
    assert reader.asked == []
    assert records(caplog, "Prompt not read ahead")[0].reason == reason  # type: ignore[attr-defined]


def test_nothing_is_read_ahead_without_a_local_llm() -> None:
    assert chatting(None).read_ahead(QUESTION) == "no local LLM"


def test_a_question_that_would_be_declined_is_not_read_ahead() -> None:
    reader = Reader()
    conversation = Conversation(
        lambda messages: "Two.",
        lambda: 4096,
        find=lambda prompt: [],
        content_only=lambda: True,
        read_ahead=reader,
    )
    assert conversation.read_ahead(QUESTION) == "declined"
    assert reader.asked == []


def test_nothing_is_read_ahead_while_a_reply_is_made() -> None:
    reader = Reader()
    writing, done = threading.Event(), threading.Event()

    def slow(messages: list[Message]) -> str:
        writing.set()
        assert done.wait(5)
        return "Two."

    conversation = Conversation(slow, lambda: 4096, read_ahead=reader)
    thread = threading.Thread(target=conversation.send, args=("Hello there.",))
    thread.start()
    assert writing.wait(5)
    assert conversation.read_ahead(QUESTION) == "busy"
    done.set()
    thread.join(5)
    assert reader.asked == []


@pytest.mark.parametrize(
    ("answer", "outcome", "logged"),
    [
        (EmptyReply("A space."), "read", "Prompt read ahead"),
        (LlmError("Down."), "failed", "Could not read the prompt ahead"),
        (LlmCancelled("Cut off."), "cut off", "Prompt read ahead cut off"),
        (None, "busy", "Prompt not read ahead"),
    ],
)
def test_how_a_read_ahead_ends(
    answer: Any, outcome: str, logged: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        assert chatting(Reader(answer)).read_ahead(QUESTION) == outcome
    assert logged in caplog.messages


# --- Cut off by a reply (RepliesFirst.ahead) ---


def test_only_the_local_llm_is_read_ahead() -> None:
    asked: list[object] = []
    ahead = RepliesFirst().ahead(lambda m: keep(asked, m, "The"), lambda: False)
    assert ahead(["m"]) is None and asked == []


def test_nothing_is_read_ahead_while_a_reply_is_written() -> None:
    replies = RepliesFirst()
    asked: list[object] = []
    ahead = replies.ahead(lambda m: keep(asked, m, "The"), lambda: True)
    with replies.reply():
        assert ahead(["m"]) is None
    assert ahead(["m"]) == "The" and asked == [["m"]]


def waits_to_be_cut_off(started: threading.Event) -> Any:
    def ask(messages: object) -> str:
        stop = ask_stop.get()
        assert stop is not None
        started.set()
        assert stop.wait(5)  # as llama-server's connection is cut when this is set
        raise LlmCancelled("Cut off while the LLM was answering.")

    return ask


def test_a_reply_cuts_the_read_ahead_off_and_waits_for_the_llm(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settled: list[int] = []
    replies = RepliesFirst(lambda: settled.append(1))
    started = threading.Event()
    got: list[object] = []
    ahead = replies.ahead(waits_to_be_cut_off(started), lambda: True)

    def run() -> None:
        try:
            got.append(ahead(["m"]))
        except LlmCancelled as e:
            got.append(e)

    thread = threading.Thread(target=run)
    with caplog.at_level(logging.INFO):
        thread.start()
        assert started.wait(2)
        with replies.reply():
            thread.join(2)
    assert isinstance(got[0], LlmCancelled)  # never asked again
    assert settled == [1]
    assert "Prompt read ahead cut off for a reply" in caplog.messages
    assert "Wiki request cut off for a reply" not in caplog.messages


def test_a_newer_read_ahead_cuts_the_older_off() -> None:
    settled: list[int] = []
    replies = RepliesFirst(lambda: settled.append(1))
    started = threading.Event()
    got: list[object] = []
    older = replies.ahead(waits_to_be_cut_off(started), lambda: True)

    def run() -> None:
        try:
            got.append(older(["How many"]))
        except LlmCancelled as e:
            got.append(e)

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(2)
    assert replies.ahead(lambda m: "The", lambda: True)(["How many moons"]) == "The"
    thread.join(2)
    assert isinstance(got[0], LlmCancelled) and settled == [1]


# --- With llama-server ---


class TimedLlm(BaseHTTPRequestHandler):
    """llama-server answering with its timings; keeps each request's body."""

    bodies: list[dict[str, Any]] = []

    def do_POST(self) -> None:
        TimedLlm.bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        answer = {
            "choices": [{"message": {"role": "assistant", "content": "The"}}],
            "timings": {"prompt_n": 40, "cache_n": 200},
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(answer).encode())

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def timed_llm() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), TimedLlm)
    TimedLlm.bodies = []
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    ).start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()


def test_llama_server_reads_the_question_for_one_token(
    timed_llm: str, caplog: pytest.LogCaptureFixture
) -> None:
    client = LlmClient(LlmSettings(url=timed_llm))
    ahead = RepliesFirst().ahead(functools.partial(client.ask, max_tokens=1), lambda: True)
    conversation = Conversation(
        client.ask, lambda: 4096, find=lambda p: [PASSAGE], read_ahead=ahead
    )
    with caplog.at_level(logging.INFO):
        assert conversation.read_ahead(QUESTION) == "read"
    [body] = TimedLlm.bodies
    assert body["max_tokens"] == 1
    assert body["messages"][0]["content"].endswith(CONTENT_RULES)
    [read] = records(caplog, "Prompt read ahead")
    assert read.tokens_read == 40 and read.tokens_reused == 200  # type: ignore[attr-defined]


def test_a_reply_logs_the_tokens_it_reused(caplog: pytest.LogCaptureFixture) -> None:
    conversation = Conversation(lambda messages: "Two.", lambda: 4096)
    times = reply_times.ReplyTimes(received_at=time.perf_counter())
    times.llm = {"prompt_n": 30, "cache_n": 210}
    token = reply_times.current.set(times)
    try:
        with caplog.at_level(logging.INFO):
            conversation.send(QUESTION)
    finally:
        reply_times.current.reset(token)
    [received] = records(caplog, "Chat reply received")
    assert received.tokens_read == 30 and received.tokens_reused == 210  # type: ignore[attr-defined]


# --- In the app ---


def app_with(tmp_path: Path, llm: Any) -> Any:
    return create_app(
        tmp_path,
        check_photo=lambda p: PhotoResult([], 80),
        prepare_voice=lambda: None,
        prepare_face=lambda photo, progress: None,
        render_clip=lambda photo, text, output: None,
        ask_llm=llm,
    )


def test_the_chat_page_has_the_question_read_ahead(tmp_path: Path) -> None:
    asked: list[list[Message]] = []
    app = app_with(tmp_path, lambda messages: keep(asked, messages, "Two moons."))
    client = TestClient(app)
    client.post("/api/consent", json={"agreed": True})
    app.state.reply_warm_up.join(5)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        response = client.post("/api/chat/ahead", json={"prompt": QUESTION})
        assert response.json() == {"read": True, "reason": "read"}
        assert asked[-1][-1]["content"] == QUESTION
        assert client.post("/api/chat/ahead", json={"prompt": "Mars"}).json() == {
            "read": False,
            "reason": "too short",
        }
        assert client.get("/api/chat").json()["turns"] == []  # nothing kept


def test_nothing_is_read_ahead_while_the_replies_warm_up(tmp_path: Path) -> None:
    asked: list[object] = []
    app = app_with(tmp_path, lambda messages: keep(asked, messages, "Two moons."))
    client = TestClient(app)
    client.post("/api/consent", json={"agreed": True})
    release = threading.Event()
    app.state.reply_warm_up = threading.Thread(target=release.wait, daemon=True)
    app.state.reply_warm_up.start()
    try:
        with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
            answer = client.post("/api/chat/ahead", json={"prompt": QUESTION}).json()
    finally:
        release.set()
    assert answer == {"read": False, "reason": "warming up"} and asked == []


def test_the_chat_page_needs_the_sample_accepted(tmp_path: Path) -> None:
    client = TestClient(app_with(tmp_path, lambda messages: "Two moons."))
    client.post("/api/consent", json={"agreed": True})
    assert client.post("/api/chat/ahead", json={"prompt": QUESTION}).status_code >= 400
