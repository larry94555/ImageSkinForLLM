"""Splits a reply into sentences while the LLM is still writing it (roadmap R20, item 12), so
each sentence can be spoken as soon as it is complete. Pure Python, no logging: the caller logs.

A sentence ends at ".", "!", "?" or "…" (with any closing quotes or brackets after it) followed by
a space, at a blank line, and at the end of a heading or list item. The end is only known once the
next word starts, so "Dr. Smith", "e.g. this", "3.5", "1. First" and "the U.S. team" don't split
(nor, as a cost of that, does "in the U.S. The"). Code blocks and inline code are kept whole, by
the same rules as speech_text.py, so each sentence can be cleaned for speech on its own.
"""

import re

from imageskin.speech_text import CODE_FENCE, INLINE_CODE, closing_fence

# Words that end with a full stop but don't end a sentence.
ABBREVIATIONS = frozenset(
    "mr mrs ms dr prof sr jr st vs etc e.g i.e cf approx no fig vol jan feb mar apr jun jul aug"
    " sep sept oct nov dec mon tue wed thu fri sat sun".split()
)
_END = re.compile(r"([.!?…]+)([\"'”’)\]]*)\s+")
# A blank line, or a line break before a list item or heading.
_BREAK = re.compile(r"\n[ \t]*\n\s*|\n(?=[ \t]*(?:\d+[.)]|[-*+]|#{1,6})[ \t])")
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t].*\n", re.M)  # a heading line is a sentence


def _in_code(text: str, at: int) -> bool:
    """Whether `at` is inside inline code, or after a backtick that may yet start some: inline
    code doesn't run past its line, so that is only while the line is still being written."""
    start = text.rfind("\n", 0, at) + 1
    end = text.find("\n", at)
    line = text[start:] if end < 0 else text[start:end]
    at -= start
    spans = [m.span() for m in INLINE_CODE.finditer(line)]
    if any(a <= at < b for a, b in spans):
        return True
    if end >= 0:
        return False
    outside = "".join(" " if any(a <= i < b for a, b in spans) else c for i, c in enumerate(line))
    return "`" in outside[:at]


def _not_an_end(text: str, end: re.Match[str], following: str) -> bool:
    """Whether the stop at `end` is inside the sentence rather than closing it."""
    if end.group(1) in ("...", "…"):
        return following[:1].islower()  # "Wait... really?" goes on
    if end.group(1) != ".":
        return False  # "!" and "?" always close
    line_start = text.rfind("\n", 0, end.start(1)) + 1
    if re.fullmatch(r"[ \t]*\d+", text[line_start : end.start(1)]):
        return True  # a list number, as in "1. First"
    word = re.search(r"(\S+)\.$", text[: end.start(1) + 1])
    if word is None:
        return False
    stem = word.group(1).lower().lstrip("\"'“‘([")
    if stem in ABBREVIATIONS or re.fullmatch(r"[a-z]", stem):  # an initial, as in "J. Smith"
        return True
    if re.fullmatch(r"(?:[a-z]\.)+[a-z]", stem):  # "U.S", "a.m"
        return True
    return following[:1].islower() or following[:1].isdigit()


class SentenceSplitter:
    """Feed it text as it arrives; it hands back each sentence once it is complete."""

    def __init__(self) -> None:
        self._text = ""

    def feed(self, chunk: str) -> list[str]:
        """Add text; return the sentences now complete, in order."""
        self._text += chunk
        sentences: list[str] = []
        while (cut := self._next_cut()) is not None:
            sentence, self._text = self._text[:cut].strip(), self._text[cut:]
            if sentence:
                sentences.append(sentence)
        return sentences

    def flush(self) -> list[str]:
        """The reply has ended: return what is left as the last sentence."""
        rest, self._text = self._text.strip(), ""
        return [rest] if rest else []

    def _next_cut(self) -> int | None:
        """Where the first complete sentence ends, or None if none is complete yet."""
        text = self._text
        fence = CODE_FENCE.search(text)
        if fence and not text[: fence.start()].strip():
            # A code block is a sentence of its own, once its closing fence line is complete.
            opened = text.find("\n", fence.end())
            close = None if opened < 0 else closing_fence(fence["fence"]).search(text, opened + 1)
            if close is None:
                return None
            done = text.find("\n", close.end())
            return None if done < 0 else done + 1
        limit = fence.start() if fence else len(text)  # cut before a code block
        head = text[:limit]
        ends = sorted(
            [*_END.finditer(head), *_BREAK.finditer(head), *_HEADING.finditer(head)],
            key=lambda m: m.start(),
        )
        for end in ends:
            following = text[end.end() :]
            if end.re is _END:
                if not following.strip():
                    return None  # the next word hasn't started: it may be "Dr. Smith"
                if _in_code(text, end.start(1)):
                    continue
                if _not_an_end(text, end, following):
                    continue
            return end.end()
        return limit if fence else None
