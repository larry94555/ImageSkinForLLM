"""Say it simpler (roadmap R157): the latest reply said again in simpler terms, by the LLM.

The button is offered only once the simpler version is known to say something new (R177):
after a few presses the LLM may give back the reply it was given, so `SimplerCheck` asks for it
ahead, and Say it simpler then says what it wrote."""

import logging
import re
import threading
import time
import unicodedata
from collections.abc import Callable
from difflib import SequenceMatcher

from imageskin.chat import LlmCancelled, LlmError, Teach, Turn, ask_stop, ms_since
from imageskin.lessons_ahead import sentences
from imageskin.teach import asks_simpler

logger = logging.getLogger(__name__)

# Two replies whose words are at least this alike say the same thing, so neither is a simpler
# way of saying the other: a word or two changed reads as the same reply (Larry, PR #211). At 0.75
# a simpler version changes at least about a quarter of the words.
SAME_WORDS = 0.75

INSTRUCTION = (
    "Say your last answer again in simpler terms, for someone new to the subject: in short"
    " sentences with everyday words, saying the same thing and adding nothing new. Don't ask me"
    " anything."
)


def latest_reply(turns: list[Turn]) -> str | None:
    return next((t.content for t in reversed(turns) if t.role == "assistant"), None)


def say_simpler(prompt: str, turns: list[Turn]) -> Teach | None:
    """What the LLM is asked for "Say it simpler" and the like, with the latest reply as its
    material; None for any other prompt, or before there is a reply."""
    if not asks_simpler(prompt):
        return None
    last = latest_reply(turns)
    if last is None:
        return None
    logger.info("Simpler reply asked", extra={"reply_chars": len(last)})
    return Teach(INSTRUCTION, [last])


def words(text: str) -> list[str]:
    """The text's words, without case, punctuation or apostrophes, so curly and straight
    quotes ("wouldn’t", "wouldn't") read the same (Larry's test of PR #211)."""
    text = re.sub(r"['’‘`]", "", unicodedata.normalize("NFKC", text).casefold())
    return re.findall(r"\w+", text)


def same(a: str, b: str) -> bool:
    """Whether two replies say the same thing, word for word or nearly."""
    return SequenceMatcher(None, words(a), words(b), autojunk=False).ratio() >= SAME_WORDS


def plainer(simpler: str, reply: str) -> bool:
    """Whether `simpler` is shorter than `reply`, or uses shorter words: a version that is only
    different isn't simpler (Larry's test of PR #211)."""
    a, b = words(simpler), words(reply)
    if not a or not b:
        return False
    return len(a) < len(b) or sum(map(len, a)) / len(a) < sum(map(len, b)) / len(b)


class _NotChecked(Exception):
    """The simpler version wasn't written: cut off, or the LLM failed."""


class SimplerCheck:
    """Whether Say it simpler would say something new for the latest reply (R177), from a
    simpler version written ahead by `write` (the LLM's answer to a `Teach`, after the chat's
    requests). It is new only when it is shorter or plainer than the reply (`plainer`) and its
    words aren't those of a reply already in the conversation, or nearly (`same`); a latest
    reply that is itself one said before has none. Only the latest reply's check is kept, and
    `forget` cuts off one being written, as a new prompt makes it out of date."""

    def __init__(self, write: Callable[[Teach], str]) -> None:
        self._write = write
        self._lock = threading.Lock()  # one check at a time
        self._kept: tuple[str, str | None] | None = None  # the reply and its simpler version
        self._stop = threading.Event()

    def check(self, turns: list[Turn]) -> bool:
        """Whether the latest reply has a simpler version that says something new."""
        last = latest_reply(turns)
        if last is None:
            return False
        earlier = [t.content for t in turns if t.role == "assistant"][:-1]
        if any(same(last, e) for e in earlier):
            # Said already: it was asked more simply and came back the same (R177).
            logger.info("Simpler reply not offered", extra={"reason": "said before"})
            return False
        with self._lock:
            kept = self._kept
            if kept is None or kept[0] != last:
                self._stop = threading.Event()
                try:
                    kept = self._kept = (last, self._written(last, turns))
                except _NotChecked:
                    return False  # not kept, so the next check asks again
        return kept[1] is not None

    def _written(self, last: str, turns: list[Turn]) -> str | None:
        start = time.perf_counter()
        token = ask_stop.set(self._stop)  # a new prompt cuts it off (`forget`)
        try:
            text = self._write(Teach(INSTRUCTION, [last])).strip()
        except LlmCancelled:
            logger.info("Simpler reply check cut off", extra={"duration_ms": ms_since(start)})
            raise _NotChecked from None
        except LlmError as e:
            logger.error(
                "Could not check for a simpler reply",
                extra={"error": str(e), "duration_ms": ms_since(start)},
            )
            raise _NotChecked from e
        finally:
            ask_stop.reset(token)
        said = [t.content for t in turns if t.role == "assistant"]
        new = plainer(text, last) and not any(same(text, s) for s in said)
        logger.info(
            "Simpler reply checked",
            extra={
                "simpler": new,
                "reply_chars": len(last),
                "simpler_chars": len(text),
                "duration_ms": ms_since(start),
            },
        )
        return text if new else None

    def ready(self, turns: list[Turn]) -> list[str] | None:
        """The latest reply's simpler version as sentences, when it was checked and is new."""
        last = latest_reply(turns)
        kept = self._kept
        if last is None or kept is None or kept[0] != last or kept[1] is None:
            return None
        return sentences(kept[1])

    def forget(self) -> None:
        """Cut off a check being written: a prompt is being answered."""
        self._stop.set()
