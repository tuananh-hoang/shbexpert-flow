"""Shared helper to generate REAL PDF documents for seed data, with bbox
coordinates that are actually correct — not mock numbers invented by hand.

Per the frontend-flow plan Phase 3: the Evidence Viewer (Screen 3,
FE_flow.jpeg) renders the actual PDF with a highlight box over the cited
line, using `react-pdf`/pdf.js. That only works if the ExtractedField.bbox
values genuinely correspond to where the text was drawn — so this module
draws each line at a known position with reportlab and returns the exact
bbox it drew, rather than seed scripts inventing plausible-looking numbers
that don't match any real rendering.

Bbox convention: PDF POINT space (1/72 inch), origin at the BOTTOM-LEFT
of the page — reportlab's native coordinate system. The frontend converts
this to CSS pixels via pdf.js's own page viewport transform at render
time, not by reinterpreting these numbers as pixels directly.

Font: DejaVu Sans (installed via apt in api/Dockerfile — see the comment
there) — reportlab's built-in core fonts (Helvetica/Times/Courier) don't
cover Vietnamese precomposed characters (đ/ư/ơ/ệ/...), which sit outside
Latin-1/WinAnsi entirely.
"""
from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_NAME = "DejaVuSans"
_LEFT_MARGIN = 50
_TITLE_SIZE = 14
_BODY_SIZE = 11
_LINE_HEIGHT = 22

_font_registered = False


def _ensure_font() -> None:
    global _font_registered
    if not _font_registered:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
        _font_registered = True


def render_document_pdf(
    title: str, lines: list[tuple[str, str, str | None]]
) -> tuple[bytes, dict[str, dict]]:
    """Renders a single-page PDF: a title line, then one `label: value`
    line per entry in `lines`. Entries with a non-None third element
    (field_key) have their drawn bbox recorded and returned; entries
    sharing the same field_key have their bboxes UNIONED (for a field
    like "ownership_structure" that spans multiple printed lines).

    Returns (pdf_bytes, bbox_by_field_key) — each bbox is
    {"page": 1, "x0", "y0", "x1", "y1"} in PDF points.
    """
    _ensure_font()
    buf = io.BytesIO()
    width, height = A4
    c = pdfcanvas.Canvas(buf, pagesize=A4)

    c.setFont(FONT_NAME, _TITLE_SIZE)
    y = height - 60
    c.drawString(_LEFT_MARGIN, y, title)
    y -= 30

    c.setFont(FONT_NAME, _BODY_SIZE)
    bbox_by_field_key: dict[str, dict] = {}
    for label, value, field_key in lines:
        text = f"{label}: {value}"
        c.drawString(_LEFT_MARGIN, y, text)
        if field_key:
            text_width = c.stringWidth(text, FONT_NAME, _BODY_SIZE)
            rect = {
                "page": 1,
                "x0": _LEFT_MARGIN,
                "y0": y - 3,
                "x1": _LEFT_MARGIN + text_width,
                "y1": y + _BODY_SIZE,
            }
            if field_key in bbox_by_field_key:
                prev = bbox_by_field_key[field_key]
                rect = {
                    "page": 1,
                    "x0": min(prev["x0"], rect["x0"]),
                    "y0": min(prev["y0"], rect["y0"]),
                    "x1": max(prev["x1"], rect["x1"]),
                    "y1": max(prev["y1"], rect["y1"]),
                }
            bbox_by_field_key[field_key] = rect
        y -= _LINE_HEIGHT

    c.showPage()
    c.save()
    return buf.getvalue(), bbox_by_field_key
