"""safe_pdf.py - read a PDF's first pages in a separate process, with a time limit.

Some PDFs make the PDF reader (PyMuPDF) hang inside its C code. That freezes the whole program - every page in the
browser stops loading. The quick checks ("is this a 1040?", "is this the UT input screens print?") run here instead:
if the file hangs, the separate process is stopped after the time limit and the preparer gets a message naming
the file and the page, while the program keeps running.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parent.parent)

_PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from core.pdfutil import open_pdf, page_text
path, n_pages, prog = sys.argv[2], int(sys.argv[3]), sys.argv[4]
def mark(s):
    with open(prog, "w") as f:
        f.write(s)
mark("open")
try:
    doc, pw = open_pdf(path)
except Exception as e:
    print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})); sys.exit(0)
n = len(doc)
texts = []
for i in range(n if n_pages <= 0 else min(n, n_pages)):
    mark(f"page {i + 1}")
    t = page_text(doc, i)
    if n_pages > 0:
        texts.append(t)
print(json.dumps({"ok": True, "pages": n, "text": texts, "password": bool(pw)}))
"""


def probe(path: str, pages: int = 15, timeout: float = 40) -> dict:
    """{ok, pages, text: [page texts], error, stuck} - stuck = 'page 7' / 'open' when the reader hung."""
    fd, prog = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        p = subprocess.Popen([sys.executable, "-c", _PROBE, APP_DIR, str(path), str(pages), prog],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            out, err = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            where = Path(prog).read_text() if Path(prog).is_file() else "?"
            return dict(ok=False, stuck=where or "open",
                        error=f"the PDF reader got stuck on {Path(path).name} ({where or 'opening it'}) after {int(timeout)} seconds")
        try:
            j = json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return dict(ok=False, error=f"couldn't read {Path(path).name}: {(err or '').strip()[-300:]}")
        return j
    finally:
        try:
            os.remove(prog)
        except OSError:
            pass


def stuck_message(path: str, res: dict) -> str:
    return (f"\"{Path(path).name}\": {res.get('error')}. Open it in Acrobat and save a copy (File → Save As, or print it to "
            "Microsoft Print to PDF), then pick the copy.")
