"""Formulas in a PDF read as one line of text, so the wiki and the chat's LLM get a formula they
can make sense of.

A formula set with LaTeX is laid out in two dimensions: a fraction is a numerator over a rule over
a denominator, and a power is a smaller character raised beside its base. Read line by line, that
comes out scrambled ("1 1 = , 1− 1 ns ps" for Euler's product), and the big sum, product and
integral signs come out as "(cid:80)" and are dropped. Here a formula is found from its fraction
rules and big signs, and read left to right into one line: "∏ 1/(1 − 1/p^s) = ∑ 1/n^s,".
Pure Python, no logging: pdf_reading.py logs.
"""

import re
from dataclasses import dataclass
from typing import Any

Obj = dict[str, Any]  # a pdfplumber character or line

# TeX's math extension font (cmex) has no text for its glyphs, so pdfminer writes "(cid:89)".
# These are the ones with a meaning on their own; the pieces of very tall brackets are left out.
_CMEX = {
    **dict.fromkeys((0x00, 0x10, 0x12, 0x20), "("),
    **dict.fromkeys((0x01, 0x11, 0x13, 0x21), ")"),
    **dict.fromkeys((0x02, 0x14, 0x22), "["),
    **dict.fromkeys((0x03, 0x15, 0x23), "]"),
    **dict.fromkeys((0x08, 0x1A, 0x28), "{"),
    **dict.fromkeys((0x09, 0x1B, 0x29), "}"),
    **dict.fromkeys((0x50, 0x58), "∑"),
    **dict.fromkeys((0x51, 0x59), "∏"),
    **dict.fromkeys((0x52, 0x5A), "∫"),
    **dict.fromkeys((0x48, 0x49), "∮"),
    **dict.fromkeys((0x53, 0x5B), "⋃"),
    **dict.fromkeys((0x54, 0x5C), "⋂"),
    **dict.fromkeys(range(0x70, 0x75), "√"),
}
BIG = set("∑∏∫∮⋃⋂")
MATH_FONTS = ("CMMI", "CMSY", "CMEX", "MSAM", "MSBM")
CID = re.compile(r"\(cid:(\d+)\)")
SPACED = set("=+−<>≤≥≈≠±→")  # said with a space each side: "1 − 1/p^s"
WORD_GAP = 0.15  # a gap wider than this share of the font size is a space
SCRIPT = 0.9  # a character smaller than this share of its base's size may be a power or index
RULE_HEIGHT = 1.5  # a fraction rule is a line or box no taller than this
REACH = 1.6  # how far, in font sizes, a numerator or denominator can be from its rule


@dataclass(frozen=True)
class Formula:
    top: float
    bottom: float
    text: str
    chars: list[Obj]  # the characters it was read from, to leave out of the page's text


def symbol(char: Obj) -> str:
    """A character's text, with the big signs of TeX's math extension font given theirs."""
    text = str(char["text"])
    found = CID.fullmatch(text)
    if found and "CMEX" in str(char.get("fontname", "")).upper():
        return _CMEX.get(int(found[1]), text)
    return text


def middle_x(obj: Obj) -> float:
    return (float(obj["x0"]) + float(obj["x1"])) / 2


def middle_y(obj: Obj) -> float:
    return (float(obj["top"]) + float(obj["bottom"])) / 2


def fraction_rules(chars: list[Obj], rules: list[Obj]) -> list[Obj]:
    """The short horizontal rules with a character just above and just below: fraction bars."""
    found = []
    for rule in rules:
        if rule["bottom"] - rule["top"] > RULE_HEIGHT or rule["x1"] - rule["x0"] < 3:
            continue
        over = [c for c in chars if rule["x0"] - 1 <= middle_x(c) <= rule["x1"] + 1]
        above = any(0 <= rule["top"] - c["bottom"] + 1 < REACH * c["size"] for c in over)
        below = any(0 <= c["top"] - rule["bottom"] + 1 < REACH * c["size"] for c in over)
        if above and below:
            found.append(rule)
    return found


def math_font(char: Obj) -> bool:
    """Whether a character is in one of TeX's math fonts: its italic letters, symbols or big
    signs (cmmi, cmsy, cmex, and the AMS msam and msbm)."""
    name = str(char.get("fontname", "")).upper()
    return any(font in name for font in MATH_FONTS)


def find_formulas(chars: list[Obj], rules: list[Obj]) -> list[Formula]:
    """The formulas on a page: each fraction rule or big sign, with every character on the same
    rows as it, read as one line. Only rows with TeX's math fonts in them are formulas, so a
    table's rules or a line under a heading are not; characters on rows of their own, and rows
    of text with something tall between them, are left as text."""
    bars = fraction_rules(chars, rules)
    seeds: list[tuple[float, float]] = []
    for bar in bars:
        over = [c for c in chars if bar["x0"] - 1 <= middle_x(c) <= bar["x1"] + 1]
        near = [c for c in over if abs(middle_y(c) - bar["top"]) < REACH * c["size"]]
        seeds.append((min(c["top"] for c in near), max(c["bottom"] for c in near)))
    seeds += [(c["top"], c["bottom"]) for c in chars if symbol(c) in BIG]
    bands = grow(sorted(seeds), chars)
    formulas = []
    for top, bottom in bands:
        inside = [c for c in chars if top <= middle_y(c) <= bottom]
        inside += [c for c in under_and_over(inside, chars) if c not in inside]
        if not any(math_font(c) for c in inside) or not one_row(inside, bars):
            continue
        own_bars = [b for b in bars if top <= b["top"] <= bottom]
        text = linear(inside, own_bars)
        if text:
            formulas.append(Formula(top, bottom, text, inside))
    return formulas


def under_and_over(inside: list[Obj], chars: list[Obj]) -> list[Obj]:
    """What is written under and over the big signs among `inside`, such as an integral's
    limits, which sit further from the row than the sign's box says."""
    found = []
    for sign in [c for c in inside if symbol(c) in BIG]:
        for c in chars:
            near = sign["x0"] - 2 <= middle_x(c) <= sign["x1"] + 4
            gap = max(c["top"] - sign["bottom"], sign["top"] - c["bottom"])
            if near and 0 <= gap < REACH * sign["size"] and c["size"] < sign["size"]:
                found.append(c)
    return found


def one_row(chars: list[Obj], bars: list[Obj]) -> bool:
    """Whether the characters, leaving out those over or under a fraction rule and those
    smaller than the rest, stand on one line."""
    size = max(c["size"] for c in chars)
    level = [
        c
        for c in chars
        if c["size"] >= SCRIPT * size
        and symbol(c) not in _CMEX.values()
        and not any(b["x0"] - 1 <= middle_x(c) <= b["x1"] + 1 for b in bars)
    ]
    return not level or max(c["bottom"] for c in level) - min(c["bottom"] for c in level) < (
        size / 2
    )


def grow(seeds: list[tuple[float, float]], chars: list[Obj]) -> list[tuple[float, float]]:
    """Bands from top to bottom, each widened until no character half in it is left out, and
    joined where they meet."""
    bands: list[tuple[float, float]] = []
    for top, bottom in seeds:
        while True:
            touching = [
                c
                for c in chars
                if min(bottom, c["bottom"]) - max(top, c["top"]) > (c["bottom"] - c["top"]) / 2
            ]
            new_top = min([top, *(c["top"] for c in touching)])
            new_bottom = max([bottom, *(c["bottom"] for c in touching)])
            if (new_top, new_bottom) == (top, bottom):
                break
            top, bottom = new_top, new_bottom
        if bands and top <= bands[-1][1]:
            top = min(top, bands[-1][0])
            bottom = max(bottom, bands[-1][1])
            bands.pop()
        bands.append((top, bottom))
    return bands


@dataclass
class _Item:
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    text: str
    big: bool = False  # a big sign, with what is written over and under it
    level: bool = False  # never a power or an index: a big sign or bracket, or a fraction


def linear(chars: list[Obj], bars: list[Obj]) -> str:
    """Characters and fraction rules read left to right as one line of text."""
    chars = [c for c in chars if symbol(c).strip() and not CID.fullmatch(symbol(c))]
    items: list[_Item] = []
    bars = sorted(bars, key=lambda b: b["x1"] - b["x0"], reverse=True)
    while bars:
        bar = bars.pop(0)

        def over(obj: Obj, bar: Obj = bar) -> bool:
            return bool(bar["x0"] - 1 <= middle_x(obj) <= bar["x1"] + 1)

        above = [c for c in chars if over(c) and middle_y(c) < bar["top"]]
        below = [c for c in chars if over(c) and middle_y(c) > bar["bottom"]]
        if not above or not below:
            continue
        inner = [b for b in bars if over(b)]
        bars = [b for b in bars if not over(b)]
        chars = [c for c in chars if not over(c)]
        top = linear(above, [b for b in inner if b["top"] < bar["top"]])
        bottom = linear(below, [b for b in inner if b["top"] > bar["top"]])
        size = max(c["size"] for c in above + below)
        height = (bar["top"] - size / 2, bar["bottom"] + size / 2)
        text = f"{grouped(top)}/{grouped(bottom)}"
        items.append(_Item(bar["x0"], bar["x1"], *height, size, text, level=True))
    for c in chars:
        text = symbol(c)
        box = (float(c["x0"]), float(c["x1"]), float(c["top"]), float(c["bottom"]))
        tex = text != c["text"]  # from TeX's math extension font
        items.append(_Item(*box, float(c["size"]), text, big=text in BIG, level=tex))
    items = limits(items)
    return line(sorted(items, key=lambda i: i.x0))


def limits(items: list[_Item]) -> list[_Item]:
    """A big sign with what is written over and under it, as "∑_(n=1)^∞"."""
    for sign in [i for i in items if i.big]:
        width = (sign.x0 - 2, sign.x1 + 4)
        under = [i for i in items if width[0] <= (i.x0 + i.x1) / 2 <= width[1]]
        lower = [i for i in under if i.top >= sign.bottom - 1 and not i.big]
        upper = [i for i in under if i.bottom <= sign.top + 1 and not i.big]
        if not lower and not upper:
            continue
        text = sign.text
        if lower:
            text += "_" + grouped(line(sorted(lower, key=lambda i: i.x0)), "^_")
        if upper:
            text += "^" + grouped(line(sorted(upper, key=lambda i: i.x0)), "^_")
        items = [i for i in items if i not in lower + upper]
        sign.text = text
    return items


def line(items: list[_Item]) -> str:
    """Items from left to right, with spaces at gaps and around signs like "=", and smaller
    raised or lowered characters as powers ("^") or indexes ("_")."""
    out = ""
    base: _Item | None = None
    script: tuple[str, list[_Item]] | None = None  # "^" or "_", and the characters in it
    previous: _Item | None = None

    def close() -> None:
        nonlocal out, script
        if script:
            out += script[0] + grouped(join(script[1]))
            script = None

    for item in items:
        mark = None
        if base is not None and item.size < SCRIPT * base.size:
            shift = (item.top + item.bottom) / 2 - (base.top + base.bottom) / 2
            if not item.level:
                mark = "^" if shift < -0.5 else "_" if shift > 0.5 else None
            elif not item.big and "/" in item.text and (shift < -0.2 * base.size or script):
                mark = "^" if shift < 0 else None  # a fraction in a power: "x^((s−3)/2)"
        if mark:
            if script and script[0] == mark:
                script[1].append(item)
            else:
                close()
                script = (mark, [item])
            continue
        close()
        if previous is not None and spaced(previous, item, out):
            out += " "
        out += item.text
        base = previous = item
    close()
    return out.strip()


def spaced(previous: _Item, item: _Item, out: str) -> bool:
    if item.text in ",.;:)]}" or out.endswith(("(", "[", "{")):
        return False
    if item.text in SPACED or out[-1:] in SPACED or previous.big:
        return True
    return item.x0 - previous.x1 > WORD_GAP * max(item.size, previous.size)


def join(items: list[_Item]) -> str:
    """The characters of a power or index, together: "s−1"."""
    return line([_Item(i.x0, i.x1, 0, 1, 1, i.text) for i in items]).replace(" ", "")


def grouped(text: str, also: str = "") -> str:
    """Text in brackets when it is more than one term: "1 − 1/p^s" becomes "(1 − 1/p^s)", while
    "p^s" and "Π(s−1)" stay as they are. Characters in `also` need brackets too."""
    depth = 0
    for ch in text:
        depth += ch in "([{"
        depth -= ch in ")]}"
        if depth == 0 and (ch.isspace() or ch in SPACED or ch in "/," or ch in also):
            return f"({text})"
    return text
