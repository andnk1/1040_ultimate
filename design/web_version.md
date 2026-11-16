# 1040 Ultimate — browser version (Pyodide) — plan and brief

Written in Cowork, 2026-11-16, after testing. Read with BUILD_NOTES.md and APPS_ARCHITECTURE.md.
This is my intent, not a script: if something doesn't fit the code or there's a better way, say so before building.
**Work phase by phase. At the end of each phase stop, report, and wait for my "go".**

## Goal
A second way to run 1040 Ultimate: inside the browser (Chrome / Edge), Python running in the tab with Pyodide,
later hosted on the firm's Cloudflare behind its two-factor login. The desktop app (run.bat, Flask) stays and stays my
main tool. Client documents never leave the computer: everything is read and calculated in the tab.

## The one rule: one engine, two front doors
```
core\      the engine — readers, rules, income summary, K-1, verify   (ONE copy, used by both)
app.py     front door 1 — desktop (Flask, run.bat, port 5067)          (as today)
web\       front door 2 — browser (Pyodide, run_web.bat, port 5070)   (new)
```
- No copy of the app, no second version of any reader or rule. A fix in `core\` reaches both.
- Nothing Windows-only inside `core\` (file windows, subprocess, ctypes, opening files in their program, run.bat logic).
- The desktop app must behave exactly as before after every phase. `tests\run_tests.bat` passes after every phase.

## What was tested already (2026-11-11 … 16)
- Pyodide 314.0.7 runs the engine. Installed and working in the browser: pdfplumber 0.11.10 (pypdfium2 5.15.2 now has an
  official browser wheel on PyPI), pdfminer.six, openpyxl, python-docx, Pillow, lxml, cryptography, Jinja2.
- **PyMuPDF has no browser version** → replaced by **MuPDF.js** (npm `mupdf`, same MuPDF engine, AGPL like PyMuPDF).
- 17 of 29 core modules import unchanged; the others fail only on `import pymupdf`.
- `tools\mupdfjs_test\` compares PyMuPDF and MuPDF.js text + word positions page by page. On my 19 K-1s: text identical
  on all; the last word-position differences (turned pages, a zero-width character) are fixed in `2_read_mupdfjs.mjs`.
  **`2_read_mupdfjs.mjs` is the reference for how MuPDF.js output must be turned into PyMuPDF's** (settings
  `preserve-whitespace,preserve-ligatures,clip,use-cid-for-unknown-unicode`; positions on the un-turned page; PyMuPDF's
  word rules incl. its quirks). Still to run it on W-2s, 1099 composites, a UT input screens print and a Karbon summary.
- Speed: pdfplumber in the browser ≈ 2.5× slower than on the desktop (110 pages 4.7 s → 11.6 s); MuPDF.js 110 pages ≈ 0.5 s.
- Download for a first-time user ≈ 35–40 MB (Pyodide + libraries + MuPDF.js), then cached by the browser.
- A rough proof-of-concept stand-in (`pymupdf_lite_poc.py`, on pdfplumber) worked on simple test PDFs but changed spacing
  — not to be used; MuPDF.js is the way.

## PyMuPDF features the engine uses (what the stand-in must cover)
Direct `import pymupdf` only in `core\pdfutil.py`, `core\utscreens.py` (and `redact_pdf.py` — masking, excluded).
Used through page/doc objects across parsers, inventory, verify, karbon, clientsum, pl, people, py_return, carryovers:
`open` (path / bytes), `needs_pass`, `authenticate`, `metadata["producer"]`, `len`, page iteration, `page.rect.width`,
`get_text()`, `get_text("words")`, `get_text("blocks", sort=True)`, `get_text("dict")` (+ `clip=`), `get_drawings()`
(Karbon pink bubbles: fill colour + rect), `insert_pdf` + `save` (splitting a brokerage package by account).

## Phase 1 — prepare the engine (desktop only, nothing visible changes)
1. One PDF door: all PyMuPDF use goes through one module (e.g. `core\pdfengine.py`). On the desktop it is the real
   PyMuPDF; in the browser it will be the MuPDF.js stand-in. Same function names for the rest of `core\`.
2. Move anything desktop-only out of `core\` (list what you find: `safe_pdf.py` subprocess time limit, file walking in
   `wip.py` / `inventory.py` if it can't work on a virtual drive, etc.). In the browser, picked files are copied onto
   Pyodide's in-memory drive, so ordinary path-based reading can stay.
3. Drop `ocrmypdf` and `pytesseract` from requirements.txt (never imported).
4. Tests pass; the regression total is unchanged. Report, stop.

## Phase 2 — "see how it looks" (local only, read-only)
`web\` + `run_web.bat` (tiny local server, port 5070, opens Chrome). Python runs in a Web Worker. Pick a client
folder → document inventory + income summary, same look as the desktop (design\DESIGN_RULES.md, cfoa-tools.css).
Nothing saved, no Verify, no K-1 pages yet. Pyodide, wheels and MuPDF.js kept inside `web\vendor\` (works offline,
no outside download site). A "Loading…" screen for the first start. Show me before going on.

## Phase 3 — the full web front door
The remaining pages (form tabs, Schedule C / E, K-1 Verification + K-1 Prep, Verify return, UT summary, exports),
reusing the templates (Jinja2 runs in Pyodide) and static JS where possible. Replace: Windows file windows → browser
folder / file pickers; saving the work-in-progress file → into the picked client folder (File System Access API);
safe_pdf time limit → a Worker that can be stopped; "open in its own program" → open in a new tab.
Plan the page-to-page flow without a server and tell me the plan before building it.

## Phase 4 — firm version (later, only when I say)
Cloudflare Pages behind the firm's two-factor login, private preview address per change. Claude API (when built) goes
through a small Cloudflare Worker that holds the key — never in the page.

## Not in the browser version
Masking / redact_pdf (separate app, as decided). UT Data Entry stays a desktop app; the browser version still exports
the same CSV.

## Checks for every phase
- `tests\run_tests.bat` passes on the desktop.
- From phase 2: the same sample folder gives the same inventory and income summary in both versions (add a way to run the
  test answer keys in the browser too).
- Decisions go in BUILD_NOTES.md (short); this file is the spec for the web version.
