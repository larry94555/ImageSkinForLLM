"""Sharing the CPU cores between the LLM and the voice and video engines (roadmap R22a).

Measured on a 4-core CPU with Gemma 3 4B in llama-server and Kokoro: with both using every
core, speaking a 3-second sentence took 14.5 s instead of 0.9 s while the LLM was writing, and
the LLM itself fell from 8.4 to 0.3 tokens a second, because each one's threads spin waiting
for cores the other holds. With 2 threads each, the sentence took 1.3 s and the LLM kept 4.7
tokens a second. So while the LLM writes, the engines use half the cores, and all of them once
it has finished. llama-server is started with --threads set to the other half (see the README).
"""

import logging
import os
from collections.abc import Callable

logger = logging.getLogger(__name__)

SetThreads = Callable[[int], None]  # how many threads the engines may use from now on


def cores() -> int:
    """The cores the engines may use: OMP_NUM_THREADS when it is set, else all of them."""
    try:
        return max(1, int(os.environ.get("OMP_NUM_THREADS") or os.cpu_count() or 1))
    except ValueError:
        return os.cpu_count() or 1


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
    """How many cores the engines use: half while the LLM writes, all of them otherwise."""

    def __init__(self, total: int | None = None, apply: SetThreads = set_threads) -> None:
        self.total = total or cores()
        self.shared = max(1, self.total // 2)
        self._apply = apply
        self.threads: int | None = None  # what the engines were last told

    def _set(self, threads: int) -> None:
        if threads != self.threads:
            self.threads = threads
            self._apply(threads)
            logger.info("Engine threads set", extra={"threads": threads, "cores": self.total})

    def llm_writing(self) -> None:
        """A prompt was sent: leave the LLM its half of the cores until it has replied."""
        self._set(self.shared)

    def llm_done(self) -> None:
        """The LLM has replied (or failed): the engines may use every core."""
        self._set(self.total)
