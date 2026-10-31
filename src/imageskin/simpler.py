"""Say it simpler (roadmap R157): the latest reply said again in simpler terms, by the LLM."""

import logging
from collections.abc import Callable

from imageskin.chat import Teach, Turn
from imageskin.customization import SIMPLER
from imageskin.teach import SIMPLER_GUIDELINES, asks_simpler, simpler_guidelines

logger = logging.getLogger(__name__)

INSTRUCTION = (
    "Say your last answer again in simpler terms, for someone new to the subject: in short"
    " sentences with everyday words, saying the same thing and adding nothing new. Don't ask me"
    " anything."
)


def instruction(guidelines: str = SIMPLER) -> str:
    """What the LLM is asked to say its last answer again with, with the Say it simpler
    guidelines (R200): as shipped, word for word as before; edited, they say how."""
    if guidelines == SIMPLER:
        return INSTRUCTION
    return f"Say your last answer again, more simply. {SIMPLER_GUIDELINES} {guidelines}"


def say_simpler(
    prompt: str, turns: list[Turn], guidelines: Callable[[], str] = lambda: SIMPLER
) -> Teach | None:
    """What the LLM is asked for "Say it simpler" and the like, with the latest reply as its
    material and Say it simpler's guidelines as they are now (R200); None for any other prompt,
    or before there is a reply."""
    if not asks_simpler(prompt):
        return None
    last = next((t.content for t in reversed(turns) if t.role == "assistant"), None)
    if last is None:
        return None
    logger.info("Simpler reply asked", extra={"reply_chars": len(last)})
    now = simpler_guidelines(guidelines)
    asked = instruction(now)
    return Teach(
        asked,
        [last],
        unguided=None if asked == INSTRUCTION else INSTRUCTION,
        feature="say it simpler",
    )
