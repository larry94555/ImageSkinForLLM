"""The spoken version of a reply: what is shown as text but not voiced is left out (item 11).

Markdown markers, code, URLs and emoji are removed, and every spoken character keeps the
index of the displayed character it came from, so a spoken word can be highlighted in the
displayed reply (R18). Pure Python, no logging: the callers log.
"""

import re
import unicodedata
from dataclasses import dataclass

# Each pattern's groups name the parts to drop; the rest of the match is spoken.
_DROPS = (
    re.compile(r"(```|~~~).*?(?:\1|\Z)", re.S),  # fenced code block, even if never closed
    re.compile(r"`[^`\n]+`"),  # inline code
    re.compile(r"!\[[^\]\n]*\]\([^)\n]*\)"),  # image
    re.compile(r"<[a-zA-Z/][^>\n]*>"),  # HTML tag, such as <br>
    re.compile(r"\((?:https?://|www\.)[^)\s]*\)"),  # URL in brackets, brackets and all
    # Bare URL; punctuation after it ends the sentence, not the URL.
    re.compile(r"(?:https?://|www\.)\S*[^\s.,!?;:'\")\]]"),
    re.compile(r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$", re.M),
)
_PARTS = (
    # A link speaks its text: drop "[" and "](url)".
    re.compile(r"(\[)[^\]\n]+(\]\([^)\n]*\))"),
    re.compile(r"^[ \t]*(#{1,6}[ \t]+)", re.M),  # heading marker
    re.compile(r"^[ \t]*((?:>[ \t]?)+)", re.M),  # quote marker
    re.compile(r"^[ \t]*([-*+][ \t]+)", re.M),  # list bullet
    # Emphasis hugs a word on one side; "2 * 3" keeps its star. Underscores inside a word stay.
    re.compile(r"(?<=\S)(\*+|~~)|(\*+|~~)(?=\S)"),
    re.compile(r"(?<![^\W_])(_+)|(_+)(?![^\W_])"),
    re.compile(r"(\|)"),  # table cell border
)
_EMOJI_PARTS = {"‍", "︎", "️", "⃣"}  # joiner, presentation, keycap
_SENTENCE_END = set(".!?:;,")


@dataclass(frozen=True)
class SpokenText:
    text: str  # what the voice says
    source: tuple[int, ...]  # for each character of text, its index in the displayed reply

    def display_span(self, start: int, end: int) -> tuple[int, int]:
        """The displayed characters that spoken characters start to end (exclusive) came from."""
        if not 0 <= start < end <= len(self.text):
            raise ValueError(f"no spoken characters {start} to {end} in {len(self.text)}")
        return self.source[start], self.source[end - 1] + 1


def _is_emoji(ch: str) -> bool:
    # So covers pictographs and flags' regional letters; Sk covers the skin-tone modifiers.
    if ch in _EMOJI_PARTS:
        return True
    return unicodedata.category(ch) == "So" or "\U0001f3fb" <= ch <= "\U0001f3ff"


def spoken_text(display: str) -> SpokenText:
    """The words of a displayed reply that should be voiced, mapped back to the reply."""
    keep = [True] * len(display)
    for pattern in _DROPS:
        for m in pattern.finditer(display):
            keep[m.start() : m.end()] = [False] * (m.end() - m.start())
    for pattern in _PARTS:
        for m in pattern.finditer(display):
            for group in range(1, (pattern.groups or 0) + 1):
                if m.start(group) >= 0:
                    keep[m.start(group) : m.end(group)] = [False] * (m.end(group) - m.start(group))

    chars: list[str] = []
    source: list[int] = []
    gap = ""  # whitespace waiting to be spoken: "" none, " " a space, "\n" a line break
    gap_at = 0
    for i, ch in enumerate(display):
        if _is_emoji(ch):
            continue
        if not keep[i] or ch.isspace():  # dropped text still separates words, as in "a<br>b"
            if not gap:
                gap_at = i
            if ch == "\n" or not gap:  # a line break wins over spaces
                gap = "\n" if ch == "\n" else " "
            continue
        if gap and chars and not (gap == " " and ch in _SENTENCE_END):
            # A line that ends without punctuation (a heading, a list item) ends a sentence,
            # so the voice pauses instead of running the lines together.
            if gap == "\n" and chars[-1] not in _SENTENCE_END:
                chars.append(".")
                source.append(gap_at)
            chars.append(" ")
            source.append(gap_at)
        gap = ""
        chars.append(ch)
        source.append(i)
    return SpokenText("".join(chars), tuple(source))
