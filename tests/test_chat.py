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
    EARLIER,
    HISTORY_SHARE,
    REPLY_TOKENS,
    SUMMARY_PROMPT,
    SYSTEM_PROMPT,
    TEMPERATURE,
    TOKENS_PER_MESSAGE,
    Conversation,
    LlmClient,
    LlmError,
    LlmSettings,
    Message,
    Turn,
    estimate,
    latest,
    system_message,
    tokens,
)
from imageskin.review import Review
from imageskin.uploads import PhotoResult

# --- Which turns are sent ---


def test_the_system_prompt_asks_for_short_replies() -> None:
    assert system_message(None) == {"role": "system", "content": SYSTEM_PROMPT}
    assert "short" in SYSTEM_PROMPT
    assert system_message("Larry lives in Seattle.")["content"].endswith(
        f"{EARLIER}\nLarry lives in Seattle."
    )


def test_only_the_latest_turns_that_fit_are_kept() -> None:
    # Each turn is about 100 tokens.
    turns = [Turn("user" if i % 2 == 0 else "assistant", f"{i:03} " + "x" * 96) for i in range(10)]
    assert [t.content[:3] for t in latest(turns, 450)] == ["006", "007", "008", "009"]
    assert latest(turns, 10_000) == turns
    assert latest(turns, 50) == []


def test_kept_turns_never_start_on_a_reply() -> None:
    turns = [Turn("user", "a" * 300), Turn("assistant", "b" * 300), Turn("user", "c" * 30)]
    assert latest(turns, 120) == [Turn("user", "c" * 30)]


# --- Counting tokens ---


@pytest.mark.parametrize(
    ("text", "at_least"),
    [
        ("Hello there", 11),  # 11 characters of English
        ("eyJhbGciOiJIUzI1NiJ9.x_Q3", 25),  # token-dense ASCII, such as a hash or base64
        ("a=b;c=d;e=f", 11),  # punctuation-heavy ASCII, such as minified code
        ("你好，我叫拉里。", 24),  # 8 Chinese characters, 3 bytes each
        ("🐶🐶🐶", 12),  # emoji, 4 bytes each
        ("Biscuit 🐶", 7),  # 8 ASCII characters and one emoji
    ],
)
def test_the_estimate_never_counts_fewer_tokens_than_bytes_allow(text: str, at_least: int) -> None:
    # A byte-level tokenizer uses at most one token per byte, ASCII included.
    assert estimate(text) >= at_least
    assert estimate(text) >= len(text.encode())


def utf8_bytes(text: str) -> int:
    """The worst a real tokenizer can do: one token per byte."""
    return len(text.encode())


DENSE_ASCII = "eyJhbGciOiJIUzI1NiJ9.x_Q3" * 8  # like a hash or base64: about a token a byte


@pytest.mark.parametrize("dense", ["你好🐶" * 20, DENSE_ASCII], ids=["chinese-emoji", "ascii"])
@pytest.mark.parametrize("server_counts", [True, False], ids=["tokenizer", "estimate"])
def test_token_dense_turns_stay_within_half_the_window(dense: str, server_counts: bool) -> None:
    # Without the server's count, the estimate must still hold against a tokenizer that uses a
    # token per byte.
    llm = FakeLlm2()
    if server_counts:
        conversation = Conversation(llm, lambda: 2048, count=utf8_bytes)
    else:
        conversation = Conversation(llm, lambda: 2048)
    for i in range(10):
        conversation.send(f"{i} {dense}")  # about 200 bytes: about 200 tokens at worst
        conversation.wait()
    for sent in llm.sent:
        if sent[0]["content"] == SUMMARY_PROMPT:
            continue
        history = sent[1:-1]
        assert (
            sum(utf8_bytes(m["content"]) + TOKENS_PER_MESSAGE for m in history)
            + (utf8_bytes(sent[0]["content"]) - utf8_bytes(SYSTEM_PROMPT))
            <= 2048 * HISTORY_SHARE
        )


def test_a_token_dense_prompt_too_long_is_refused_by_its_real_count() -> None:
    # 300 characters would pass at 3 characters a token; at 4 bytes each it can't fit.
    with pytest.raises(ValueError, match="too long"):
        Conversation(FakeLlm2(), lambda: 2048, count=utf8_bytes).send("🐶" * 300)
    with pytest.raises(ValueError, match="too long"):
        Conversation(FakeLlm2(), lambda: 2048).send("🐶" * 300)
    # Token-dense ASCII is counted a token a byte too when the server can't count.
    with pytest.raises(ValueError, match="too long"):
        Conversation(FakeLlm2(), lambda: 2048).send(DENSE_ASCII * 6)


# --- The conversation ---


class FakeLlm2:
    """Answers chat prompts with "Reply N" and summary requests with "SUMMARY N"."""

    def __init__(self) -> None:
        self.sent: list[list[Message]] = []
        self.fail_summary = False

    def __call__(self, messages: list[Message]) -> str:
        self.sent.append(messages)
        if messages[0]["content"] == SUMMARY_PROMPT:
            if self.fail_summary:
                raise LlmError("busy")
            return f"SUMMARY {len(self.sent)}"
        return f"Reply {len(self.sent)}"


def test_a_conversation_remembers_earlier_turns(caplog: pytest.LogCaptureFixture) -> None:
    llm = FakeLlm2()
    conversation = Conversation(llm, lambda: 4096)
    with caplog.at_level(logging.INFO):
        assert conversation.send("  My name is Larry. ") == Turn("assistant", "Reply 1")
        conversation.send("What is my name?")
    assert llm.sent[1][1:] == [
        {"role": "user", "content": "My name is Larry."},
        {"role": "assistant", "content": "Reply 1"},
        {"role": "user", "content": "What is my name?"},
    ]
    assert conversation.turns()[-1] == Turn("assistant", "Reply 2")
    assert "Chat prompt sent" in caplog.text and "Chat reply received" in caplog.text


def test_a_streamed_reply_is_logged_sentence_by_sentence(caplog: pytest.LogCaptureFixture) -> None:
    def stream(messages: list[Message]) -> Iterator[str]:
        yield from ["Hi Lar", "ry. Dr. Smith", " says hi", "! Bye"]

    conversation = Conversation(FakeLlm2(), lambda: 4096, stream=stream)
    with caplog.at_level(logging.INFO):
        assert conversation.send("Hi") == Turn("assistant", "Hi Larry. Dr. Smith says hi! Bye")
    ready = [r for r in caplog.records if r.message == "Reply sentence ready"]
    assert [(r.sentence, r.chars) for r in ready] == [(1, 9), (2, 18), (3, 3)]  # type: ignore[attr-defined]
    assert "Reply started" in caplog.messages


def test_an_empty_streamed_reply_is_an_error(caplog: pytest.LogCaptureFixture) -> None:
    conversation = Conversation(FakeLlm2(), lambda: 4096, stream=lambda messages: iter([" "]))
    with pytest.raises(LlmError, match="empty reply"):
        conversation.send("Hi")
    assert conversation.turns() == []


def test_older_turns_are_summarized_when_the_history_passes_half_the_window(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = FakeLlm2()
    conversation = Conversation(llm, lambda: 4096)  # history budget: 2048 tokens
    with caplog.at_level(logging.INFO):
        for i in range(5):
            conversation.send(f"Prompt {i} " + "x" * 590)  # about 600 tokens each
            conversation.wait()
    summaries = [m for m in llm.sent if m[0]["content"] == SUMMARY_PROMPT]
    assert len(summaries) == 1
    # Prompts 0 and 1 were summarized; 2 and 3 are still sent word for word, then 4.
    assert "User: Prompt 0" in summaries[0][1]["content"]
    assert "Prompt 2" not in summaries[0][1]["content"]
    last = llm.sent[-1]
    assert last[0]["content"].endswith(f"{EARLIER}\nSUMMARY 5")
    assert [m["content"][:8] for m in last[1:] if m["role"] == "user"] == [
        "Prompt 2",
        "Prompt 3",
        "Prompt 4",
    ]
    assert sum(tokens(m) for m in last[:-1]) - tokens(system_message(None)) <= 4096 * HISTORY_SHARE
    assert "Conversation summarized" in caplog.text
    # The chat still shows everything that was said.
    assert len(conversation.turns()) == 10


def test_the_reply_does_not_wait_for_the_summary() -> None:
    release = threading.Event()
    llm = FakeLlm2()

    def slow_summaries(messages: list[Message]) -> str:
        if messages[0]["content"] == SUMMARY_PROMPT:
            assert release.wait(5)
        return llm(messages)

    conversation = Conversation(slow_summaries, lambda: 4096)
    for i in range(4):
        conversation.send(f"Prompt {i} " + "x" * 590)
    # The 4th reply came back while its summary is still being made.
    assert conversation.turns()[-1].content.startswith("Reply")
    assert not any(m[0]["content"] == SUMMARY_PROMPT for m in llm.sent)
    release.set()
    conversation.send("Prompt 4")  # waits for the summary, then is sent with it
    assert llm.sent[-1][0]["content"].endswith(f"{EARLIER}\nSUMMARY 5")


def test_waiting_without_a_summary_returns_at_once() -> None:
    Conversation(FakeLlm2(), lambda: 4096).wait()


def test_a_summary_is_summarized_again_with_the_next_turns() -> None:
    llm = FakeLlm2()
    conversation = Conversation(llm, lambda: 4096)
    for i in range(9):
        conversation.send(f"Prompt {i} " + "x" * 590)
        conversation.wait()
    summaries = [m for m in llm.sent if m[0]["content"] == SUMMARY_PROMPT]
    assert len(summaries) >= 2
    assert summaries[1][1]["content"].startswith("Summary of what came before: SUMMARY")


def test_if_summarizing_fails_the_oldest_turns_are_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = FakeLlm2()
    llm.fail_summary = True
    conversation = Conversation(llm, lambda: 4096)
    with caplog.at_level(logging.WARNING):
        for i in range(5):
            assert conversation.send(f"Prompt {i} " + "x" * 590).content.startswith("Reply")
            conversation.wait()
    last = [m for m in llm.sent if m[0]["content"] != SUMMARY_PROMPT][-1]
    assert last[0] == system_message(None)
    assert sum(tokens(m) for m in last[:-1]) - tokens(system_message(None)) <= 2048
    assert "Could not summarize the conversation" in caplog.text


def test_a_prompt_too_long_for_the_window_is_refused(caplog: pytest.LogCaptureFixture) -> None:
    llm = FakeLlm2()
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError, match="too long"):
        Conversation(llm, lambda: 2048).send("y" * 3000)
    assert llm.sent == []
    assert "Chat prompt too long" in caplog.text


def test_an_empty_prompt_is_refused() -> None:
    with pytest.raises(ValueError, match="Type something"):
        Conversation(FakeLlm2(), lambda: 4096).send("   ")


def test_a_failed_reply_leaves_the_conversation_as_it_was(caplog: pytest.LogCaptureFixture) -> None:
    def fail(messages: list[Message]) -> str:
        raise LlmError("Could not reach the LLM")

    conversation = Conversation(fail, lambda: 4096)
    with caplog.at_level(logging.ERROR), pytest.raises(LlmError):
        conversation.send("Hi")
    assert conversation.turns() == []
    assert "Chat reply failed" in caplog.text


# --- The client, against a fake llama-server ---


class FakeLlm(BaseHTTPRequestHandler):
    answer: tuple[int, bytes] = (200, b"")
    props: tuple[int, bytes] = (404, b"")
    tokenize: tuple[int, bytes] = (404, b"")
    received: list[dict[str, object]] = []

    def do_GET(self) -> None:  # noqa: N802 (the name http.server calls)
        FakeLlm.received.append({"path": self.path})
        status, body = FakeLlm.props
        self.send_response(status)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 (the name http.server calls)
        length = int(self.headers["Content-Length"])
        FakeLlm.received.append({"path": self.path, **json.loads(self.rfile.read(length))})
        status, body = FakeLlm.tokenize if self.path == "/tokenize" else FakeLlm.answer
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
            "temperature": TEMPERATURE,
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


def events(*pieces: object) -> bytes:
    """A streamed answer: server-sent events, as llama-server and OpenAI send them."""
    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}) + "\n\n"
        for piece in pieces
    ]
    return ("".join(lines) + "data: [DONE]\n\n").encode()


def test_the_client_streams_the_reply(fake_llm: str) -> None:
    # llama-cpp-python's server sends ": ping" comments between events.
    answer = b": ping - 2026-10-10 01:31:50\n\nevent: message\n" + events(
        "Hello", None, " there.", ""
    )
    FakeLlm.answer = (200, answer.replace(b"[DONE]", b'{"choices": [{}]}\n\ndata: [DONE]'))
    client = LlmClient(LlmSettings(url=fake_llm, model="qwen"))
    assert list(client.stream([{"role": "user", "content": "Hi"}])) == ["Hello", " there."]
    assert FakeLlm.received[0]["stream"] is True


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        ((500, b"model not loaded"), r"refused the prompt \(500\)"),
        ((200, b"data: <html>\n\n"), "could not be read"),
        ((200, b'data: {"choices": []}\n\n'), "could not be read"),
    ],
)
def test_bad_streams_say_what_went_wrong(
    fake_llm: str, answer: tuple[int, bytes], message: str
) -> None:
    FakeLlm.answer = answer
    with pytest.raises(LlmError, match=message):
        list(LlmClient(LlmSettings(url=fake_llm)).stream([]))


class Stalled:
    """A response the LLM stops sending part way through."""

    def __enter__(self) -> "Stalled":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self) -> bytes:
        raise TimeoutError("timed out")

    def __iter__(self) -> Iterator[bytes]:
        yield b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n'
        raise TimeoutError("timed out")


def test_an_llm_that_stops_answering_is_named() -> None:
    client = LlmClient(LlmSettings(url="http://x/v1"))
    with patch("urllib.request.urlopen", return_value=Stalled()):
        with pytest.raises(LlmError, match="Could not reach the LLM"):
            client.ask([])
        pieces = client.stream([])
        assert next(pieces) == "Hello"
        with pytest.raises(LlmError, match="stopped answering"):
            next(pieces)


def test_an_llm_that_is_not_running_is_named() -> None:
    server = HTTPServer(("127.0.0.1", 0), FakeLlm)
    port = server.server_port
    server.server_close()  # nothing listens there now
    with pytest.raises(LlmError, match=f"Could not reach the LLM at http://127.0.0.1:{port}/v1"):
        LlmClient(LlmSettings(url=f"http://127.0.0.1:{port}/v1", timeout_s=5)).ask([])


@pytest.mark.parametrize(
    ("props", "expected"),
    [
        ((200, b'{"default_generation_settings": {"n_ctx": 8192}}'), 8192),
        ((200, b'{"n_ctx": 16384}'), 16384),
        ((200, b'{"default_generation_settings": {"n_ctx": 0}}'), 4096),
        ((200, b'{"other": 1}'), 4096),
        ((200, b"[]"), 4096),
        ((404, b""), 4096),
    ],
)
def test_the_context_window_comes_from_the_server_when_it_says(
    fake_llm: str, props: tuple[int, bytes], expected: int, caplog: pytest.LogCaptureFixture
) -> None:
    FakeLlm.props = props
    with caplog.at_level(logging.INFO):
        assert (
            LlmClient(LlmSettings(url=fake_llm, context_tokens=4096)).context_tokens() == expected
        )
    assert FakeLlm.received == [{"path": "/props"}]
    source = "server" if expected != 4096 else "config"
    assert f"LLM context window from the {source}" in caplog.text


def test_the_window_is_asked_for_until_the_server_answers(fake_llm: str) -> None:
    port = fake_llm.split(":")[2].split("/")[0]
    down = LlmClient(LlmSettings(url="http://127.0.0.1:1/v1", context_tokens=4096, timeout_s=5))
    assert down.context_tokens() == 4096
    assert down._window is None  # asked again next time
    FakeLlm.props = (200, b'{"n_ctx": 8192}')
    client = LlmClient(LlmSettings(url=f"http://127.0.0.1:{port}/v1"))
    assert client.context_tokens() == client.context_tokens() == 8192
    assert len(FakeLlm.received) == 1  # then remembered


def test_tokens_are_estimated_while_the_server_is_down() -> None:
    client = LlmClient(LlmSettings(url="http://127.0.0.1:1/v1", timeout_s=5))
    assert client.count("Hello") == estimate("Hello")
    assert client._can_count  # asked again once it is up


def test_tokens_are_counted_by_the_server(fake_llm: str) -> None:
    FakeLlm.tokenize = (200, b'{"tokens": [1, 2, 3, 4, 5]}')
    client = LlmClient(LlmSettings(url=fake_llm))
    assert client.count("Hello there") == 5
    assert client.count("Hello there") == 5  # counted once, then remembered
    assert FakeLlm.received == [{"path": "/tokenize", "content": "Hello there"}]


def test_tokens_are_estimated_when_the_server_cant_count(
    fake_llm: str, caplog: pytest.LogCaptureFixture
) -> None:
    FakeLlm.tokenize = (404, b"")
    client = LlmClient(LlmSettings(url=fake_llm))
    with caplog.at_level(logging.WARNING):
        assert client.count("🐶🐶") == estimate("🐶🐶")
        assert client.count("Hello") == estimate("Hello")
    assert len(FakeLlm.received) == 1  # not asked again
    assert "can't count tokens" in caplog.text


def test_the_counting_cache_is_kept_small(fake_llm: str) -> None:
    FakeLlm.tokenize = (200, b'{"tokens": [1]}')
    client = LlmClient(LlmSettings(url=fake_llm))
    for i in range(1002):
        client.count(str(i))
    assert client.count("1001") == 1
    assert len(FakeLlm.received) == 1002


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
