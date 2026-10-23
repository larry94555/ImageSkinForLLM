"""When each part of the app's start began and ended (roadmap R96c), in milliseconds from the
process starting, so `imageskin time-startup` can say where the time goes before the ready
line. Each part is kept the first time it runs before the ready line: a warm-up run again
after a sample is accepted is not the start."""

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def process_age_s() -> float:
    """How long ago this process started, from /proc on Linux, or 0 when it can't tell (the
    parts are then timed from when the app began to be made)."""
    try:
        with open("/proc/self/stat", encoding="ascii") as f:
            # The command's name can hold spaces, so the fields are counted after its ")".
            fields = f.read().rsplit(")", 1)[1].split()
        with open("/proc/uptime", encoding="ascii") as f:
            uptime = float(f.read().split()[0])
        started = int(fields[19]) / os.sysconf("SC_CLK_TCK")  # field 22, starttime
    except (OSError, ValueError, IndexError):
        return 0.0
    return max(0.0, uptime - started)


class StartupTimes:
    """The start's parts, each with its start and end in ms from the process starting."""

    def __init__(self, age_s: float | None = None) -> None:
        age = process_age_s() if age_s is None else age_s
        self._zero = time.perf_counter() - age
        self.started_wall = time.time() - age  # the process's start, for other processes
        self._lock = threading.Lock()
        self._parts: dict[str, dict[str, Any]] = {}

    def now_ms(self) -> float:
        return round((time.perf_counter() - self._zero) * 1000, 1)

    def begin(self, name: str) -> None:
        with self._lock:
            # Once ready, the start is over: a warm-up run then, for a sample accepted later,
            # is not part of it.
            if name not in self._parts and "ready" not in self._parts:
                self._parts[name] = {"name": name, "start_ms": self.now_ms(), "end_ms": None}

    def end(self, name: str, error: str | None = None) -> None:
        with self._lock:
            part = self._parts.get(name)
            if part is None or part["end_ms"] is not None:
                return  # not begun, or this is a later run's end
            part["end_ms"] = self.now_ms()
            if error:
                part["error"] = error
        logger.log(
            logging.WARNING if error else logging.INFO,
            "Start-up part finished",
            extra={"part": name, "at_ms": part["end_ms"], "error": error},
        )

    def mark(self, name: str) -> None:
        """A moment rather than a part, such as the ready line: it begins and ends at once."""
        self.begin(name)
        self.end(name)

    def timed(self, name: str, fn: Callable[[], T]) -> Callable[[], T]:
        """`fn`, kept as the part `name` the first time it runs, with its error if it fails."""

        def run() -> T:
            self.begin(name)
            try:
                result = fn()
            except Exception as e:
                self.end(name, error=str(e) or type(e).__name__)
                raise
            self.end(name)
            return result

        return run

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            parts = sorted((dict(p) for p in self._parts.values()), key=lambda p: p["start_ms"])
        return {"started_wall": self.started_wall, "now_ms": self.now_ms(), "parts": parts}
