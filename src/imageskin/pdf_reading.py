"""Reading a PDF's content (roadmap R36, item 25): text as paragraphs, slides page by page and
tables as rows and columns, each piece with the page it came from. The wiki (R37) is built from
what is read here.

pdfplumber (MIT, on pdfminer.six) does the reading, on the CPU. A page wider than it is tall is
taken as a slide; any other page is split into paragraphs at the gaps between lines. Tables are
found from their ruling lines, so a table drawn without lines is read as text. A scanned page is
a picture with no text in it: it is listed in `pages_without_text`, since there is no OCR yet.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pdfplumber

logger = logging.getLogger(__name__)

PdfKind = Literal["text", "slides", "tables"]
PieceKind = Literal["paragraph", "slide", "table"]
Progress = Callable[[int, int], None]  # pages read, pages in all

# A gap between two lines taller than this share of a line's height starts a new paragraph.
PARAGRAPH_GAP = 0.6
UNKNOWN_CHARACTER = re.compile(r"\(cid:\d+\)")


class ReadingError(Exception):
    """The PDF could not be read; the message says why, for the person who added it."""


@dataclass(frozen=True)
class Piece:
    page: int  # from 1
    kind: PieceKind
    text: str  # a table's rows, one per line with " | " between cells
    rows: list[list[str]] | None = None  # a table's cells


@dataclass(frozen=True)
class Reading:
    kind: PdfKind
    pages: int
    pieces: list[Piece]
    pages_without_text: list[int]


def read_pdf(path: Path, progress: Progress | None = None) -> Reading:
    """Read every page of a PDF, or raise ReadingError."""
    pieces: list[Piece] = []
    landscape = 0
    without_text: list[int] = []
    try:
        with pdfplumber.open(path) as pdf:
            total = len(pdf.pages)
            for number, page in enumerate(pdf.pages, start=1):
                slide = page.width > page.height
                landscape += slide
                found = read_page(page, number, slide)
                if not found and not page.chars:
                    without_text.append(number)
                pieces += found
                page.close()  # frees the page's parsed objects; a long PDF would fill memory
                if progress:
                    progress(number, total)
    except Exception as e:  # pdfminer raises many kinds for a broken or locked PDF
        raise ReadingError(
            "This PDF could not be read. It may be damaged or locked with a password."
        ) from e
    if without_text:
        logger.warning(
            "PDF pages with no text, maybe scanned; they are skipped",
            extra={"path": str(path), "pages": without_text},
        )
    return Reading(pdf_kind(pieces, landscape, total), total, pieces, without_text)


def read_page(page: Any, number: int, slide: bool) -> list[Piece]:
    """A page's tables and its text around them, top to bottom."""
    found: list[tuple[float, Piece]] = []
    boxes = []
    for table in page.find_tables():
        rows = [[clean(cell) for cell in row] for row in table.extract()]
        rows = [row for row in rows if any(row)]
        if len(rows) < 2 or max(len(row) for row in rows) < 2:
            continue  # a box around some text, not a table
        boxes.append(table.bbox)
        text = "\n".join(" | ".join(row) for row in rows)
        found.append((table.bbox[1], Piece(number, "table", text, rows)))
    rest = page.filter(lambda obj: not any(inside(obj, box) for box in boxes)) if boxes else page
    lines = [line for line in rest.extract_text_lines() if line["text"].strip()]
    if slide and lines:
        text = "\n".join(clean(line["text"]) for line in lines)
        found.append((lines[0]["top"], Piece(number, "slide", text)))
    elif lines:
        for top, text in paragraphs(lines):
            found.append((top, Piece(number, "paragraph", text)))
    return [piece for _, piece in sorted(found, key=lambda f: f[0])]


def paragraphs(lines: list[dict[str, Any]]) -> list[tuple[float, str]]:
    """Lines joined into paragraphs, each with where it starts on the page."""
    found: list[tuple[float, list[str]]] = []
    previous: dict[str, Any] | None = None
    for line in lines:
        height = line["bottom"] - line["top"]
        if previous is None or line["top"] - previous["bottom"] > PARAGRAPH_GAP * height:
            found.append((line["top"], []))
        found[-1][1].append(clean(line["text"]))
        previous = line
    return [(top, join_lines(texts)) for top, texts in found]


def join_lines(lines: list[str]) -> str:
    """'exam-' and 'ple' become 'example'; other lines are joined with a space."""
    text = ""
    for line in lines:
        if text.endswith("-") and line[:1].islower():
            text = text[:-1] + line
        else:
            text = f"{text} {line}" if text else line
    return text


def pdf_kind(pieces: list[Piece], landscape: int, pages: int) -> PdfKind:
    """Slides when most pages are wider than tall; tables when there are at least as many tables
    as paragraphs; text otherwise."""
    if pages and landscape * 2 > pages:
        return "slides"
    tables = sum(piece.kind == "table" for piece in pieces)
    if tables and tables >= sum(piece.kind == "paragraph" for piece in pieces):
        return "tables"
    return "text"


def inside(obj: dict[str, Any], box: tuple[float, float, float, float]) -> bool:
    """Whether an object's middle is within a box (x0, top, x1, bottom)."""
    x = (obj["x0"] + obj["x1"]) / 2
    y = (obj["top"] + obj["bottom"]) / 2
    return bool(box[0] <= x <= box[2] and box[1] <= y <= box[3])


def clean(text: str | None) -> str:
    """Runs of spaces and line breaks become one space, and a character the PDF gives no text
    for, which pdfminer writes as "(cid:127)", is left out."""
    return " ".join(UNKNOWN_CHARACTER.sub("", text or "").split())
