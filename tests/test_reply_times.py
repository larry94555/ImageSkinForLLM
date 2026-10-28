import logging
import time

import pytest

from imageskin import reply_times
from imageskin.reply_times import ReplyTimes, note, note_llm, note_now


def test_nothing_is_kept_without_a_prompt_being_timed() -> None:
    note(first_token_at=1.0)
    note_llm({"prompt_n": 3})
    assert reply_times.current.get() is None


def test_the_first_token_and_sentence_are_kept_and_the_last_token_moves_on() -> None:
    times = ReplyTimes(received_at=0.0)
    token = reply_times.current.set(times)
    try:
        note(first_token_at=1.0, last_token_at=1.0, history_tokens=40)
        note(first_token_at=2.0, last_token_at=2.0, history_tokens=99)
        note_now("first_sentence_at")
        later = times.first_sentence_at
        note_now("first_sentence_at")
    finally:
        reply_times.current.reset(token)
    assert times.first_token_at == 1.0 and times.last_token_at == 2.0
    assert times.history_tokens == 40
    assert later is not None and times.first_sentence_at == later


def test_only_llama_servers_timings_are_kept() -> None:
    times = ReplyTimes(received_at=0.0)
    token = reply_times.current.set(times)
    try:
        note_llm("not a dict")
        assert times.llm is None
        note_llm({"prompt_n": 30, "cache_n": 100, "predicted_per_second": 6.2, "n_ctx": 4096})
    finally:
        reply_times.current.reset(token)
    assert times.llm == {"prompt_n": 30, "cache_n": 100, "predicted_per_second": 6.2}
    assert times.as_dict()["llm"] == times.llm
    assert times.as_dict()["received_at"] == 0.0


def test_llm_requests_are_kept_only_while_a_list_is_set() -> None:
    """R96a: the wiki's build keeps each request's time and llama-server's timings."""
    reply_times.note_request({"prompt_n": 3}, 10.0)  # nothing set: nothing kept, no error
    kept: list[dict[str, object]] = []
    token = reply_times.requests.set(kept)
    try:
        reply_times.note_request({"prompt_n": 30, "cache_n": 5, "n_ctx": 4096}, 120.5)
        reply_times.note_request("not a dict", 3.0)
    finally:
        reply_times.requests.reset(token)
    assert kept == [{"duration_ms": 120.5, "prompt_n": 30, "cache_n": 5}, {"duration_ms": 3.0}]


def test_a_step_is_kept_and_logged_with_its_start_end_and_duration(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R134c: each step of the thinking, in ms from the prompt's arrival."""
    reply_times.add_step("no prompt", 0.0, 1.0)  # nothing timed: nothing kept, no error
    times = ReplyTimes(received_at=10.0)
    token = reply_times.current.set(times)
    caplog.set_level(logging.INFO, logger="imageskin.reply_times")
    try:
        reply_times.add_step("searching", 10.5, 12.0, passages=3)
    finally:
        reply_times.current.reset(token)
    assert times.steps == [
        {
            "step": "searching",
            "start_ms": 500.0,
            "end_ms": 2000.0,
            "duration_ms": 1500.0,
            "passages": 3,
        }
    ]
    assert times.as_dict()["steps"] == times.steps
    logged = [r for r in caplog.records if r.getMessage() == "Thinking step"]
    assert len(logged) == 1 and logged[0].duration_ms == 1500.0  # type: ignore[attr-defined]


def test_a_timed_step_is_kept_even_when_it_fails() -> None:
    times = ReplyTimes(received_at=time.perf_counter())
    token = reply_times.current.set(times)
    try:
        with reply_times.step("reading"):
            pass
        with pytest.raises(ValueError), reply_times.step("writing", tokens=4):
            raise ValueError("no")
    finally:
        reply_times.current.reset(token)
    assert [s["step"] for s in times.steps] == ["reading", "writing"]
    assert times.steps[1]["error"] == "ValueError" and times.steps[1]["tokens"] == 4
    assert all(s["duration_ms"] >= 0 for s in times.steps)


def test_the_steps_line_names_the_longest_step(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="imageskin.reply_times")
    times = ReplyTimes(received_at=0.0)
    reply_times.log_steps(times)  # none yet: still a line
    times.steps = [
        {"step": "waiting for the warm-up", "duration_ms": 9000.0},
        {"step": "LLM reading the prompt", "duration_ms": 2000.0},
    ]
    times.answered_at = 12.0
    reply_times.log_steps(times, reply_id="r1")
    first, second = [r for r in caplog.records if r.getMessage() == "Thinking steps"]
    assert first.longest_step is None and first.duration_ms is None  # type: ignore[attr-defined]
    assert second.longest_step == "waiting for the warm-up"  # type: ignore[attr-defined]
    assert second.longest_ms == 9000.0 and second.duration_ms == 12000.0  # type: ignore[attr-defined]
    assert second.steps == 2 and second.reply_id == "r1"  # type: ignore[attr-defined]


def test_a_runs_parts_are_cut_to_the_wait_that_overlaps_them() -> None:
    """R134c: a prompt that waited for the warm-up is told the part of its wait each part took."""
    with reply_times.part("not kept"):  # no run being timed on this thread: nothing kept
        pass
    parts = reply_times.Parts()
    token = reply_times.parts.set(parts)
    try:
        with reply_times.part("engines"):
            pass
        with pytest.raises(RuntimeError), reply_times.part("voice"):
            raise RuntimeError("failed")  # a failed part still ends
        unfinished = parts.begin("idle video")
    finally:
        reply_times.parts.reset(token)
    now = time.perf_counter()
    found = {name: (start, end) for name, start, end in parts.during(0.0, now + 1)}
    assert set(found) == {"engines", "voice", "idle video"}
    assert found["idle video"][1] == now + 1  # not finished: counted until the wait ended
    assert parts.during(now + 1, now + 2) == [("idle video", now + 1, now + 2)]
    parts.end(unfinished)
    parts.end(99)  # not a part: ignored
    parts.clear()
    assert parts.during(0.0, now + 2) == []
