import json
import logging
from pathlib import Path

import pytest

from imageskin import thinking_report
from imageskin.reply_times import ReplyTimes
from imageskin.thinking_report import ThinkingReport


def timed(prompt_s: float = 12.0) -> ReplyTimes:
    times = ReplyTimes(received_at=0.0, answered_at=prompt_s)
    times.steps = [
        {
            "step": "LLM reading the prompt",
            "start_ms": 9000.0,
            "end_ms": 11000.0,
            "duration_ms": 2000.0,
            "tokens_read": 170,
            "tokens_reused": 900,
        },
        {
            "step": "waiting for the warm-up",
            "start_ms": 0.0,
            "end_ms": 9000.0,
            "duration_ms": 9000.0,
        },
        {
            "step": "warm-up: making the voice ready",
            "start_ms": 0.0,
            "end_ms": 8000.0,
            "duration_ms": 8000.0,
        },
    ]
    return times


def test_each_prompt_is_written_as_a_table_of_its_steps(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """R134c: the steps in a Markdown file that is easy to open, latest prompt first."""
    report = ThinkingReport(tmp_path / "speed")
    caplog.set_level(logging.INFO, logger="imageskin.thinking_report")
    report.add(timed(), "Hi", summary_running=True)
    report.add(ReplyTimes(received_at=0.0), "x" * 200)  # no steps, not answered
    text = report.path.read_text(encoding="utf-8")
    assert text.startswith("# Where the thinking goes")
    assert text.index("x" * 79 + "…") < text.index(": Hi")  # the latest first, cut short
    assert "No steps were timed." in text
    assert "longest step was **waiting for the warm-up** (9.0 s)" in text
    assert "A summary of the conversation was being made" in text
    rows = [line for line in text.splitlines() if line.startswith("| ")]
    assert rows[1:] == [
        "| waiting for the warm-up | 0.0 s | 9.0 s | 9.0 s | 75% |  |",
        "| ↳ making the voice ready | 0.0 s | 8.0 s | 8.0 s | 67% |  |",
        "| LLM reading the prompt | 9.0 s | 11.0 s | 2.0 s | 17% "
        "| tokens read 170, tokens reused 900 |",
    ]
    assert "Thinking steps written" in caplog.messages


def test_only_the_latest_prompts_are_kept_and_they_outlast_a_restart(tmp_path: Path) -> None:
    for n in range(thinking_report.KEEP + 3):
        ThinkingReport(tmp_path).add(timed(), f"prompt {n}")
    kept = json.loads((tmp_path / "thinking-steps.json").read_text(encoding="utf-8"))
    assert len(kept) == thinking_report.KEEP
    assert kept[0]["prompt"] == f"prompt {thinking_report.KEEP + 2}"


def test_an_unreadable_file_is_started_again_and_a_failed_write_is_only_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "thinking-steps.json").write_text("{not json", encoding="utf-8")
    ThinkingReport(tmp_path).add(timed(), "Hi")
    assert len(json.loads((tmp_path / "thinking-steps.json").read_text("utf-8"))) == 1
    (tmp_path / "thinking-steps.json").write_text('{"a": 1}', encoding="utf-8")
    ThinkingReport(tmp_path).add(timed(), "Hi")  # not a list: started again
    assert len(json.loads((tmp_path / "thinking-steps.json").read_text("utf-8"))) == 1
    blocked = tmp_path / "file"
    blocked.write_text("", encoding="utf-8")
    ThinkingReport(blocked / "speed").add(timed(), "Hi")  # can't make the folder: no error
    assert "Could not write the thinking steps" in caplog.text
