"""Documents -> what is sent to the Claude API (spec: design/ai_requests.md, "What is sent").

Originals are sent, not masked (Lady, 2026-11-12: the firm's API agreement allows client data).
- PDF: a PDF document block (base64) - the original; a long document sends only its AI pages (the inventory's page list),
  and a password-protected PDF is opened with the usual passwords and sent without the password.
- Excel (.xlsx / .xlsm): every sheet as text, the sheet name as a heading, one line per row (cells separated by " | "),
  calculated values (not formulas). Word (.docx): paragraphs and tables in order. Text files as they are.
- Each document is preceded by a label line: "Document 3 - <file name> (Excel)".
"""
from __future__ import annotations

import base64
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

PDF = {".pdf"}
XLSX = {".xlsx", ".xlsm"}
DOCX = {".docx"}
TEXT = {".txt", ".csv", ".md", ".eml"}
KIND = {**{e: "PDF" for e in PDF}, **{e: "Excel" for e in XLSX}, **{e: "Word" for e in DOCX}, **{e: "text" for e in TEXT}}


def kind_of(path: str) -> str | None:
    return KIND.get(Path(path).suffix.lower())


# ---------------------------------------------------------------- Excel / Word / text -> text
def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return "%.15g" % v                       # 4939.23 stays 4939.23; float noise (0.30000000000000004) goes
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    return str(v).replace("\r", " ").replace("\n", " ").strip()


def xlsx_text(src) -> str:
    """Every sheet: '## Sheet: <name>' then one line per non-empty row. src = a path or a file-like object."""
    from openpyxl import load_workbook
    wb = load_workbook(src if hasattr(src, "read") else str(src), data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        out.append(f"## Sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = [_cell(v) for v in row]
            while cells and cells[-1] == "":
                cells.pop()
            if cells:
                out.append(" | ".join(cells))
        out.append("")
    wb.close()
    return "\n".join(out).strip()


def docx_text(path) -> str:
    """Paragraphs and tables in the order they appear (table rows as 'a | b | c')."""
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    d = docx.Document(str(path))
    out = []
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            t = Paragraph(el, d).text.strip()
            if t:
                out.append(t)
        elif tag == "tbl":
            for row in Table(el, d).rows:
                cells, last = [], None
                for c in row.cells:                  # merged cells repeat - keep one
                    if c._tc is last:
                        continue
                    last = c._tc
                    cells.append(c.text.replace("\n", " ").strip())
                if any(cells):
                    out.append(" | ".join(cells))
            out.append("")
    return "\n".join(out).strip()


def text_file(path) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def as_text(path) -> str:
    ext = Path(path).suffix.lower()
    if ext in XLSX:
        return xlsx_text(path)
    if ext in DOCX:
        return docx_text(path)
    return text_file(path)


# ---------------------------------------------------------------- what each document sends
def plan(path: str, pages: list | None = None) -> dict:
    """What Send will use for one document: {sent, problem}. sent = 'original' / 'pages 1, 2, 5 of 40'.
    problem = why it can't be sent ('' when it can)."""
    k = kind_of(path)
    if not k:
        return dict(sent="", problem=f"{Path(path).suffix or 'This'} files can't be sent - save it as PDF, .xlsx or .docx")
    if not Path(path).is_file():
        return dict(sent="", problem="File not found")
    if k == "PDF" and pages:
        return dict(sent="pages " + ", ".join(map(str, pages)), problem="")
    return dict(sent="original", problem="")


def label(num, name: str, kind: str) -> str:
    return f"Document {num} - {name} ({kind})"


def pdf_bytes(path: str, pages: list | None = None) -> bytes:
    """The PDF to send: the file as it is, or (a page list / a password) a copy in memory with only those pages, no password."""
    from core.pdfutil import open_pdf
    import pymupdf
    with pymupdf.open(path) as probe:
        plain = not probe.needs_pass
    if plain and not pages:
        return Path(path).read_bytes()
    doc, _ = open_pdf(path)
    try:
        if pages:
            keep = [p - 1 for p in pages if 1 <= p <= len(doc)]
            if keep:
                doc.select(keep)
        return doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()


def blocks_for(doc: dict) -> list[dict]:
    """Content blocks for one document. doc = {num, name, path, pages}."""
    k = kind_of(doc["path"])
    head = {"type": "text", "text": label(doc["num"], doc["name"], k)}
    if k == "PDF":
        data = base64.standard_b64encode(pdf_bytes(doc["path"], doc.get("pages"))).decode("ascii")
        return [head, {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}]
    text = as_text(doc["path"])
    return [head, {"type": "text", "text": text or "(no text found in this document)"}]


# ---------------------------------------------------------------- Schedule E template (built in memory, never saved)
def schedule_e_template_text(rows: list | None) -> str:
    """The standard Schedule E sheet - written by core.sche_template.write_template (the Export Template code), in memory,
    then read back as text like any Excel document."""
    from core.sche_template import write_template
    buf = BytesIO()
    write_template(buf, rows or None)
    buf.seek(0)
    return xlsx_text(buf)
