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
"""

import logging
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

SetThreads = Callable[[int], None]  # how many threads the engines may use from now on


def cores() -> int:
    """The cores the engines may use: OMP_NUM_THREADS when it is set, else all of them. A cap
    below the count is logged, as it leaves the engines fewer cores than the LLM's half."""
    count = os.cpu_count() or 1
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
