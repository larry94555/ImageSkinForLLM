"""Small PDFs of each kind for the reading tests (roadmap R36), made with reportlab."""

from pathlib import Path

from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

# Two paragraphs of two lines each; the first breaks "setup" across its lines.
TEXT = [
    ["The product guide covers set-", "up and care."],
    ["Clean the lens with a soft cloth. Do not use", "water or any cleaning liquid."],
]
SLIDES = [["Quarterly review", "Sales grew 12%"], ["Next steps", "Hire two engineers"]]
TABLE = [["Item", "Price", "Stock"], ["Lens", "$40", "12"], ["Cloth", "$5", "300"]]


def text_pdf(path: Path) -> Path:
    """Two pages, each with the TEXT paragraphs."""
    pdf = canvas.Canvas(str(path), pagesize=letter)
    for _ in range(2):
        y = 700.0
        for paragraph in TEXT:
            for line in paragraph:
                pdf.drawString(72, y, line)
                y -= 14
            y -= 20
        pdf.showPage()
    pdf.save()
    return path


def slides_pdf(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=landscape(letter))
    for title, point in SLIDES:
        pdf.setFont("Helvetica-Bold", 28)
        pdf.drawString(72, 500, title)
        pdf.setFont("Helvetica", 18)
        pdf.drawString(72, 440, point)
        pdf.showPage()
    pdf.save()
    return path


def table_pdf(path: Path, blank_page: bool = False) -> Path:
    """A title and a ruled table; with blank_page, then a page with no text, like a scan."""
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.drawString(72, 720, "Price list")
    top, row_h, col_w = 680.0, 24.0, 100.0
    pdf.grid(
        [72 + col_w * i for i in range(len(TABLE[0]) + 1)],
        [top - row_h * i for i in range(len(TABLE) + 1)],
    )
    for r, row in enumerate(TABLE):
        for c, cell in enumerate(row):
            pdf.drawString(78 + col_w * c, top - row_h * (r + 1) + 8, cell)
    pdf.showPage()
    if blank_page:
        pdf.rect(72, 72, 400, 600, fill=1)  # a picture of a page, with no text
        pdf.showPage()
    pdf.save()
    return path
