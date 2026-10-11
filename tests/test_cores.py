import logging
import os
import sys
import threading
from pathlib import Path
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


def core_record(efficiency: int, mask: int, group: int = 0, relationship: int = 0) -> bytes:
    """One SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX record for a core, as Windows lays it out."""
    import struct

    body = bytes([0, efficiency]) + bytes(20) + struct.pack("<H", 1)
    body += struct.pack("<QH", mask, group) + bytes(6)
    return struct.pack("<II", relationship, 8 + len(body)) + body


def test_windows_performance_cpus_are_the_cores_of_the_highest_class() -> None:
    from imageskin.cores import windows_performance_cpus

    # The i7-1360P: 4 performance cores with 2 threads each, then 8 efficiency cores.
    i7 = b"".join(core_record(1, 0b11 << (2 * n)) for n in range(4))
    i7 += b"".join(core_record(0, 1 << (8 + n)) for n in range(8))
    assert windows_performance_cpus(i7) == list(range(8))
    # Records of another relationship are skipped.
    assert windows_performance_cpus(core_record(0, 1, relationship=2) + i7) == list(range(8))
    alike = b"".join(core_record(0, 0b11 << (2 * n)) for n in range(4))
    assert windows_performance_cpus(alike) is None  # all cores alike
    assert windows_performance_cpus(b"") is None
    beyond = core_record(1, 1, group=1) + core_record(0, 2)
    assert windows_performance_cpus(beyond) is None  # beyond the first 64 CPUs
    no_size = i7[:4] + b"\0\0\0\0" + i7[8:]  # a record with no size ends the list
    assert windows_performance_cpus(no_size) is None


def test_linux_performance_cpus_come_from_the_hybrid_cpu_list(tmp_path: Path) -> None:
    from imageskin.cores import linux_performance_cpus, parse_cpu_list

    assert parse_cpu_list("0-7,16\n") == [0, 1, 2, 3, 4, 5, 6, 7, 16]
    listed = tmp_path / "cpus"
    listed.write_text("0-3\n")
    assert linux_performance_cpus(listed) == [0, 1, 2, 3]
    assert linux_performance_cpus(tmp_path / "missing") is None  # not a hybrid CPU
    listed.write_text("\n")
    assert linux_performance_cpus(listed) is None
    listed.write_text("zero")
    assert linux_performance_cpus(listed) is None


def test_the_app_is_kept_on_the_performance_cores(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from imageskin.cores import ALL_CORES, use_performance_cores

    monkeypatch.delenv(ALL_CORES, raising=False)
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    pinned: list[list[int]] = []
    with caplog.at_level(logging.INFO):
        assert use_performance_cores(lambda: list(range(8)), pinned.append) == 8
    assert pinned == [list(range(8))]
    kept = next(
        r for r in caplog.records if r.getMessage() == "Kept the app on the performance cores"
    )
    assert kept.cpus == 8  # type: ignore[attr-defined]
    with patch("os.cpu_count", return_value=16):
        assert cores(8) == 8 and cores() == 16 and caplog.records[-1].levelname == "INFO"
    # All cores alike, or no way to tell: left on every core.
    assert use_performance_cores(lambda: None, pinned.append) is None and len(pinned) == 1

    def refused(cpus: list[int]) -> None:
        raise PermissionError("not allowed")

    with caplog.at_level(logging.WARNING):
        assert use_performance_cores(lambda: [0, 1], refused) is None
    assert caplog.records[-1].getMessage() == "Could not keep the app on the performance cores"
    monkeypatch.setenv(ALL_CORES, "1")
    with caplog.at_level(logging.INFO):
        assert use_performance_cores(lambda: [0, 1], pinned.append) is None
    assert len(pinned) == 1 and caplog.records[-1].getMessage() == "The app may use every core"


def test_performance_cpus_by_platform(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from imageskin import cores as module

    monkeypatch.setattr(sys, "platform", "win32")
    with patch.object(module, "_windows_processor_info", return_value=core_record(0, 1)):
        assert module.performance_cpus() is None
    with (
        patch.object(module, "_windows_processor_info", side_effect=OSError(87, "bad")),
        caplog.at_level(logging.WARNING),
    ):
        assert module.performance_cpus() is None
    assert caplog.records[-1].getMessage() == "Could not tell the performance cores apart"
    monkeypatch.setattr(sys, "platform", "linux")
    with patch.object(module, "linux_performance_cpus", return_value=[0, 1]):
        assert module.performance_cpus() == [0, 1]
    monkeypatch.setattr(sys, "platform", "darwin")
    assert module.performance_cpus() is None


@pytest.mark.skipif(not hasattr(os, "sched_setaffinity"), reason="Linux only")
def test_linux_pin_sets_every_thread() -> None:
    from imageskin.cores import _linux_pin

    every = sorted(os.sched_getaffinity(0))
    started = threading.Event()
    stop = threading.Event()

    def wait() -> None:
        started.set()
        stop.wait(5)

    worker = threading.Thread(target=wait)
    worker.start()
    started.wait(5)
    try:
        _linux_pin(every[:1])
        assert os.sched_getaffinity(worker.native_id) == set(every[:1])  # type: ignore[arg-type]
    finally:
        _linux_pin(every)
        stop.set()
        worker.join()
