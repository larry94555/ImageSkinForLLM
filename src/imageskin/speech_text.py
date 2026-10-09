"""The spoken version of a reply: what is shown as text but not voiced is left out (item 11).

Markdown markers, code, URLs and emoji are removed. Pure Python, no logging: the callers log.
"""

import re
import unicodedata

# Each pattern's groups name the parts to drop; the rest of the match is spoken.
_DROPS = (
    # Fenced code block: it ends at a line with a fence as long or longer of the same character,
    # so a ```` block can hold ```; a block that is never closed runs to the end.
    re.compile(
        r"^[ \t]*(?P<fence>(?P<c>[`~])(?P=c){2,}).*?(?:^[ \t]*(?P=fence)(?P=c)*[ \t]*$|\Z)",
        re.S | re.M,
    ),
    # Inline code ends at the same number of backticks it starts with, so ``a`b`` is one span.
    re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)"),
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
    re.compile(r"^[ \t]*([-*+][ \t]+|\d+[.)][ \t]+)", re.M),  # list bullet or number
    # Emphasis hugs a word on one side; "2 * 3" keeps its star. Underscores inside a word stay.
    re.compile(r"(?<=\S)(\*+|~~)|(\*+|~~)(?=\S)"),
    re.compile(r"(?<![^\W_])(_+)|(_+)(?![^\W_])"),
    re.compile(r"(\|)"),  # table cell border
)
# A line the voice should end with a pause: a heading, list item, quote or table row.
_STRUCTURAL_LINE = re.compile(r"^[ \t]*(?:#{1,6}[ \t]|[-*+][ \t]|\d+[.)][ \t]|>|\|)")
_EMOJI_PARTS = {"\u200d", "\ufe0e", "\ufe0f", "\u20e3"}  # joiner, presentation, keycap
_SENTENCE_END = set(".!?:;,")


def _is_emoji(ch: str) -> bool:
    # So covers pictographs and flags' regional letters; Sk covers the skin-tone modifiers.
    if ch in _EMOJI_PARTS:
        return True
    return unicodedata.category(ch) == "So" or "\U0001f3fb" <= ch <= "\U0001f3ff"


def spoken_text(display: str) -> str:
    """The words of a displayed reply that should be voiced."""
    keep = [True] * len(display)
    for pattern in _DROPS:
        for m in pattern.finditer(display):
            keep[m.start() : m.end()] = [False] * (m.end() - m.start())
    for pattern in _PARTS:
        for m in pattern.finditer(display):
            for group in range(1, (pattern.groups or 0) + 1):
                if m.start(group) >= 0:
                    keep[m.start(group) : m.end(group)] = [False] * (m.end(group) - m.start(group))

    structural = [False] * len(display)  # whether each character is on a structural line
    start = 0
    for line in display.splitlines(keepends=True):
        if _STRUCTURAL_LINE.match(line):
            structural[start : start + len(line)] = [True] * len(line)
        start += len(line)

    chars: list[str] = []
    last = 0  # index in display of the last character spoken
    gap = False  # whether whitespace or dropped text waits between the last word and the next
    line_breaks = 0
    for i, ch in enumerate(display):
        if _is_emoji(ch):
            continue
        if not keep[i] or ch.isspace():  # dropped text still separates words, as in "a<br>b"
            if not gap:
                gap, line_breaks = True, 0
            line_breaks += ch == "\n"
            continue
        if gap and chars and not (line_breaks == 0 and ch in _SENTENCE_END):
            # A paragraph, or a heading, list item, quote or table row, that ends without
            # punctuation ends a sentence, so the voice pauses instead of running them
            # together. A single line break inside a paragraph is only a space.
            ends_block = line_breaks >= 2 or structural[last] or structural[i]
            if line_breaks and ends_block and chars[-1] not in _SENTENCE_END:
                chars.append(".")
            chars.append(" ")
        gap = False
        chars.append(ch)
        last = i
    return "".join(chars)
