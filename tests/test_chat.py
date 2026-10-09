import json
import logging
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin.app import CHAT_LOCKED, create_app
from imageskin.chat import (
    REPLY_TOKENS,
    SYSTEM_PROMPT,
    Conversation,
    LlmClient,
    LlmError,
    LlmSettings,
    Message,
    Turn,
    fit,
)
from imageskin.review import Review
from imageskin.uploads import PhotoResult

# --- Which turns are sent ---


def test_the_system_prompt_asks_for_short_replies() -> None:
    assert fit([Turn("user", "Hi")], 4096) == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Hi"},
    ]
    assert "short" in SYSTEM_PROMPT


def test_the_whole_conversation_is_sent_when_it_fits() -> None:
    turns = [Turn("user", "Hi"), Turn("assistant", "Hello!"), Turn("user", "How are you?")]
    assert [m["content"] for m in fit(turns, 4096)[1:]] == ["Hi", "Hello!", "How are you?"]


def test_the_oldest_turns_are_dropped_when_the_window_is_full() -> None:
    # Each turn is about 100 tokens; a 1024-token window leaves room for 6 of them.
    turns = [Turn("user" if i % 2 == 0 else "assistant", f"{i:03} " + "x" * 296) for i in range(20)]
    sent = fit(turns, 1024)
    assert sent[0]["role"] == "system"
    assert sent[1]["role"] == "user"  # never starts on a reply whose prompt was dropped
    assert sent[-1]["content"].startswith("019")
    assert [m["content"][:3] for m in sent[1:]] == ["014", "015", "016", "017", "018", "019"]
    assert sum(len(m["content"]) // 3 + 4 for m in sent) <= 1024 - REPLY_TOKENS


def test_the_newest_prompt_is_sent_even_when_too_long() -> None:
    sent = fit([Turn("user", "a"), Turn("assistant", "b"), Turn("user", "y" * 50_000)], 1024)
    assert [m["role"] for m in sent] == ["system", "user"]


# --- The conversation ---


def test_a_conversation_remembers_earlier_turns(caplog: pytest.LogCaptureFixture) -> None:
    sent: list[list[Message]] = []

    def ask(messages: list[Message]) -> str:
        sent.append(messages)
        return f"Reply {len(sent)}"

    conversation = Conversation(ask, 4096)
    with caplog.at_level(logging.INFO):
        assert conversation.send("  My name is Larry. ") == Turn("assistant", "Reply 1")
        conversation.send("What is my name?")
    assert [m["content"] for m in sent[1][1:]] == [
        "My name is Larry.",
        "Reply 1",
        "What is my name?",
    ]
    assert conversation.turns()[-1] == Turn("assistant", "Reply 2")
    assert "Chat prompt sent" in caplog.text and "Chat reply received" in caplog.text


def test_an_empty_prompt_is_refused() -> None:
    with pytest.raises(ValueError, match="Type something"):
        Conversation(lambda m: "x", 4096).send("   ")


def test_a_failed_reply_leaves_the_conversation_as_it_was(caplog: pytest.LogCaptureFixture) -> None:
    def fail(messages: list[Message]) -> str:
        raise LlmError("Could not reach the LLM")

    conversation = Conversation(fail, 4096)
    with caplog.at_level(logging.ERROR), pytest.raises(LlmError):
        conversation.send("Hi")
    assert conversation.turns() == []
    assert "Chat reply failed" in caplog.text


# --- The client, against a fake llama-server ---


class FakeLlm(BaseHTTPRequestHandler):
    answer: tuple[int, bytes] = (200, b"")
    received: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802 (the name http.server calls)
        length = int(self.headers["Content-Length"])
        FakeLlm.received.append({"path": self.path, **json.loads(self.rfile.read(length))})
        status, body = FakeLlm.answer
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def fake_llm() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), FakeLlm)
    FakeLlm.received = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1/"
    server.shutdown()
    server.server_close()


def reply(content: object) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": content}}]}
    ).encode()


def test_the_client_asks_the_chat_api(fake_llm: str) -> None:
    FakeLlm.answer = (200, reply(" Hello there! \n"))
    client = LlmClient(LlmSettings(url=fake_llm, model="qwen"))
    messages = [{"role": "user", "content": "Hi"}]
    assert client.ask(messages) == "Hello there!"
    assert FakeLlm.received == [
        {
            "path": "/v1/chat/completions",
            "model": "qwen",
            "messages": messages,
            "max_tokens": REPLY_TOKENS,
        }
    ]


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        ((500, b'{"error": "model not loaded"}'), r"refused the prompt \(500\): .*not loaded"),
        ((200, b"<html>"), "not JSON"),
        ((200, b'{"choices": []}'), "without a reply"),
        ((200, reply("  ")), "empty reply"),
        ((200, reply(None)), "empty reply"),
    ],
)
def test_bad_answers_say_what_went_wrong(
    fake_llm: str, answer: tuple[int, bytes], message: str
) -> None:
    FakeLlm.answer = answer
    with pytest.raises(LlmError, match=message):
        LlmClient(LlmSettings(url=fake_llm)).ask([{"role": "user", "content": "Hi"}])


def test_an_llm_that_is_not_running_is_named() -> None:
    server = HTTPServer(("127.0.0.1", 0), FakeLlm)
    port = server.server_port
    server.server_close()  # nothing listens there now
    with pytest.raises(LlmError, match=f"Could not reach the LLM at http://127.0.0.1:{port}/v1"):
        LlmClient(LlmSettings(url=f"http://127.0.0.1:{port}/v1", timeout_s=5)).ask([])


# --- The API ---


def chat_app(tmp_path: Path, ask: object) -> TestClient:
    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            ask_llm=ask,  # type: ignore[arg-type]
        )
    )
    client.post("/api/consent", json={"agreed": True})
    return client


def test_the_api_chats_once_the_sample_is_accepted(tmp_path: Path) -> None:
    client = chat_app(tmp_path, lambda messages: f"You said {messages[-1]['content']}")
    assert client.get("/api/chat").json() == {"turns": []}
    with patch("imageskin.app.load_review", return_value=Review(accepted=False)):
        locked = client.post("/api/chat", json={"prompt": "Hi"})
    assert locked.status_code == 403 and locked.json()["detail"] == CHAT_LOCKED

    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        answer = client.post("/api/chat", json={"prompt": "Hi"})
        assert answer.json() == {"role": "assistant", "content": "You said Hi"}
        assert client.post("/api/chat", json={"prompt": " "}).status_code == 400
    assert client.get("/api/chat").json()["turns"] == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "You said Hi"},
    ]


def test_the_api_says_when_the_llm_fails(tmp_path: Path) -> None:
    def fail(messages: list[Message]) -> str:
        raise LlmError("Could not reach the LLM at http://x/v1. Is llama-server running?")

    client = chat_app(tmp_path, fail)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        failed = client.post("/api/chat", json={"prompt": "Hi"})
    assert failed.status_code == 502
    assert "Is llama-server running?" in failed.json()["detail"]
