import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import uvicorn
from test_reply_video import tone_clip, video_app

from imageskin import time_reply
from imageskin.cli import main
from imageskin.review import Review
from imageskin.time_reply import ClipSeen, Measured, clip_seconds, markdown, summarize


@pytest.fixture(autouse=True)
def stop_patches() -> Iterator[None]:
    yield
    patch.stopall()


# --- Playing the reply back on paper ---


def clip(n: int, sentence: float, started: float, ready: float, whole: float) -> dict[str, Any]:
    return {
        "url": f"/api/chat/clips/abc/{n}",
        "sentence_at": sentence,
        "started_at": started,
        "ready_at": ready,
        "whole_at": whole,
    }


def measured() -> Measured:
    """A reply sent at 10.0 on the client's clock, which is 100 s behind the server's."""
    m = Measured("Hi", spoken=False, sent_at=10.0, answered_at=14.0, status=200, offset=100.0)
    m.reply = {
        "streamed": True,
        "timings": {
            "received_at": 110.01,
            "waited_warm_up_ms": 0.0,
            "waited_turn_ms": 5.0,
            "history_tokens": 120,
            "prompt_sent_at": 110.02,
            "first_token_at": 110.5,
            "first_sentence_at": 111.0,
            "last_token_at": 113.0,
            "answered_at": 113.9,
            "llm": {"prompt_n": 40, "cache_n": 300, "prompt_per_second": 51.234},
        },
    }
    first = ClipSeen(1, clip(1, 111.0, 111.0, 112.0, 113.5), seen_at=12.05)
    first.first_byte_at, first.downloaded_at, first.seconds = 12.1, 13.6, 2.0
    # The second clip arrives after the first has ended at 114.1, so a gap is heard.
    second = ClipSeen(2, clip(2, 112.0, 113.5, 114.4, 115.0), seen_at=14.45)
    second.first_byte_at, second.downloaded_at, second.seconds = 14.5, 15.1, 1.5
    # The third arrives in time: no gap.
    third = ClipSeen(3, clip(3, 113.0, 115.0, 115.2, 115.6), seen_at=15.25)
    third.first_byte_at, third.downloaded_at, third.seconds = 15.3, 15.7, 1.0
    m.clips = [first, second, third]
    return m


def test_the_reply_is_played_back_on_paper() -> None:
    r = summarize(measured())
    assert r["reached_server_ms"] == 10 and r["waited_turn_ms"] == 5.0
    assert (r["first_token_ms"], r["first_sentence_ms"], r["last_token_ms"]) == (500, 1000, 3000)
    assert r["answered_ms"] == 4000 and r["history_tokens"] == 120
    # Larry's timing 2: clip 1's first bytes came at 2.1 s, 1.1 s after the first sentence.
    assert r["first_word_heard_ms"] == 2100 and r["first_sentence_to_heard_ms"] == 1100
    one, two, three = r["clips"]
    assert (one["waited_ms"], one["voice_ms"], one["video_ms"]) == (0, 1000, 1500)
    assert one["gap_ms"] is None and one["plays_ms"] == 2100 and one["seen_ms"] == 2050
    assert two["waited_ms"] == 1500  # behind clip 1's video
    # Larry's timing 3: clip 1 ends at 4.1 s; clip 2 arrives at 4.5 s, late by 0.4 s.
    assert two["plays_ms"] == 4500 and two["gap_ms"] == 400 and two["late"] is True
    # Clip 3 arrived (5.3 s) before clip 2 ended (6.0 s): it plays right after, with no gap.
    assert three["plays_ms"] == 6000 and three["gap_ms"] == 0 and three["late"] is False
    assert r["stop_answered_ms"] is None


def test_the_tables_name_every_timing() -> None:
    m = measured()
    stopped = Measured("Stop me", spoken=True, sent_at=0.0, status=409, error="Couldn't")
    stopped.stopped_at, stopped.stop_answered_at, stopped.answered_at = 1.0, 1.02, 1.5
    report = markdown([summarize(m), summarize(stopped)], "Local LLM")
    assert report.startswith("# Where the time goes: a reply (Local LLM)")
    assert "| 1 | typed | 0.0 | 5.0 | 120 | 40 | 300 | 51.2 | 500 | 1000 | 3000 |" in report
    assert "| 2 | spoken |" in report
    clip_two = "| 2 | 2000 | 1500 | 900 | 600 | 4400 | 4450 | 4500 | 5100 | 1.5 | 4500 | 400 | yes"
    assert clip_two in report
    assert "Stop answered in 20 ms; the next prompt could be taken 500 ms after Stop." in report
    assert "Error: Couldn't" in report


def test_a_reply_without_clips_is_timed_from_its_arrival() -> None:
    m = Measured("Hi", spoken=False, sent_at=5.0, answered_at=6.0, status=200)
    m.reply = {"timings": {"received_at": 50.0, "answered_at": 50.9}}
    r = summarize(m)
    assert r["reached_server_ms"] == 0 and r["clips"] == []
    assert r["first_word_heard_ms"] is None and r["llm"] == {}


def test_a_clips_length_is_read_with_ffprobe(tmp_path: Path) -> None:
    video = tmp_path / "1.mp4"
    tone_clip(0.5, video)
    seconds = clip_seconds(video)
    assert seconds is not None and 0.4 < seconds < 0.7
    (tmp_path / "bad.mp4").write_bytes(b"not a video")
    assert clip_seconds(tmp_path / "bad.mp4") is None
    with patch("imageskin.time_reply.shutil.which", return_value=None):
        assert clip_seconds(video) is None


# --- Against the running app ---


class Running:
    """The app on a real port, so the command reaches it over HTTP as it would on a server."""

    def __init__(self, app: Any) -> None:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, args=([sock],), daemon=True)
        self.thread.start()
        while not self.server.started:
            time.sleep(0.01)

    def close(self) -> None:
        self.server.should_exit = True
        self.thread.join(10)


def running_app(tmp_path: Path, render: Any, stream: Any) -> Running:
    client = video_app(tmp_path, render, stream)
    patch("imageskin.app.load_review", return_value=Review(accepted=True)).start()
    return Running(client.app)


def test_the_command_times_replies_against_the_running_app(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def render(photo: Path, text: str, output: Path) -> None:
        tone_clip(0.5, output)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield from ["Hello there. ", "How are ", "you today?"]

    app = running_app(tmp_path / "home", render, stream)
    out = tmp_path / "speed"
    try:
        code = main(["time-reply", "--url", app.url, "--out", str(out), "Hi", "Again"])
    finally:
        app.close()
    assert code == 0
    [written] = list(out.glob("reply-*.json"))
    saved = json.loads(written.read_text())
    assert saved["llm"].startswith("Local")
    first, second = saved["results"]
    assert first["status"] == 200 and first["error"] is None and first["streamed"] is True
    assert [c["clip"] for c in first["clips"]] == [1, 2]
    for c in first["clips"]:
        assert c["seconds"] is not None and 0.4 < c["seconds"] < 0.7
        assert c["sentence_ms"] <= c["listed_ms"] <= c["plays_ms"]
        assert c["error"] is None
    assert first["first_sentence_ms"] <= first["first_word_heard_ms"]
    assert first["clips"][1]["gap_ms"] is not None
    assert second["history_tokens"] > 0
    printed = capsys.readouterr()
    assert "# Where the time goes: a reply" in printed.out and str(out) in printed.out
    assert written.with_suffix(".md").exists()
    logged = printed.out + printed.err  # the command's own JSON log lines
    assert '"Timing a reply"' in logged and '"Replies timed"' in logged


def test_stop_is_timed_at_the_first_clip(tmp_path: Path) -> None:
    go = threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        tone_clip(0.3, output)
        go.wait(5)  # the reply is still being made when Stop is pressed

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield from ["One. ", "Two. ", "Three."]

    app = running_app(tmp_path / "home", render, stream)
    try:
        code = time_reply.run(app.url, ["Count"], tmp_path / "speed", spoken=None, stop=True)
    finally:
        go.set()
        app.close()
    assert code == 0
    [written] = list((tmp_path / "speed").glob("reply-*.json"))
    counted, stopped = json.loads(written.read_text())["results"]
    assert counted["error"] is None and len(counted["clips"]) == 3
    assert stopped["error"] is None and stopped["stop_answered_ms"] is not None
    assert stopped["next_prompt_taken_after_stop_ms"] is not None


def test_a_spoken_prompt_is_sent_as_one(tmp_path: Path) -> None:
    sent: list[dict[str, Any]] = []
    real_ask = time_reply.ask

    def ask(url: str, body: dict[str, Any] | None = None, timeout: float = 30) -> Any:
        if body is not None and url.endswith("/api/chat"):
            sent.append(body)
        return real_ask(url, body, timeout)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield "Fine."

    app = running_app(tmp_path / "home", lambda p, t, o: tone_clip(0.3, o), stream)
    try:
        with patch("imageskin.time_reply.ask", ask):
            time_reply.run(app.url, ["One", "Two"], tmp_path / "speed", spoken=2)
    finally:
        app.close()
    assert [b["spoken"] for b in sent] == [False, True]


def test_an_app_that_cant_be_reached_is_an_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"  # nothing listens there
    sock.close()
    assert time_reply.run(url, ["Hi"], tmp_path / "speed") == 1
    assert "Could not reach the app" in caplog.messages
    assert not (tmp_path / "speed").exists()


def test_a_refused_prompt_is_reported(tmp_path: Path) -> None:
    app = running_app(tmp_path / "home", lambda p, t, o: None, None)
    patch("imageskin.app.load_review", return_value=Review(accepted=False)).start()
    try:
        assert time_reply.run(app.url, ["Hi"], tmp_path / "speed") == 1
    finally:
        app.close()
    [written] = list((tmp_path / "speed").glob("reply-*.json"))
    [result] = json.loads(written.read_text())["results"]
    assert result["status"] == 403 and "locked" in result["error"].lower()
