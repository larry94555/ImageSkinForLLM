"""Where the time goes in a reply, as the server sees it (roadmap R96): the waits before the
prompt reaches the LLM, the LLM's first token, first sentence and last token, and llama-server's
own timings. The chat API returns them with the reply, so `imageskin time-reply` can measure a
reply without the browser.

Every step between a prompt's arrival and its reply is also kept, with its start, end and
duration, and logged as `Thinking step` when it ends (R134c), so a long "Thinking…" can be
broken down step by step; the warm-up's own parts are kept too, for a prompt that waited for it."""

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# The fields of llama-server's `timings` (sent with the last piece of a streamed reply) that are
# kept: tokens read from the prompt and their speed, tokens reused from its cache, and tokens
# written and their speed.
LLM_TIMING_KEYS = (
    "cache_n",
    "prompt_n",
    "prompt_ms",
    "prompt_per_second",
    "predicted_n",
    "predicted_ms",
    "predicted_per_second",
)


@dataclass
class ReplyTimes:
    """One prompt's times, as time.perf_counter() seconds (the clock of the clips' times), or
    milliseconds where the name says so. A time is None when it didn't happen: a reply made
    without the LLM has no tokens."""

    received_at: float
    waited_warm_up_ms: float = 0.0  # for the replies' warm-up after a sample was accepted
    waited_turn_ms: float = 0.0  # behind the prompt before, or the wiki's LLM request
    history_tokens: int | None = None  # the conversation sent with the prompt
    looked_up_ms: float | None = None  # looking the prompt up in the wiki and PDFs (R96a)
    asked_tokens: int | None = None  # the prompt as sent, with what was found in the content
    prompt_sent_at: float | None = None
    first_token_at: float | None = None
    first_sentence_at: float | None = None
    last_token_at: float | None = None
    answered_at: float | None = None
    llm: dict[str, Any] | None = None  # llama-server's own timings; a provider sends none
    # Each step of the thinking, in the order they ended, in ms from `received_at` (R134c).
    steps: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# The prompt being answered on this thread, if its times are being kept.
current: ContextVar[ReplyTimes | None] = ContextVar("reply_times", default=None)


def note(**times: Any) -> None:
    """Set these fields on the prompt being answered, if any. A time already set is kept, so
    only the first token or sentence counts."""
    kept = current.get()
    if kept is None:
        return
    for name, value in times.items():
        if getattr(kept, name) is None or name in ("last_token_at", "answered_at", "llm"):
            setattr(kept, name, value)


def note_now(name: str) -> None:
    """Note that `name` happened now."""
    note(**{name: time.perf_counter()})


def note_llm(timings: object) -> None:
    """Keep llama-server's timings for the prompt being answered, when it sent them."""
    if isinstance(timings, dict):
        note(llm={k: timings[k] for k in LLM_TIMING_KEYS if k in timings})


# The LLM requests made on this thread, while a list is set here: the wiki's build keeps each
# part's and outline step's llama-server timings this way (R96a).
requests: ContextVar[list[dict[str, Any]] | None] = ContextVar("llm_requests", default=None)


def note_request(timings: object, duration_ms: float) -> None:
    """Keep one LLM request's time and llama-server's timings, if requests are being kept."""
    kept = requests.get()
    if kept is None:
        return
    llm = (
        {k: timings[k] for k in LLM_TIMING_KEYS if k in timings}
        if isinstance(timings, dict)
        else {}
    )
    kept.append({"duration_ms": duration_ms, **llm})


def ms_from(times: ReplyTimes, at: float) -> float:
    return round((at - times.received_at) * 1000, 1)


def add_step(name: str, start: float, end: float, **detail: Any) -> None:
    """Keep a step of the prompt being answered, from `start` to `end` (time.perf_counter()
    seconds), and log it (R134c). Nothing is kept when no prompt is being timed."""
    kept = current.get()
    if kept is None:
        return
    step = {
        "step": name,
        "start_ms": ms_from(kept, start),
        "end_ms": ms_from(kept, end),
        "duration_ms": round((end - start) * 1000, 1),
        **detail,
    }
    kept.steps.append(step)
    logger.info("Thinking step", extra=step)


@contextmanager
def step(name: str, **detail: Any) -> Iterator[None]:
    """Time what is done inside as a step of the prompt being answered (R134c). A step that
    fails is kept too, with its error."""
    start = time.perf_counter()
    try:
        yield
    except BaseException as e:
        add_step(name, start, time.perf_counter(), error=type(e).__name__, **detail)
        raise
    add_step(name, start, time.perf_counter(), **detail)


def log_steps(times: ReplyTimes, **detail: Any) -> None:
    """One line for the whole prompt once it is answered: how many steps, and the longest, so
    where the time went shows at a glance (R134c)."""
    longest = max(times.steps, key=lambda s: s["duration_ms"], default=None)
    logger.info(
        "Thinking steps",
        extra={
            "steps": len(times.steps),
            "longest_step": None if longest is None else longest["step"],
            "longest_ms": None if longest is None else longest["duration_ms"],
            "duration_ms": None if times.answered_at is None else ms_from(times, times.answered_at),
            **detail,
        },
    )


class Parts:
    """The parts of a run done in the background, such as the replies' warm-up, as
    time.perf_counter() seconds, so a prompt that waited for it can say which parts it waited
    for (R134c). Set as `parts` on the thread doing the run; `part` keeps nothing otherwise."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._kept: list[tuple[str, float, float | None]] = []

    def clear(self) -> None:
        with self._lock:
            self._kept = []

    def begin(self, name: str) -> int:
        with self._lock:
            self._kept.append((name, time.perf_counter(), None))
            return len(self._kept) - 1

    def end(self, index: int) -> None:
        with self._lock:
            if index < len(self._kept):
                name, start, _ = self._kept[index]
                self._kept[index] = (name, start, time.perf_counter())

    def during(self, start: float, end: float) -> list[tuple[str, float, float]]:
        """The parts that ran between `start` and `end`, cut to that time: the part of the wait
        each one took. A part not finished by `end` counts until `end`."""
        with self._lock:
            kept = list(self._kept)
        found = []
        for name, began, ended in kept:
            ended = end if ended is None else ended
            if began < end and ended > start:
                found.append((name, max(began, start), min(ended, end)))
        return found


# The background run whose parts are being kept on this thread, if any.
parts: ContextVar[Parts | None] = ContextVar("parts", default=None)


@contextmanager
def part(name: str) -> Iterator[None]:
    """Keep what is done inside as a part of the run being timed on this thread, if any."""
    kept = parts.get()
    if kept is None:
        yield
        return
    index = kept.begin(name)
    try:
        yield
    finally:
        kept.end(index)
