import logging

import pytest

from imageskin import startup as startup_module
from imageskin.startup import StartupTimes, process_age_s


def test_each_part_is_kept_from_its_first_run(caplog: pytest.LogCaptureFixture) -> None:
    times = StartupTimes(age_s=1.0)
    with caplog.at_level(logging.INFO):
        times.begin("test warm-up")
        times.end("test warm-up")
        first = times.snapshot()["parts"][0]
        times.begin("test warm-up")  # run again after a sample is accepted: not the start
        times.end("test warm-up", error="later")
    part = times.snapshot()["parts"][0]
    assert part == first and "error" not in part
    assert part["start_ms"] >= 1000 and part["end_ms"] >= part["start_ms"]
    # Filtered by part: an earlier test's warm-up thread can still log meanwhile.
    ours = [r for r in caplog.records if getattr(r, "part", None) == "test warm-up"]
    assert [r.getMessage() for r in ours] == ["Start-up part finished"]


def test_a_part_that_fails_keeps_its_error(caplog: pytest.LogCaptureFixture) -> None:
    times = StartupTimes(age_s=0)

    def broken() -> None:
        raise RuntimeError("no model")

    with pytest.raises(RuntimeError), caplog.at_level(logging.INFO):
        times.timed("face models", broken)()
    failed = [r for r in caplog.records if getattr(r, "part", None) == "face models"]
    assert [r.levelno for r in failed] == [logging.WARNING]
    assert times.timed("speaker model", lambda: 7)() == 7
    parts = {p["name"]: p for p in times.snapshot()["parts"]}
    assert parts["face models"]["error"] == "no model"
    assert "error" not in parts["speaker model"]


def test_a_mark_is_a_moment_and_an_unbegun_end_is_ignored() -> None:
    times = StartupTimes(age_s=0)
    times.end("never begun")
    times.mark("ready")
    times.begin("LLM warm-up")  # after the ready line: not the start
    (ready,) = times.snapshot()["parts"]
    assert ready["name"] == "ready" and ready["end_ms"] - ready["start_ms"] < 5


def test_the_process_age_comes_from_proc_or_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    assert process_age_s() >= 0  # Linux: the time since this test run began

    def missing(*_: object, **__: object) -> None:
        raise OSError("no /proc")

    monkeypatch.setattr(startup_module, "open", missing, raising=False)
    assert process_age_s() == 0.0
    times = StartupTimes()
    assert times.snapshot()["now_ms"] < 1000
