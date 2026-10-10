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
    assert share.threads == 2
    with share.llm():
        assert share.threads == 2
    assert share.threads == 2
    share.llm_done()
    share.llm_done()  # once more than started: fine
    assert share.threads == 4
    assert [r.threads for r in caplog.records] == [4, 2, 4]  # type: ignore[attr-defined]
    assert all(r.cores == 4 for r in caplog.records)  # type: ignore[attr-defined]
    assert told == []  # the libraries are told by the thread that runs the engines (below)


def test_each_thread_that_runs_the_engines_applies_the_count_itself() -> None:
    """PyTorch keeps a thread count per thread, and OpenCV's setter must not be called while
    another thread is inside OpenCV, so only the clips' thread applies the current count, before
    each step, and only when it changed for that thread."""
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
    assert told == [("clips", 2), ("clips-2", 4)]


def test_the_llm_finishing_does_not_touch_the_libraries_while_a_clip_is_rendered() -> None:
    """The regression for a review finding: the LLM's request thread used to tell OpenCV its
    thread count the moment the LLM finished, while the clips' thread could be inside OpenCV."""
    told: list[tuple[str, int]] = []
    inside, finished = threading.Event(), threading.Event()
    share = CoreShare(total=4, apply=lambda n: told.append((threading.current_thread().name, n)))
    share.llm_writing()

    def engines() -> None:
        share.apply_here()
        inside.set()  # inside OpenCV, say
        finished.wait(5)
        share.apply_here()  # the next step applies the new count

    worker = threading.Thread(target=engines, name="clips")
    worker.start()
    assert inside.wait(5)
    share.llm_done()  # while the clip is rendered: recorded, not applied
    assert told == [("clips", 2)] and share.threads == 4
    finished.set()
    worker.join(5)
    assert told == [("clips", 2), ("clips", 4)]


def test_one_core_is_never_split() -> None:
    told: list[int] = []
    share = CoreShare(total=1, apply=told.append)
    share.llm_writing()
    share.apply_here()
    share.llm_done()
    share.apply_here()
    assert told == [1]


def test_the_cores_are_counted_when_not_given() -> None:
    with patch("imageskin.cores.cores", return_value=6):
        share = CoreShare(apply=lambda n: None)
    assert (share.total, share.shared) == (6, 3)
    with patch("imageskin.cores.set_threads") as fake:  # the libraries are told by default
        share = CoreShare(total=2)
        share.llm_done()
        share.apply_here()
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
