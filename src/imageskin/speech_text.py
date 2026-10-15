"""The spoken version of a reply: what is shown as text but read badly aloud (item 11).

Markdown markers, HTML tags and decorative emoji are left out. Links, code, pictures and tables
are replaced by a short phrase that says what they are and points to the text, so a sentence
never breaks off ("see the guide or the link in the text below", not "see the guide or"). Pure
Python, no logging: the callers log.
"""

import re
import unicodedata
from collections.abc import Callable

from imageskin.speech_math import (
    EQUATION,
    EQUATION_BLOCK,
    MATH,
    SUBSCRIPT_RUN,
    SUPERSCRIPT_RUN,
    greek_name,
    math_parts,
    power,
    say_math,
    symbol_words,
)

LINK = "the link in the text below"
LINKS = "the links in the text below"
CODE = "the code shown below"
PICTURE = "the picture in the text below"
CODE_BLOCK = "See the code shown below."
TABLE = "See the table in the text below."
_BLOCKS = {CODE_BLOCK, TABLE, EQUATION_BLOCK}  # said as a sentence of their own
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


# Math opened and not closed yet. $$, \[ and \( may run over several lines, so they stay open
# until closed; a $ only to the end of its line, and a $ before a digit is money ("$5").
_DISPLAY_OPENED = re.compile(r"\$\$|\\[\[(]")
_DOLLAR_OPENED = re.compile(r"(?<![\\$\w])\$(?![\s$\d])[^\n]*$")


# What isn't math even with a $ in it: code blocks, inline code (or a backtick that may yet
# start some, on the line still being written) and URLs.
_NOT_MATH = (_REPLACE[0][0], INLINE_CODE, re.compile(r"`[^`\n]*\Z"), _AUTOLINK, _URL_ONLY)


def _without_code(text: str) -> str:
    """`text` with what isn't math blanked out, so a $ in it opens nothing."""
    for pattern in _NOT_MATH:
        text = pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), text)
    return text


def inside_math(text: str, at: int) -> bool:
    """Whether cutting `text` at `at` would split math (roadmap R16b): math that is closed, or
    that has been opened and may yet be closed while the reply is still being written. $$, \\[
    and \\( count across lines, a single $ only on its own line. A $ in code or a URL opens
    nothing."""
    text = _without_code(text)
    spans = [m.span() for m in MATH.finditer(text)]
    if any(a < at < b for a, b in spans):
        return True
    before = "".join(
        " " if any(a <= i < b for a, b in spans) else c for i, c in enumerate(text[:at])
    )
    if _DISPLAY_OPENED.search(before):
        return True
    if text.find("\n", at) >= 0:
        return False  # a $ closes on its own line, and this line is complete
    return _DOLLAR_OPENED.search(before[before.rfind("\n") + 1 :]) is not None


def inside_whole(text: str, at: int) -> bool:
    """Whether cutting `text` at `at` would split a picture, link, autolink, HTML tag,
    bracketed URL or math (roadmap R16b), which speech_text replaces whole; or one that has
    been opened and may yet be closed, while the line is still being written (roadmap R22b). A
    line with a `|` may be a table's row, and a table is replaced whole too, so no cut falls
    on it."""
    start = text.rfind("\n", 0, at) + 1
    end = text.find("\n", at)
    line = text[start:] if end < 0 else text[start:end]
    if "|" in line or inside_math(text, at):
        return True
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


def _own_line(display: str, m: re.Match[str]) -> bool:
    """Whether the match is all there is on its lines, so it reads as a sentence of its own."""
    start = display.rfind("\n", 0, m.start()) + 1
    end = display.find("\n", m.end())
    return not (
        display[start : m.start()].strip() or display[m.end() : end if end >= 0 else None].strip()
    )


def _spaced(display: str, start: int, end: int, words: str) -> str:
    """Words said in place of display[start:end], set apart from a word joined to it, as in
    "2π" ("2 pi") or "x²" ("x squared")."""
    if start and display[start - 1].isalnum():
        words = " " + words
    if end < len(display) and display[end].isalnum():
        words += " "
    return words


_GREEK = "\u0391-\u03a9\u03b1-\u03c9"
# A fraction written with a slash, with a number, a letter or a bracket on each side and maybe a
# power: "1/p", "1/n^s", "1/(1 − 1/p^s)". Numbers on both sides ("24/7", a date) and words
# ("and/or", "n/a") are left as written.
_BRACKETED = r"\((?:[^()\n]|\([^()\n]*\)){1,60}\)"
_TERM = (
    rf"(?:\d+(?:\.\d+)?|[A-Za-z{_GREEK}]|{_BRACKETED})"
    rf"(?:\^(?:\{{[^{{}}\n]+\}}|\([^()\n]{{1,20}}\)|-?\w+))?"
)
SLASH_FRACTION = re.compile(rf"(?<![\w/.^])({_TERM})/({_TERM})(?![\w/])")
# A minus sign before one: "1 - 1/p" is "1 minus the fraction 1 over p".
_MINUS_BEFORE = re.compile(rf"(?<=[\w)][ \t])[-−](?=[ \t]+{_TERM}/{_TERM})")
_OPERATOR_BEFORE = re.compile(r"(?:[-−+×*]|\b(?:minus|plus|times))\s*\Z")
_OPERATOR_AFTER = re.compile(r"\s*(?:[-−+×*^]|(?:minus|plus|times)\b)")


def in_expression(display: str, start: int, end: int) -> bool:
    """Whether the math from `start` to `end` is next to a "+", "-" or the like, so a fraction
    that is all of it still needs saying as "the fraction" to be heard one way."""
    return bool(
        _OPERATOR_BEFORE.search(display[max(0, start - 8) : start])
        or _OPERATOR_AFTER.match(display, end)
    )


def slash_tex(text: str) -> str:
    """Slash fractions as LaTeX, innermost first: "1/(1 − 1/p^s)" is
    "\\frac{1}{1 − \\frac{1}{p^s}}"."""

    def frac(m: re.Match[str]) -> str:
        top, bottom = (
            part[1:-1] if part[:1] == "(" and part[-1:] == ")" else part for part in m.groups()
        )
        return rf"\frac{{{top}}}{{{bottom}}}"

    while True:
        inner = re.sub(rf"(?<![\w/.^])({_TERM})/({_TERM})", frac, text)
        if inner == text:
            return text
        text = inner


def say_slash_fraction(m: re.Match[str]) -> str | None:
    top, bottom = (part.strip("()") for part in m.groups())
    if top.isdigit() and bottom.isdigit():
        return None  # "24/7" or a date, not a formula
    if top.isalpha() and bottom.isalpha():
        return None  # "n/a", "w/o"
    return say_math(slash_tex(m[0]), in_expression(m.string, m.start(), m.end()))


_LIMIT = r"\([^()\n]{1,20}\)|[\w∞]+"
# A sum, product or integral with where it runs, as a PDF's formula is read (pdf_math.py):
# "∫_0^∞" is "the integral from 0 to infinity of".
BIG_WITH_LIMITS = re.compile(rf"([∑∏∫])_({_LIMIT})(?:\^({_LIMIT}))?")


def say_big_with_limits(m: re.Match[str]) -> str:
    words = [symbol_words(m[1]) or m[1], "from", say_math(m[2].strip("()")) or m[2]]
    if m[3]:
        words += ["to", say_math(m[3].strip("()")) or m[3]]
    return " ".join([*words, "of"])


BIG_SIGN = re.compile("[∑∏∫]")


def say_big_sign(m: re.Match[str]) -> str:
    """A sum, product or integral sign: "the sum", or "the sum of" before what it adds up, and
    "of" alone after the same word ("the product ∏ 1/p" is "the product of 1 over p")."""
    words = symbol_words(m[0]) or m[0]
    if not re.match(r"[ \t]+[\w(]", m.string[m.end() :]):
        return words  # nothing after it to add up
    before = m.string[: m.start()].split()
    return "of" if before and before[-1].lower() == words.split()[-1] else f"{words} of"


_SYMBOL_RULES: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], str | None]], ...] = (
    (BIG_WITH_LIMITS, say_big_with_limits),
    (SLASH_FRACTION, say_slash_fraction),
    (_MINUS_BEFORE, lambda m: "minus"),
    # A Greek letter used as a function: "ζ(s)" is "zeta of s".
    (
        re.compile(rf"(?<![^\W\d_])([{_GREEK}])\(([^()\n]{{1,40}})\)"),
        lambda m: f"{greek_name(m[1])} of {say_math(m[2]) or m[2]}",
    ),
    # A Greek letter on its own, not part of a Greek word.
    (re.compile(rf"(?<![\u0370-\u03ff])[{_GREEK}](?![\u0370-\u03ff])"), lambda m: greek_name(m[0])),
    (SUPERSCRIPT_RUN, lambda m: say_math(m[0])),  # "x²" is "x squared"
    (SUBSCRIPT_RUN, lambda m: say_math(m[0])),  # "x₁" is "x sub 1"
    # A power written with a caret after a word or bracket: "n^s", "2^{10}", "e^(−nx)".
    (
        re.compile(r"(?<=[\w)])\^(?:\{([^{}\n]+)\}|\(([^()\n]+)\)|(-?\w+))"),
        lambda m: " ".join(power((say_math(m[1] or m[2] or m[3]) or m[0][1:]).split())),
    ),
    # A comparison between two words or numbers, as in "s > 1" or "x = 2".
    (
        re.compile(r"(?<=[\w)][ \t])(<=|>=|[<>=])(?=[ \t]+[\w(\-−∑∏∫√∞])"),
        lambda m: say_math(m[1].replace("<=", "≤").replace(">=", "≥")),
    ),
    (BIG_SIGN, say_big_sign),
    (re.compile("[∞≤≥≠≈≡∝∈∉⊂⊆∪∩∀∃∂∇→⇒⇔×÷±∓°√∛−⋅⋯]"), lambda m: symbol_words(m[0])),
)


def math_in_words(text: str) -> str:
    """The math symbols, powers and fractions in plain text said in words, as the voice says
    them, and the rest left as it is. A PDF's formula, given to the chat's LLM like this, is
    worded by the LLM in full (Gemma 3 4B dropped most of "∏ 1/(1 − 1/p^s) = ∑ 1/n^s")."""
    done = [False] * len(text)
    said: dict[int, tuple[int, str]] = {}  # where a replacement starts: where it ends, words
    for pattern, saying in _SYMBOL_RULES:
        for m in pattern.finditer(text):
            if any(done[m.start() : m.end()]):
                continue
            words = saying(m)
            if words:
                said[m.start()] = (m.end(), _spaced(text, m.start(), m.end(), words))
                done[m.start() : m.end()] = [True] * (m.end() - m.start())
    out, at = [], 0
    for start in sorted(said):
        end, words = said[start]
        out += [text[at:start], words]
        at = end
    return "".join([*out, text[at:]])


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
    # Math is said in words when it is short, and pointed to when it is not (roadmap R16b).
    for m in MATH.finditer(display):
        if done[m.start()]:
            continue
        tex, block = math_parts(m)
        words = say_math(tex, in_expression(display, m.start(), m.end()))
        if words is None:
            words = EQUATION_BLOCK if block and _own_line(display, m) else EQUATION
        drop(m.start(), m.end(), _spaced(display, m.start(), m.end(), words))
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
    # Greek letters and math symbols outside LaTeX, as in "ζ(s)" and "π ≈ 3.14", by name.
    for pattern, saying in _SYMBOL_RULES:
        for m in pattern.finditer(display):
            if any(done[m.start() : m.end()]) or not all(keep[m.start() : m.end()]):
                continue
            said = saying(m)
            if said:
                drop(m.start(), m.end(), _spaced(display, m.start(), m.end(), said))
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
