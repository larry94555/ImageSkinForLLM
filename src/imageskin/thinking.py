"""What the app is doing while it thinks about a prompt (R134c): the stage it is at, a line of
detail about it, and how long it has taken, so the chat can show them while the user waits, and
say afterwards how long the thinking took. Each prompt being answered has one `Thinking`, set on
its thread with `current`; the steps that take time call `stage` and `wrote`, which do nothing
when no prompt is being followed (a lesson written ahead, a wiki build)."""

import logging
import time
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)

# What the stage says before any step has said what it is doing.
STARTING = "Starting to think"


class Thinking:
    """One prompt's thinking. Written by the thread answering it and read by the chat's
    requests for it: the stage and its detail are replaced together, as one tuple, so a read
    never sees one stage's name with another's detail."""

    def __init__(self, now: float | None = None) -> None:
        self.started_at = time.perf_counter() if now is None else now
        self._stage: tuple[str, str | None, float] = (STARTING, None, self.started_at)
        self._words = 0

    def stage(self, name: str, detail: str | None = None) -> None:
        """Start a stage, or change the detail of the one under way."""
        now = time.perf_counter()
        was, _, since = self._stage
        if name != was:
            logger.debug(
                "Thinking stage",
                extra={"stage": name, "after": was, "after_ms": round((now - since) * 1000)},
            )
            self._stage = (name, detail, now)
        else:
            self._stage = (name, detail, since)

    def wrote(self, piece: str) -> None:
        """A piece of the reply came from the LLM: the stage says how many words so far."""
        self._words += len(piece.split())
        self.stage("Writing the reply", f"{self._words} words so far")

    def elapsed(self) -> float:
        """Seconds since the prompt arrived."""
        return time.perf_counter() - self.started_at

    def now(self) -> dict[str, Any]:
        """The stage, its detail and the time it and the whole thinking have taken, in seconds."""
        name, detail, since = self._stage
        at = time.perf_counter()
        return {
            "stage": name,
            "detail": detail,
            "stage_s": round(at - since, 1),
            "elapsed_s": round(at - self.started_at, 1),
        }


# The prompt being answered on this thread, if its thinking is followed.
current: ContextVar[Thinking | None] = ContextVar("thinking", default=None)


def stage(name: str, detail: str | None = None) -> None:
    """Start a stage of the prompt being answered, if any."""
    thinking = current.get()
    if thinking is not None:
        thinking.stage(name, detail)


def wrote(piece: str) -> None:
    """Count a piece of the reply written for the prompt being answered, if any."""
    thinking = current.get()
    if thinking is not None:
        thinking.wrote(piece)


def took() -> float | None:
    """Seconds the prompt being answered has taken so far, to one decimal; None if none is."""
    thinking = current.get()
    return None if thinking is None else round(thinking.elapsed(), 1)


def plural(n: int, word: str) -> str:
    """'1 passage', '3 passages'."""
    return f"{n} {word}{'' if n == 1 else 's'}"
