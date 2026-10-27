"""Say it simpler (roadmap R157): the latest reply said again in simpler terms, by the LLM."""

import logging

from imageskin.chat import Teach, Turn
from imageskin.teach import asks_simpler

logger = logging.getLogger(__name__)

INSTRUCTION = (
    "Say your last answer again in simpler terms, for someone new to the subject: in short"
    " sentences with everyday words, saying the same thing and adding nothing new. Don't ask me"
    " anything."
)


def say_simpler(prompt: str, turns: list[Turn]) -> Teach | None:
    """What the LLM is asked for "Say it simpler" and the like, with the latest reply as its
    material; None for any other prompt, or before there is a reply."""
    if not asks_simpler(prompt):
        return None
    last = next((t.content for t in reversed(turns) if t.role == "assistant"), None)
    if last is None:
        return None
    logger.info("Simpler reply asked", extra={"reply_chars": len(last)})
    return Teach(INSTRUCTION, [last])
