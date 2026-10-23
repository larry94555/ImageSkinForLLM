import gzip
import json
import logging
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from imageskin import time_reply, time_startup
from imageskin.cli import main
from imageskin.time_reply import Measured

PAGE = b'<script type="module" src="/assets/app.js"></script><link href="/assets/index.css">'
GZIPPED = {"Content-Encoding": "gzip"}
CSS = b"@font-face{src:url(./inter.woff2)}.x{background:url(data:image/png;base64,AA)}"


class FakeApp:
    """The parts of the app's API that time-startup uses: ready after a few asks, with
    llama-server's /health loading for a few more."""

    def __init__(self) -> None:
        self.startup_asks = 0
        self.health_asks = 0
        self.ready_after = 3
        self.loaded_after = 5
        self.chosen: dict[str, Any] | None = {"name": "boss"}
        self.provider = "local"
        self.calls: list[str] = []

    def startup(self) -> dict[str, Any]:
        self.startup_asks += 1
        parts = [
            {"name": "app made", "start_ms": 900.0, "end_ms": 1200.0},
            {"name": "face models", "start_ms": 1000.0, "end_ms": 1500.0},
            {"name": "LLM warm-up", "start_ms": 1100.0, "end_ms": 1300.0, "error": None},
        ]
        if self.startup_asks >= self.ready_after:
            parts.append({"name": "ready", "start_ms": 2000.0, "end_ms": 2000.0})
        return {"started_wall": time.time() - 2.5, "now_ms": 2500.0, "parts": parts}

    def answer(self, method: str, path: str, gzipped: bool) -> tuple[int, Any, dict[str, str]]:
        self.calls.append(f"{method} {path}")
        if path == "/api/startup":
            return 200, self.startup(), {}
        if path == "/health":  # llama-server's, as llm_url is this address plus /v1
            self.health_asks += 1
            if self.health_asks < self.loaded_after:
                return 503, {"error": "Loading model"}, {}
            return 200, {"status": "ok"}, {}
        if path == "/":
            return 200, PAGE, {"Content-Type": "text/html"}
        if path == "/assets/app.js":
            return 200, b"console.log(1)", {"Content-Type": "application/javascript"}
        if path == "/assets/index.css":
            if gzipped:
                return 200, gzip.compress(CSS), {"Content-Type": "text/css", **GZIPPED}
            return 200, CSS, {"Content-Type": "text/css"}
        if path == "/assets/inter.woff2":
            return 200, b"\0" * 300, {"Content-Type": "font/woff2"}
        if path == "/api/start-now/faces":
            return 200, [{"name": "boss"}, {"name": "parent"}], {}
        if path.startswith("/faces/"):
            return 200, b"\xff" * 100, {"Content-Type": "image/jpeg"}
        if path == "/api/start-now":
            return 200, {"chosen": self.chosen}, {}
        if path == "/api/prepare":
            return 200, {"state": "done"}, {}
        if path in ("/api/start-now/lines/welcome-back", "/api/prepare/clips/welcome-back"):
            return 200, b"\0" * 2048, {"Content-Type": "video/mp4"}
        if path == "/api/llm":
            return 200, {"provider": self.provider}, {}
        if path in time_startup.CHAT_OPENING:
            return 200, {}, {}
        return 404, {"detail": "Not Found"}, {}


@pytest.fixture
def app() -> Iterator[tuple[str, FakeApp]]:
    fake = FakeApp()

    class Handler(BaseHTTPRequestHandler):
        def handle_one(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            gzipped = "gzip" in (self.headers.get("Accept-Encoding") or "")
            status, answer, headers = fake.answer(method, self.path, gzipped)
            data = answer if isinstance(answer, bytes) else json.dumps(answer).encode()
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            if "Content-Type" not in headers:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            self.handle_one("GET")

        def do_PUT(self) -> None:
            self.handle_one("PUT")

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", fake
    server.shutdown()


REPLY = {
    "prompt": "Hi",
    "spoken": False,
    "error": None,
    "waited_warm_up_ms": 0,
    "waited_turn_ms": 0,
    "history_tokens": 10,
    "prompt_sent_ms": 5,
    "first_token_ms": 600,
    "first_sentence_ms": 900,
    "last_token_ms": 2000,
    "llm": {},
    "first_sentence_to_heard_ms": 1500,
    "first_word_heard_ms": 2400,
    "stop_answered_ms": None,
    "clips": [],
}


@pytest.fixture(autouse=True)
def quick() -> Iterator[None]:
    """Asks at once, and prompts answered without an LLM."""
    with (
        patch.object(time_startup, "POLL_S", 0.01),
        patch.object(time_reply, "measure", return_value=Measured("Hi", False)),
        patch.object(time_reply, "summarize", return_value=REPLY),
    ):
        yield


def test_the_start_is_timed(
    app: tuple[str, FakeApp], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    url, fake = app
    with caplog.at_level(logging.INFO):
        code = time_startup.run(url, url + "/v1", tmp_path / "out")
    assert code == 0
    results = json.loads(next((tmp_path / "out").glob("startup-*.json")).read_text())
    assert [p["name"] for p in results["startup"]["parts"]][-1] == "ready"
    llm = results["llm"]
    assert llm["already_loaded"] is False and llm["loaded_ms"] >= llm["began_ms"] - 1
    assert fake.health_asks == fake.loaded_after  # waited for the model to load
    assert len(results["prompts"]) == 2
    load = results["first_load"]
    assert load["page"]["files"] == 1 and load["scripts and styles"]["files"] == 2
    assert [r["url"] for r in load["fonts"]["rows"]] == [url + "/assets/inter.woff2"]
    assert load["face pictures"]["files"] == 2 and load["face pictures"]["bytes"] == 200
    styles = next(r for r in load["scripts and styles"]["rows"] if r["url"].endswith(".css"))
    assert styles["bytes"] == len(gzip.compress(CSS))  # on the wire, compressed
    assert "text" not in styles
    opening = results["chat_opening"]
    assert opening["opening"]["files"] == len(time_startup.CHAT_OPENING)
    assert opening["welcome_back"]["url"].endswith("/api/start-now/lines/welcome-back")
    assert results["llm_change"]["saved_ms"] >= 0
    assert "PUT /api/llm" in fake.calls
    report = next((tmp_path / "out").glob("startup-*.md")).read_text()
    for heading in (
        "Start-up (Larry's timings 7 and 10)",
        "The first prompt and the next",
        "The browser's first load",
        "Opening the chat after a restart",
        "Changing the LLM in Settings",
    ):
        assert heading in report
    assert "llama-server answering /health" in report and "| face models | 1000.0 |" in report
    # The fake's LLM warm-up ends 1.3 s after the start, before llama-server is seen loaded.
    assert "The LLM's warm-up ended before llama-server had loaded its model" in report
    assert any(r.message == "Start timed" and r.failed == 0 for r in caplog.records)  # type: ignore[attr-defined]


def test_an_llm_loaded_before_the_timing_began_is_shown_as_before(
    app: tuple[str, FakeApp], tmp_path: Path
) -> None:
    url, fake = app
    fake.loaded_after = 0
    fake.chosen = None  # the person's own: Welcome back is Prepare's
    fake.provider = "claude"
    assert time_startup.run(url, url, tmp_path) == 1  # the LLM change isn't timed
    results = json.loads(next(tmp_path.glob("startup-*.json")).read_text())
    assert results["llm"]["already_loaded"] is True
    welcome = results["chat_opening"]["welcome_back"]
    assert welcome["url"].endswith("/api/prepare/clips/welcome-back")
    assert "not llama.cpp" in results["llm_change"]["error"]
    report = next(tmp_path.glob("startup-*.md")).read_text()
    assert "| before " in report and "not llama.cpp" in report
    assert "warm-up ended before" not in report  # loaded already: nothing to say


def test_an_app_that_never_gets_ready_is_an_error(
    app: tuple[str, FakeApp], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    url, fake = app
    fake.ready_after = 10**6
    with patch.object(time_startup, "READY_LIMIT_S", 0.2):
        assert time_startup.run(url, url, tmp_path) == 1
    assert "Could not time the start" in caplog.text
    assert not list(tmp_path.glob("startup-*"))


def test_an_app_not_listening_yet_is_waited_for(tmp_path: Path) -> None:
    with pytest.raises(time_reply.TimingError):
        time_startup.wait_until_ready("http://127.0.0.1:9", limit_s=0.05)


def test_a_fetch_that_fails_is_reported(app: tuple[str, FakeApp]) -> None:
    url, _ = app
    refused = time_startup.fetch(url + "/nothing")
    assert refused["status"] == 404 and refused["error"] == "refused (404)"
    unreachable = time_startup.fetch("http://127.0.0.1:9/")
    assert unreachable["status"] is None and unreachable["error"]


def test_no_welcome_back_before_anything_is_prepared(app: tuple[str, FakeApp]) -> None:
    url, fake = app
    fake.chosen = None
    with patch.object(fake, "answer", side_effect=lambda m, p, g: (200, {"state": "idle"}, {})):
        assert time_startup.welcome_back_path(url) is None
    assert time_startup.welcome_back_path("http://127.0.0.1:9") is None


def test_the_llm_change_reports_what_went_wrong(app: tuple[str, FakeApp]) -> None:
    assert "Could not read" in time_startup.change_llm("http://127.0.0.1:9")["error"]
    url, fake = app
    real = fake.answer

    def refuse_put(method: str, path: str, gzipped: bool) -> tuple[int, Any, dict[str, str]]:
        if method == "PUT":
            return 400, {"detail": "no"}, {}
        return real(method, path, gzipped)

    with patch.object(fake, "answer", side_effect=refuse_put):
        assert "wasn't saved" in time_startup.change_llm(url)["error"]


def test_llama_servers_health_is_beside_its_v1() -> None:
    assert time_startup.llm_health_url("http://llama:8080/v1/") == "http://llama:8080/health"
    assert time_startup.llm_health_url("http://llama:8080") == "http://llama:8080/health"


def test_the_command_times_the_start(app: tuple[str, FakeApp], tmp_path: Path) -> None:
    url, _ = app
    out = tmp_path / "speed"
    assert main(["time-startup", "--url", url, "--llm-url", url + "/v1", "--out", str(out)]) == 0
    assert list(out.glob("startup-*.md"))


def test_a_watch_that_fails_oddly_keeps_watching(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hosted run of PR #150 had no time for llama-server: the watch had ended."""
    import http.client

    answers: list[Exception | None] = [http.client.BadStatusLine("x"), None]

    class Ok:
        status = 200

        def __enter__(self) -> "Ok":
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def urlopen(*_: object, **__: object) -> Ok:
        failure = answers.pop(0)
        if failure:
            raise failure
        return Ok()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    seen: dict[str, Any] = {}
    time_startup.watch_llm("http://llama/health", seen, threading.Event())
    assert "wall" in seen and seen["already"] is False
    assert seen["error"].startswith("BadStatusLine")


def test_an_llm_never_seen_is_reported(tmp_path: Path) -> None:
    results = {
        "startup": {"started_wall": 0, "now_ms": 1, "parts": []},
        "llm": {"loaded_ms": None, "already_loaded": False, "began_ms": 5, "error": "refused"},
        "prompts": [],
        "first_load": {},
        "chat_opening": {"opening": {"rows": [], "ms": 1}, "welcome_back": None},
        "llm_change": {"error": "Not timed"},
    }
    report = time_startup.markdown(results)
    assert "| llama-server answering /health | - | not seen | - | refused |" in report
