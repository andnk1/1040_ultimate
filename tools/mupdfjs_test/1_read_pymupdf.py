"""Step 1 - read every PDF in a folder with PyMuPDF (what 1040 Ultimate uses today) and save what it sees.
Run from C:\\dev\\1040_ultimate\\tools\\mupdfjs_test:   python 1_read_pymupdf.py "<folder with sample PDFs>"
Writes pymupdf.json next to this file. Uses the app's own password rules (core\\pdfutil.py).
"""
import json, sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]                 # C:\dev\1040_ultimate
sys.path.insert(0, str(APP))
import pymupdf
from core.pdfutil import open_pdf

folder = Path(sys.argv[1])
out = {"engine": f"PyMuPDF {pymupdf.__version__} (MuPDF {pymupdf.mupdf_version})", "files": {}}
for p in sorted(folder.rglob("*.pdf"), key=lambda p: str(p).lower()):
    rel = str(p.relative_to(folder))
    try:
        doc, pw = open_pdf(p)
    except Exception as e:                                # noqa: BLE001
        out["files"][rel] = {"error": f"{type(e).__name__}: {e}"}
        continue
    with doc:
        pages = [{"text": pg.get_text(),
                  "words": [[round(w[0], 1), round(w[1], 1), round(w[2], 1), round(w[3], 1), w[4]] for w in pg.get_text("words")]}
                 for pg in doc]
    out["files"][rel] = {"password": pw, "pages": pages}
    print(f"read  {rel}  ({len(pages)} pages)")
Path(__file__).with_name("pymupdf.json").write_text(json.dumps(out), encoding="utf-8")
print(f"\nDone - {len(out['files'])} PDFs -> pymupdf.json   [{out['engine']}]")
