import json
import logging
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from imageskin import time_reply, time_setup
from imageskin.cli import main
from imageskin.time_reply import Measured


class FakeApp:
    """The parts of the app's API that setup uses, with Prepare and Start now each taking a
    few polls to finish."""

    def __init__(self, accents: bool = True, set_up: bool = False, start_fails: bool = False):
        self.accents, self.start_fails = accents, start_fails
        self.photos: list[dict[str, Any]] = [{"id": "old"}] if set_up else []
        self.sounds: list[dict[str, Any]] = []
        self.consent = set_up
        self.prepare_polls = 0
        self.prepared = 0
        self.start_polls = 0
        self.person: str | None = None
        self.calls: list[str] = []

    def prepare_status(self) -> dict[str, Any]:
        self.prepare_polls += 1
        if self.prepare_polls < 3:
            return {"state": "running", "steps": []}
        steps = [{"key": "voice", "seconds": 1.5}, {"key": "clips", "seconds": 4.0}]
        return {"state": "done", "steps": steps}

    def start_status(self) -> dict[str, Any]:
        self.start_polls += 1
        if self.start_fails:
            return {"state": "failed", "error": "The download failed.", "chat_ready": False}
        state = ["downloading", "getting-ready", "ready"][min(self.start_polls - 1, 2)]
        chat_ready = self.start_polls >= 4
        return {"state": state, "person": self.person, "chat_ready": chat_ready}

    def answer(self, method: str, path: str, body: bytes) -> tuple[int, Any, dict[str, str]]:
        self.calls.append(f"{method} {path}")
        if path == "/health":
            return 200, {"status": "ok"}, {}
        if path == "/api/consent":
            if method == "POST":
                self.consent = True
            return 200, {"agreed": self.consent}, {}
        if path.startswith("/api/uploads/") and path.count("/") == 3:
            kind = path.rsplit("/", 1)[1]
            items = self.photos if kind == "photos" else self.sounds
            if method == "GET":
                return 200, items, {}
            if b"refuse me" in body:
                return 415, {"detail": "This is not a photo."}, {}
            item = {"id": f"{kind}{len(items)}", "problems": []}
            items.append(item)
            return 200, item, {"Server-Timing": "receive;dur=2.0, faces;dur=300.4, total;dur=310"}
        if path == "/api/uploads/photos/chosen":
            return 200, {"id": json.loads(body)["id"]}, {}
        if path == "/api/prepare":
            if method == "POST":
                self.prepare_polls, self.prepared = 0, self.prepared + 1
            return 200, self.prepare_status(), {}
        if path == "/api/prepare/clips/sample":
            return 200, b"\0" * 2048, {}
        if path == "/api/accent":
            if method == "PUT":
                self.prepare_polls, self.prepared = 0, self.prepared + 1  # prepares again
            return 200, {"accent": "own", "available": self.accents}, {}
        if path == "/api/start-now":
            if method == "POST":
                self.start_polls = 0
                self.person = json.loads(body)["role"]
                return 200, {"state": "downloading"}, {}
            if self.person is None:
                return 200, {"state": "idle", "chosen": None, "chat_ready": False}, {}
            return 200, {**self.start_status(), "chosen": {"name": self.person}}, {}
        if path == "/api/start-now/own-voice":
            return 200, {"own_voice": True}, {}
        return 404, {"detail": "Not Found"}, {}


@pytest.fixture
def app() -> Iterator[tuple[str, FakeApp]]:
    fake = FakeApp()

    class Handler(BaseHTTPRequestHandler):
        def handle_one(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            status, answer, headers = fake.answer(method, self.path, self.rfile.read(length))
            data = answer if isinstance(answer, bytes) else json.dumps(answer).encode()
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            self.handle_one("GET")

        def do_POST(self) -> None:
            self.handle_one("POST")

        def do_PUT(self) -> None:
            self.handle_one("PUT")

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", fake
    server.shutdown()


@pytest.fixture(autouse=True)
def quick() -> Iterator[None]:
    """Polls at once, and the first prompt after Start now answered without an LLM."""
    reply = {"waited_warm_up_ms": 4000, "first_word_heard_ms": 9000, "error": None}
    with (
        patch.object(time_setup, "POLL_S", 0),
        patch.object(time_reply, "measure", return_value=Measured("Hi", False)),
        patch.object(time_reply, "summarize", return_value=reply),
    ):
        yield


def files(tmp_path: Path) -> tuple[list[Path], list[Path]]:
    photo, other, sound = tmp_path / "me.png", tmp_path / "me2.png", tmp_path / "me.wav"
    photo.write_bytes(b"png")
    other.write_bytes(b"png")
    sound.write_bytes(b"wav")
    return [photo, other], [sound] * 3


def test_setup_is_timed_step_by_step(
    app: tuple[str, FakeApp], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    url, fake = app
    photos, recordings = files(tmp_path)
    with caplog.at_level(logging.INFO):
        code = time_setup.run(url, photos, recordings, tmp_path / "out")
    assert code == 0
    results = json.loads(next((tmp_path / "out").glob("setup-*.json")).read_text())
    assert [r["file"] for r in results["photos"]] == ["me.png", "me2.png"]
    assert len(results["recordings"]) == 3
    first = results["photos"][0]
    assert first["steps"] == {"receive": 2, "faces": 300, "total": 310}
    assert first["total_ms"] >= 0 and first["problems"] == []
    whats = [p["what"] for p in results["prepare"]]
    assert whats == [
        "Prepare",
        "Prepare again, another photo",
        "Prepare again, another accent",
        "Prepare, avatar in your own voice",
    ]
    assert fake.prepared == 4
    prepared = results["prepare"][0]
    assert prepared["steps"] == {"voice": 1.5, "clips": 4.0}
    assert [s for s, _ in prepared["states"]] == ["running", "done"]
    assert prepared["sample_plays_ms"] >= prepared["ms"]
    start, switch = results["people"]
    assert [s for s, _ in start["states"]] == ["downloading", "getting-ready", "ready", "chat open"]
    assert start["person"] == "Professor" and switch["person"] == "Boss"
    assert start["reply_warm_up_wait_ms"] == 4000 and start["first_word_heard_ms"] == 9000
    report = next((tmp_path / "out").glob("setup-*.md")).read_text()
    for heading in ("Photos (Larry's timing 8)", "Recordings (Larry's timing 9)", "Start now"):
        assert heading in report
    assert "Prepare again, another accent" in report and "voice (s)" in report
    assert any(r.message == "Setup timed" and r.failed == 0 for r in caplog.records)  # type: ignore[attr-defined]
    assert "PUT /api/start-now/own-voice" in fake.calls


def test_an_app_already_set_up_is_left_alone(
    app: tuple[str, FakeApp], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    url, fake = app
    fake.photos, fake.consent = [{"id": "old"}], True
    assert time_setup.run(url, *files(tmp_path), tmp_path / "out") == 1
    assert "The app is already set up" in caplog.text
    assert not any(c.startswith("POST") for c in fake.calls)
    fake.photos = []
    fake.person = "boss"  # a default person chosen counts too
    assert time_setup.run(url, *files(tmp_path), tmp_path / "out") == 1
    assert time_setup.run(url, *files(tmp_path), tmp_path / "out", anyway=True) == 0


def test_no_accent_change_without_a_voice_that_has_accents(
    app: tuple[str, FakeApp], tmp_path: Path
) -> None:
    url, fake = app
    fake.accents = False
    photos, recordings = files(tmp_path)
    assert time_setup.run(url, photos[:1], recordings, tmp_path / "out") == 0
    results = json.loads(next((tmp_path / "out").glob("setup-*.json")).read_text())
    assert [p["what"] for p in results["prepare"]] == [
        "Prepare",
        "Prepare, avatar in your own voice",
    ]


def test_failures_are_reported_and_fail_the_run(app: tuple[str, FakeApp], tmp_path: Path) -> None:
    url, fake = app
    fake.start_fails = True
    photos, recordings = files(tmp_path)
    recordings[0].write_bytes(b"refuse me")
    assert time_setup.run(url, photos, recordings, tmp_path / "out") == 1
    results = json.loads(next((tmp_path / "out").glob("setup-*.json")).read_text())
    assert results["recordings"][0]["error"].startswith("415")
    assert results["people"][0]["error"] == "The download failed."
    # Without a default person, the avatar can't be prepared in your own voice.
    assert "Prepare, avatar in your own voice" not in [p["what"] for p in results["prepare"]]


def test_a_prepare_that_fails_or_cant_start_is_reported(app: tuple[str, FakeApp]) -> None:
    url, fake = app
    with patch.object(fake, "prepare_status", return_value={"state": "failed", "error": "No."}):
        assert time_setup.prepare(url, "Prepare")["error"] == "No."
    refused = time_setup.prepare(url, "Prepare", lambda: time_reply.ask(url + "/api/nothing"))
    assert refused["error"].startswith("404")
    with patch.object(time_setup, "PREPARE_LIMIT_S", 0.0):
        assert "didn't finish" in time_setup.prepare(url, "Prepare")["error"]


def test_an_app_that_cant_be_reached_is_an_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert time_setup.run("http://127.0.0.1:9", *files(tmp_path), tmp_path / "out") == 1
    assert "Could not reach the app" in caplog.text
    assert time_setup.upload("http://127.0.0.1:9", "photos", files(tmp_path)[0][0])["error"]
    assert time_setup.first_byte_ms("http://127.0.0.1:9/x") is None


def test_the_command_times_setup(app: tuple[str, FakeApp], tmp_path: Path) -> None:
    url, _ = app
    photos, recordings = files(tmp_path)
    with patch.object(time_setup, "run", return_value=0) as run:
        argv = ["time-setup", "--url", url, "--photo", str(photos[0]), "--out", str(tmp_path)]
        assert main(argv) == 0
    assert run.call_args.args == (
        url,
        [photos[0]],
        list(time_setup.DEFAULT_RECORDINGS),
        tmp_path,
        False,
    )
    assert all(p.is_file() for p in [*time_setup.DEFAULT_PHOTOS, *time_setup.DEFAULT_RECORDINGS])
