import logging
import sys
from unittest.mock import patch

import pytest

from imageskin.cores import CoreShare, cores, set_threads


def test_the_cores_are_all_of_them_unless_omp_num_threads_says(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    with patch("os.cpu_count", return_value=8):
        assert cores() == 8
    monkeypatch.setenv("OMP_NUM_THREADS", "3")
    assert cores() == 3
    monkeypatch.setenv("OMP_NUM_THREADS", "0")
    assert cores() == 1
    monkeypatch.setenv("OMP_NUM_THREADS", "lots")
    with patch("os.cpu_count", return_value=6):
        assert cores() == 6
    monkeypatch.setenv("OMP_NUM_THREADS", "")
    with patch("os.cpu_count", return_value=None):
        assert cores() == 1


def test_the_engines_get_half_the_cores_while_the_llm_writes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    told: list[int] = []
    share = CoreShare(total=4, apply=told.append)
    caplog.set_level(logging.INFO)
    share.llm_done()
    share.llm_writing()
    share.llm_writing()  # told only when it changes
    share.llm_done()
    assert told == [4, 2, 4]
    assert [r.threads for r in caplog.records] == [4, 2, 4]  # type: ignore[attr-defined]
    assert all(r.cores == 4 for r in caplog.records)  # type: ignore[attr-defined]


def test_one_core_is_never_split() -> None:
    told: list[int] = []
    share = CoreShare(total=1, apply=told.append)
    share.llm_writing()
    share.llm_done()
    assert told == [1]


def test_the_cores_are_counted_when_not_given() -> None:
    with patch("imageskin.cores.cores", return_value=6):
        share = CoreShare(apply=lambda n: None)
    assert (share.total, share.shared) == (6, 3)


def test_set_threads_tells_the_libraries_that_are_installed() -> None:
    class Lib:
        threads: int | None = None

        @classmethod
        def set_num_threads(cls, n: int) -> None:
            cls.threads = n

        setNumThreads = set_num_threads

    with patch.dict(sys.modules, {"torch": Lib, "cv2": Lib}):
        set_threads(3)
    assert Lib.threads == 3
    with patch.dict(sys.modules, {"torch": None, "cv2": None}):  # neither installed
        set_threads(2)
