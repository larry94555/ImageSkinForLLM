import logging
from pathlib import Path

import pytest
from pdf_samples import SLIDES, TABLE, formula_pdf, powers_pdf, slides_pdf, table_pdf, text_pdf

from imageskin.pdf_reading import ReadingError, clean, join_lines, pdf_kind, read_pdf


def test_text_is_read_as_paragraphs_with_their_page(tmp_path: Path) -> None:
    progress: list[tuple[int, int]] = []
    reading = read_pdf(text_pdf(tmp_path / "guide.pdf"), lambda *p: progress.append(p))

    assert reading.kind == "text" and reading.pages == 2 and reading.pages_without_text == []
    assert [(p.page, p.kind, p.text) for p in reading.pieces] == [
        (page, "paragraph", text)
        for page in (1, 2)
        for text in (
            "The product guide covers setup and care.",
            "Clean the lens with a soft cloth. Do not use water or any cleaning liquid.",
        )
    ]
    assert progress == [(1, 2), (2, 2)]


def test_slides_are_read_page_by_page(tmp_path: Path) -> None:
    reading = read_pdf(slides_pdf(tmp_path / "review.pdf"))

    assert reading.kind == "slides"
    assert [(p.page, p.kind, p.text) for p in reading.pieces] == [
        (1, "slide", "\n".join(SLIDES[0])),
        (2, "slide", "\n".join(SLIDES[1])),
    ]


def test_tables_are_read_as_rows_and_a_page_with_no_text_is_listed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        reading = read_pdf(table_pdf(tmp_path / "prices.pdf", blank_page=True))

    assert reading.kind == "tables" and reading.pages == 2
    title, table = reading.pieces
    assert (title.page, title.kind, title.text) == (1, "paragraph", "Price list")
    assert (table.page, table.kind, table.rows) == (1, "table", TABLE)
    assert table.text.splitlines()[1] == "Lens | $40 | 12"
    assert reading.pages_without_text == [2]
    warned = [r for r in caplog.records if r.message.startswith("PDF pages with no text")]
    assert warned[0].__dict__["pages"] == [2]


def test_a_formula_is_read_as_one_line_in_its_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # reportlab can't use TeX's math fonts, so its Helvetica stands in for them here.
    monkeypatch.setattr("imageskin.pdf_math.MATH_FONTS", ("HELVETICA",))
    with caplog.at_level(logging.INFO):
        reading = read_pdf(formula_pdf(tmp_path / "euler.pdf"))

    assert [p.text for p in reading.pieces] == [
        "Euler noticed that the sum 1/n = S grows without end.",
        "of its correspondents",  # words set close together are still words
    ]
    logged = [r for r in caplog.records if r.message == "Formulas read as one line"]
    assert logged[0].__dict__["formulas"] == 1 and logged[0].__dict__["pages"] == [1]


def test_a_formula_with_only_powers_is_read_with_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("imageskin.pdf_math.MATH_FONTS", ("TIMES-ITALIC",))  # for TeX's cmmi
    reading = read_pdf(powers_pdf(tmp_path / "pythagoras.pdf"))

    assert [p.text for p in reading.pieces] == [
        "Pythagoras showed that x^2 + y^2 = z^2 in a right triangle. It is well known1",
    ]  # a footnote's number in plain text is left as it is


def test_a_broken_pdf_raises_a_plain_reading_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7\nnot really a pdf\n%%EOF\n")
    with pytest.raises(ReadingError, match="could not be read"):
        read_pdf(broken)


def test_lines_broken_with_a_hyphen_are_joined() -> None:
    assert join_lines(["the set-", "up", "is quick"]) == "the setup is quick"
    assert join_lines(["Price -", "Total"]) == "Price - Total"  # not a word broken in two
    assert join_lines([]) == ""


def test_the_kind_of_pdf_comes_from_its_pages_and_pieces() -> None:
    assert pdf_kind([], 0, 0) == "text"
    assert pdf_kind([], 2, 3) == "slides"
    assert pdf_kind([], 1, 2) == "text"  # half isn't most


def test_cleaning_leaves_out_characters_with_no_text() -> None:
    assert clean("(cid:127) Sales  grew\n12%") == "Sales grew 12%"
    assert clean(None) == ""
