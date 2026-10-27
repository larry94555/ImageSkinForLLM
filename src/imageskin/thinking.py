"""What the app is doing while it thinks about a prompt (R134c): a few plain words for the stage
it is at, and how long it has taken, so the chat can show them while the user waits, and say
afterwards how long the thinking took. The words are for anyone, with no numbers or technical
terms, and never stay the same for more than 10 seconds: a stage that goes on longer moves on to
the next of its phrases every `PHRASE_S` seconds (Larry, testing PR #179). Each prompt being
answered has one `Thinking`, set on its thread with `current`; the steps that take time call
`stage`, which does nothing when no prompt is being followed (a lesson written ahead, a wiki
build). The replies' warm-up, which a prompt can wait minutes for after a start, says each of its
steps with `getting_ready`."""

import logging
import time
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)

# What the stage says before any step has said what it is doing.
STARTING = "Getting started"
# While the LLM reads the prompt, and once it has started writing.
ANSWERING = "Thinking about the answer"
WRITING = "Writing the answer"
# Waiting for the replies' warm-up, before it has said which step it is at.
GETTING_READY = "Getting ready"
# The warm-up's steps (`getting_ready`).
WAKING_VOICE = "Waking up the voice"
FIRST_WORD = "Practising a first word"
FACE = "Getting the face ready"
INSTRUCTIONS = "Reading my instructions"  # the LLM reading the system prompt

# How long one phrase is shown before the next: within the 5 to 10 seconds Larry asked for.
PHRASE_S = 8.0
# The phrases each stage goes through while it lasts, its own name first; the last ones repeat.
# A stage not listed keeps its name, which is fine for a step that takes a moment.
PHRASES: dict[str, list[str]] = {
    GETTING_READY: [GETTING_READY, "Waking everything up", "Setting things up"],
    WAKING_VOICE: [WAKING_VOICE, "Loading the voice", "Warming up the voice"],
    FIRST_WORD: [FIRST_WORD, "Getting the lips moving", "Checking the voice and face"],
    FACE: [FACE, "Making the face look natural", "Getting ready to listen", "Setting up the face"],
    INSTRUCTIONS: [INSTRUCTIONS, "Getting my thoughts in order", "Still getting ready"],
    "Finishing the last answer": [
        "Finishing the last answer",
        "Finishing something else first",
        "Next in line",
        "Still finishing up",
    ],
    "Remembering our conversation": [
        "Remembering our conversation",
        "Going over what we said",
        "Keeping the main points",
    ],
    "Looking through your documents": [
        "Looking through your documents",
        "Finding the right pages",
        "Picking the best parts",
    ],
    ANSWERING: [
        "Reading your question",
        "Reading what I found",
        ANSWERING,
        "Weighing what matters most",
        "Planning the answer",
        "Still thinking it through",
    ],
    WRITING: [WRITING, "Choosing the words", "Writing the next part", "Still writing"],
}


def phrase(stage: str, seconds: float) -> str:
    """What to say `seconds` into a stage: its phrases in turn, `PHRASE_S` each, the list
    starting again (after its first) once it runs out."""
    phrases = PHRASES.get(stage, [stage])
    n = int(seconds // PHRASE_S)
    if n < len(phrases):
        return phrases[n]
    later = phrases[1:] or phrases
    return later[(n - len(phrases)) % len(later)]


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
        """What to say now about the stage, and the seconds the whole thinking has taken."""
        name, since = self._stage
        at = time.perf_counter()
        return {"stage": phrase(name, at - since), "elapsed_s": round(at - self.started_at, 1)}


# The prompt being answered on this thread, if its thinking is followed.
current: ContextVar[Thinking | None] = ContextVar("thinking", default=None)

# The step the replies' warm-up is at, for a prompt waiting for it; one warm-up runs at a time.
_ready_step = [GETTING_READY]


def getting_ready(step: str) -> None:
    """Say which step the replies' warm-up is at."""
    _ready_step[0] = step
    logger.debug("Warm-up step", extra={"step": step})


def ready_step() -> str:
    """The step the replies' warm-up is at."""
    return _ready_step[0]


def stage(name: str) -> None:
    """Start a stage of the prompt being answered, if any."""
    thinking = current.get()
    if thinking is not None:
        thinking.stage(name)


def took() -> float | None:
    """Seconds the prompt being answered has taken so far, to one decimal; None if none is."""
    thinking = current.get()
    return None if thinking is None else round(thinking.elapsed(), 1)
