"""What the app is doing while it thinks about a prompt (R134c): a few plain words for the stage
it is at, and how long it has taken, so the chat can show them while the user waits, and say
afterwards how long the thinking took. The words are for anyone, with no numbers or technical
terms (Larry, testing PR #179). Each prompt being answered has one `Thinking`, set on its thread
with `current`; the steps that take time call `stage`, which does nothing when no prompt is being
followed (a lesson written ahead, a wiki build)."""

import logging
import time
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)

# What the stage says before any step has said what it is doing.
STARTING = "Getting started"
# Once the LLM has started writing.
WRITING = "Writing the answer"


class Thinking:
    """One prompt's thinking. Written by the thread answering it and read by the chat's
    requests for it: the stage and when it started are replaced together, as one tuple."""

    def __init__(self, now: float | None = None) -> None:
        self.started_at = time.perf_counter() if now is None else now
        self._stage: tuple[str, float] = (STARTING, self.started_at)

    def stage(self, name: str) -> None:
        """Start a stage; the one under way again changes nothing."""
        was, since = self._stage
        if name == was:
            return
        now = time.perf_counter()
        logger.debug(
            "Thinking stage",
            extra={"stage": name, "after": was, "after_ms": round((now - since) * 1000)},
        )
        self._stage = (name, now)

    def elapsed(self) -> float:
        """Seconds since the prompt arrived."""
        return time.perf_counter() - self.started_at

    def now(self) -> dict[str, Any]:
        """The stage and the seconds the whole thinking has taken."""
        return {"stage": self._stage[0], "elapsed_s": round(self.elapsed(), 1)}


# The prompt being answered on this thread, if its thinking is followed.
current: ContextVar[Thinking | None] = ContextVar("thinking", default=None)


def stage(name: str) -> None:
    """Start a stage of the prompt being answered, if any."""
    thinking = current.get()
    if thinking is not None:
        thinking.stage(name)


def took() -> float | None:
    """Seconds the prompt being answered has taken so far, to one decimal; None if none is."""
    thinking = current.get()
    return None if thinking is None else round(thinking.elapsed(), 1)
