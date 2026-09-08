"""Minimal pure-Python PDF writer for contract snapshots (FR-29, FR-31).

Deliberately tiny: text-only, Helvetica, A4, automatic pagination. It exists
so the signed-contract snapshot needs no heavyweight dependency (reportlab,
weasyprint + cairo, ...) — the PDF is an evidentiary copy of the exact terms
the creator accepted, not a designed document. Characters outside WinAnsi are
replaced with `?` (the contract body is English, Q3/Q4).
"""
from __future__ import annotations

import textwrap
from datetime import datetime

PAGE_WIDTH = 595  # A4 portrait, points
PAGE_HEIGHT = 842
MARGIN_LEFT = 50
MARGIN_TOP = 60
MARGIN_BOTTOM = 60
FONT_SIZE = 10
TITLE_FONT_SIZE = 14
LINE_HEIGHT = 14
WRAP_WIDTH = 95  # characters per line at 10pt Helvetica on a 495pt text width


def _escape(text: str) -> str:
    out = text.encode("cp1252", errors="replace").decode("cp1252")
    return out.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(lines: list[str]) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        if not line.strip():
            wrapped.append("")
            continue
        wrapped.extend(textwrap.wrap(line, width=WRAP_WIDTH, break_long_words=True) or [""])
    return wrapped


def _page_content(title: str | None, lines: list[str], page_no: int, total_pages: int) -> bytes:
    ops = ["BT"]
    y = PAGE_HEIGHT - MARGIN_TOP
    if title:
        ops.append(f"/F1 {TITLE_FONT_SIZE} Tf 1 0 0 1 {MARGIN_LEFT} {y} Tm ({_escape(title)}) Tj")
        y -= LINE_HEIGHT * 2
    ops.append(f"/F1 {FONT_SIZE} Tf 1 0 0 1 {MARGIN_LEFT} {y} Tm {LINE_HEIGHT} TL")
    for line in lines:
        ops.append(f"({_escape(line)}) Tj T*")
    ops.append("ET")
    footer = f"Page {page_no} of {total_pages}"
    ops.append(f"BT /F1 8 Tf 1 0 0 1 {MARGIN_LEFT} {MARGIN_BOTTOM - 25} Tm ({_escape(footer)}) Tj ET")
    return "\n".join(ops).encode("latin-1")


def render_text_pdf(title: str, body_lines: list[str], *, metadata: dict[str, str] | None = None) -> bytes:
    """Build a valid single-font PDF 1.4 document from plain-text lines."""
    wrapped = _wrap(body_lines)
    usable_height = PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    first_page_lines = int((usable_height - LINE_HEIGHT * 2) // LINE_HEIGHT)
    other_page_lines = int(usable_height // LINE_HEIGHT)

    pages: list[list[str]] = []
    idx = 0
    pages.append(wrapped[idx : idx + first_page_lines])
    idx += first_page_lines
    while idx < len(wrapped):
        pages.append(wrapped[idx : idx + other_page_lines])
        idx += other_page_lines

    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    # 1: catalog, 2: pages, 3: font — page objects follow.
    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages_obj_index = add(b"")  # placeholder, filled after page ids are known
    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")

    page_ids: list[int] = []
    total = len(pages)
    for n, page_lines in enumerate(pages, start=1):
        content = _page_content(title if n == 1 else None, page_lines, n, total)
        content_id = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        page_id = add(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("latin-1")
        )
        page_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_obj_index - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")

    meta = metadata or {}
    info_parts = [f"/Producer ({_escape('AI YouTube Content Ecosystem')})", f"/Title ({_escape(title)})"]
    for key in ("Author", "Subject", "Keywords"):
        if key in meta:
            info_parts.append(f"/{key} ({_escape(meta[key])})")
    info_parts.append(f"/CreationDate (D:{datetime.utcnow():%Y%m%d%H%M%S}Z)")
    info_id = add(("<< " + " ".join(info_parts) + " >>").encode("latin-1"))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1") + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info {info_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    return bytes(out)
