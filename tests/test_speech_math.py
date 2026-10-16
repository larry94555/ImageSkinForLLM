import pytest

from imageskin.speech_math import (
    EQUATION,
    EQUATION_BLOCK,
    MAX_WORDS,
    greek_name,
    say_math,
    symbol_words,
)
from imageskin.speech_text import LINK, inside_whole, spoken_text


@pytest.mark.parametrize(
    ("tex", "said"),
    [
        (r"\zeta(s)", "zeta of s"),
        (r"\zeta\left(s\right)", "zeta of s"),
        (r"\pi", "pi"),
        (r"\Gamma(s)", "gamma of s"),
        (r"x^2 + 1", "x squared plus 1"),
        (r"x^3 - y^{n+1}", "x cubed minus y to the power of n plus 1"),
        (r"\frac{1}{n^s}", "1 over n to the power of s"),
        (r"\sqrt{2}", "the square root of 2"),
        (r"\sqrt[3]{x}", "the cube root of x"),
        (r"\sqrt[n]{x}", "the nth root of x"),
        (r"f(x, y)", "f of x, y"),
        (r"n(n+1)/2", "n n plus 1 over 2"),  # not a function: no "of"
        (r"a_n \le b_n", "a sub n is less than or equal to b sub n"),
        (r"\sin^2 x + \cos^2 x = 1", "sine squared of x plus cosine squared of x equals 1"),
        (r"\ln(x)", "the natural log of x"),
        (r"\operatorname{Li}(x)", "L i of x"),
        (r"\sum", "the sum"),
        (
            r"\zeta(s) = \sum_{n=1}^{\infty} \frac{1}{n^s}",
            "zeta of s equals the sum from n equals 1 to infinity of 1 over n to the power of s",
        ),
        (
            r"\lim_{x \to 0} \frac{\sin x}{x} = 1",
            "the limit as x goes to 0 of sine of x over x equals 1",
        ),
        (r"\int_0^1 x\,dx", "the integral from 0 to 1 of x d x"),
        (r"\binom{n}{k}", "n choose k"),
        (r"\mathbb{R}", "R"),
        (r"\text{if } s > 1", "if s is greater than 1"),
        (r"x \in A, \; y \notin B", "x in A, y is not in B"),
        (r"a \\ b", "a, b"),
        (r"n! \cdot m'", "n factorial times m prime"),
        ("π ≈ 3.14", "pi is approximately 3.14"),
        ("x² − 1", "x squared minus 1"),
        ("x₁ + ∑", "x sub 1 plus the sum"),
        ("√2", "the square root of 2"),
        ("10⁻¹⁰", "10 to the power of minus 10"),
        ("[a]", "a"),
        ("", ""),
    ],
)
def test_latex_is_said_in_words(tex: str, said: str) -> None:
    assert say_math(tex) == said


def test_latex_that_cannot_be_said_well_is_not_said() -> None:
    assert say_math(r"\unknowncommand{x}") is None
    assert say_math("x ☃ y") is None
    assert say_math(" + ".join(["x"] * MAX_WORDS)) is None  # too long to say


def test_greek_letters_and_symbols_have_names() -> None:
    assert greek_name("ζ") == "zeta" and greek_name("λ") == "lambda" and greek_name("Ω") == "omega"
    assert greek_name("a") is None
    assert symbol_words("≤") == "is less than or equal to"
    assert symbol_words("−") == "minus"
    assert symbol_words("∫") == "the integral"
    assert symbol_words("∛") == "the cube root of"
    assert symbol_words("a") is None


@pytest.mark.parametrize(
    ("display", "said"),
    [
        # Larry's example (2026-10-14): the zeta function, in LaTeX or as plain symbols.
        (
            "The Riemann zeta function $\\zeta(s)$ is key.",
            "The Riemann zeta function zeta of s is key.",
        ),
        ("The Riemann zeta function ζ(s) is key.", "The Riemann zeta function zeta of s is key."),
        # Larry's reply that was spoken badly (2026-10-14).
        (
            "Yes, it does. The integral representation shows a link between ζ(s) and ζ(1-s).",
            "Yes, it does. The integral representation shows a link between zeta of s and zeta"
            " of 1 minus s.",
        ),
        (
            "Here π ≈ 3.14 and 2π is a full turn.",
            "Here pi is approximately 3.14 and 2 pi is a full turn.",
        ),
        ("Use \\(x^2\\) here.", "Use x squared here."),
        ("It is $$\\pi r^2$$ in all.", "It is pi r squared in all."),
        (
            "Then \\[e^{i\\pi} + 1 = 0\\] holds.",
            "Then e to the power of i pi plus 1 equals 0 holds.",
        ),
        (
            "Sum 1/n^s for x ≤ 3, at 30°.",
            "Sum 1 over n to the power of s for x is less than or equal to 3, at 30 degrees.",
        ),
        ("Area is πr² and 2^{10} is big.", "Area is pi r squared and 2 to the power of 10 is big."),
        ("$\\pi$ is a number.", "Pi is a number."),
        (
            "It holds for s > 1 and x <= 2, so y = 3.",
            "It holds for s is greater than 1 and x is less than or equal to 2, so y equals 3.",
        ),
        ("Keep a=b and 2 < x.", "Keep a=b and 2 is less than x."),
        ("Near Re(s) = 1/2.", "Near Re(s) equals 1 over 2."),
        ("It costs $5 and $10 today.", "It costs $5 and $10 today."),  # money, not math
        ("Greek λόγος stays.", "Greek λόγος stays."),  # a Greek word is not spelled out
        ("Run `x^2` and `π`.", "Run x^2 and π."),  # code is said as written
        ("Go to https://a.io/π now.", f"Go to {LINK} now."),
        ("So $\\unknown{x}$ holds.", f"So {EQUATION} holds."),
    ],
)
def test_math_in_a_reply_is_said_in_words(display: str, said: str) -> None:
    assert spoken_text(display) == said


def test_a_long_equation_on_its_own_lines_is_a_sentence_pointing_to_the_text() -> None:
    long = " + ".join(f"x_{i}" for i in range(20))
    assert (
        spoken_text(f"Here it is\n\n$${long}$$\n\nDone.") == f"Here it is. {EQUATION_BLOCK} Done."
    )
    assert spoken_text(f"So \\[{long}\\] holds.") == f"So {EQUATION} holds."
    zeta = "Riemann wrote\n\n$$\n\\zeta(s) = \\sum_{n=1}^{\\infty} n^{-s}\n$$\n\nfor s > 1."
    said = (
        "Riemann wrote. Zeta of s equals the sum from n equals 1 to infinity of n to the power"
        " of minus s. for s is greater than 1."  # the text after it is said as written
    )
    assert spoken_text(zeta) == said


def test_a_cut_inside_math_is_known() -> None:
    line = "so $a, b$ and \\(c, d\\) hold"
    assert inside_whole(line, line.index(",") + 1)
    assert inside_whole(line, line.index("c,") + 2)
    assert not inside_whole(line, line.index(" and"))


@pytest.mark.parametrize(
    ("tex", "said"),
    [
        # Larry heard "1 minus 1 over p" as (1 minus 1) over p (2026-10-15).
        (r"1 - \frac{1}{p}", "1 minus the fraction 1 over p"),
        (r"\frac{1}{p} + 1", "the fraction 1 over p, plus 1"),
        (r"\frac{x+1}{2}", "the quantity x plus 1, divided by 2"),
        (
            r"\prod_p \frac{1}{1 - p^{-s}} = \zeta(s)",
            "the product from p of 1 divided by the quantity 1 minus p to the power of minus s,"
            " equals zeta of s",
        ),
        (
            r"\frac{1}{1 - \frac{1}{p^s}}",
            "1 divided by the quantity 1 minus the fraction 1 over p to the power of s",
        ),
        (r"\frac{\sin x}{x}", "sine of x over x"),  # one term over one term
    ],
)
def test_a_fraction_is_said_so_it_can_be_heard_only_one_way(tex: str, said: str) -> None:
    assert say_math(tex) == said


def test_a_fraction_next_to_text_that_goes_on_with_it_is_the_fraction() -> None:
    assert say_math(r"\frac{1}{p}") == "1 over p"
    assert say_math(r"\frac{1}{p}", in_expression=True) == "the fraction 1 over p"
