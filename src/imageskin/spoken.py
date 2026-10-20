"""Spoken questions heard in context (roadmap R24, Larry's test on PR #91): the browser's speech
recognition doesn't know the content's names and terms, and hears "Euler" as "Oiler" or
"Boiler". Before a spoken question is answered, the LLM is given the content's own words and
puts back any it misheard; a change is kept only when every word it adds is one of them."""

import logging
import re
import time
from collections import Counter
from collections.abc import Callable
from difflib import SequenceMatcher
from typing import Any

from imageskin.chat import LlmError

logger = logging.getLogger(__name__)

ALIKE = 0.5  # how alike a misheard word and the word put in its place are spelled, at least
MOST_WORDS = 100  # the content's words given to the LLM, the most used first
_WORD = re.compile(r"[^\W\d_][\w'’-]*")
_POSSESSIVE = re.compile(r"['’]s$")
# Capitalised at the start of a sentence, not because they are names or terms.
_COMMON = {
    "this", "that", "these", "those", "there", "their", "they", "then", "than", "what", "when",
    "where", "which", "while", "with", "from", "into", "each", "every", "some", "many", "most",
    "more", "also", "both", "here", "however", "thus", "such", "since", "after", "before",
    "about", "other", "only", "first", "second", "finally", "using", "given", "let", "for",
    "and", "the", "its", "his", "her", "our", "your", "but", "not", "all", "any", "how", "why",
}  # fmt: skip


def vocabulary(contents: list[dict[str, Any]]) -> list[str]:
    """The content's names and terms: every word of its titles, and the capitalised words of
    its summaries, the most used first."""
    counts: Counter[str] = Counter()
    spelled: dict[str, str] = {}

    def add(word: str) -> None:
        word = _POSSESSIVE.sub("", word)
        key = word.lower()
        if len(key) < 3 or key in _COMMON:
            return
        counts[key] += 1
        spelled.setdefault(key, word)

    def walk(entries: list[dict[str, Any]]) -> None:
        for entry in entries:
            for word in _WORD.findall(str(entry.get("title", ""))):
                add(word)
            for word in _WORD.findall(str(entry.get("summary", ""))):
                if word[0].isupper():
                    add(word)
            walk(entry.get("entries", []))

    for pdf in contents:
        walk(pdf.get("entries", []))
    return [spelled[k] for k, _ in counts.most_common(MOST_WORDS)]


def words_of(text: str) -> list[str]:
    return [_POSSESSIVE.sub("", w.lower()) for w in _WORD.findall(text)]


def sounds_like(word: str, dropped: list[str]) -> bool:
    """Whether a word put in is spelled like a word it replaced, or like the dropped words run
    together ("fun shun" for "function"): misheard words sound alike, and are mostly spelled
    alike ("Oiler" and "Euler" are 0.6 alike, "Boiler" and "function" 0.14)."""
    return any(
        SequenceMatcher(None, word, d).ratio() >= ALIKE for d in [*dropped, "".join(dropped)]
    )


def kept(heard: str, said: str, terms: list[str]) -> bool:
    """Whether the LLM's version only puts the content's words in place of misheard ones: the
    words are compared in order, so every word left as heard keeps its place (swapping who did
    what to whom changes the question; review on PR #91), and each run of words changed must
    be content words that sound like the words they replace, at most one fewer of them (two
    misheard words can be one term)."""
    known = {w for t in terms for w in words_of(t)}
    before, after = words_of(heard), words_of(said)
    changes = [
        (before[i1:i2], after[j1:j2])
        for op, i1, i2, j1, j2 in SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
        if op != "equal"
    ]
    return bool(changes) and all(
        added
        and len(dropped) <= len(added) + 1
        and all(w in known and sounds_like(w, dropped) for w in added)
        for dropped, added in changes
    )


def corrected(heard: str, terms: list[str], write: Callable[[str, list[str]], str]) -> str:
    """The spoken question with any misheard names or terms put back, or as it was heard."""
    if not terms:
        return heard
    instruction = (
        f"A participant asked a question out loud, and speech recognition wrote it down as:"
        f' "{heard}" Speech recognition often mishears names and terms, such as "Oiler" or "Boiler"'
        ' for "Euler". The names and terms of the subject are in the reference text. If a word'
        " in the question sounds like one of them and the question makes more sense with it,"
        " put that name or term in its place. Change nothing else. Say only the question."
    )
    start = time.monotonic()
    try:
        said = write(instruction, [", ".join(terms)]).strip().strip('"').strip()
    except LlmError as e:
        logger.error("Could not check a spoken question", extra={"error": str(e)})
        return heard
    ms = round((time.monotonic() - start) * 1000)
    if said != heard and kept(heard, said, terms):
        logger.info(
            "Spoken question corrected", extra={"heard": heard, "meant": said, "duration_ms": ms}
        )
        return said
    logger.info("Spoken question kept", extra={"heard": heard, "duration_ms": ms})
    return heard
