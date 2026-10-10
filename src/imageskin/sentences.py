"""Splits a reply into sentences while the LLM is still writing it (roadmap R20, item 12), so
each sentence can be spoken as soon as it is complete. Pure Python, no logging: the caller logs.

A sentence ends at ".", "!", "?" or "…" (with any closing quotes or brackets after it) followed by
a space, at a blank line, and at the end of a heading or list item. The end is only known once the
next word starts, so "Dr. Smith", "e.g. this", "3.5", "1. First" and "the U.S. team" don't split
(nor, as a cost of that, does "in the U.S. The"). Code blocks and inline code are kept whole, by
the same rules as speech_text.py, so each sentence can be cleaned for speech on its own.

With `first_clause`, the reply's first sentence is cut at its first clause (roadmap R22b), so
the first clip is short and can be spoken while the LLM is still writing the rest: at a comma,
semicolon, colon or dash after at least FIRST_CLAUSE_MIN words, before a joining word such as
"and" or "because", or failing those after FIRST_CLAUSE_MAX words (stretched up to
FIRST_CLAUSE_LIMIT so the clause doesn't end on a word that leads into the next).
"""

import re

from imageskin.speech_text import CODE_FENCE, INLINE_CODE, closing_fence, inside_whole

# Words that end with a full stop but don't end a sentence.
ABBREVIATIONS = frozenset(
    "mr mrs ms dr prof sr jr st vs etc e.g i.e cf approx no fig vol jan feb mar apr jun jul aug"
    " sep sept oct nov dec mon tue wed thu fri sat sun".split()
)
_END = re.compile(r"([.!?…]+)([\"'”’)\]]*)\s+")
_WORD = re.compile(r"\S+")
FIRST_CLAUSE_MIN = 3  # words a first clause must have
FIRST_CLAUSE_MAX = 8  # words after which the first clause is cut without a clause boundary...
FIRST_CLAUSE_LIMIT = 12  # ...unless that would end it on a leading word, up to this many words
# Words that start a clause of their own, so the cut comes before them.
JOINING = frozenset(
    "and but or nor so yet because which who whom whose while when where if although though as"
    " until since unless whereas".split()
)
# Words that lead into the next, which a clause shouldn't end on.
LEADING = frozenset(
    "a an the of in on at to for with by from into onto over under about as than that this these"
    " those his her its their our my your and or but nor so yet very really quite too not no is"
    " are was were be been being has have had do does did will would can could should may might"
    " must".split()
)
_DASHES = ("-", "—", "–")
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


def first_clause_cut(text: str) -> int | None:
    """Where the first clause of `text`, an unfinished sentence, ends, or None while it has no
    clause yet. The cut is only made once the next word has started, so "Hi Larry," waits for
    what follows (it may be the end of the sentence)."""
    words = list(_WORD.finditer(text))
    for i in range(FIRST_CLAUSE_MIN, min(len(words) - 1, FIRST_CLAUSE_LIMIT) + 1):
        last = words[i - 1].group()
        if _in_code(text, words[i - 1].end() - 1):
            continue
        word = last.rstrip("\"'”’)]").lower()
        following = words[i].group().lstrip("\"'“‘([").lower()
        dash = max(last.find("—"), last.find("–"))
        cut = None
        if dash > 0:  # a dash joined to the word before it, as in "a leader—a great one"
            cut = words[i - 1].start() + dash
        elif (
            word.endswith((",", ";", ":")) or following in JOINING or following in _DASHES
        ) and last not in _DASHES:
            cut = words[i - 1].end()
        elif i >= FIRST_CLAUSE_MAX and (
            word.strip(".!?") not in LEADING or i == FIRST_CLAUSE_LIMIT
        ):
            cut = words[i - 1].end()
        # Not inside a picture, link or HTML tag, which are spoken (or left out) whole.
        if cut is not None and not inside_whole(text, cut):
            return cut
    return None


class SentenceSplitter:
    """Feed it text as it arrives; it hands back each sentence once it is complete. With
    `first_clause`, the first sentence's first clause is handed back as a sentence of its own."""

    def __init__(self, first_clause: bool = False) -> None:
        self._text = ""
        self._first_clause = first_clause
        self._count = 0  # sentences handed back so far

    def feed(self, chunk: str) -> list[str]:
        """Add text; return the sentences now complete, in order."""
        self._text += chunk
        sentences: list[str] = []
        while (cut := self._next_cut()) is not None:
            sentence, self._text = self._text[:cut].strip(), self._text[cut:]
            if sentence:
                sentences.append(sentence)
                self._count += 1
        return sentences

    def flush(self) -> list[str]:
        """The reply has ended: return what is left as the last sentence."""
        rest, self._text = self._text.strip(), ""
        return [rest] if rest else []

    def _next_cut(self) -> int | None:
        """Where the first complete sentence ends, or None if none is complete yet."""
        cut = self._next_sentence_cut()
        if self._first_clause and self._count == 0:
            text = self._text if cut is None else self._text[:cut]
            fence = CODE_FENCE.search(text)
            clause = first_clause_cut(text[: fence.start()] if fence else text)
            if clause is not None:
                return clause
        return cut

    def _next_sentence_cut(self) -> int | None:
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
