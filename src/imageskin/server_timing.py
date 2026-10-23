"""Each step's time in a request, sent back in its `Server-Timing` header (roadmap R96b), so
`imageskin time-setup`, and the browser's developer tools, see where an upload's time went
(Larry's timings 8 and 9) without reading the log."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_steps: ContextVar[dict[str, float] | None] = ContextVar("server_timing_steps", default=None)


@contextmanager
def collecting() -> Iterator[dict[str, float]]:
    """Collect the steps timed in this request, as milliseconds by name."""
    steps: dict[str, float] = {}
    token = _steps.set(steps)
    try:
        yield steps
    finally:
        _steps.reset(token)


@contextmanager
def step(name: str) -> Iterator[None]:
    """Time the block as step `name`, added to any time it already has; outside a request
    that collects steps, it costs one clock read."""
    start = time.perf_counter()
    try:
        yield
    finally:
        steps = _steps.get()
        if steps is not None:
            steps[name] = steps.get(name, 0.0) + (time.perf_counter() - start) * 1000


def header(steps: dict[str, float]) -> str:
    """The steps as a Server-Timing header: `convert;dur=12.3, faces;dur=402.0`."""
    return ", ".join(f"{name};dur={ms:.1f}" for name, ms in steps.items())


def parse(value: str | None) -> dict[str, float]:
    """A Server-Timing header back into milliseconds by name; entries without dur are left out."""
    steps: dict[str, float] = {}
    for entry in (value or "").split(","):
        name, *params = (p.strip() for p in entry.split(";"))
        for p in params:
            key, _, ms = p.partition("=")
            if name and key == "dur":
                try:
                    steps[name] = float(ms)
                except ValueError:
                    pass
    return steps
