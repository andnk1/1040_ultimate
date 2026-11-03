"""clientsum.py - read the client "Summary" (PDF or Word) into a list of items.

Every bullet / numbered point / separate line (paragraph) becomes one item. Lines that are only a number
(footnote / source markers such as "1", "2 3") are dropped. A "Title: text" item is split into a bold title + text.
In a PDF, wrapped lines are joined back: a new item starts at a bullet / number, or at a new text block when the
document has no bullets.
"""
from __future__ import annotations

import re
from pathlib import Path

EXTS = {".pdf", ".docx", ".txt"}
BULLET = re.compile(r"^\s*(?:[•●○◦▪▫■□\-–—*·►▶➢✓✔]|\(?\d{1,2}[.)]|\(?[a-zA-Z][.)])\s+")
ONLY_NUM = re.compile(r"^[\d\s,;.\[\]()]*$")


def _clean(s: str) -> str:
    s = s.replace(" ", " ").replace("​", "")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=[.!?)])\s+\d{1,2}(?:\s*,?\s*\d{1,2})*$", "", s)   # trailing source markers "... savings. 1 3"
    return s


def _docx_lines(path) -> list[tuple[str, bool]]:
    import docx
    d = docx.Document(str(path))
    out = []
    for p in d.paragraphs:
        ppr = p._p.pPr
        listed = ppr is not None and ppr.numPr is not None
        style = p.style.name or ""
        if style.startswith(("Heading", "Title", "Subtitle")) and not listed:
            continue                         # a heading isn't an item
        out.append((p.text, listed or "List" in style))
    for t in d.tables:                       # a table: one item per row
        for row in t.rows:
            cells = []
            for c in row.cells:
                v = c.text.strip()
                if v and v not in cells:
                    cells.append(v)
            if cells:
                out.append((" — ".join(cells), True))
    return out


def _pdf_blocks(path) -> list[list[str]]:
    from .pdfutil import open_pdf
    doc, _ = open_pdf(path)
    blocks = []
    with doc:
        for page in doc:
            for b in page.get_text("blocks", sort=True):
                if b[6] == 0 and b[4].strip():
                    blocks.append([l for l in b[4].splitlines() if l.strip()])
    return blocks


def _split_title(s: str) -> tuple[str, str]:
    m = re.match(r"^([^:]{3,90}):\s+(.+)$", s)
    if m and not re.search(r"https?$", m.group(1)):
        return m.group(1).strip(), m.group(2).strip()
    return "", s


def _items_from_texts(texts: list[str]) -> list[dict]:
    out = []
    for t in texts:
        t = BULLET.sub("", _clean(t), count=1).strip()
        if not t or ONLY_NUM.match(t):
            continue
        title, text = _split_title(t)
        out.append(dict(title=title, text=text))
    return out


def read_client_summary(path) -> dict:
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in EXTS:
        raise ValueError(f"{ext or 'no extension'} files aren't read - save it as PDF or Word (.docx)")
    texts: list[str] = []
    if ext == ".docx":
        for t, _listed in _docx_lines(p):
            texts.append(t)                  # every paragraph is its own item
    elif ext == ".txt":
        raw = p.read_text(encoding="utf-8", errors="replace")
        texts = _join_wrapped([[l for l in raw.splitlines()]], blank_splits=True)
    else:
        texts = _join_wrapped(_pdf_blocks(p))
    return dict(file=p.name, items=_items_from_texts(texts))


def _join_wrapped(blocks: list[list[str]], blank_splits: bool = False) -> list[str]:
    """PDF / text lines -> items. Bullets present: each bullet starts an item, the lines after it continue it.
    No bullets: each text block (paragraph) is an item; in a .txt file a blank line ends an item."""
    has_bullets = any(BULLET.match(l) for b in blocks for l in b)
    out: list[str] = []
    res = _join(blocks, has_bullets, blank_splits)
    for text in res:
        # with bullets: a short line on its own without a bullet is a heading ("Client summary") - not an item
        if has_bullets and not BULLET.match(text) and len(text.split()) <= 6 and not re.search(r"[.!?:]$", text.strip()):
            continue
        out.append(text)
    return out


def _join(blocks, has_bullets, blank_splits) -> list[str]:
    out: list[str] = []
    for b in blocks:
        cur = None
        for l in b:
            if blank_splits and not l.strip():
                if cur is not None:
                    out.append(cur)
                cur = None
                continue
            if cur is None or (has_bullets and BULLET.match(l)):
                if cur is not None:
                    out.append(cur)
                cur = l.strip()
            else:
                cur += " " + l.strip()
        if cur is not None:
            out.append(cur)
    return out
