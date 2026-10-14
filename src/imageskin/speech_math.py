"""Math in a reply, said in words (roadmap R16b), the way speech_text.py says what a link is.

LaTeX between $...$, $$...$$, \\(...\\) or \\[...\\] is read aloud when it is short
("$\\zeta(s)$" is "zeta of s", "$x^2 + 1$" is "x squared plus 1"); a longer one, or one with a
command this module doesn't know, is replaced by a phrase pointing to the text. Outside LaTeX,
Greek letters and math symbols are said by name ("π" is "pi", "≤" is "is less than or equal
to"). Only what is spoken changes: the reply on screen is left as written. Pure Python, no
logging: the callers log.
"""

import re
import unicodedata

EQUATION = "the equation in the text below"
EQUATION_BLOCK = "See the equation in the text below."
# LaTeX that would take more words than this to say is pointed to instead.
MAX_WORDS = 30

# Math in a reply: $$...$$ and \[...\] on lines of their own or not, then \(...\) and $...$.
# A $ that opens math is not followed by a space and one that closes it not preceded by one,
# nor followed by a digit, so "$5 and $10" is money, not math.
MATH = re.compile(
    r"\$\$(?P<display>.+?)\$\$"
    r"|\\\[(?P<display2>.+?)\\\]"
    r"|\\\((?P<inline>.+?)\\\)"
    r"|(?<![\\$\w])\$(?![\s$])(?P<inline2>[^$\n]+?)(?<![\s\\])\$(?![\d$])",
    re.S,
)


def math_parts(m: re.Match[str]) -> tuple[str, bool]:
    """The LaTeX inside a MATH match, and whether it is display math (on a line of its own)."""
    display = m["display"] if m["display"] is not None else m["display2"]
    if display is not None:
        return display, True
    return m["inline"] if m["inline"] is not None else m["inline2"], False


_GREEK_NAMES = (
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho"
    " sigma tau upsilon phi chi psi omega"
).split()
# What a command says. Greek letters say their names, capitals too ("\Gamma" is "gamma").
_SAY = {
    **{g: g for g in _GREEK_NAMES},
    **{g.capitalize(): g for g in _GREEK_NAMES},
    "varepsilon": "epsilon",
    "vartheta": "theta",
    "varphi": "phi",
    "varrho": "rho",
    "varsigma": "sigma",
    "cdot": "times",
    "times": "times",
    "ast": "times",
    "div": "divided by",
    "pm": "plus or minus",
    "mp": "minus or plus",
    "le": "is less than or equal to",
    "leq": "is less than or equal to",
    "ge": "is greater than or equal to",
    "geq": "is greater than or equal to",
    "ll": "is much less than",
    "gg": "is much greater than",
    "ne": "is not equal to",
    "neq": "is not equal to",
    "approx": "is approximately",
    "sim": "is similar to",
    "simeq": "is approximately",
    "cong": "is congruent to",
    "equiv": "is equivalent to",
    "propto": "is proportional to",
    "infty": "infinity",
    "in": "in",
    "notin": "is not in",
    "subset": "is a subset of",
    "subseteq": "is a subset of",
    "cup": "union",
    "cap": "intersection",
    "setminus": "minus",
    "emptyset": "the empty set",
    "varnothing": "the empty set",
    "forall": "for all",
    "exists": "there exists",
    "neg": "not",
    "land": "and",
    "lor": "or",
    "partial": "partial",
    "nabla": "del",
    "to": "to",
    "rightarrow": "to",
    "mapsto": "maps to",
    "Rightarrow": "implies",
    "implies": "implies",
    "iff": "if and only if",
    "Leftrightarrow": "if and only if",
    "ldots": "and so on",
    "cdots": "and so on",
    "dots": "and so on",
    "prime": "prime",
    "perp": "is perpendicular to",
    "parallel": "is parallel to",
    "angle": "angle",
    "degree": "degrees",
    "circ": "degrees",
    "hbar": "h bar",
    "ell": "l",
}
# Functions, said with "of" after them: "\sin x" is "sine of x".
_FUNCTIONS = {
    "sin": "sine",
    "cos": "cosine",
    "tan": "tangent",
    "sec": "secant",
    "csc": "cosecant",
    "cot": "cotangent",
    "arcsin": "arc sine",
    "arccos": "arc cosine",
    "arctan": "arc tangent",
    "sinh": "hyperbolic sine",
    "cosh": "hyperbolic cosine",
    "tanh": "hyperbolic tangent",
    "log": "log",
    "ln": "the natural log",
    "exp": "the exponential",
    "det": "the determinant",
    "gcd": "the greatest common divisor",
    "max": "the maximum",
    "min": "the minimum",
    "Re": "the real part",
    "Im": "the imaginary part",
}
# Sums, products, integrals and limits, said with where they run from and to.
_BIG = {
    "sum": "the sum",
    "prod": "the product",
    "int": "the integral",
    "iint": "the double integral",
    "oint": "the contour integral",
    "lim": "the limit",
}
# Commands that only change spacing, size or style, and say nothing.
_SILENT = set(
    "left right big Big bigg Bigg bigl bigr Bigl Bigr displaystyle textstyle quad qquad limits"
    " nolimits , ; ! : { } | $ % & #".split()
)
_FONTS = set("mathbb mathbf mathit mathcal mathsf mathfrak boldsymbol bm mathrm".split())
_TEXT = set("text textrm textit textbf mbox".split())
# Letters that are usually functions, so "f(x)" is "f of x" but "n(n+1)" is "n n plus 1".
_FUNCTION_LETTERS = set("fghFGHPL")
# Symbols as the command they stand for.
_UNICODE = {
    "∞": "infty",
    "≤": "le",
    "≥": "ge",
    "≠": "ne",
    "≈": "approx",
    "≡": "equiv",
    "∝": "propto",
    "∈": "in",
    "∉": "notin",
    "⊂": "subset",
    "⊆": "subseteq",
    "∪": "cup",
    "∩": "cap",
    "∀": "forall",
    "∃": "exists",
    "∂": "partial",
    "∇": "nabla",
    "→": "to",
    "⇒": "implies",
    "⇔": "iff",
    "×": "times",
    "÷": "div",
    "±": "pm",
    "∓": "mp",
    "°": "degree",
    "∑": "sum",
    "∏": "prod",
    "∫": "int",
    "√": "sqrt",
    "∛": "cbrt",
    "−": "-",
    "⋅": "cdot",
    "⋯": "cdots",
}
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿⁱ", "0123456789+-ni")
_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋", "0123456789+-")
SUPERSCRIPT_RUN = re.compile("[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿⁱ]+")
SUBSCRIPT_RUN = re.compile("[₀₁₂₃₄₅₆₇₈₉₊₋]+")
_TOKEN = re.compile(
    rf"\\[a-zA-Z]+|\\.|\d+(?:\.\d+)?|[a-zA-Z]+|{SUPERSCRIPT_RUN.pattern}|{SUBSCRIPT_RUN.pattern}|\S"
)
_SYMBOLS = {
    "=": ["equals"],
    "+": ["plus"],
    "-": ["minus"],
    "*": ["times"],
    "/": ["over"],
    "<": ["is", "less", "than"],
    ">": ["is", "greater", "than"],
    "!": ["factorial"],
    "'": ["prime"],
    ",": [","],
    ";": [","],
}
_QUIET = set(".:|&~")  # said as nothing


def greek_name(ch: str) -> str | None:
    """The name of a Greek letter ("ζ" is "zeta"), or None for any other character."""
    if not ("Α" <= ch <= "Ω" or "α" <= ch <= "ω"):
        return None
    name = unicodedata.name(ch, "").split()[-1].lower()
    return "lambda" if name == "lamda" else name  # Unicode spells it LAMDA


def symbol_words(ch: str) -> str | None:
    """What a math symbol or Greek letter outside LaTeX says, or None if it isn't one."""
    command = _UNICODE.get(ch)
    if command in _SYMBOLS:
        return " ".join(_SYMBOLS[command])
    if command == "sqrt":
        return "the square root of"
    if command == "cbrt":
        return "the cube root of"
    if command in _BIG:
        return _BIG[command]
    if command is not None and command in _SAY:
        return _SAY[command]
    return greek_name(ch)


def power(exponent: list[str]) -> list[str]:
    """How a power is said: "squared", "cubed" or "to the power of ..."."""
    if exponent == ["2"]:
        return ["squared"]
    if exponent == ["3"]:
        return ["cubed"]
    return ["to", "the", "power", "of", *exponent]


class _Unsayable(Exception):
    """LaTeX with a command this module doesn't know how to say."""


class _Reader:
    def __init__(self, tex: str) -> None:
        self.tokens: list[str] = _TOKEN.findall(tex)
        self.at = 0
        self.function = False  # whether the last thing said takes "of" before brackets
        self.in_limit = False  # under \lim, where "\to" is "goes to"

    def peek(self) -> str | None:
        return self.tokens[self.at] if self.at < len(self.tokens) else None

    def take(self) -> str:
        self.at += 1
        return self.tokens[self.at - 1]

    def run(self, stop: str | None = None) -> list[str]:
        """Words until `stop` (taken) or the end."""
        words: list[str] = []
        while (token := self.peek()) is not None:
            if token == stop:
                self.take()
                break
            if token in ")]}" and stop is not None:
                break  # a bracket closing an outer group
            words += self.item(words)
        return words

    def argument(self) -> list[str]:
        """A command's argument: a {group} or one token."""
        if self.peek() == "{":
            self.take()
            return self.run("}")
        if self.peek() is None:
            return []
        return self.item([])

    def item(self, before: list[str]) -> list[str]:
        was_function, self.function = self.function, False
        token = self.take()
        if token in _UNICODE:  # a symbol, as the command or character it stands for
            command = _UNICODE[token]
            token = "\\" + command if command.isalpha() else command
        if token.startswith("\\") and token[1:] in _SILENT:
            self.function = was_function  # "\zeta\left(s\right)" is still "zeta of s"
            return []
        if token == "{":
            return self.run("}")
        if token == "(":
            inside = self.run(")")
            return ["of", *inside] if was_function and before[-1:] != ["of"] else inside
        if token == "[":
            return self.run("]")
        if token in ")]}" or token in _QUIET:
            return []
        if token == "^":
            words = power(self.argument())
            self.function = was_function  # "f^2(x)" is still a function
            return words
        if token == "_":
            words = ["sub", *self.argument()]
            self.function = was_function
            return words
        if token in _SYMBOLS:
            return list(_SYMBOLS[token])
        if SUPERSCRIPT_RUN.fullmatch(token):
            exponent = token.translate(_SUPERSCRIPTS)  # "x⁻¹⁰" is "x to the power of minus 10"
            return power(["minus", exponent[1:]] if exponent[:1] == "-" else [exponent])
        if SUBSCRIPT_RUN.fullmatch(token):
            return ["sub", token.translate(_SUBSCRIPTS)]
        if token[0].isdigit():
            return [token]
        if token.isascii() and token.isalpha():
            if token in _FUNCTIONS:
                return self.function_words(_FUNCTIONS[token])
            self.function = len(token) == 1 and token in _FUNCTION_LETTERS
            return list(token)  # "dx" is "d x"
        if token.startswith("\\"):
            return self.command(token[1:])
        if (name := greek_name(token)) is not None:
            self.function = True
            return [name]
        raise _Unsayable(token)

    def function_words(self, name: str) -> list[str]:
        words = name.split()
        if self.peek() == "^":  # "\sin^2 x" is "sine squared of x"
            self.take()
            words += power(self.argument())
        self.function = True
        return [*words, "of"]

    def command(self, name: str) -> list[str]:
        if name in _SILENT:
            return []
        if name == "\\":
            return [","]  # a new line
        if name in _BIG:
            return self.big(name)
        if name in _FUNCTIONS:
            return self.function_words(_FUNCTIONS[name])
        if name in ("frac", "dfrac", "tfrac"):
            top = self.argument()
            return [*top, "over", *self.argument()]
        if name == "binom":
            top = self.argument()
            return [*top, "choose", *self.argument()]
        if name in ("sqrt", "cbrt"):
            root = "cube" if name == "cbrt" else "square"
            if self.peek() == "[":
                self.take()
                index = self.run("]")
                root = "cube" if index == ["3"] else " ".join(index) + "th"
            return ["the", root, "root", "of", *self.argument()]
        if name in _TEXT:
            return self.raw_text()
        if name in _FONTS:
            return self.argument()
        if name == "operatorname":
            return self.function_words(" ".join(self.argument()))
        if name in _SAY:
            if name == "to" and self.in_limit:
                return ["goes", "to"]
            self.function = name in _GREEK_NAMES or name.lower() in _GREEK_NAMES
            return _SAY[name].split()
        raise _Unsayable(name)

    def big(self, name: str) -> list[str]:
        """A sum, product, integral or limit with where it runs: "the sum from n equals 1 to
        infinity of"."""
        words = _BIG[name].split()
        while self.peek() in ("_", "^", "\\limits"):
            mark = self.take()
            if mark == "_":
                self.in_limit = name == "lim"
                words += ["as" if name == "lim" else "from", *self.argument()]
                self.in_limit = False
            elif mark == "^":
                words += ["to", *self.argument()]
        return [*words, "of"]

    def raw_text(self) -> list[str]:
        if self.peek() != "{":
            return [self.take()] if self.peek() is not None else []
        self.take()
        words, depth = [], 1
        while (token := self.peek()) is not None:
            self.take()
            depth += {"{": 1, "}": -1}.get(token, 0)
            if depth == 0:
                break
            if token not in "{}":
                words.append(token)
        return words


def say_math(tex: str) -> str | None:
    """LaTeX said in words, or None when it is too long to say or has a command this module
    doesn't know: the caller then points to the text instead."""
    try:
        words = _Reader(tex).run()
    except _Unsayable:
        return None
    if words[-1:] == ["of"]:
        words.pop()  # "\sum" alone is "the sum", not "the sum of"
    if sum(w != "," for w in words) > MAX_WORDS:
        return None
    return re.sub(r"(?:\s*,)+", ",", " ".join(words)).strip(" ,")
