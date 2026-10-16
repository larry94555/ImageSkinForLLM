from typing import Any

import pytest

from imageskin import pdf_math
from imageskin.pdf_math import find_formulas, grouped, linear, scripts, symbol


def chars(*rows: tuple[str, str, float, float, float, float, float]) -> list[dict[str, Any]]:
    """Characters as pdfplumber gives them: text, font, size, x0, x1, top, bottom."""
    keys = ("text", "fontname", "size", "x0", "x1", "top", "bottom")
    return [dict(zip(keys, row, strict=True)) for row in rows]


def rule(x0: float, x1: float, top: float) -> dict[str, Any]:
    return {"x0": x0, "x1": x1, "top": top, "bottom": top + 0.4}


# Euler's product as Wilkins's translation of Riemann's paper sets it (page 2), read line by line
# as "1 1 = , 1− 1 ns ps" with the product and sum signs as "(cid:89)" and "(cid:80)".
EULER = chars(
    ("(cid:89)", "HVYSAN+CMEX10", 10.0, 250.4, 263.1, 559.7, 569.7),
    ("1", "CMR12", 12.0, 279.9, 285.8, 544.4, 556.3),
    ("1", "CMR12", 12.0, 266.3, 272.1, 566.7, 578.6),
    ("−", "CMSY10", 12.0, 274.8, 284.1, 564.3, 576.3),
    ("1", "CMR12", 12.0, 290.2, 296.0, 558.6, 570.5),
    ("p", "CMMI12", 12.0, 287.9, 293.8, 574.9, 586.8),
    ("s", "CMMI8", 8.0, 293.8, 297.7, 574.6, 582.6),
    ("=", "CMR12", 12.0, 304.0, 313.1, 552.5, 564.4),
    ("(cid:80)", "CMEX10", 10.0, 316.4, 326.9, 561.7, 571.7),
    ("1", "CMR12", 12.0, 330.9, 336.7, 544.4, 556.3),
    ("n", "CMMI12", 12.0, 328.1, 335.1, 560.7, 572.6),
    ("s", "CMMI8", 8.0, 335.1, 339.0, 560.4, 568.4),
    (",", "CMMI12", 12.0, 340.7, 343.9, 552.5, 564.4),
)
EULER_RULES = [rule(266.3, 299.4, 558.9), rule(287.9, 298.2, 573.1), rule(328.1, 339.5, 558.9)]
# The lines of text just before and after it.
BEFORE = chars(
    *((ch, "CMR12", 12.0, 103 + 7 * i, 109 + 7 * i, 525.1, 537.0) for i, ch in enumerate("product"))
)
AFTER = chars(
    ("i", "CMR12", 12.0, 102.9, 106.1, 594.8, 606.7),
    ("f", "CMR12", 12.0, 106.1, 109.7, 594.8, 606.7),
)


def test_euler_s_product_is_read_as_one_line() -> None:
    (formula,) = find_formulas(BEFORE + EULER + AFTER, EULER_RULES)

    assert formula.text == "∏ 1/(1 − 1/p^s) = ∑ 1/n^s,"
    assert formula.chars == EULER  # the lines of text around it are left as text
    assert (formula.top, formula.bottom) == (544.4, 586.8)


def test_a_formula_in_one_column_leaves_the_other_column_s_prose_as_text() -> None:
    # Euler's product in the left column, with three lines of prose in the right column beside
    # it, on the rows it spans.
    prose = [
        dict(c, x0=c["x0"] + 420 - 103, x1=c["x1"] + 420 - 103, top=top, bottom=top + 11.9)
        for top in (542.0, 556.0, 570.0)
        for c in BEFORE
    ]
    (formula,) = find_formulas(BEFORE + EULER + AFTER + prose, EULER_RULES)

    assert formula.text == "∏ 1/(1 − 1/p^s) = ∑ 1/n^s,"
    assert formula.chars == EULER  # the right column is left as text


def test_a_formula_as_wide_as_the_page_is_read_whole() -> None:
    # The same formula with its terms spread across the page: each gap is narrow enough to be
    # within one formula.
    spread = [dict(c, x0=c["x0"] * 1.4 - 100, x1=c["x1"] * 1.4 - 100) for c in EULER]
    rules = [dict(r, x0=r["x0"] * 1.4 - 100, x1=r["x1"] * 1.4 - 100) for r in EULER_RULES]
    (formula,) = find_formulas(spread, rules)

    assert formula.text == "∏ 1/(1 − 1/p^s) = ∑ 1/n^s,"


def test_an_integral_has_its_limits_and_powers() -> None:
    # ∫_0^∞ e^{-nx} dx = 1/n, with the limits further from the sign than its box says.
    found = linear(
        chars(
            ("∞", "CMSY8", 8.0, 233.6, 242.1, 684.7, 692.6),
            ("(cid:90)", "CMEX10", 10.0, 230.7, 236.2, 702.2, 712.2),
            ("0", "CMR8", 8.0, 231.3, 235.5, 717.1, 725.1),
            ("e", "CMMI12", 12.0, 242.6, 248.0, 699.0, 711.0),
            ("−", "CMSY8", 8.0, 248.0, 254.6, 695.8, 703.7),
            ("n", "CMMI8", 8.0, 254.6, 259.8, 697.3, 705.3),
            ("x", "CMMI8", 8.0, 259.8, 264.5, 697.3, 705.3),
            ("d", "CMMI12", 12.0, 268.9, 275.0, 699.0, 711.0),
            ("x", "CMMI12", 12.0, 275.0, 281.6, 699.0, 711.0),
            ("=", "CMR12", 12.0, 285.0, 294.1, 699.0, 711.0),
            ("1", "CMR12", 12.0, 298.6, 304.4, 691.0, 702.9),
            ("n", "CMMI12", 12.0, 298.0, 305.0, 707.2, 719.2),
        ),
        [rule(297.5, 305.5, 705.0)],
    )
    assert found == "∫_0^∞ e^(−nx) dx = 1/n"


def test_an_index_and_a_bracket_from_the_math_font() -> None:
    # g_1(b) after a word, with the bracket in TeX's math extension font, which is never an
    # index: a formula with no fraction or big sign, found by its index.
    so = chars(
        ("s", "CMR12", 12.0, 80.0, 85.0, 600.0, 612.0),
        ("o", "CMR12", 12.0, 85.0, 91.0, 600.0, 612.0),
    )
    g_1 = chars(
        ("g", "CMMI12", 12.0, 100.0, 106.0, 600.0, 612.0),
        ("1", "CMR8", 8.0, 106.0, 110.0, 606.0, 614.0),
        ("(cid:0)", "CMEX10", 10.0, 111.0, 115.0, 601.0, 611.0),
        ("b", "CMMI12", 12.0, 115.0, 120.0, 600.0, 612.0),
        ("(cid:1)", "CMEX10", 10.0, 120.0, 124.0, 601.0, 611.0),
    )
    (formula,) = find_formulas(so + g_1, [])
    assert formula.text == "so g_1 (b)"


def test_powers_alone_make_a_formula_but_a_footnote_s_number_does_not() -> None:
    # x² + y² = z² as TeX sets it: italic letters (cmmi) with roman powers (cmr8) raised.
    pythagoras = chars(
        ("x", "CMMI12", 12.0, 100.0, 106.7, 600.0, 612.0),
        ("2", "CMR8", 8.0, 107.0, 111.2, 596.0, 604.0),
        ("+", "CMR12", 12.0, 114.0, 123.1, 600.0, 612.0),
        ("y", "CMMI12", 12.0, 126.0, 131.9, 600.0, 612.0),
        ("2", "CMR8", 8.0, 132.0, 136.2, 596.0, 604.0),
        ("=", "CMR12", 12.0, 139.0, 148.1, 600.0, 612.0),
        ("z", "CMMI12", 12.0, 151.0, 156.5, 600.0, 612.0),
        ("2", "CMR8", 8.0, 156.6, 160.8, 596.0, 604.0),
    )
    (formula,) = find_formulas(pythagoras, [])
    assert formula.text == "x^2 + y^2 = z^2"
    footnote = chars(
        ("n", "CMR12", 12.0, 100.0, 106.5, 600.0, 612.0),
        ("1", "CMR8", 8.0, 106.6, 110.8, 596.0, 604.0),
    )
    assert find_formulas(footnote, []) == []


def test_rows_without_math_fonts_are_not_formulas() -> None:
    # A heading with a line under it, over the next line of text: not a fraction.
    heading = chars(
        ("S", "Helvetica", 12.0, 72, 80, 100, 112), ("t", "Helvetica", 12.0, 80, 84, 100, 112)
    )
    text = chars(
        ("O", "Helvetica", 12.0, 72, 80, 116, 128), ("k", "Helvetica", 12.0, 80, 86, 116, 128)
    )
    assert find_formulas(heading + text, [rule(72, 84, 113.5)]) == []


def test_lines_of_text_with_a_tall_sign_between_them_are_left_as_text() -> None:
    lines = chars(
        ("a", "CMR12", 12.0, 100, 106, 600, 612),
        ("(cid:80)", "CMEX10", 10.0, 120, 130, 606, 616),
        ("b", "CMMI12", 12.0, 140, 146, 610, 622),
    )
    assert find_formulas(lines, []) == []


def test_symbols_from_the_math_extension_font_get_their_text() -> None:
    assert symbol({"text": "(cid:88)", "fontname": "ABCDEF+CMEX10"}) == "∑"
    assert symbol({"text": "(cid:89)", "fontname": "CMEX10"}) == "∏"
    assert (
        symbol({"text": "(cid:64)", "fontname": "CMEX10"}) == "(cid:64)"
    )  # a tall bracket's piece
    assert symbol({"text": "(cid:89)", "fontname": "Helvetica"}) == "(cid:89)"


def test_more_than_one_term_is_put_in_brackets() -> None:
    assert grouped("1 − 1/p^s") == "(1 − 1/p^s)"
    assert grouped("p^s") == "p^s"
    assert grouped("Π(s − 1)") == "Π(s − 1)"
    assert grouped("p^2", also="^_") == "(p^2)"


def page(font: str, script_font: str = "") -> list[dict[str, Any]]:
    """A full page of text, 60 lines of 80 characters, with a raised smaller character after
    every tenth one when script_font is given."""
    found = []
    for line in range(60):
        top = 72.0 + 12 * line
        for i in range(80):
            x = 72.0 + 6 * i
            found.append(
                {
                    "text": "a",
                    "fontname": font,
                    "size": 10.0,
                    "x0": x,
                    "x1": x + 5.5,
                    "top": top,
                    "bottom": top + 10,
                }
            )
            if script_font and i % 10 == 9:
                found.append(
                    {
                        "text": "2",
                        "fontname": script_font,
                        "size": 7.0,
                        "x0": x + 5.5,
                        "x1": x + 5.9,
                        "top": top - 3,
                        "bottom": top + 4,
                    }
                )
    return found


def test_finding_scripts_is_not_a_search_of_every_pair_of_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks = 0

    def counted(obj: dict[str, Any]) -> float:
        nonlocal checks
        checks += 1
        return float(obj["top"] + obj["bottom"]) / 2

    monkeypatch.setattr(pdf_math, "middle_y", counted)
    assert scripts(page("Times-Roman")) == [] and checks == 0  # no math font: not searched
    with_math = page("CMMI10", "CMR7")
    found = scripts(with_math)
    assert len(found) == 60 * 8
    # Every pair would be about 23 million checks; each character meets only its neighbours.
    assert checks < 200 * len(with_math)
