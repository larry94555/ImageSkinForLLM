import json
import logging
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pdf_samples import text_pdf
from test_reply_video import tone_clip, video_app
from test_time_reply import Running

from imageskin import time_pdf, time_reply
from imageskin.chat import Message
from imageskin.cli import main
from imageskin.review import Review
from imageskin.time_reply import TimingError


def pdfs_left(url: str) -> Any:
    """The PDFs the app still has."""
    return time_reply.ask(url + "/api/content")


@pytest.fixture(autouse=True)
def stop_patches() -> Iterator[None]:
    yield
    patch.stopall()


# --- The tables ---


def step(
    stage: str, n: int, took: float, ended: float, *requests: dict[str, Any]
) -> dict[str, Any]:
    return {
        "stage": stage,
        "step": n,
        "duration_ms": took,
        "ended_ms": ended,
        "requests": list(requests),
    }


STEPS = [
    step(
        "topics",
        1,
        9000.4,
        9000.4,
        {"prompt_n": 2000, "cache_n": 100, "prompt_ms": 50_000.0},
        {"prompt_n": 2000, "cache_n": 2000, "prompt_ms": 50_000.0, "predicted_n": 100},
    ),
    step("topics", 2, 4000.0, 13000.4, {"predicted_n": 50, "predicted_ms": 10_000.0}),
    step("outline", 1, 2000.0, 15000.4, {}),
]


def test_each_step_sums_its_requests_timings() -> None:
    first, second, outline = time_pdf.step_rows(STEPS)
    # Asked twice: the tokens add up, and the speed is over both requests' time.
    assert first == ["Topics", 1, 9000, 9000, 2, 4000, 2100, 40.0, 100, None]
    assert second == ["Topics", 2, 4000, 13000, 1, 0, 0, None, 50, 5.0]
    assert outline == ["Outline", 1, 2000, 15000, 1, 0, 0, None, 0, None]
    totals = time_pdf.stage_totals(STEPS)
    assert totals["topics"] == {
        "steps": 2,
        "ms": 13000.4,
        "prompt_n": 4000,
        "cache_n": 2100,
        "predicted_n": 150,
    }
    assert totals["outline"]["steps"] == 1


def pdf_result(**kw: Any) -> dict[str, Any]:
    return {
        "pdf_id": "abc",
        "name": "sample.pdf",
        "bytes": 1000,
        "upload_ms": 40,
        "read_ms": 1200,
        "pages": 19,
        "kind": "text",
        "counts": {"paragraph": 80, "slide": 0, "table": 1},
        "wiki_ms": 15100,
        "total_ms": 16340,
        "wiki_built_s": 15.0,
        "parts": 2,
        "wiki_pages": 7,
        "topic": "Primes",
        "steps": STEPS,
        "asked_during_build": None,
        **kw,
    }


def test_the_report_has_the_pdf_its_steps_and_the_answers() -> None:
    report = time_pdf.markdown(
        {"pdf": pdf_result(), "answers": [], "replaced": pdf_result(steps=[])}, "Local LLM"
    )
    assert report.startswith("# Where the time goes: the wiki and answers from it (Local LLM)")
    assert "19 pages read as text (80 paragraphs, 1 tables); 2 wiki parts, 7 wiki topics" in report
    assert "| 40 | 1200 | 15100 | 16340 | 15000 |" in report
    assert "| Topics | 2 | 13000 | 4000 | 2100 | 150 |" in report
    assert "| Topics | 1 | 9000 | 9000 | 2 | 4000 | 2100 | 40.0 | 100 | - |" in report
    assert "## The PDF replaced by itself: sample.pdf" in report
    assert "## Asked while the wiki was built" not in report


def test_the_longer_requests_take_the_first_topic() -> None:
    assert time_pdf.longer_requests("Rain") == [
        "What can you talk about?",
        "Teach me about Rain",
        "Quiz me on Rain",
        "Assess me",
    ]
    assert time_pdf.longer_requests(None) == ["What can you talk about?", "Assess me"]


# --- Against the running app ---


def wiki_or_reply(messages: list[Message]) -> str:
    """The wiki's topics when asked for them, a plain answer otherwise."""
    if "topics" in messages[0]["content"]:
        return json.dumps({"topics": [{"title": "Lens care", "pages": [1], "text": "Clean it."}]})
    return "Clean the lens with a soft cloth."


def running_app(tmp_path: Path) -> Running:
    def stream(messages: list[Message]) -> Iterator[str]:
        yield from ["Use a soft cloth. ", "Never use water."]

    client = video_app(tmp_path, lambda p, t, o: tone_clip(0.3, o), stream, ask_llm=wiki_or_reply)
    patch("imageskin.app.load_review", return_value=Review(accepted=True)).start()
    return Running(client.app)


def test_the_command_times_a_pdf_and_answers_from_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    app = running_app(tmp_path / "home")
    pdf = text_pdf(tmp_path / "guide.pdf")
    out = tmp_path / "speed"
    try:
        code = main(
            ["time-pdf", str(pdf), "How do I clean the lens?", "--url", app.url]
            + ["--out", str(out), "--spoken", "1", "--replace"]
        )
        left = pdfs_left(app.url)
    finally:
        app.close()
    assert code == 0
    assert left == []  # removed again, without --keep
    [written] = list(out.glob("pdf-*.json"))
    saved = json.loads(written.read_text())
    p = saved["pdf"]
    assert (p["pages"], p["kind"], p["parts"], p["topic"]) == (2, "text", 1, "Lens care")
    assert p["read_ms"] >= 0 and p["wiki_ms"] >= 0 and p["total_ms"] >= p["upload_ms"]
    assert [(s["stage"], s["step"]) for s in p["steps"]] == [("topics", 1)]
    during = p["asked_during_build"]
    assert during["prompt"] == "How do I clean the lens?" and during["error"] is None
    prompts = [a["prompt"] for a in saved["answers"]]
    assert prompts == ["How do I clean the lens?", *time_pdf.longer_requests("Lens care")]
    question = saved["answers"][0]
    assert question["spoken"] is True and question["looked_up_ms"] is not None
    assert question["asked_tokens"] > 0 and question["first_word_heard_ms"] is not None
    assert saved["replaced"]["pdf_id"] == p["pdf_id"]
    printed = capsys.readouterr()
    assert "## Answers from the wiki" in printed.out and str(out) in printed.out
    assert written.with_suffix(".md").exists()
    assert '"Timing a PDF"' in printed.err + printed.out
    assert '"PDF timed"' in printed.err + printed.out


def test_keep_leaves_the_pdf(tmp_path: Path) -> None:
    app = running_app(tmp_path / "home")
    try:
        code = time_pdf.run(
            app.url, text_pdf(tmp_path / "guide.pdf"), [], tmp_path / "speed", keep=True
        )
        left = pdfs_left(app.url)
    finally:
        app.close()
    assert code == 0 and [p["name"] for p in left] == ["guide.pdf"]


def test_a_pdf_that_cant_be_read_fails_the_run_and_is_removed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    app = running_app(tmp_path / "home")
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7\nnot really\n%%EOF\n")
    try:
        code = time_pdf.run(app.url, broken, ["Hi"], tmp_path / "speed")
        left = pdfs_left(app.url)
    finally:
        app.close()
    assert code == 1 and left == []
    assert "Could not time the PDF" in caplog.messages
    assert not (tmp_path / "speed").exists()


def test_a_failure_after_the_wiki_still_writes_the_report(tmp_path: Path) -> None:
    with (
        patch("imageskin.time_pdf.ask", return_value={}),
        patch("imageskin.time_pdf.time_reply.llm_name", return_value="Local"),
        patch("imageskin.time_pdf.process", return_value=pdf_result()),
        patch("imageskin.time_pdf.time_reply.measure", side_effect=TimingError("gone")),
        patch("imageskin.time_pdf.remove") as remove,
    ):
        assert time_pdf.run("http://app", Path("x.pdf"), ["Q"], tmp_path / "speed") == 1
    [written] = list((tmp_path / "speed").glob("pdf-*.json"))
    assert json.loads(written.read_text())["error"] == "gone"
    remove.assert_not_called()  # process was replaced, so nothing was added


def test_a_question_that_failed_during_the_build_fails_the_run(tmp_path: Path) -> None:
    failed = {"prompt": "Q", "error": "No clips came."}
    with (
        patch("imageskin.time_pdf.ask", return_value={}),
        patch("imageskin.time_pdf.time_reply.llm_name", return_value="Local"),
        patch("imageskin.time_pdf.process", return_value=pdf_result(asked_during_build=failed)),
        patch("imageskin.time_pdf.time_reply.measure"),
        patch("imageskin.time_pdf.time_reply.summarize", return_value={"error": None}),
        patch("imageskin.time_pdf.markdown", return_value=""),
    ):
        assert time_pdf.run("http://app", Path("x.pdf"), ["Q"], tmp_path / "speed") == 1


def test_a_wiki_that_fails_is_an_error(tmp_path: Path) -> None:
    statuses = iter(
        [
            {"abc": {"state": "done", "pages": 1, "kind": "text", "counts": {}}},
            {"abc": {"state": "failed", "error": "The AI refused."}},
        ]
    )
    with (
        patch("imageskin.time_pdf.upload", return_value={"id": "abc", "name": "a.pdf"}),
        patch("imageskin.time_pdf.ask", side_effect=lambda url, *a, **k: next(statuses)),
        pytest.raises(TimingError, match="The AI refused"),
    ):
        time_pdf.process("http://app", Path("a.pdf"), None, [])


def test_a_pdf_that_never_finishes_is_given_up(tmp_path: Path) -> None:
    with (
        patch("imageskin.time_pdf.BUILD_LIMIT_S", 0.2),
        patch("imageskin.time_pdf.POLL_S", 0.05),
        patch("imageskin.time_pdf.ask", return_value={"abc": {"state": "reading"}}),
        pytest.raises(TimingError, match="wasn't done"),
    ):
        time_pdf.wait_for("http://app", "/api/content/readings", "abc", {"done"})


def test_an_app_that_cant_be_reached_is_an_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"  # nothing listens there
    sock.close()
    assert time_pdf.run(url, Path("x.pdf"), [], tmp_path / "speed") == 1
    assert "Could not reach the app" in caplog.messages
    caplog.clear()
    with caplog.at_level(logging.ERROR):
        time_pdf.remove(url, "abc")
    assert "Could not remove the timed PDF" in caplog.messages


def test_a_missing_pdf_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["time-pdf", str(tmp_path / "nope.pdf")]) == 1
    assert '"No such PDF"' in capsys.readouterr().err
