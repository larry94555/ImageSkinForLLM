from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from imageskin import setup_progress
from imageskin.setup_progress import CLOUD_STEP_S, Progress, clock, duration

PHASES: list[tuple[str, setup_progress.Kind]] = [
    ("Uploads", "uploads"),
    ("Prepare", "prepare"),
    ("Prepare again, another photo", "photo"),
    ("Start now", "start"),
]


def step(
    key: str, done: int, total: int, seconds: float | None = None, left_s: int | None = None
) -> dict[str, Any]:
    return {
        "key": key,
        "label": key.title(),
        "done": done,
        "total": total,
        "seconds": seconds,
        "left_s": left_s,
    }


def test_durations_read_as_a_person_would_say_them() -> None:
    assert duration(40.4) == "40 s"
    assert duration(-3) == "0 s"
    assert duration(12 * 60 + 10) == "12 min"
    assert duration(3900) == "1 h 05 min"
    assert clock(3600 * 5 + 60 * 7) == "05:07 UTC"


def test_before_any_step_finishes_the_cloud_times_are_the_guess(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.txt", PHASES, started=0.0)
    assert progress.slower == 1.0
    text = progress.text(now=30.0)
    assert "Now: 1 of 4, Uploads." in text
    cloud = sum(CLOUD_STEP_S.values()) + sum(v for k, v in CLOUD_STEP_S.items() if k != "voice")
    assert f"About {duration(cloud + setup_progress.START_NOW_GUESS_S)} left in all" in text
    assert "a rough guess" in text and "Done:" not in text
    progress.begin("Prepare")
    assert "About 6 min left in this Prepare." in progress.text(now=60.0)


def test_time_left_follows_how_slow_this_machine_is(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.txt", PHASES, started=0.0)
    progress.begin("Prepare")
    status = {
        "state": "running",
        "steps": [
            step("voice", 1, 1, seconds=86.0),  # ten times the cloud's 8.6 s
            step("models", 1, 1, seconds=24.0),  # and the 2.4 s
            step("shapes", 10, 100, left_s=600),
            step("loop", 0, 1),
            step("align", 1, 1),  # kept from before: no time of its own
            step("clips", 0, 1),
        ],
    }
    progress.prepare(status)
    progress.prepare(status)  # the same finished steps seen again count once
    assert progress.slower == pytest.approx(10.0)
    # The running step's own estimate, then the ones not started at ten times the cloud's.
    assert progress.left_in_prepare() == pytest.approx(600 + 2520 + 250)
    text = progress.text(now=600.0)
    assert "Now: 2 of 4, Prepare." in text
    assert "Step: Shapes (10 of 100)." in text
    assert "About 56 min left in this Prepare." in text
    assert "10.0 times as long as in the cloud" in text
    assert "Done: Uploads." in text
    photo = sum(v for k, v in CLOUD_STEP_S.items() if k != "voice") * 10
    assert progress.left_after() == pytest.approx(photo + setup_progress.START_NOW_GUESS_S)
    progress.begin("Start now")
    text = progress.text(now=900.0)
    assert "left in this Prepare" not in text
    assert "About 3 min left in all" in text
    assert "Done: Uploads; Prepare; Prepare again, another photo." in text


def test_the_file_is_written_now_and_then_and_whole(tmp_path: Path) -> None:
    path = tmp_path / "speed" / "p.txt"
    progress = Progress(path, PHASES)
    progress.begin("Prepare")
    assert "Now: 2 of 4" in path.read_text()
    assert not path.with_suffix(".saving").exists()
    progress.status = {"steps": []}
    path.write_text("old")
    progress.prepare({"state": "running", "steps": [step("voice", 0, 1)]})
    assert path.read_text() == "old"  # written a moment ago
    with patch.object(setup_progress, "WRITE_EVERY_S", 0.0):
        progress.prepare({"state": "running", "steps": [step("voice", 0, 1)]})
    assert "Step: Voice (0 of 1)." in path.read_text()
    progress.begin("Nothing like it")  # an unknown phase keeps the current one
    assert progress.current == 1


def test_the_end_says_where_the_results_are(tmp_path: Path) -> None:
    path = tmp_path / "p.txt"
    progress = Progress(path, PHASES, started=0.0)
    progress.done(tmp_path / "setup.md", 0)
    assert "No errors." in path.read_text()
    assert path.read_text().endswith(f"Results: {tmp_path / 'setup.md'}\n")
    progress.done(tmp_path / "setup.md", 2)
    assert "Steps that failed: 2" in path.read_text()
    Progress(path, [], started=0.0).stopped(KeyboardInterrupt())
    assert "during starting: KeyboardInterrupt()" in path.read_text()


def test_nothing_is_written_without_a_file_or_where_it_cant_be(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    Progress(None, PHASES).begin("Prepare")
    Progress(None, PHASES).done(tmp_path / "x.md", 0)
    blocked = tmp_path / "file"
    blocked.write_text("")
    Progress(blocked / "p.txt", PHASES).begin("Prepare")
    Progress(blocked / "p.txt", PHASES).done(tmp_path / "x.md", 0)
    assert caplog.text.count("Could not write the progress file") == 2
