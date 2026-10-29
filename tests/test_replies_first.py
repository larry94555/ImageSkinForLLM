import io
import json
import logging
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin import reply_times
from imageskin.app import create_app
from imageskin.chat import LlmCancelled, LlmClient, LlmSettings, Message, ask_stop
from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.replies_first import RepliesFirst
from imageskin.reply_times import ReplyTimes
from imageskin.review import Review
from imageskin.uploads import PhotoResult

PDF = b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF\n"


def in_wiki_thread(
    replies: RepliesFirst, ask: Any, stop: threading.Event | None = None
) -> tuple[threading.Thread, list[object]]:
    """Runs the wiki's ask in a thread of its own, as the wiki's builder does, with the build's
    stop; gives the thread and what it answered or raised."""
    got: list[object] = []
    asked = replies.wiki(ask)

    def run() -> None:
        token = ask_stop.set(stop)
        try:
            got.append(asked("part 1", max_tokens=5))
        except BaseException as e:  # noqa: BLE001 (what the test checks)
            got.append(e)
        finally:
            ask_stop.reset(token)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, got


def test_with_no_reply_the_wiki_asks_at_once() -> None:
    replies = RepliesFirst()
    seen: list[tuple[object, ...]] = []

    def ask(*args: object, **kwargs: object) -> str:
        seen.append((*args, kwargs))
        return "topics"

    thread, got = in_wiki_thread(replies, ask)
    thread.join(2)
    assert got == ["topics"] and seen == [("part 1", {"max_tokens": 5})]


def test_the_wiki_waits_while_a_reply_is_written(caplog: pytest.LogCaptureFixture) -> None:
    replies = RepliesFirst()
    asked = threading.Event()

    def ask(*args: object, **kwargs: object) -> str:
        asked.set()
        return "topics"

    with caplog.at_level(logging.INFO):
        with replies.reply():
            thread, got = in_wiki_thread(replies, ask)
            time.sleep(0.3)
            assert not asked.is_set()  # held back while the reply is written
        thread.join(2)
    assert got == ["topics"]
    waited = [r for r in caplog.records if r.message == "Wiki waited for a reply"]
    assert waited and waited[0].duration_ms >= 200  # type: ignore[attr-defined]


def test_a_wiki_request_is_cut_off_by_a_reply_and_asked_again_after_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    replies = RepliesFirst()
    started = threading.Event()
    calls: list[int] = []

    def ask(*args: object, **kwargs: object) -> str:
        calls.append(1)
        if len(calls) == 1:
            stop = ask_stop.get()
            assert stop is not None
            started.set()
            assert stop.wait(5)  # as llama-server's connection is cut when this is set
            raise LlmCancelled("Cut off while the LLM was answering.")
        return "topics"

    with caplog.at_level(logging.INFO):
        thread, got = in_wiki_thread(replies, ask)
        assert started.wait(2)
        with replies.reply():
            time.sleep(0.2)
            assert len(calls) == 1  # not asked again while the reply is written
        thread.join(2)
    assert got == ["topics"] and len(calls) == 2
    assert "Wiki request cut off for a reply" in caplog.messages
    assert "Wiki request paused for a reply; it is asked again after it" in caplog.messages


def test_a_removed_pdf_still_stops_the_wiki_request() -> None:
    replies = RepliesFirst()
    build_stop = threading.Event()
    started = threading.Event()

    def ask(*args: object, **kwargs: object) -> str:
        stop = ask_stop.get()
        assert stop is not None and stop is not build_stop  # its own, which counts both
        started.set()
        assert stop.wait(5)
        raise LlmCancelled("Cut off while the LLM was answering.")

    thread, got = in_wiki_thread(replies, ask, build_stop)
    assert started.wait(2)
    build_stop.set()  # the PDF is removed
    thread.join(2)
    assert len(got) == 1 and isinstance(got[0], LlmCancelled)  # not asked again


def test_a_removed_pdf_stops_the_wiki_waiting_for_a_reply() -> None:
    replies = RepliesFirst()
    build_stop = threading.Event()
    with replies.reply():
        thread, got = in_wiki_thread(replies, lambda *a, **k: "topics", build_stop)
        time.sleep(0.1)
        build_stop.set()
        thread.join(3)  # within the second it checks
        assert len(got) == 1 and isinstance(got[0], LlmCancelled)


def test_another_failure_of_the_wiki_request_is_not_asked_again() -> None:
    def ask(*args: object, **kwargs: object) -> str:
        raise ValueError("no")

    thread, got = in_wiki_thread(RepliesFirst(), ask)
    thread.join(2)
    assert len(got) == 1 and isinstance(got[0], ValueError)


class OnceSlowLlm(BaseHTTPRequestHandler):
    """llama-server answering the wiki: its first request takes until the client hangs up, as a
    long wiki part would; the next is answered at once."""

    requests = 0
    hung_up = threading.Event()

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers["Content-Length"]))
        OnceSlowLlm.requests += 1
        if OnceSlowLlm.requests == 1:
            self.connection.settimeout(0.05)
            for _ in range(200):
                try:
                    if self.connection.recv(1, socket.MSG_PEEK) == b"":
                        break
                except TimeoutError:
                    continue
                except OSError:
                    break
            OnceSlowLlm.hung_up.set()
            return
        answer = {"choices": [{"message": {"role": "assistant", "content": "Primes"}}]}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(answer).encode())

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def once_slow_llm() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), OnceSlowLlm)
    OnceSlowLlm.requests, OnceSlowLlm.hung_up = 0, threading.Event()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()


def test_llama_server_sees_the_wiki_request_cut_off_by_a_reply(once_slow_llm: str) -> None:
    client = LlmClient(LlmSettings(url=once_slow_llm))
    replies = RepliesFirst()
    build_stop = threading.Event()  # the wiki's builder always sets one (WikiJob._run)
    thread, got = in_wiki_thread(
        replies, lambda *a, **k: client.ask([{"role": "user", "content": "Part 1"}]), build_stop
    )
    time.sleep(0.3)  # llama-server is writing the wiki's part
    started = time.perf_counter()
    with replies.reply():
        assert OnceSlowLlm.hung_up.wait(2)  # it stops working on the part at once
        assert time.perf_counter() - started < 1
        assert OnceSlowLlm.requests == 1
    thread.join(5)
    assert got == ["Primes"] and OnceSlowLlm.requests == 2  # asked again after the reply


def test_the_app_writes_a_reply_before_the_wiki_asks_the_llm(tmp_path: Path) -> None:
    calls: list[str] = []
    chat_asked, chat_may_answer = threading.Event(), threading.Event()

    def llm(messages: list[Message]) -> str:
        if threading.current_thread().name == "wiki":
            calls.append("wiki")
            return '{"topics": []}'
        calls.append("chat asked")
        chat_asked.set()
        assert chat_may_answer.wait(5)
        calls.append("chat answered")
        return "Two moons."

    def lesson(path: Path, progress: Progress) -> Reading:
        return Reading("text", 1, [Piece(1, "paragraph", "Phobos and Deimos circle Mars.")], [])

    app = create_app(
        tmp_path,
        check_photo=lambda p: PhotoResult([], 80),
        prepare_voice=lambda: None,
        prepare_face=lambda photo, progress: None,
        render_clip=lambda photo, text, output: None,
        ask_llm=llm,
        read_pdf=lesson,
    )
    client = TestClient(app)
    client.post("/api/consent", json={"agreed": True})
    replies: list[int] = []
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        chatting = threading.Thread(
            target=lambda: replies.append(
                client.post("/api/chat", json={"prompt": "Which moons?"}).status_code
            )
        )
        chatting.start()
        assert chat_asked.wait(5)
        client.post("/api/content", files={"file": ("space.pdf", io.BytesIO(PDF))})
        app.state.readings.wait()
        time.sleep(0.3)
        assert "wiki" not in calls  # the wiki waits while the reply is written
        chat_may_answer.set()
        chatting.join(5)
    app.state.wiki.wait()
    assert replies == [200]
    assert calls[:2] == ["chat asked", "chat answered"] and "wiki" in calls[2:]


def test_only_the_chats_requests_to_the_local_llm_go_first() -> None:
    replies = RepliesFirst()
    seen: list[bool] = []
    local = [True]

    def ask(*args: object, **kwargs: object) -> str:
        seen.append(bool(replies._replies))
        return "Rain."

    def stream(*args: object, **kwargs: object) -> Iterator[str]:
        seen.append(bool(replies._replies))
        yield "Rain."

    asked = replies.asking(ask, lambda: local[0])
    streamed = replies.streaming(stream, lambda: local[0])
    assert asked("Hi") == "Rain." and list(streamed("Hi")) == ["Rain."]
    local[0] = False  # a provider answers both at once, elsewhere
    assert asked("Hi") == "Rain." and list(streamed("Hi")) == ["Rain."]
    assert seen == [True, True, False, False] and replies._replies == 0


def test_a_reply_made_without_the_llm_leaves_the_wiki_request_alone(tmp_path: Path) -> None:
    wiki_asking, wiki_may_answer = threading.Event(), threading.Event()
    stops: list[bool] = []

    def llm(messages: list[Message]) -> str:
        if threading.current_thread().name == "wiki":
            if not wiki_asking.is_set():
                wiki_asking.set()
                assert wiki_may_answer.wait(5)
                stop = ask_stop.get()
                stops.append(stop is not None and stop.is_set())
            return '{"topics": []}'
        return "Two moons."

    def lesson(path: Path, progress: Progress) -> Reading:
        return Reading("text", 1, [Piece(1, "paragraph", "Phobos and Deimos circle Mars.")], [])

    app = create_app(
        tmp_path,
        check_photo=lambda p: PhotoResult([], 80),
        prepare_voice=lambda: None,
        prepare_face=lambda photo, progress: None,
        render_clip=lambda photo, text, output: None,
        ask_llm=llm,
        read_pdf=lesson,
    )
    client = TestClient(app)
    client.post("/api/consent", json={"agreed": True})
    client.post("/api/content", files={"file": ("space.pdf", io.BytesIO(PDF))})
    assert wiki_asking.wait(5)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        reply = client.post("/api/chat", json={"prompt": "What can you talk about?"})
    wiki_may_answer.set()
    app.state.wiki.wait()
    assert reply.status_code == 200
    assert stops == [False]  # answered from the topics, so the wiki's request wasn't cut off


def test_a_reply_waits_for_the_requests_cut_off_for_it_to_stop(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R147: llama-server goes on reading a cut-off request's prompt, so the reply waits until
    it has stopped, rather than share the threads with it and lose its conversation's slot."""
    settled: list[str] = []
    replies = RepliesFirst(lambda: settled.append("settled"))
    started = threading.Event()

    calls: list[int] = []

    def ask(*args: object, **kwargs: object) -> str:
        calls.append(1)
        if len(calls) == 1:
            stop = ask_stop.get()
            assert stop is not None
            started.set()
            assert stop.wait(5)
            raise LlmCancelled("Cut off while the LLM was answering.")
        return "topics"

    thread, got = in_wiki_thread(replies, ask)
    assert started.wait(2)
    times = ReplyTimes(received_at=time.perf_counter())
    token = reply_times.current.set(times)
    try:
        with caplog.at_level(logging.INFO), replies.reply():
            assert settled == ["settled"]
    finally:
        reply_times.current.reset(token)
    thread.join(2)
    assert got == ["topics"]
    assert "Reply waited for the requests cut off to stop" in caplog.messages
    # R134c: the wait is a step of the prompt's thinking.
    [step] = times.steps
    assert step["step"] == "waiting for the requests cut off to stop"
    assert step["requests"] == 1 and step["read_ahead"] is False


def test_a_reply_with_nothing_to_cut_off_does_not_wait() -> None:
    settled: list[str] = []
    with RepliesFirst(lambda: settled.append("settled")).reply():
        pass
    assert settled == []


def test_a_settle_that_fails_still_lets_the_wiki_go_on_after_the_reply() -> None:
    """Codex's review on PR #181: the reply's count is taken back even when settling raises."""

    def settle() -> None:
        raise TypeError("an unexpected /slots answer")

    replies = RepliesFirst(settle)
    started = threading.Event()
    calls: list[int] = []

    def ask(*args: object, **kwargs: object) -> str:
        calls.append(1)
        if len(calls) == 1:
            stop = ask_stop.get()
            assert stop is not None
            started.set()
            assert stop.wait(5)
            raise LlmCancelled("Cut off while the LLM was answering.")
        return "topics"

    thread, got = in_wiki_thread(replies, ask)
    assert started.wait(2)
    with pytest.raises(TypeError), replies.reply():
        pass
    thread.join(2)
    assert got == ["topics"]
