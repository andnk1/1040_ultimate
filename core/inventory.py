"""inventory.py - scan the document folder, classify every file, decide where it goes.

Route (step 1 - before any amounts are read):
  program  - a tax form the program will read (parsers come in later steps)
  ai       - a tax document the program can't read yet -> AI review
  context  - letters, notes, e-mails, organizers -> AI reads for facts
  excluded - deliberately left out (e.g. 1099-DA when a Koinly report is present)
  skipped  - draft / estimate / duplicate / the prior-year return itself / unsupported file
AI pages: for long documents only the pages the AI needs are listed (never 300-page detail).
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path

from .pdfutil import open_pdf, page_text, has_text

PDF_EXT = {".pdf"}
SHEET_EXT = {".xlsx", ".xls", ".xlsm", ".csv"}
NOTE_EXT = {".txt", ".eml", ".msg", ".docx", ".doc", ".rtf", ".htm", ".html"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".bmp", ".gif"}

LONG_DOC = 10           # documents longer than this only send their summary pages to the AI
CLASSIFY_PAGES = 6      # pages read to classify a document

# issuer: text or file-name keyword -> display name
ISSUERS = [
    ("ROBINHOOD", "Robinhood"), ("SCHWAB", "Charles Schwab"), ("FIDELITY", "Fidelity"),
    ("NATIONAL FINANCIAL SERVICES", "Fidelity (National Financial)"), ("M1 FINANCE", "M1"), ("M1 ", "M1"),
    ("INTERACTIVE BROKERS", "Interactive Brokers"), ("COINBASE", "Coinbase"), ("KRAKEN", "Kraken"),
    ("GEMINI", "Gemini"), ("VANGUARD", "Vanguard"), ("E*TRADE", "E*TRADE"), ("ETRADE", "E*TRADE"),
    ("MORGAN STANLEY", "Morgan Stanley"), ("MERRILL", "Merrill"), ("WEBULL", "Webull"), ("PUBLIC.COM", "Public"),
    ("APEX CLEARING", "Apex Clearing"), ("TD AMERITRADE", "TD Ameritrade"), ("WEALTHFRONT", "Wealthfront"),
    ("BETTERMENT", "Betterment"), ("SOFI", "SoFi"), ("KOINLY", "Koinly"), ("GUSTO", "Gusto (payroll)"),
    ("ADP", "ADP (payroll)"), ("PAYCHEX", "Paychex (payroll)"), ("DEEL", "Deel (payroll)"), ("RIPPLING", "Rippling (payroll)"),
]

FORM_1099 = ["1099-DIV", "1099-INT", "1099-B", "1099-MISC", "1099-OID", "1099-R", "1099-NEC", "1099-K", "1099-G", "1099-DA"]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).upper()


def _year(text: str, py: int | None) -> int | None:
    """Tax year - only when the document says it: "Tax Year 2025" or "calendar year 2025" (any capitalisation).
    Other years on the page (dates, form revisions, account-opening dates ...) are not used."""
    yrs = Counter(int(y) for y in re.findall(r"(?:\btax\s+year|\bcalendar\s+year)\s*:?\s*(20\d\d)\b", text, re.I))
    if not yrs:
        return None
    if py and (py + 1) in yrs and yrs[py + 1] == max(yrs.values()):
        return py + 1
    return yrs.most_common(1)[0][0]


def return_year(text: str) -> int | None:
    """Tax year of a return: 'Form 1040 (2024)', '2024 U.S. Individual Income Tax Return', 'Two Year Comparison 2023 & 2024'."""
    t = re.sub(r"\s+", " ", text)
    pats = [r"Form 1040 \((20\d\d)\)", r"\b(20\d\d)\s*U\.S\. Individual Income Tax Return",
            r"Form 1040\s*(20\d\d)\s*U\.S\.", r"20\d\d & (20\d\d) Two Year", r"Two Year Comparison Report[^&]*?20\d\d & (20\d\d)",
            r"Return Carryover Summary (20\d\d)", r"Taxable Year Ended December 31, (20\d\d)", r"1040 (20\d\d) "]
    for pat in pats:
        m = re.findall(pat, t)
        if m:
            return Counter(int(x) for x in m).most_common(1)[0][0]
    return None


def _issuer(text: str, name: str) -> str | None:
    up = _norm(text[:1500])     # header area only - holdings listed further down name other companies
    fn = " " + _norm(name.replace("_", " ").replace("-", " ")) + " "
    for key, disp in ISSUERS:
        if key in fn or (" " + key) in (" " + fn):
            return disp
    for key, disp in ISSUERS:
        if key.strip() in ("M1",):
            continue
        if key in up:
            return disp
    # not a known issuer: the form's own "Payer's name: ..." line
    m = re.search(r"PAYER[’'`]?S\s+NAME\s*:\s*([^\n]{3,60})", text, re.I)
    if m:
        v = m.group(1).strip(" .,")
        if v and not re.match(r"(street|address|city)", v, re.I):
            return v
    return None


def classify_text(text: str, name: str, n_pages: int, producer: str) -> dict:
    """Document type from its text (first pages) and file name."""
    up = _norm(text)
    fn = _norm(name)
    forms = [f for f in FORM_1099 if f in up]
    d = dict(doc_type="Other document", family="other", forms=forms)

    def is_(t, fam):
        d.update(doc_type=t, family=fam)
        return d

    # Karbon client organizer ("Client Request Summary")
    if "CLIENT REQUEST SUMMARY" in up and "CLIENT ORGANIZER" in up:
        return is_("Karbon organizer", "karbon")
    # tax returns
    if ("INDIVIDUAL INCOME TAX RETURN" in up or "TWO YEAR COMPARISON" in up or "ULTRATAX" in _norm(producer)) and \
            ("1040" in up) and n_pages >= 5:
        return is_("Tax return (1040)", "return")
    if re.search(r"U\.S\. RETURN OF PARTNERSHIP INCOME|FORM 1065 .*RETURN|U\.S\. INCOME TAX RETURN FOR AN S CORPORATION|U\.S\. CORPORATION INCOME TAX RETURN", up) and n_pages >= 5 \
            and not re.search(r"FORM 1099-[A-Z]+\s*\(REV", up):   # IRS 1099 forms mention business returns in their notes
        return is_("Business tax return", "bizreturn")
    # Koinly (name or text) - before 1099-DA, because Koinly reports mention 1099-DA
    if "KOINLY" in fn or ("KOINLY" in up and re.search(r"8949|SCHEDULE D|SCHEDULE 1|TAX REPORT|CAPITAL GAINS REPORT", up)):
        if "8949" in up and "SALES AND OTHER DISPOSITIONS" in up:
            return is_("Koinly - Form 8949", "koinly")
        if "SCHEDULE D" in up and "CAPITAL GAINS AND LOSSES" in up:
            return is_("Koinly - Schedule D", "koinly")
        if "SCHEDULE 1" in up and "ADDITIONAL INCOME" in up:
            return is_("Koinly - Schedule 1", "koinly")
        return is_("Koinly - report", "koinly")
    if name.lower().endswith(".csv"):
        return is_("CSV file", "sheet")
    # K-1s
    # a broker 1099 mentions "Schedule K-1 (Form 1065)" in its instructions - only a real K-1 form counts
    k1_form = re.search(r"SHARE OF (CURRENT YEAR )?INCOME,? DEDUCTIONS", up)
    irs_1099 = re.search(r"FORM 1099-[A-Z]+\s*\(REV", up)
    if ("SCHEDULE K-1" in up or "SCHEDULE K–1" in up) and (k1_form or (len(forms) < 2 and not irs_1099)):
        if "1120-S" in up or "SHAREHOLDER'S SHARE" in up or "SHAREHOLDER’S SHARE" in up:
            return is_("K-1 (1120-S)", "k1s")
        if "BENEFICIARY'S SHARE" in up or "BENEFICIARY’S SHARE" in up or "FORM 1041" in up:
            return is_("K-1 (1041)", "k1t")
        if "1065" in up or "PARTNER'S SHARE" in up or "PARTNER’S SHARE" in up:
            return is_("K-1 (1065)", "k1p")
        return is_("K-1 (type unknown)", "k1x")
    # 1099-DA standalone (crypto exchanges)
    if "1099-DA" in up and "DIGITAL ASSET" in up and len([f for f in forms if f != "1099-DA"]) < 2:
        return is_("1099-DA", "1099da")
    # one 1099 form type printed as the title (IRS form or a bank's substitute form) - the other forms are only
    # named in the instructions; brokerage composites print DIV / INT / B / MISC sections together
    if "COMPOSITE" not in up and "CONSOLIDATED" not in up:
        titled = Counter(m.group(1) for m in re.finditer(r"(?:FORM|SUBSTITUTE FOR FORM|20\d\d)\s+(1099-[A-Z]+)\b", up))
        if titled:
            top, n = titled.most_common(1)[0]
            others = {f for f in titled if f != top and f in ("1099-DIV", "1099-INT", "1099-B", "1099-MISC")}
            if n >= 3 and all(n > c for f, c in titled.items() if f != top) and not others:
                fam = {"1099-R": "1099r", "1099-INT": "1099int", "1099-NEC": "1099nec", "1099-MISC": "1099misc",
                       "1099-DIV": "1099div", "1099-B": "1099b", "1099-G": "1099g", "1099-K": "1099k",
                       "1099-OID": "1099oid", "1099-DA": "1099da"}.get(top)
                if fam:
                    return is_(top, fam)
    # 1099-SA (HSA / MSA distributions) - before the composite check (its instructions name other forms)
    if re.search(r"1099-SA\b", up) and re.search(r"\bHSA\b|\bMSA\b|HEALTH SAVINGS", up) and "COMPOSITE" not in up:
        return is_("1099-SA", "1099sa")
    # brokerage composite
    if "COMPOSITE" in up or "CONSOLIDATED" in up or len(forms) >= 2:
        if len(forms) >= 1:
            return is_("1099 Composite", "composite")
    if "WAGE AND TAX STATEMENT" in up or re.search(r"\bW-2\b", up) and "WAGES, TIPS" in up:
        return is_("W-2", "w2")
    if "SSA-1099" in up or "SOCIAL SECURITY BENEFIT STATEMENT" in up:
        return is_("SSA-1099", "ssa")
    if "1099-R" in up and "PENSIONS" in up:
        return is_("1099-R", "1099r")
    for f, fam in (("1099-NEC", "1099nec"), ("1099-MISC", "1099misc"), ("1099-K", "1099k"), ("1099-G", "1099g"),
                   ("1099-INT", "1099int"), ("1099-DIV", "1099div"), ("1099-B", "1099b"), ("1099-OID", "1099oid")):
        if f in up:
            return is_(f, fam)
    if "1098-T" in up or "TUITION STATEMENT" in up:
        return is_("1098-T", "1098t")
    if "1098-E" in up or "STUDENT LOAN INTEREST STATEMENT" in up:
        return is_("1098-E", "1098e")
    if "MORTGAGE INTEREST STATEMENT" in up or re.search(r"\b1098\b", up) and "MORTGAGE" in up:
        return is_("1098 (mortgage)", "1098")
    if "1095-A" in up or "HEALTH INSURANCE MARKETPLACE STATEMENT" in up:
        return is_("1095-A", "1095a")
    if "5498" in up and "IRA CONTRIBUTION" in up:
        return is_("5498 (IRA contributions)", "5498")
    if "1040-ES" in up and "ESTIMATED TAX" in up and n_pages <= 4:
        return is_("Estimated tax voucher / payments", "estimates")
    if re.search(r"\bSTATEMENT PERIOD\b|\bACCOUNT STATEMENT\b|\bBEGINNING BALANCE\b", up):
        return is_("Account statement", "statement")
    return d


# family -> route (step 1). Everything not listed -> "ai".
ROUTE = {
    "w2": "program", "composite": "program", "1099int": "program", "1099div": "program", "1099b": "program",
    "1099r": "program", "1099misc": "program", "1099nec": "program", "1099g": "program", "1099k": "program",
    "1099oid": "program", "1099sa": "program", "ssa": "program", "1098": "program", "1098e": "program", "1098t": "program",
    "k1p": "program", "koinly": "program", "1099da": "program", "sheet": "ai",
    "k1s": "ai", "k1t": "ai", "k1x": "ai", "1095a": "program", "5498": "ai", "statement": "ai",
    "estimates": "context", "other": "context", "karbon": "context", "bizreturn": "context", "note": "context",
}

ROUTE_LBL = {"program": "Program", "ai": "AI", "context": "Context (AI)", "excluded": "Excluded", "skipped": "Skipped"}


def _summary_pages(doc, n: int) -> list[int]:
    """For a long document: pages (1-based) that look like summary / form pages, max 4."""
    hits = []
    for i in range(min(n, 12)):
        t = _norm(page_text(doc, i))
        if any(k in t for k in ("SUMMARY", "TOTAL", "COPY B", "FORM 1099", "SCHEDULE K-1", "YEAR-END")):
            hits.append(i + 1)
        if len(hits) >= 4:
            break
    return hits or [1]


def summary_pages_for(path, n_pages: int) -> list[int] | None:
    """Pages the AI needs from a long document (None = all pages)."""
    if not n_pages or n_pages <= LONG_DOC:
        return None
    try:
        doc, _ = open_pdf(path)
    except Exception:  # noqa: BLE001
        return None
    with doc:
        return _summary_pages(doc, n_pages)


def _file_hash(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_folder(folder: str | Path) -> list[str]:
    folder = Path(folder)
    return [str(p) for p in sorted(folder.rglob("*"), key=lambda p: str(p).lower())
            if p.is_file() and not p.name.startswith(("~$", "."))]


def scan_folder(folder, py_year=None, py_return=None, extra_passwords=None) -> dict:
    return scan_files(list_folder(folder), py_year, py_return, extra_passwords)


def scan_files(paths: list, py_year: int | None = None, py_return: str | Path | None = None,
               extra_passwords=None) -> dict:
    """paths: the documents the user picked (files, in the order picked)."""
    py_ret = Path(py_return).resolve() if py_return else None
    files = [Path(p) for p in paths if Path(p).is_file()]
    docs, hashes = [], {}
    for p in files:
        print(f"     scan: {p.name}", flush=True)
        rel = p.name
        ext = p.suffix.lower()
        d = dict(file=rel, path=str(p), name=p.name, ext=ext, size=p.stat().st_size, pages=None, text=None, year=None,
                 issuer=None, doc_type="", family="other", forms=[], route="ai", note="", ai_pages="",
                 password=False)
        # duplicates (same bytes)
        try:
            h = _file_hash(p)
        except OSError:
            h = None
        if h and h in hashes:
            d.update(doc_type="Duplicate", route="skipped", note=f"Same file as {hashes[h]}")
            docs.append(d)
            continue
        if h:
            hashes[h] = rel
        if py_ret and p.resolve() == py_ret:
            d.update(doc_type="Prior-year return (selected)", family="pyreturn", route="skipped",
                     note="The prior-year return picked above — read separately.")
            docs.append(d)
            continue
        if re.search(r"\b(draft|estimate[sd]?)\b", p.stem, re.I) and "1040-es" not in p.stem.lower():
            d["draft"] = True
        if ext in PDF_EXT:
            try:
                doc, pw = open_pdf(p, extra_passwords)
            except ValueError:
                d.update(doc_type="Password-protected PDF", route="ai",
                         note="Couldn't open — password not found in the file name. Add it on the masking step.")
                docs.append(d)
                continue
            except Exception as e:  # noqa: BLE001
                d.update(doc_type="Unreadable PDF", route="ai", note=f"Couldn't open: {e}")
                docs.append(d)
                continue
            with doc:
                n = len(doc)
                d["pages"], d["password"] = n, bool(pw)
                texts = [page_text(doc, i) for i in range(min(n, CLASSIFY_PAGES))]
                text = "\n".join(texts)
                txt_pages = sum(has_text(t) for t in texts)
                d["text"] = "yes" if txt_pages == len(texts) else ("partial" if txt_pages else "no")
                producer = (doc.metadata or {}).get("producer") or ""
                if not txt_pages:
                    d.update(doc_type="Scanned / image PDF", family="scan", route="ai",
                             note="No text layer — the AI reads it as an image (slower, check the amounts).")
                else:
                    d.update(classify_text(text, p.name, n, producer))
                    d["year"] = return_year(text) if d["family"] in ("return", "bizreturn") else _year(text, py_year)
                    d["issuer"] = _issuer(text, p.name)
                    d["route"] = ROUTE.get(d["family"], "ai")
                    if d["family"] == "return":
                        if py_year and d["year"] == py_year:
                            d.update(route="skipped", note="Looks like a prior-year return — pick it in 'Prior-year return' instead.")
                        else:
                            d.update(route="context", note="A tax return in the documents folder — the AI reads it as context.")
                    if d["route"] in ("ai", "context") and n > LONG_DOC:
                        sp = _summary_pages(doc, n)
                        d["ai_pages"] = ", ".join(map(str, sp)) + f" of {n}"
                        d["ai_page_list"] = sp
                    elif d["route"] in ("ai", "context"):
                        d["ai_pages"] = f"all ({n})"
        elif ext in SHEET_EXT:
            d.update(doc_type="Spreadsheet / CSV", family="sheet", route="ai",
                     note="Read by the AI for now (Koinly CSV / workpapers parser comes later).")
            if "koinly" in p.name.lower():
                d.update(doc_type="Koinly - CSV export", family="koinly", route="program", note="")
        elif ext in NOTE_EXT:
            d.update(doc_type="Note / e-mail / letter", family="note", route="context")
        elif ext in IMG_EXT:
            d.update(doc_type="Image", family="image", route="ai", note="Photo/scan — the AI reads it as an image.")
        else:
            d.update(doc_type="Unsupported file type", family="unsupported", route="skipped",
                     note=f"{ext or 'no extension'} files aren't read.")
        if d.get("draft") and d["route"] not in ("skipped",):
            d.update(route="skipped", note=("Draft / estimate in the file name — skipped. " + d["note"]).strip())
        docs.append(d)

    for d in docs:
        if d["family"] in ("other", "note", "return", "bizreturn", "estimates", "karbon"):
            d["issuer"] = None
    _apply_rules(docs, py_year)
    counts = Counter(d["route"] for d in docs)
    missing = [str(p) for p in paths if not Path(p).is_file()]
    return dict(docs=docs, missing=missing, counts={k: counts.get(k, 0) for k in ROUTE_LBL})


def _apply_rules(docs: list, py_year: int | None) -> None:
    koinly = [d for d in docs if d["family"] == "koinly" and d["route"] != "skipped"]
    for d in docs:
        # Koinly takes precedence over any 1099-DA
        if d["family"] == "1099da" and d["route"] != "skipped":
            if koinly:
                d.update(route="excluded", ai_pages="",
                         note=f"Koinly report present — 1099-DA{(' from ' + d['issuer']) if d['issuer'] else ''} ignored. "
                              "Preparer to verify it is included in Koinly.")
            else:
                d["note"] = (d["note"] + " No Koinly report — totals come from the 1099-DA summary page.").strip()
        # composite that also carries a 1099-DA section
        if d["family"] == "composite" and "1099-DA" in d["forms"] and koinly:
            d["note"] = (d["note"] + " Includes a 1099-DA section — ignored (Koinly present); verify it's in Koinly.").strip()
        # tax year check
        if py_year and d.get("year") and d["family"] not in ("return", "pyreturn") and d["route"] in ("program", "ai"):
            if d["year"] != py_year + 1:
                d["year_flag"] = True
                d["note"] = (f"Tax year {d['year']} — expected {py_year + 1}. " + d["note"]).strip()
