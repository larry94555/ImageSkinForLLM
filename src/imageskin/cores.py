"""Sharing the CPU cores between the LLM and the voice and video engines (roadmap R22a).

Measured on a 4-core CPU with Gemma 3 4B in llama-server and Kokoro: with both using every
core, speaking a 3-second sentence took 14.5 s instead of 0.9 s while the LLM was writing, and
the LLM itself fell from 8.4 to 0.3 tokens a second, because each one's threads spin waiting
for cores the other holds. With 2 threads each, the sentence took 1.3 s and the LLM kept 4.7
tokens a second. So while the LLM is busy (writing a reply, or summarizing the conversation
after one), the engines use half the cores, and all of them once it has finished. llama-server
is started with --threads set to the other half (see the README).

PyTorch's thread count is per thread once a thread has used it, and OpenCV's setter is not safe
to call while another thread is inside OpenCV, so an LLM request starting or ending only records
the count, and the thread that runs the engines applies it itself (`apply_here`) before each
step, between engine operations.

On a CPU with performance and efficiency cores, such as Intel's 12th-generation and later laptop
chips, the app is kept on the performance cores and counts only theirs (roadmap R22g). On
Larry's i7-1360P (4 performance cores with 2 threads each, 8 efficiency cores) the app counted 16
cores and spread over all of them, though an efficiency core is about 3 times slower per thread;
kept on the performance cores with 8 threads, Pocket TTS spoke about 1.7 times faster
(0.38 to 0.45 seconds of work per second of speech against 0.6 to 1.2).
"""

import logging
import os
import struct
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

SetThreads = Callable[[int], None]  # how many threads the engines may use from now on


ALL_CORES = "IMAGESKIN_ALL_CORES"  # set to 1 to spread over every core, as before R22g
LINUX_PERFORMANCE_CPUS = Path("/sys/devices/cpu_core/cpus")  # Intel's hybrid CPUs on Linux
RELATION_PROCESSOR_CORE = 0  # Windows' LOGICAL_PROCESSOR_RELATIONSHIP for one core


def parse_cpu_list(text: str) -> list[int]:
    """The CPUs in a Linux CPU list such as "0-7,16"."""
    cpus: list[int] = []
    for part in text.strip().split(","):
        if part:
            first, _, last = part.partition("-")
            cpus.extend(range(int(first), int(last or first) + 1))
    return cpus


def linux_performance_cpus(path: Path = LINUX_PERFORMANCE_CPUS) -> list[int] | None:
    """The performance cores' logical CPUs, which Linux lists for Intel's hybrid CPUs only."""
    try:
        cpus = parse_cpu_list(path.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None
    return cpus or None


def windows_performance_cpus(info: bytes) -> list[int] | None:
    """The performance cores' logical CPUs, from what GetLogicalProcessorInformationEx says of
    each core: the cores of the highest efficiency class, when there are two or more classes.

    Each record is a SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX: its relationship and size, then a
    PROCESSOR_RELATIONSHIP whose EfficiencyClass is at byte 9 and whose first GROUP_AFFINITY (the
    mask of the core's logical CPUs and its group) is at byte 32. Only group 0, which holds the
    first 64 logical CPUs, is used.
    """
    core_list: list[tuple[int, int, int]] = []  # efficiency class, group, mask
    offset = 0
    while offset + 42 <= len(info):
        relationship, size = struct.unpack_from("<II", info, offset)
        if size == 0:
            break
        if relationship == RELATION_PROCESSOR_CORE:
            mask, group = struct.unpack_from("<QH", info, offset + 32)
            core_list.append((info[offset + 9], group, mask))
        offset += size
    classes = {efficiency for efficiency, _, _ in core_list}
    if len(classes) < 2:
        return None
    fastest = max(classes)
    if any(group != 0 for efficiency, group, _ in core_list if efficiency == fastest):
        return None
    mask = 0
    for efficiency, _, core_mask in core_list:
        if efficiency == fastest:
            mask |= core_mask
    return [cpu for cpu in range(64) if mask >> cpu & 1]


def _windows_processor_info() -> bytes:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    size = wintypes.DWORD(0)
    kernel32.GetLogicalProcessorInformationEx(RELATION_PROCESSOR_CORE, None, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(size.value)
    if not kernel32.GetLogicalProcessorInformationEx(
        RELATION_PROCESSOR_CORE, buffer, ctypes.byref(size)
    ):
        raise OSError(ctypes.get_last_error(), "GetLogicalProcessorInformationEx failed")  # type: ignore[attr-defined,unused-ignore]
    return buffer.raw[: size.value]


def _windows_pin(cpus: list[int]) -> None:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    mask = sum(1 << cpu for cpu in cpus)
    if not kernel32.SetProcessAffinityMask(kernel32.GetCurrentProcess(), mask):
        raise OSError(ctypes.get_last_error(), "SetProcessAffinityMask failed")  # type: ignore[attr-defined,unused-ignore]


def _linux_pin(cpus: list[int]) -> None:
    """Every thread of the process, since Linux sets one thread at a time."""
    for task in os.listdir("/proc/self/task"):
        os.sched_setaffinity(int(task), cpus)  # type: ignore[attr-defined,unused-ignore]


def performance_cpus() -> list[int] | None:
    """The performance cores' logical CPUs on a CPU that also has efficiency cores, or None when
    all its cores are alike or it can't be told (macOS keeps no such setting)."""
    try:
        if sys.platform == "win32":
            return windows_performance_cpus(_windows_processor_info())
        if sys.platform.startswith("linux"):
            return linux_performance_cpus()
    except OSError as e:
        logger.warning("Could not tell the performance cores apart", extra={"error": str(e)})
    return None


def use_performance_cores(
    find: Callable[[], list[int] | None] = performance_cpus,
    pin: Callable[[list[int]], None] | None = None,
) -> int | None:
    """Keep the app on the performance cores, when the CPU also has efficiency cores, and return
    how many logical CPUs it kept; None leaves it on every core. Called before the engines
    start their threads. IMAGESKIN_ALL_CORES=1 turns it off."""
    if os.environ.get(ALL_CORES) == "1":
        logger.info("The app may use every core", extra={"setting": ALL_CORES})
        return None
    cpus = find()
    if not cpus:
        return None
    pin = pin or (_windows_pin if sys.platform == "win32" else _linux_pin)
    try:
        pin(cpus)
    except OSError as e:
        logger.warning("Could not keep the app on the performance cores", extra={"error": str(e)})
        return None
    logger.info(
        "Kept the app on the performance cores",
        extra={"cpus": len(cpus), "cpu_count": os.cpu_count(), "setting": f"{ALL_CORES}=1 undoes"},
    )
    return len(cpus)


def cores(count: int | None = None) -> int:
    """The cores the engines may use: OMP_NUM_THREADS when it is set, else all of them (or the
    `count` the app is kept on). A cap below the count is logged, as it leaves the engines fewer
    cores than the LLM's half."""
    count = count or os.cpu_count() or 1
    try:
        capped = int(os.environ.get("OMP_NUM_THREADS") or count)
    except ValueError:
        return count
    if capped < count:
        logger.warning(
            "OMP_NUM_THREADS caps the engines' cores; leave it unset, the app shares the cores"
            " with the LLM itself",
            extra={"omp_num_threads": capped, "cpu_count": count},
        )
    return max(1, capped)


def set_threads(n: int) -> None:
    """Tell PyTorch (the voice) and OpenCV (the video) how many threads to use, when installed."""
    try:
        import torch
    except ImportError:
        pass
    else:
        torch.set_num_threads(n)
    try:
        import cv2
    except ImportError:
        pass
    else:
        cv2.setNumThreads(n)


class CoreShare:
    """How many cores the engines use: half while the LLM is busy, all of them otherwise."""

    def __init__(self, total: int | None = None, apply: SetThreads | None = None) -> None:
        self.total = total or cores()
        self.shared = max(1, self.total // 2)
        self._apply = apply or set_threads
        self.threads: int | None = None  # what the engines were last told
        self._busy = 0  # LLM requests under way
        self._lock = threading.Lock()
        self._local = threading.local()  # what this thread was last told

    def _set(self, threads: int) -> None:
        """Record the count for the engines' thread to apply before its next step: not applied
        here, since it may be inside the engines right now."""
        if threads != self.threads:
            self.threads = threads
            logger.info("Engine threads set", extra={"threads": threads, "cores": self.total})

    def _apply_here(self, threads: int) -> None:
        self._local.threads = threads
        self._apply(threads)

    def apply_here(self) -> None:
        """Apply the current count on this thread, when it hasn't got it yet. The thread that
        runs the engines calls this before each step, as PyTorch keeps a count per thread."""
        with self._lock:
            threads = self.threads
        if threads is not None and getattr(self._local, "threads", None) != threads:
            self._apply_here(threads)

    def llm_writing(self) -> None:
        """An LLM request started: leave the LLM its half of the cores until all are done."""
        with self._lock:
            self._busy += 1
            if self._busy == 1:
                self._set(self.shared)

    def llm_done(self) -> None:
        """An LLM request ended (or failed): once none is left, the engines may use every core."""
        with self._lock:
            self._busy = max(0, self._busy - 1)
            if self._busy == 0:
                self._set(self.total)

    @contextmanager
    def llm(self) -> Iterator[None]:
        """While an LLM request is under way."""
        self.llm_writing()
        try:
            yield
        finally:
            self.llm_done()
