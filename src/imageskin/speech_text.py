"""The spoken version of a reply: what is shown as text but read badly aloud (item 11).

Markdown markers, HTML tags and decorative emoji are left out. Links, code, pictures and tables
are replaced by a short phrase that says what they are and points to the text, so a sentence
never breaks off ("see the guide or the link in the text below", not "see the guide or"). Pure
Python, no logging: the callers log.
"""

import re
import unicodedata

LINK = "the link in the text below"
LINKS = "the links in the text below"
CODE = "the code shown below"
PICTURE = "the picture in the text below"
CODE_BLOCK = "See the code shown below."
TABLE = "See the table in the text below."
_BLOCKS = {CODE_BLOCK, TABLE}  # said as a sentence of their own
# Emoji that stand for a word, as in "I ❤️ it". Others are decoration and stay silent.
_EMOJI_WORDS = {"❤": "love", "♥": "love"}
# Inline code of up to this many words is spoken as is, such as `main()`.
_SHORT_CODE_WORDS = 2

# Short forms the voice would spell out ("Jr." as "J R"), said as the words they stand for. "St."
# is left as it is: it is "Saint" or "Street" depending on the sentence.
_SHORT_FORMS = {
    "jr": "Junior",
    "sr": "Senior",
    "dr": "Doctor",
    "mr": "Mister",
    "mrs": "Missus",
    "prof": "Professor",
    "vs": "versus",
    "etc": "et cetera",
    "e.g": "for example",
    "i.e": "that is",
    "approx": "approximately",
}
_SHORT_FORM = re.compile(
    r"(?<![\w.])(" + "|".join(re.escape(k) for k in _SHORT_FORMS) + r")\.(?![\w.])", re.I
)
# These go on to more of the sentence, often a name ("Dr. Smith", "Python vs. Java"), so a capital
# after them doesn't end it.
_GO_ON = {"dr", "mr", "mrs", "prof", "vs", "e.g", "i.e", "approx"}
# After a short form, what shows its full stop also ends the sentence.
_SENTENCE_AFTER = re.compile(r"[ \t]*(?:$|\n|[ \t][\"'“‘(\[]*[A-Z])")


# The Markdown code rules, shared with the sentence splitter (sentences.py) so both agree on
# where code starts and ends. A code fence is three or more of the same character, ` or ~.
CODE_FENCE = re.compile(r"^[ \t]*(?P<fence>(?P<c>[`~])(?P=c){2,})", re.M)
# Inline code ends at the same number of backticks it starts with, so ``a`b`` is one span.
INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")


def closing_fence(fence: str) -> re.Pattern[str]:
    """The line that closes a code block opened by `fence`: a fence as long or longer of the
    same character, alone on its line, so a ```` block can hold ```."""
    return re.compile(rf"^[ \t]*{re.escape(fence)}{re.escape(fence[0])}*[ \t]*$", re.M)


_URL = r"(?:https?://|www\.)\S*[^\s.,!?;:'\")\]]"  # punctuation after it is not part of it
_PICTURE = re.compile(r"!\[[^\]\n]*\]\([^)\n]*\)")
_AUTOLINK = re.compile(r"<(?:https?://|www\.)[^>\s]*>")  # such as <https://a.io>
_HTML_TAG = re.compile(r"<[a-zA-Z/][^>\n]*>")  # such as <br>
_BRACKETED_URL = re.compile(r"\((?:https?://|www\.)[^)\s]*\)")  # brackets and all
_LINK = re.compile(r"\[[^\]\n]+\]\([^)\n]*\)")  # its text is spoken, without the rest
# Each pattern replaces what it matches with the phrase, or with nothing when there is none.
# They run in order, and a match that starts inside text an earlier one handled is skipped.
_REPLACE = (
    # Fenced code block: it ends at a line with a fence as long or longer of the same character,
    # so a ```` block can hold ```; a block that is never closed runs to the end.
    (
        re.compile(
            CODE_FENCE.pattern + r".*?(?:^[ \t]*(?P=fence)(?P=c)*[ \t]*$|\Z)",
            re.S | re.M,
        ),
        CODE_BLOCK,
    ),
    (_PICTURE, PICTURE),
    (_AUTOLINK, LINK),
    (_HTML_TAG, ""),
    (re.compile(r"(?<=\])\([^)\n]*\)"), ""),  # where a link goes: its text is spoken instead
    (_BRACKETED_URL, LINK),
    # Table: a header row, the row of dashes under it, and the rows after it.
    (
        re.compile(
            r"^[^\n]*\|[^\n]*\n[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$"
            r"(?:\n[^\n]*\|[^\n]*)*",
            re.M,
        ),
        TABLE,
    ),
    (re.compile(r"^[ \t]*-{3,}[ \t]*$", re.M), ""),  # horizontal rule
    # Bare URLs; several in a row, as in "a, b and c", are one phrase.
    (re.compile(rf"{_URL}(?:(?:[ \t]*,[ \t]*|[ \t]+)(?:and[ \t]+)?{_URL})*"), LINK),
)
_URL_ONLY = re.compile(_URL)
# What is spoken (or left out) whole, on one line: a picture, an autolink, an HTML tag, a link
# with where it goes, or a URL in brackets. Cut in two, neither part would match its rule.
_WHOLE = (_PICTURE, _AUTOLINK, _HTML_TAG, _BRACKETED_URL, _LINK)
# The start of one of those, not yet closed on a line still being written.
_OPENED = re.compile(
    r"(?:!?\[[^\]\n]*|\]\([^)\n]*|<[a-zA-Z/][^>\n]*|\((?:https?://|www\.)[^)\s]*)$"
)


def inside_whole(text: str, at: int) -> bool:
    """Whether cutting `text` at `at` would split a picture, link, autolink, HTML tag or
    bracketed URL, which speech_text replaces whole; or one that has been opened and may yet
    be closed, while the line is still being written (roadmap R22b)."""
    start = text.rfind("\n", 0, at) + 1
    end = text.find("\n", at)
    line = text[start:] if end < 0 else text[start:end]
    at -= start
    spans = [m.span() for pattern in _WHOLE for m in pattern.finditer(line)]
    if any(a < at < b for a, b in spans):
        return True
    if end >= 0:
        return False
    outside = "".join(" " if any(a <= i < b for a, b in spans) else c for i, c in enumerate(line))
    return _OPENED.search(outside[:at]) is not None


_PARTS = (
    # A link speaks its text: drop "[" and "](url)".
    re.compile(r"(\[)[^\]\n]+(\]\([^)\n]*\))"),
    re.compile(r"^[ \t]*(#{1,6}[ \t]+)", re.M),  # heading marker
    re.compile(r"^[ \t]*((?:>[ \t]?)+)", re.M),  # quote marker
    re.compile(r"^[ \t]*([-*+][ \t]+|\d+[.)][ \t]+)", re.M),  # list bullet or number
    # Emphasis hugs a word on one side; "2 * 3" keeps its star. Underscores inside a word stay.
    re.compile(r"(?<=\S)(\*+|~~)|(\*+|~~)(?=\S)"),
    re.compile(r"(?<![^\W_])(_+)|(_+)(?![^\W_])"),
    re.compile(r"(\|)"),  # a stray table cell border
)
# A line the voice should end with a pause: a heading, list item, quote or table row.
_STRUCTURAL_LINE = re.compile(r"^[ \t]*(?:#{1,6}[ \t]|[-*+][ \t]|\d+[.)][ \t]|>|\|)")
_EMOJI_PARTS = {"‍", "︎", "️", "⃣"}  # joiner, presentation, keycap
_SENTENCE_END = set(".!?:;,")


def _is_emoji(ch: str) -> bool:
    # So covers pictographs and flags' regional letters; Sk covers the skin-tone modifiers.
    if ch in _EMOJI_PARTS:
        return True
    return unicodedata.category(ch) == "So" or "\U0001f3fb" <= ch <= "\U0001f3ff"


def _emoji_words(display: str, keep: list[bool]) -> dict[int, str]:
    """Emoji standing for a word, between two spoken words on one line, by where they start."""
    said = {}
    for i, ch in enumerate(display):
        word = _EMOJI_WORDS.get(ch)
        if word is None or (i and _is_emoji(display[i - 1])):
            continue
        before = display[:i].rstrip(" \t")
        end = i
        while end < len(display) and _is_emoji(display[end]):
            end += 1
        after_start = len(display) - len(display[end:].lstrip(" \t"))
        if (
            before
            and before[-1].isalnum()
            and keep[len(before) - 1]
            and after_start < len(display)
            and display[after_start].isalnum()
            and keep[after_start]
        ):
            said[i] = word
    return said


def _replace(display: str) -> tuple[list[bool], dict[int, str]]:
    """Which characters of the reply are spoken, and the phrases said in place of the rest."""
    keep = [True] * len(display)
    done = [False] * len(display)  # handled by a replacement, so later patterns skip it
    say: dict[int, str] = {}

    def drop(start: int, end: int, phrase: str = "") -> None:
        keep[start:end] = [False] * (end - start)
        done[start:end] = [True] * (end - start)
        for i in [i for i in say if start <= i < end]:
            del say[i]
        if phrase:
            say[start] = phrase

    for pattern, phrase in _REPLACE[:1]:
        for m in pattern.finditer(display):
            drop(m.start(), m.end(), phrase)
    # Short inline code is spoken without its backticks; longer code is replaced by a phrase.
    for m in INLINE_CODE.finditer(display):
        if done[m.start()]:
            continue
        if _URL_ONLY.search(m.group(2)):
            drop(m.start(), m.end(), LINK)
        elif len(m.group(2).split()) > _SHORT_CODE_WORDS:
            drop(m.start(), m.end(), CODE)
        else:  # the code itself is kept as it is, stars and underscores too
            drop(m.start(1), m.end(1))
            drop(m.end(2), m.end())
            done[m.start(2) : m.end(2)] = [True] * (m.end(2) - m.start(2))
    for pattern, phrase in _REPLACE[1:]:
        for m in pattern.finditer(display):
            if done[m.start()]:
                continue
            several = phrase == LINK and len(_URL_ONLY.findall(m.group())) > 1
            drop(m.start(), m.end(), LINKS if several else phrase)
    for pattern in _PARTS:
        for m in pattern.finditer(display):
            for group in range(1, (pattern.groups or 0) + 1):
                if m.start(group) >= 0 and not done[m.start(group)]:
                    keep[m.start(group) : m.end(group)] = [False] * (m.end(group) - m.start(group))
    # Short forms in what is still spoken as written (not in code) are said as words.
    for m in _SHORT_FORM.finditer(display):
        if any(done[m.start() : m.end()]) or not all(keep[m.start() : m.end()]):
            continue
        short = m.group(1).lower()
        ends = short not in _GO_ON and _SENTENCE_AFTER.match(display, m.end())
        drop(m.start(), m.end() - 1 if ends else m.end(), _SHORT_FORMS[short])
    say.update(_emoji_words(display, keep))
    return keep, say


def spoken_text(display: str) -> str:
    """The words of a displayed reply that should be voiced."""
    keep, say = _replace(display)

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
        word = say.get(i, ch)
        if i not in say:
            if _is_emoji(ch):
                continue
            if not keep[i] or ch.isspace():  # dropped text still separates words, as in "a<br>b"
                if not gap:
                    gap, line_breaks = True, 0
                line_breaks += ch == "\n"
                continue
        if word in _BLOCKS and chars and chars[-1][-1] not in _SENTENCE_END:
            chars.append(".")  # a code block or table is a sentence of its own
        if gap and chars and not (line_breaks == 0 and word[0] in _SENTENCE_END):
            # A paragraph, or a heading, list item, quote or table row, that ends without
            # punctuation ends a sentence, so the voice pauses instead of running them
            # together. A single line break inside a paragraph is only a space.
            ends_block = line_breaks >= 2 or structural[last] or structural[i]
            if line_breaks and ends_block and chars[-1][-1] not in _SENTENCE_END:
                chars.append(".")
            chars.append(" ")
        before = chars[-2] if chars[-1:] == [" "] else "".join(chars[-1:])
        if i in say and (not before or before[-1] in ".!?"):
            word = word[0].upper() + word[1:]  # a phrase that starts a sentence
        gap = False
        chars.append(word)
        last = i
    return "".join(chars)
