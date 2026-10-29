import logging
from pathlib import Path

import pytest

from imageskin.warm_up_time import FILENAME, last_warm_up_s, save_warm_up_s, seconds_left


def test_the_last_warm_up_time_is_kept_across_a_restart(tmp_path: Path) -> None:
    assert last_warm_up_s(tmp_path) is None
    save_warm_up_s(tmp_path / "home", 14.73)
    assert last_warm_up_s(tmp_path / "home") == 14.7


@pytest.mark.parametrize(
    "saved", ["not json", "[]", '{"other": 1}', '{"seconds": "ten"}', '{"seconds": -3}']
)
def test_a_broken_warm_up_time_is_logged_and_not_used(
    tmp_path: Path, saved: str, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / FILENAME).write_text(saved)
    with caplog.at_level(logging.WARNING):
        assert last_warm_up_s(tmp_path) is None
    assert caplog.records


def test_a_warm_up_time_that_cannot_be_kept_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / FILENAME).mkdir()  # a folder in the way
    with caplog.at_level(logging.WARNING):
        save_warm_up_s(tmp_path, 3)
    assert "Could not keep the warm-up time" in caplog.text


@pytest.mark.parametrize("seconds", [float("nan"), float("inf"), -1.0])
def test_a_warm_up_time_that_is_not_a_time_is_not_kept(
    tmp_path: Path, seconds: float, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        save_warm_up_s(tmp_path, seconds)
    assert not (tmp_path / FILENAME).exists() and "Warm-up time not kept" in caplog.text


def test_seconds_left_counts_down_to_none() -> None:
    assert seconds_left(None, 0) is None  # never timed
    assert seconds_left(float("nan"), 0) is None and seconds_left(float("inf"), 0) is None
    assert seconds_left(20, 0) == 20
    assert seconds_left(20, 12.5) == 8  # rounded up: never 0 while it still runs
    assert seconds_left(20, 19.9) == 1
    assert seconds_left(20, 20) is None and seconds_left(20, 45) is None  # taking longer
