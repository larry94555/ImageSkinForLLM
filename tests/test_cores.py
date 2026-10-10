import logging
import sys
import threading
from unittest.mock import patch

import pytest

from imageskin.cores import CoreShare, cores, set_threads


def test_the_cores_are_all_of_them_unless_omp_num_threads_says(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    with patch("os.cpu_count", return_value=8):
        assert cores() == 8
    monkeypatch.setenv("OMP_NUM_THREADS", "3")
    with patch("os.cpu_count", return_value=8), caplog.at_level(logging.WARNING):
        assert cores() == 3  # capped below the count, which is logged
    assert caplog.messages[0].startswith("OMP_NUM_THREADS caps the engines' cores")
    assert (caplog.records[0].omp_num_threads, caplog.records[0].cpu_count) == (3, 8)  # type: ignore[attr-defined]
    caplog.clear()
    with patch("os.cpu_count", return_value=3):
        assert cores() == 3 and caplog.records == []  # not a cap: nothing to say
    monkeypatch.setenv("OMP_NUM_THREADS", "0")
    assert cores() == 1
    monkeypatch.setenv("OMP_NUM_THREADS", "lots")
    with patch("os.cpu_count", return_value=6):
        assert cores() == 6
    monkeypatch.setenv("OMP_NUM_THREADS", "")
    with patch("os.cpu_count", return_value=None):
        assert cores() == 1


def test_the_engines_get_half_the_cores_while_the_llm_is_busy(
    caplog: pytest.LogCaptureFixture,
) -> None:
    told: list[int] = []
    share = CoreShare(total=4, apply=told.append)
    caplog.set_level(logging.INFO)
    share.llm_done()
    share.llm_writing()
    share.llm_writing()  # a second request (the summary after a reply): told only when it changes
    share.llm_done()  # one is still under way
    assert told == [4, 2]
    with share.llm():
        assert told == [4, 2]
    assert told == [4, 2]
    share.llm_done()
    share.llm_done()  # once more than started: fine
    assert told == [4, 2, 4]
    assert [r.threads for r in caplog.records] == [4, 2, 4]  # type: ignore[attr-defined]
    assert all(r.cores == 4 for r in caplog.records)  # type: ignore[attr-defined]


def test_each_thread_that_runs_the_engines_applies_the_count_itself() -> None:
    """PyTorch keeps a thread count per thread, so the clips' thread applies the current one
    before each step, and only when it changed for that thread."""
    told: list[tuple[str, int]] = []
    share = CoreShare(total=4, apply=lambda n: told.append((threading.current_thread().name, n)))
    share.apply_here()  # nothing told yet: nothing to apply
    share.llm_writing()

    def engines() -> None:
        share.apply_here()
        share.apply_here()  # already applied on this thread

    worker = threading.Thread(target=engines, name="clips")
    worker.start()
    worker.join()
    share.llm_done()
    worker = threading.Thread(target=engines, name="clips-2")
    worker.start()
    worker.join()
    main = threading.current_thread().name
    assert told == [(main, 2), ("clips", 2), (main, 4), ("clips-2", 4)]


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
    with patch("imageskin.cores.set_threads") as fake:  # the libraries are told by default
        CoreShare(total=2).llm_done()
    fake.assert_called_once_with(2)


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
