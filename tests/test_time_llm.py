import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pdf_samples import text_pdf

from imageskin import time_llm
from imageskin.cli import main
from imageskin.json_grammar import compact_grammar
from imageskin.time_llm import LlmTimingError, markdown, wiki_estimate_s
from imageskin.wiki import TOPICS_SCHEMA, Part

TOPICS = {"topics": [{"title": "Prime numbers", "pages": [1], "text": "Primes have two."}]}
TIMINGS = {
    "prompt_n": 40,
    "cache_n": 95,
    "prompt_per_second": 51.234,
    "predicted_n": 20,
    "predicted_per_second": 4.56,
}


class FakeLlama(BaseHTTPRequestHandler):
    """llama-server's endpoints the timing uses, answering at once."""

    asked: list[dict[str, Any]] = []
    loading = 0  # /health answers 503 this many times first

    def log_message(self, *args: object) -> None:
        pass

    def send(self, status: int, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            if FakeLlama.loading:
                FakeLlama.loading -= 1
                self.send(503, {"error": "Loading model"})
            else:
                self.send(200, {"status": "ok"})
        elif self.path == "/props":
            self.send(
                200,
                {
                    "model_path": "/models/gemma-3-4b-it-Q4_K_M.gguf",
                    "default_generation_settings": {"n_ctx": 4096},
                    "total_slots": 4,
                    "build_info": "b1-abc",
                },
            )
        else:
            self.send(404, {})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/tokenize":
            self.send(200, {"tokens": body["content"].split()})
            return
        FakeLlama.asked.append(body)
        if not body.get("stream"):
            content = json.dumps(TOPICS) if "grammar" in body else "Hi"
            self.send(200, {"choices": [{"message": {"content": content}}], "timings": TIMINGS})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for i, piece in enumerate(["Hello there, ", "I am here. ", "Ask me anything."]):
            event: dict[str, Any] = {"choices": [{"delta": {"content": piece}}]}
            if i == 2:
                event["timings"] = TIMINGS
            self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


@pytest.fixture
def llama() -> Iterator[str]:
    FakeLlama.asked = []
    FakeLlama.loading = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeLlama)
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    ).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_a_setting_is_timed_as_the_app_asks_and_added_to_the_table(
    llama: str, tmp_path: Path
) -> None:
    pdf = text_pdf(tmp_path / "a.pdf")
    FakeLlama.loading = 2
    with patch.object(time_llm, "READY_POLL_S", 0.01):
        assert time_llm.run(llama + "/v1", "now", pdf, tmp_path / "speed", ["Hi", "And?"]) == 0
    rows = json.loads((tmp_path / "speed" / "llm-settings.json").read_text())
    assert len(rows) == 1
    row = rows[0]
    assert row["label"] == "now"
    assert row["server"] == {"model": "gemma-3-4b-it-Q4_K_M.gguf", "n_ctx": 4096, "slots": 4,
                             "build": "b1-abc"}  # fmt: skip
    assert len(row["replies"]) == 2
    reply = row["replies"][0]
    assert reply["text"] == "Hello there, I am here. Ask me anything."
    assert reply["first_token_ms"] <= reply["first_sentence_ms"] <= reply["last_token_ms"]
    assert reply["llm"]["cache_n"] == 95
    assert reply["llm"]["prompt_per_second"] == 51.2
    assert row["wiki"]["topics"] == ["Prime numbers"]
    # The warm-up first, as the app does, then the conversation with each reply kept in it.
    warm, first, second, wiki = FakeLlama.asked
    assert warm["max_tokens"] == 1
    assert [m["role"] for m in second["messages"]] == ["system", "user", "assistant", "user"]
    assert second["messages"][2]["content"] == reply["text"]
    assert first["stream"] is True
    # The wiki part is asked for as the app asks for it, with the same compact grammar (R98).
    assert wiki["grammar"] == compact_grammar(TOPICS_SCHEMA) and "response_format" not in wiki
    assert wiki["messages"][1]["content"].startswith("[page 1]")
    report = (tmp_path / "speed" / "llm-settings.md").read_text()
    assert "| now | gemma-3-4b-it-Q4_K_M.gguf | 4 | 95 |" in report
    assert "- **now:** Prime numbers" in report


def test_a_setting_timed_again_replaces_its_row(llama: str, tmp_path: Path) -> None:
    pdf = text_pdf(tmp_path / "a.pdf")
    out = tmp_path / "speed"
    for label in ("now", "3 threads", "now"):
        assert time_llm.run(llama, label, pdf, out, ["Hi"]) == 0
    rows = json.loads((out / "llm-settings.json").read_text())
    assert [r["label"] for r in rows] == ["3 threads", "now"]


def test_a_server_that_never_gets_ready_fails_the_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pdf = text_pdf(tmp_path / "a.pdf")
    with (
        patch.object(time_llm, "READY_LIMIT_S", 0.05),
        patch.object(time_llm, "READY_POLL_S", 0.01),
    ):
        assert time_llm.run("http://127.0.0.1:9", "now", pdf, tmp_path) == 1
    assert "Could not time llama-server" in caplog.text
    assert not (tmp_path / "llm-settings.json").exists()


def test_a_wiki_answer_without_a_reply_is_an_error() -> None:
    class Answer:
        def __enter__(self) -> "Answer":
            return self

        def __exit__(self, *exc: object) -> None:
            pass

        def read(self) -> bytes:
            return b'{"choices": []}'

    with patch.object(time_llm, "post", return_value=Answer()), pytest.raises(LlmTimingError):
        time_llm.time_wiki_part("http://x", Part("[page 1] A", [1]))


def test_a_pdf_without_text_is_an_error(llama: str) -> None:
    with (
        patch.object(time_llm, "read_pdf") as read,
        pytest.raises(LlmTimingError, match="No text"),
    ):
        read.return_value.pieces = []
        time_llm.first_part(Path("empty.pdf"), llama)


def test_the_sample_pdfs_wiki_is_estimated_from_the_speeds() -> None:
    wiki = {"llm": {"prompt_per_second": 48.0, "predicted_per_second": 4.0}}
    assert wiki_estimate_s(wiki) == round(24064 / 48 + 12521 / 4)
    assert wiki_estimate_s({"llm": {"prompt_per_second": None, "predicted_per_second": 4}}) is None


def test_the_table_shows_missing_numbers_as_dashes() -> None:
    row: dict[str, Any] = {
        "label": "odd",
        "server": {"model": "m.gguf", "slots": None},
        "replies": [],
        "wiki": {"llm": time_llm.llm_timings({}), "took_ms": 5.0, "topics": []},
        "wiki_estimate_s": None,
    }
    report = markdown([row])
    assert "| odd | m.gguf | - | - |" in report
    assert "- **odd:** none" in report


def test_a_missing_table_starts_empty_and_an_unreadable_one_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("{")
    (tmp_path / "obj.json").write_text("{}")
    assert time_llm.saved_rows(tmp_path / "missing.json") == []
    with pytest.raises(LlmTimingError, match="Could not read"):
        time_llm.saved_rows(tmp_path / "bad.json")
    with pytest.raises(LlmTimingError, match="list of rows"):
        time_llm.saved_rows(tmp_path / "obj.json")


def test_an_unreadable_table_is_kept_and_nothing_is_measured(llama: str, tmp_path: Path) -> None:
    pdf = text_pdf(tmp_path / "a.pdf")
    (tmp_path / "llm-settings.json").write_text('[{"label": "before"')
    assert time_llm.run(llama, "now", pdf, tmp_path, ["Hi"]) == 1
    assert (tmp_path / "llm-settings.json").read_text() == '[{"label": "before"'
    assert FakeLlama.asked == []
    assert not list(tmp_path.glob("*.part"))


def test_a_stream_cut_off_before_it_is_done_is_an_error() -> None:
    cut = [b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n', b"\n"]
    with pytest.raises(LlmTimingError, match="ended before"):
        list(time_llm.events(iter(cut)))


def test_the_command_times_the_server_named(tmp_path: Path) -> None:
    pdf = text_pdf(tmp_path / "a.pdf")
    with patch.object(time_llm, "run", return_value=0) as run:
        args = ["time-llm", "3 threads", "--llm-url", "http://l:8081", "--pdf", str(pdf)]
        assert main([*args, "--out", str(tmp_path)]) == 0
    run.assert_called_once_with("http://l:8081", "3 threads", pdf, tmp_path)


def test_the_command_refuses_a_missing_pdf(tmp_path: Path) -> None:
    assert main(["time-llm", "now", "--pdf", str(tmp_path / "none.pdf")]) == 1
