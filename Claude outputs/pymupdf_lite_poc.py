"""pymupdf.py (lite) - a stand-in for the parts of PyMuPDF that 1040 Ultimate's readers use, built on pdfplumber
(+ pypdfium2 for passwords / page copying), so the same reader code can run in Pyodide (browser).
Proof of concept only: covers open / needs_pass / authenticate / metadata / pages / page.rect /
get_text("" | "words" | "blocks" | "dict") / get_drawings (filled rects) / insert_pdf + save.
"""
from __future__ import annotations

import io
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium


class Rect:
    def __init__(self, *a):
        if len(a) == 1:
            a = tuple(a[0])
        self.x0, self.y0, self.x1, self.y1 = (float(v) for v in a) if a else (0, 0, 0, 0)

    width = property(lambda s: s.x1 - s.x0)
    height = property(lambda s: s.y1 - s.y0)

    def contains(self, p):
        x, y = p[:2]
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def __iter__(self):
        return iter((self.x0, self.y0, self.x1, self.y1))


def _lines(words, tol=3.0):
    """Group words into lines (same baseline) -> [[word dict, ...]] in reading order."""
    rows = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(rows[-1][0]["top"] - w["top"]) <= tol:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w["x0"]) for r in rows]


class Page:
    def __init__(self, pp):
        self._p = pp
        self.rect = Rect(0, 0, float(pp.width), float(pp.height))

    def _words(self, clip=None):
        p = self._p if clip is None else self._p.within_bbox(tuple(clip), relative=False, strict=False)
        return p.extract_words(keep_blank_chars=False, use_text_flow=True, extra_attrs=["fontname", "size"])

    def get_text(self, kind="text", sort=False, clip=None):
        if kind in ("text", ""):
            return (self._p.extract_text(layout=False) or "") + ("\n" if self._p.chars else "")
        lines = _lines(self._words(clip))
        if kind == "words":           # (x0, y0, x1, y1, text, block, line, word) like PyMuPDF
            return [(w["x0"], w["top"], w["x1"], w["bottom"], w["text"], 0, li, wi)
                    for li, ln in enumerate(lines) for wi, w in enumerate(ln)]
        if kind == "blocks":          # one block per line here (MuPDF groups paragraphs - a known difference)
            return [(ln[0]["x0"], min(w["top"] for w in ln), ln[-1]["x1"], max(w["bottom"] for w in ln),
                     " ".join(w["text"] for w in ln) + "\n", i, 0) for i, ln in enumerate(lines)]
        if kind == "dict":
            blocks = []
            for i, ln in enumerate(lines):
                bbox = (ln[0]["x0"], min(w["top"] for w in ln), ln[-1]["x1"], max(w["bottom"] for w in ln))
                spans = [dict(text=w["text"] + " ", bbox=(w["x0"], w["top"], w["x1"], w["bottom"]),
                              font=w.get("fontname", ""), size=w.get("size", 0)) for w in ln]
                blocks.append(dict(type=0, bbox=bbox, lines=[dict(bbox=bbox, spans=spans)]))
            return dict(width=self.rect.width, height=self.rect.height, blocks=blocks)
        raise ValueError(f"get_text({kind!r}) not covered by the lite shim")

    def get_drawings(self):
        out = []
        for r in self._p.rects:
            c = r.get("non_stroking_color")
            fill = tuple(c) if isinstance(c, (list, tuple)) and len(c) == 3 else None
            out.append(dict(fill=fill, rect=Rect(r["x0"], r["top"], r["x1"], r["bottom"])))
        return out


class Document:
    def __init__(self, filename=None, stream=None, filetype=None):
        if filename is None and stream is None:          # pymupdf.open() -> new empty document
            self._new = pdfium.PdfDocument.new()
            self._pl = None
            return
        self._new = None
        self._data = Path(filename).read_bytes() if filename is not None else bytes(stream)
        self.name = str(filename or "")
        self._pw = None
        self._pl = None
        try:
            self._pl = pdfplumber.open(io.BytesIO(self._data))
            len(self._pl.pages)
            self.needs_pass = False
        except Exception:                                 # noqa: BLE001 - encrypted with a user password
            self.needs_pass = True

    def authenticate(self, pw):
        try:
            self._pl = pdfplumber.open(io.BytesIO(self._data), password=pw)
            len(self._pl.pages)
            self._pw, self.needs_pass = pw, False
            return 1
        except Exception:                                 # noqa: BLE001
            return 0

    @property
    def metadata(self):
        m = (self._pl.metadata if self._pl else {}) or {}
        return {"producer": m.get("Producer", ""), "creator": m.get("Creator", ""), "title": m.get("Title", "")}

    def __len__(self):
        return len(self._new) if self._new is not None else len(self._pl.pages)

    page_count = property(__len__)

    def __getitem__(self, i):
        return Page(self._pl.pages[i])

    def __iter__(self):
        return (self[i] for i in range(len(self)))

    def insert_pdf(self, src, from_page=0, to_page=None):
        s = pdfium.PdfDocument(src._data, password=src._pw)
        to = from_page if to_page is None else to_page
        self._new.import_pages(s, list(range(from_page, to + 1)))

    def save(self, path):
        with open(path, "wb") as f:
            self._new.save(f)

    def close(self):
        if self._pl:
            self._pl.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def open(filename=None, stream=None, filetype=None):     # noqa: A001 - same name as PyMuPDF
    return Document(filename, stream=stream, filetype=filetype)
