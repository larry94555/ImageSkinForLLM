"""What the app is doing while it thinks about a prompt (R134c): a few plain words for the stage
it is at, and how long it has taken, so the chat can show them while the user waits, and say
afterwards how long the thinking took. The words are a tutor's, speaking to a student, with no
technical terms, and they show progress: each stage says its phrases once, `PHRASE_S` seconds
each, and never goes back to one it said (Larry, testing PR #179). A stage that goes on longer
counts its parts: the real ones where the work can be counted (the video frames made, the
sentences written), otherwise one part each `PHRASE_S`, out of how many the same stage took last
time. Each prompt being answered has one `Thinking`, set on its thread with `current`; the steps
that take time call `stage`, which does nothing when no prompt is being followed (a lesson
written ahead, a wiki build). The replies' warm-up, which a prompt can wait minutes for after a
start, says each of its steps with `getting_ready`, and its counted work with `ready_part`."""

import json
import logging
import math
import threading
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)

# What the stage says before any step has said what it is doing.
STARTING = "Getting started"
# While the LLM reads the prompt, and once it has started writing.
ANSWERING = "Thinking about the answer"
WRITING = "Writing my answer"
# Waiting for the replies' warm-up, before it has said which step it is at.
GETTING_READY = "Getting ready for our lesson"
# The warm-up's steps (`getting_ready`): the voice loaded, a first word said, the face at rest
# made (the idle video), and the LLM reading the system prompt.
WAKING_VOICE = "Getting ready to talk with you"
FIRST_WORD = "Practising my first words"
FACE = "Getting settled in front of you"
INSTRUCTIONS = "Reviewing my lesson notes"
# The warm-up remembers how long its own steps take; a prompt waiting for one doesn't.
WARM_UP_STEPS = {GETTING_READY, WAKING_VOICE, FIRST_WORD, FACE, INSTRUCTIONS}

# How long one phrase or part is shown before the next: within the 5 to 10 seconds Larry asked
# for.
PHRASE_S = 8.0
# Work that can be counted, as the frames of a video, is shown in this many parts.
PARTS = 10
# The phrases each stage says in turn while it lasts, said once each. A stage not listed keeps
# its name, which is fine for a step that takes a moment.
PHRASES: dict[str, list[str]] = {
    GETTING_READY: [GETTING_READY, "Setting up my desk", "Getting my things together"],
    WAKING_VOICE: [WAKING_VOICE, "Getting ready to answer you"],
    FIRST_WORD: [FIRST_WORD, "Warming up to talk"],
    FACE: [FACE, "Getting comfortable"],
    INSTRUCTIONS: [INSTRUCTIONS, "Going over today's plan"],
    "Finishing my last answer": ["Finishing my last answer", "You're next in line"],
    "Remembering what we talked about": [
        "Remembering what we talked about",
        "Going over our lesson so far",
    ],
    "Looking through the course material": [
        "Looking through the course material",
        "Finding the right pages",
    ],
    ANSWERING: ["Reading your question", ANSWERING, "Planning how to explain it"],
    WRITING: [WRITING],
}


class Part(NamedTuple):
    """How far a stage's work has come: `done` of `total`, or `done` so far when the total
    isn't known."""

    done: int
    total: int | None = None


# How long each stage took the last time it ran, in seconds, to count the parts of one whose work
# can't be counted; kept in the file `remember_in` names, from one start to the next, since the
# warm-up runs once a start.
_usual: dict[str, float] = {}
_usual_file: list[Path | None] = [None]
_usual_lock = threading.Lock()


def remember_in(path: Path) -> None:
    """Keep how long the stages take in `path`, reading what it has."""
    with _usual_lock:
        _usual_file[0] = path
        _usual.clear()
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            logger.warning("Could not read how long thinking took", extra={"error": str(e)})
            return
        if isinstance(saved, dict):
            _usual.update(
                {
                    k: float(v)
                    for k, v in saved.items()
                    if isinstance(v, int | float) and not isinstance(v, bool) and v > 0
                }
            )


def usual(stage: str) -> float | None:
    """Seconds the stage took last time, if it is known."""
    with _usual_lock:
        return _usual.get(stage)


def _took(stage: str, seconds: float) -> None:
    """Remember how long a stage took, for the next time. Only the stages that say their parts
    once their phrases are said: the others are over before their phrases are."""
    if stage not in PHRASES or seconds < PHRASE_S:
        return
    with _usual_lock:
        _usual[stage] = round(seconds, 1)
        path = _usual_file[0]
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(_usual), encoding="utf-8")
        except OSError as e:
            logger.warning("Could not keep how long thinking took", extra={"error": str(e)})


def say(stage: str, seconds: float, part: Part | None = None) -> str:
    """What to say `seconds` into a stage: its phrases in turn, `PHRASE_S` each and each once.
    Counted work says its part all along; other work, once its phrases are said, says the part
    of the time it took last time it has reached."""
    phrases = PHRASES.get(stage, [stage])
    n = int(seconds // PHRASE_S)
    words = phrases[min(n, len(phrases) - 1)]
    if part is not None:
        if part.total:
            shown = min(PARTS, max(1, math.ceil(part.done / part.total * PARTS)))
            return f"{words}, part {shown} of {PARTS}"
        return f"{words}, part {max(1, part.done)}"
    if n < len(phrases) or stage not in PHRASES:
        return words
    k = n + 1
    took = usual(stage)
    expected = None if took is None else math.ceil(took / PHRASE_S)
    if expected is not None and k <= expected:
        return f"{words}, part {k} of about {expected}"
    if expected is not None:
        return f"{words}, part {k}, longer than last time"
    return f"{words}, part {k}"


class Thinking:
    """One prompt's thinking. Written by the thread answering it and read by the chat's
    requests for it: the stage, when it started and its part are replaced together, as one
    tuple."""

    def __init__(self, now: float | None = None) -> None:
        self.started_at = time.perf_counter() if now is None else now
        self._stage: tuple[str, float, Part | None] = (STARTING, self.started_at, None)

    def stage(self, name: str, since: float | None = None, part: Part | None = None) -> None:
        """Start a stage, at `since` if it began before this prompt followed it (a step of the
        warm-up); the one under way again only takes its new part."""
        was, started, _ = self._stage
        if name == was:
            self._stage = (name, started, part)
            return
        now = time.perf_counter()
        if was not in WARM_UP_STEPS:
            _took(was, now - started)
        logger.debug(
            "Thinking stage",
            extra={"stage": name, "after": was, "after_ms": round((now - started) * 1000)},
        )
        self._stage = (name, now if since is None else since, part)

    def done(self) -> None:
        """The reply is in: remember how long its last stage took."""
        name, started, _ = self._stage
        if name not in WARM_UP_STEPS:
            _took(name, time.perf_counter() - started)

    def elapsed(self) -> float:
        """Seconds since the prompt arrived."""
        return time.perf_counter() - self.started_at

    def now(self) -> dict[str, Any]:
        """What to say now about the stage, and the seconds the whole thinking has taken."""
        name, since, part = self._stage
        at = time.perf_counter()
        return {"stage": say(name, at - since, part), "elapsed_s": round(at - self.started_at, 1)}


# The prompt being answered on this thread, if its thinking is followed.
current: ContextVar[Thinking | None] = ContextVar("thinking", default=None)


class ReadyStep(NamedTuple):
    """The step the replies' warm-up is at, when it began, its part, and its thread."""

    name: str
    since: float
    part: Part | None
    thread: int


# One warm-up runs at a time.
_ready = [ReadyStep(GETTING_READY, time.perf_counter(), None, 0)]


def getting_ready(step: str) -> None:
    """Say which step the replies' warm-up is at, on the warm-up's thread."""
    was = _ready[0]
    now = time.perf_counter()
    if was.thread == threading.get_ident() and was.name != step:
        _took(was.name, now - was.since)
    _ready[0] = ReadyStep(step, now, None, threading.get_ident())
    logger.debug("Warm-up step", extra={"step": step})


def ready_part(done: int, total: int) -> None:
    """Say how far the warm-up's step has come, as frames made of a video's. Only on the
    warm-up's own thread: the same work for a reply says nothing."""
    was = _ready[0]
    if was.thread == threading.get_ident():
        _ready[0] = was._replace(part=Part(done, total))


def ready_step() -> ReadyStep:
    """The step the replies' warm-up is at."""
    return _ready[0]


def warm_up_ended() -> None:
    """The warm-up is over: remember how long its last step took."""
    was = _ready[0]
    if was.thread == threading.get_ident():
        _took(was.name, time.perf_counter() - was.since)
        _ready[0] = was._replace(thread=0)


def stage(name: str, part: Part | None = None, since: float | None = None) -> None:
    """Start a stage of the prompt being answered, if any, or say its part."""
    thinking = current.get()
    if thinking is not None:
        thinking.stage(name, since, part)


def took() -> float | None:
    """Seconds the prompt being answered has taken so far, to one decimal; None if none is."""
    thinking = current.get()
    return None if thinking is None else round(thinking.elapsed(), 1)
