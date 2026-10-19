"""py_return.py - read the prior-year 1040 print package.

What it reads
  * Front-page summary
      - UltraTax: "Two Year Comparison Report" pages 1-2 (both years, filing status, dependents)
      - any other software: Form 1040 pages 1-2 (line numbers in the right-hand column)
  * Forms / schedules filed (page titles)
  * Expected documents for this year (payers, employers, K-1 entities, brokers)
      - UltraTax: Salaries & Wages Report, Broker Reconciliation Worksheet, Federal Statements
        (interest / dividend payers), K-1 Reconciliation Worksheets
      - any software: Schedule B payer lines, Schedule E page 2 line 28 names
  * Carryovers to next year (UltraTax "Return Carryover Summary")
Nothing identifying is kept: no SSNs, no addresses; people only by first name.
"""
from __future__ import annotations

import re
from collections import OrderedDict

import pdfplumber

from .pdfutil import open_pdf, page_text
from .inventory import return_year

AMT = re.compile(r"^\(?-?\$?[\d,]+(\.\d+)?\)?\.?$")


def _num(s: str) -> float | None:
    s = s.replace("$", "").replace(",", "").rstrip(".")
    neg = s.startswith("(") or s.startswith("-")
    s = s.strip("()-")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _rows(words, tol=3.5):
    out = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(out[-1][0] - w["top"]) < tol:
            out[-1][1].append(w)
        else:
            out.append([w["top"], [w]])
    for r in out:
        r[1].sort(key=lambda w: w["x0"])
    return out


# ---------------------------------------------------------------- Two Year Comparison (UltraTax)
# label on the Two Year Comparison (start of text, lower case) -> short label. Matched by text, not line number,
# because UltraTax renumbers the lines between years.
TWO_YEAR_LABELS = [
    ("salaries and wages", "Wages"), ("interest income", "Taxable interest"), ("tax exempt interest", "Tax-exempt interest"),
    ("dividend income", "Ordinary dividends"), ("qualified dividend", "Qualified dividends"),
    ("taxable state/local refunds", "Taxable state/local refunds"), ("alimony received", "Alimony received"),
    ("business income", "Business income (Sch C)"), ("capital gain", "Capital gain/loss"),
    ("other gains", "Other gains/losses (4797)"), ("taxable ira", "Taxable IRA distributions"),
    ("taxable pensions", "Taxable pensions"), ("rent and royalty", "Rent & royalty (Sch E p1)"),
    ("partnership/s corp", "Partnership / S corp (K-1s)"), ("estate or trust", "Estate / trust income"),
    ("farm income", "Farm income"), ("unemployment", "Unemployment"), ("taxable social security", "Taxable social security"),
    ("other income", "Other income"), ("total income", "Total income"), ("moving expenses", "Moving expenses"),
    ("deductible part of self", "Deductible SE tax"), ("sep/simple", "SEP/SIMPLE/qualified plans"),
    ("se health insurance", "SE health insurance"), ("penalty on early", "Early withdrawal penalty"),
    ("alimony paid", "Alimony paid"), ("ira deductions", "IRA deduction"), ("student loan", "Student loan interest"),
    ("other adjustments", "Other adjustments"), ("adjusted gross income", "AGI"), ("medical", "Medical"),
    ("taxes", "Taxes (SALT)"), ("interest", "Interest (mortgage / investment)"), ("contributions", "Charitable contributions"),
    ("casualty", "Casualty losses"), ("miscellaneous", "Miscellaneous deductions"),
    ("allowable itemized", "Itemized deductions"), ("standard deduction", "Standard deduction"),
    ("deduction taken", "Deduction taken"), ("additional deductions", "Additional deductions (Sch 1-A)"),
    ("taxable income before", None), ("taxable income from", None), ("qbid", "QBI deduction"),
    ("qualified business income", "QBI deduction"), ("taxable income", "Taxable income"),
    ("tax on taxable income", "Tax"), ("alternative minimum", "AMT"), ("excess advance", "Excess APTC repayment"),
    ("child care credit", "Child care credit"), ("education credits", "Education credits"),
    ("retirement savings", "Retirement savings credit"), ("child & other dependent", "Child / other dependent credit"),
    ("general business", "General business credit"), ("other credits", "Other credits"), ("total credits", "Total credits"),
    ("net tax liability", "Net tax liability"), ("self-employment taxes", "Self-employment tax"),
    ("other taxes", "Other taxes"), ("total tax", "Total tax"), ("income tax withheld", "Withholding"),
    ("estimated tax payments", "Estimated payments"), ("earned income credit", "Earned income credit"),
    ("additional child tax", "Additional child tax credit"), ("other refundable", "Other refundable credits"),
    ("other payments", "Other payments"), ("total payments", "Total payments"), ("tax due/-refund", "Tax due / (refund)"),
    ("penalties and interest", "Penalties & interest"), ("net tax due/-refund", "Net due / (refund)"),
    ("refund applied", "Refund applied to next year"), ("refund received", "Refund received"),
    ("effective tax rate", "Effective rate %"),
]
EXACT = {"medical", "taxes", "interest", "contributions"}


def _canon(label: str):
    l = re.sub(r"\s+", " ", label.lower()).strip(" .")
    for key, out in sorted(TWO_YEAR_LABELS, key=lambda x: -len(x[0])):
        if (l == key) if key in EXACT else l.startswith(key):
            return key, out
    return None, None


def _two_year(pdf, pages: list[int]) -> dict | None:
    years, lines, fs, dep = None, {}, None, None
    for pi in pages:
        p = pdf.pages[pi]
        rows = _rows(p.extract_words())
        cols = None
        for top, wl in rows:
            txt = [w["text"] for w in wl]
            yrs = [w for w in wl if re.fullmatch(r"20\d\d", w["text"])]
            if len(yrs) >= 2 and any(w["text"] == "Differences" for w in wl):
                cols = [((w["x0"] + w["x1"]) / 2) for w in yrs[:2]] + \
                       [next((w["x0"] + w["x1"]) / 2 for w in wl if w["text"] == "Differences")]
                years = [int(yrs[0]["text"]), int(yrs[1]["text"])]
                break
        if not cols:
            continue
        amt_rows = []   # (top, {col: value})
        label_rows = []  # (top, line no)
        for top, wl in rows:
            first = wl[0]["text"]
            m = re.fullmatch(r"(\d{1,2})\.", first) if wl[0]["x0"] < 140 else None
            if not m and len(wl) > 1 and wl[0]["x0"] < 60 and re.fullmatch(r"[A-Za-z]", first):
                m = re.fullmatch(r"(\d{1,2})\.", wl[1]["text"])     # "I 8." (vertical side label)
            if m:
                right = [w for w in wl if re.fullmatch(r"\d{1,2}\.", w["text"]) and w["x0"] > 200]
                stop = right[0]["x0"] if right else cols[0] - 70
                lbl = " ".join(w["text"] for w in wl if 70 <= w["x0"] < stop and not AMT.match(w["text"])
                               and not set(w["text"]) <= set(". "))
                key, out = _canon(lbl)
                label_rows.append((top, out or ("?" + lbl), wl))      # unknown labels still claim their amounts
            vals = {}
            for w in wl:
                if w["x0"] > cols[0] - 70 and AMT.match(w["text"]) and not re.fullmatch(r"\d{1,2}\.", w["text"]):
                    c = min(range(3), key=lambda i: abs(cols[i] - (w["x0"] + w["x1"]) / 2))
                    v = _num(w["text"])
                    if v is not None and abs(cols[c] - w["x1"]) < 90:
                        vals[c] = v
            if vals:
                amt_rows.append((top, vals))
            txt = [w["text"] for w in wl]
            if any(t in ("SGL", "MFJ", "MFS", "HOH", "QSS", "QW") for t in txt):
                fs = [t for t in txt if t in ("SGL", "MFJ", "MFS", "HOH", "QSS", "QW")]
        # dependents: numbers on the row right above "Dependents"
        for i, (top, wl) in enumerate(rows):
            if wl[0]["text"] == "Dependents" and i > 0:
                ds = [w["text"] for w in rows[i - 1][1] if re.fullmatch(r"\d{1,2}", w["text"])]
                if ds:
                    dep = ds[:2]
        # UltraTax prints each value ~10pt above its own label: an amount row belongs to the nearest label BELOW it
        label_tops = [t for t, _, _ in label_rows]
        for top, n, wl in label_rows:
            same = {}
            for w in wl:
                if w["x0"] > cols[0] - 70 and AMT.match(w["text"]) and not re.fullmatch(r"\d{1,2}\.", w["text"]):
                    c = min(range(3), key=lambda i: abs(cols[i] - (w["x0"] + w["x1"]) / 2))
                    same[c] = _num(w["text"])
            lines[n] = same
        for t, v in amt_rows:
            if any(abs(t - lt) < 3.5 for lt in label_tops):
                continue                                   # on a label row - already taken
            below = [(lt, n) for lt, n, _ in label_rows if 0 < lt - t <= 16]
            if below:
                lt, n = min(below)
                if not lines.get(n):
                    lines[n] = v
    if not years:
        return None
    out, seen = [], set()
    for _, lbl in TWO_YEAR_LABELS:
        if lbl and lbl in lines and lbl not in seen:
            seen.add(lbl)
            v = lines[lbl]
            out.append(dict(line="", label=lbl, prior=v.get(0), cur=v.get(1), diff=v.get(2)))
    fs = fs or []
    return dict(source="UltraTax Two Year Comparison", years=years,
                filing_status=dict(prior=fs[0] if len(fs) > 1 else None, cur=fs[-1] if fs else None),
                dependents=dict(prior=dep[0] if dep and len(dep) > 1 else None, cur=dep[-1] if dep else None),
                lines=out)


# ---------------------------------------------------------------- Form 1040 pages (any software)
F1040_P1 = OrderedDict([("1a", "W-2 wages"), ("1z", "Wages (total)"), ("2a", "Tax-exempt interest"),
                        ("2b", "Taxable interest"), ("3a", "Qualified dividends"), ("3b", "Ordinary dividends"),
                        ("4a", "IRA distributions"), ("4b", "Taxable IRA"), ("5a", "Pensions"), ("5b", "Taxable pensions"),
                        ("6a", "Social security"), ("6b", "Taxable social security"), ("7", "Capital gain/loss"),
                        ("7a", "Capital gain/loss"), ("8", "Schedule 1 income"), ("9", "Total income"),
                        ("10", "Adjustments"), ("11", "AGI"), ("11a", "AGI"), ("12", "Standard / itemized deduction"),
                        ("12e", "Standard / itemized deduction"), ("13", "QBI deduction"), ("13a", "QBI deduction"),
                        ("14", "Total deductions"), ("15", "Taxable income")])
F1040_P2 = OrderedDict([("16", "Tax"), ("17", "Schedule 2 line 3"), ("18", "Tax before credits"),
                        ("19", "Child / other dependent credit"), ("20", "Schedule 3 credits"), ("21", "Total credits"),
                        ("22", "Tax after credits"), ("23", "Other taxes (Sch 2)"), ("24", "Total tax"),
                        ("25a", "W-2 withholding"), ("25b", "1099 withholding"), ("25c", "Other withholding"),
                        ("25d", "Withholding (total)"), ("26", "Estimated payments"), ("27", "Earned income credit"),
                        ("27a", "Earned income credit"), ("28", "Additional child tax credit"), ("29", "AOTC refundable"),
                        ("31", "Schedule 3 refundable"), ("32", "Other payments/credits"), ("33", "Total payments"),
                        ("34", "Overpaid"), ("35a", "Refund"), ("36", "Applied to next year"), ("37", "Amount owed"),
                        ("38", "Estimated tax penalty")])
LINE_ID = re.compile(r"^(\d{1,2}[a-z]?)$")


def _form_lines(page, keep: dict) -> dict:
    W = page.width
    vals = {}
    for top, wl in _rows(page.extract_words(), tol=4):
        ids = [w for w in wl if LINE_ID.match(w["text"]) and w["text"] in keep and w["x0"] > W * 0.38]
        for w in ids:
            nxt = [x for x in ids if x["x0"] > w["x0"]]
            stop = nxt[0]["x0"] if nxt else W
            a = [x for x in wl if w["x1"] < x["x0"] < stop and AMT.match(x["text"]) and any(c.isdigit() for c in x["text"])
                 and not x["text"].endswith(",") and not LINE_ID.match(x["text"])]
            if a and w["text"] not in vals:
                v = _num(a[0]["text"])
                if v is not None:
                    vals[w["text"]] = v
    return vals


def _filing_status_form(page) -> str | None:
    """X mark next to a filing-status label on Form 1040 page 1."""
    ws = page.extract_words()
    labels = {"Single": "SGL", "jointly": "MFJ", "separately": "MFS", "household": "HOH", "surviving": "QSS"}
    lab = [(w, code) for w in ws for k, code in labels.items() if w["text"].startswith(k)]
    xs = [w for w in ws if w["text"] == "X"]
    best = None
    for x in xs:
        for w, code in lab:
            d = abs(x["top"] - w["top"]) + abs(x["x1"] - w["x0"]) * 0.2
            if abs(x["top"] - w["top"]) < 8 and (best is None or d < best[0]):
                best = (d, code)
    return best[1] if best and best[0] < 60 else None


# ---------------------------------------------------------------- forms filed
FORM_TITLES = [
    ("Schedule 1", r"SCHEDULE 1\s*\(Form 1040\)"), ("Schedule 2", r"SCHEDULE 2\s*\(Form 1040\)"),
    ("Schedule 3", r"SCHEDULE 3\s*\(Form 1040\)"), ("Schedule A", r"SCHEDULE A\s*\(Form 1040\)|Schedule A \(Form 1040\) 20"),
    ("Schedule B", r"SCHEDULE B\s*\(Form 1040\)|Schedule B \(Form 1040\) 20"), ("Schedule C", r"SCHEDULE C\s*\(Form 1040\)|Schedule C \(Form 1040\) 20"),
    ("Schedule D", r"SCHEDULE D\s*\(Form 1040\)|Schedule D \(Form 1040\) 20"), ("Schedule E", r"SCHEDULE E\s*\(Form 1040\)|Schedule E \(Form 1040\) 20"),
    ("Schedule F", r"SCHEDULE F\s*\(Form 1040\)"), ("Schedule H", r"SCHEDULE H\s*\(Form 1040\)"),
    ("Schedule SE", r"SCHEDULE SE\s*\(Form 1040\)|Schedule SE \(Form 1040\) 20"), ("Schedule 8812", r"SCHEDULE 8812"),
]
for _f, _t in [("1116", "Foreign Tax Credit"), ("2210", "Underpayment of Estimated Tax"), ("2441", "Child and Dependent Care"),
               ("3800", "General Business Credit"), ("4562", "Depreciation and Amortization"), ("4797", "Sales of Business Property"),
               ("4952", "Investment Interest Expense"), ("5329", "Additional Taxes on Qualified Plans"), ("5695", "Residential Energy"),
               ("6198", "At-Risk Limitations"), ("6251", "Alternative Minimum Tax"), ("6781", "Gains and Losses From Section 1256"),
               ("8283", "Noncash Charitable"), ("8582", "Passive Activity Loss"), ("8606", "Nondeductible IRAs"),
               ("8829", "Business Use of Your Home"), ("8863", "Education Credits"), ("8889", "Health Savings Accounts"),
               ("8938", "Specified Foreign Financial Assets"), ("8949", "Sales and Other Dispositions"), ("8959", "Additional Medicare Tax"),
               ("8960", "Net Investment Income Tax"), ("8962", "Premium Tax Credit"), ("8995", "Qualified Business Income Deduction"),
               ("7203", "S Corporation Shareholder Stock and Debt Basis"), ("7217", "Partner's Report of Property Distributed"),
               ("1040-ES", "Estimated Tax for Individuals"), ("4868", "Application for Automatic Extension"),
               ("8958", "Allocation of Tax Amounts Between Certain Individuals"), ("8801", "Credit for Prior Year Minimum Tax"),
               ("2555", "Foreign Earned Income"), ("8615", "Tax for Certain Children"), ("8814", "Parents' Election"),
               ("8880", "Credit for Qualified Retirement Savings"), ("5695", "Residential Clean Energy"),
               ("8936", "Clean Vehicle Credit"), ("8396", "Mortgage Interest Credit"), ("4684", "Casualties and Thefts"),
               ("6252", "Installment Sale Income"), ("8824", "Like-Kind Exchanges"), ("8853", "Archer MSAs"),
               ("8862", "Information To Claim Certain Credits After Disallowance"), ("8867", "Paid Preparer's Due Diligence")]:
    FORM_TITLES.append(("Form " + _f, re.escape(_t)))


FORM_SHORT = {
    "Schedule 1": "Add'l income & adj.", "Schedule 2": "Add'l taxes", "Schedule 3": "Add'l credits & pmts",
    "Schedule A": "Itemized ded.", "Schedule B": "Interest & div.", "Schedule C": "Business", "Schedule D": "Capital gains",
    "Schedule E": "Rental / K-1", "Schedule F": "Farm", "Schedule H": "Household empl.", "Schedule SE": "SE tax",
    "Schedule 8812": "Child tax credit", "1116": "Foreign tax credit", "2210": "Underpayment penalty", "2441": "Dependent care",
    "3800": "Gen. business credit", "4562": "Depreciation", "4797": "Business property sales", "4952": "Investment interest",
    "5329": "Retirement plan taxes", "5695": "Energy credits", "6198": "At-risk", "6251": "AMT", "6781": "§1256 contracts",
    "8283": "Noncash charity", "8582": "Passive loss", "8606": "Nondeductible IRA", "8829": "Home office", "8863": "Education credits",
    "8889": "HSA", "8938": "Foreign assets", "8949": "Cap gains detail", "8959": "Add'l Medicare", "8960": "NIIT",
    "8962": "Premium tax credit", "8995": "QBI", "7203": "S corp basis", "7217": "Partner property distr.",
    "1040-ES": "Estimates", "4868": "Extension", "8958": "Community property", "8801": "Prior-yr AMT credit",
    "2555": "Foreign earned income", "8615": "Kiddie tax", "8814": "Child's interest/div", "8880": "Saver's credit",
    "8936": "Clean vehicle credit", "8396": "Mortgage credit", "4684": "Casualty / theft", "6252": "Installment sale",
    "8824": "Like-kind exchange", "8853": "Archer MSA", "8862": "Credits after disallowance", "8867": "Due diligence",
}


# ---------------------------------------------------------------- expected documents
STOP = {"INC", "LLC", "LP", "L", "P", "CO", "CORP", "CORPORATION", "COMPANY", "THE", "OF", "NA", "N", "A", "BANK", "FUND",
        "MARKETS", "SECURITIES", "FINANCIAL", "SERVICES", "LTD", "TRUST", "AND", "&", "GROUP", "HOLDINGS", "US", "USA"}


def _clean_name(s: str) -> str:
    s = re.sub(r"\(\d{3,}\)|X\d{3,}|\*+[-\d*]*", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .$-")
    return s


def _expected_ultratax(pages_text: list[str]) -> list[dict]:
    exp = []
    for i, t in enumerate(pages_text):
        pg = i + 1
        if "Salaries & Wages Report" in t:
            t = t.split("\nTaxpayer", 1)[0]          # federal block only (the state block repeats A, B, ... with state codes)
            for m in re.finditer(r"^([A-M]) (?:[TS] )?([A-Z][A-Z0-9 &.,'-]{2,}?) [\d,]+ ", t, re.M):
                exp.append(dict(kind="W-2", name=_clean_name(m.group(2)), page=pg))
        if "Broker Reconciliation Worksheet" in t:
            m = re.search(r"Payer.s name\s+Account number\s*\n(.+)", t)
            if m:
                exp.append(dict(kind="1099 (broker)", name=_clean_name(m.group(1)), page=pg))
        if "Federal Statements" in t:
            for sec, kind in (("Interest Income", "1099-INT"), ("Dividend Income", "1099-DIV")):
                m = re.search(r"Form 1040, " + sec + r"(.*?)(?:\nTOTAL|\nForm 1040,|\Z)", t, re.S)
                if m:
                    for ln in m.group(1).splitlines():
                        ln = ln.strip()
                        if re.match(r"^[A-Z][A-Z0-9 &.,'()/-]{3,}$", ln) and not re.match(r"^(PAYER|ORDINARY|QUALIFIED|DIVIDENDS|TOTAL|DESCRIPTION|AMOUNT)", ln):
                            exp.append(dict(kind=kind, name=_clean_name(ln), page=pg))
        if "K-1 Reconciliation Worksheet" in t and "Qualified Business Income" not in t:
            m = re.search(r"Entity Name\s*(.+?)\s*EIN\s+\S*?(\d{3,4})\s+Entity Type\s+([A-Z ]+?)\s+Screen", t)
            if m:
                exp.append(dict(kind="K-1 (" + ("1120-S" if "S CORP" in m.group(3) else "1041" if "TRUST" in m.group(3) or "ESTATE" in m.group(3) else "1065") + ")",
                                name=_clean_name(m.group(1)), ein4=m.group(2)[-4:], page=pg))
    return exp


def _expected_forms(pdf) -> list[dict]:
    """Schedule B payers and Schedule E p2 entities, from the IRS forms (any software)."""
    exp = []
    for i, p in enumerate(pdf.pages):
        t = p.extract_text() or ""
        if re.search(r"SCHEDULE B\s*\(Form 1040\)|Interest and Ordinary Dividends", t) and "Part I" in t:
            for top, wl in _rows(p.extract_words(), tol=3):
                txt = " ".join(w["text"] for w in wl if w["x0"] < p.width * 0.75 and not re.fullmatch(r"\.+", w["text"]))
                amt = [w for w in wl if w["x0"] > p.width * 0.75 and AMT.match(w["text"]) and any(c.isdigit() for c in w["text"])]
                name = re.sub(r"^(1|5)\s+", "", txt).strip()
                if amt and re.match(r"^[A-Z][A-Za-z0-9 &.,'()-]{3,}$", name) and not re.search(
                        r"(?i)total|add the amounts|subtract|excludable|schedule|instructions|part|line|form|note|list name|^(ordinary|qualified|dividends?|interest|amount|payer|description)\b", name):
                    kind = "1099-DIV" if wl[0]["top"] > p.height * 0.55 else "1099-INT"
                    exp.append(dict(kind=kind, name=_clean_name(name), page=i + 1))
        if "Part II Income or Loss From Partnerships and S Corporations" in re.sub(r"\s+", " ", t):
            for m in re.finditer(r"^([A-D]) (.+?) ([PS]) (?:\S*\d{3,4})", t, re.M):
                exp.append(dict(kind="K-1 (" + ("1065" if m.group(3) == "P" else "1120-S") + ")",
                                name=_clean_name(m.group(2)), page=i + 1))
    return exp


def _carryovers(pages_text: list[str]) -> list[dict]:
    out = []
    for i, t in enumerate(pages_text):
        if "Return Carryover Summary" not in t:
            continue
        body = t.split("Carryover to", 1)[-1]
        for ln in body.splitlines()[1:]:
            m = re.match(r"^(.*?)\s+(-?[\d,]+)$", ln.strip())
            if m and len(m.group(1)) > 3:
                out.append(dict(item=re.sub(r"\s+", " ", m.group(1)), amount=_num(m.group(2)), page=i + 1))
    return out


# ---------------------------------------------------------------- main
def read_prior_return(path, extra_passwords=None) -> dict:
    doc, pw = open_pdf(path, extra_passwords)
    with doc:
        producer = (doc.metadata or {}).get("producer") or ""
        texts = [page_text(doc, i) for i in range(len(doc))]
    n = len(texts)
    flat = [re.sub(r"\s+", " ", t) for t in texts]
    year = return_year("\n".join(texts[:60]))
    ultratax = "UltraTax" in producer or any("Two Year Comparison Report" in t for t in flat)
    res = dict(file=str(path), pages=n, year=year, software="UltraTax CS" if ultratax else (producer or "unknown"),
               summary=None, filing_status=None, dependents=None, forms=[], expected=[], carryovers=[], warnings=[])

    with pdfplumber.open(str(path), password=pw or "") as pdf:
        # summary
        two = [i for i, t in enumerate(flat) if "Two Year Comparison Report - Page" in t]
        if two:
            ty = _two_year(pdf, two[:2])
            if ty:
                res["summary"] = ty
                res["filing_status"] = ty["filing_status"]["cur"]
                res["dependents"] = ty["dependents"]["cur"]
        if not res["summary"]:
            p1 = next((i for i, t in enumerate(flat) if "Individual Income Tax Return" in t and "first name" in t and "Reconciliation" not in t), None)
            p2 = next((i for i, t in enumerate(flat) if i != p1 and re.search(r"Form 1040 \(20\d\d\)\s*Page 2|Page 2 .*Tax and Credits|Tax and Credits .*16 Tax", t)
                       and "Refund" in t), None)
            if p1 is not None:
                l1 = _form_lines(pdf.pages[p1], F1040_P1)
                l2 = _form_lines(pdf.pages[p2], F1040_P2) if p2 is not None else {}
                seen, lines = set(), []
                for k, lbl in list(F1040_P1.items()) + list(F1040_P2.items()):
                    v = l1.get(k) if k in F1040_P1 and k in l1 else l2.get(k)
                    if v is None or lbl in seen:
                        continue
                    seen.add(lbl)
                    lines.append(dict(line=k, label=lbl, prior=None, cur=v, diff=None))
                res["summary"] = dict(source=f"Form 1040 (pages {p1 + 1}" + (f", {p2 + 1})" if p2 is not None else ")"),
                                      years=[None, year], lines=lines,
                                      filing_status=dict(prior=None, cur=_filing_status_form(pdf.pages[p1])),
                                      dependents=dict(prior=None, cur=None))
                res["filing_status"] = res["summary"]["filing_status"]["cur"]
            else:
                res["warnings"].append("Form 1040 pages not found — summary not available.")
        res["expected"] = _expected_forms(pdf)
        keys = ("Salaries & Wages Report", "Broker Reconciliation Worksheet", "Federal Statements", "K-1 Reconciliation Worksheet",
                "Return Carryover Summary")
        plumb = [(pdf.pages[i].extract_text() or "") if any(k in flat[i] for k in keys) else "" for i in range(n)]
    # forms filed
    found = OrderedDict()
    for i, t in enumerate(flat):
        if not re.search(r"OMB No|Sequence No|Department of the Treasury", t):
            continue                                      # only real IRS form pages, not summaries / letters
        for name, pat in FORM_TITLES:
            if name in found:
                continue
            if name.startswith("Form "):
                num = name[5:]
                # the form's own footer "Form 8829 (2024)" - pages that only mention the form don't count
                if re.search(pat, t, re.I) and re.search(r"Form\s*" + re.escape(num) + r"\s*\(20\d\d\)", t):
                    found[name] = i + 1
            elif re.search(pat, t) and re.search(re.escape(name) + r"\s*\(Form 1040\)\s*(\(?20\d\d\)?)", t, re.I):
                found[name] = i + 1
    res["forms"] = [dict(form=k, page=v, short=FORM_SHORT.get(k.replace("Form ", ""), "")) for k, v in found.items()]
    if ultratax:
        res["expected"] = _expected_ultratax(plumb) + res["expected"]
    res["expected"] = _dedupe_expected(res["expected"])
    res["carryovers"] = _carryovers(plumb if ultratax else texts)
    return res


def _key(name: str) -> set:
    return {t for t in re.sub(r"[^A-Z0-9 ]", " ", name.upper()).split() if t not in STOP and len(t) > 1}


def _dedupe_expected(exp: list) -> list:
    out = []
    for e in exp:
        if not re.search(r"[A-Za-z]{3,}", e["name"]):
            continue                                   # masked / blank names ("C 82,794")
        k = _key(e["name"])
        if not k:
            continue
        dup = next((o for o in out if _key(o["name"]) == k or (k <= _key(o["name"]) or _key(o["name"]) <= k)
                    and o["kind"][:3] == e["kind"][:3]), None)
        if dup:
            if e["kind"] not in dup["kind"]:
                dup["kind"] += " / " + e["kind"]
            continue
        out.append(dict(e))
    return out


def match_expected(expected: list, docs: list) -> None:
    """Marks each expected item received / not received, and each document new / matched (in place)."""
    for e in expected:
        e["received"] = []
    for d in docs:
        if d["route"] in ("skipped",) or d["family"] in ("pyreturn", "return", "note", "other", "scan", "image"):
            continue
        hay = _key(" ".join(filter(None, [d.get("issuer") or "", d["name"]])))
        hit = False
        for e in expected:
            k = _key(e["name"])
            if k and (k & hay) and max(len(t) for t in (k & hay)) >= 4:
                e["received"].append(d["file"])
                hit = True
        d["on_py"] = hit


# ---------------------------------------------------------------- Schedule C (prior year)
SCHC_LINES = OrderedDict([
    ("1", "Gross receipts or sales"), ("2", "Returns and allowances"), ("3", "Subtract line 2 from line 1"),
    ("4", "Cost of goods sold"), ("5", "Gross profit"), ("6", "Other income"), ("7", "Gross income"),
    ("8", "Advertising"), ("9", "Car and truck expenses"), ("10", "Commissions and fees"), ("11", "Contract labor"),
    ("12", "Depletion"), ("13", "Depreciation and section 179"), ("14", "Employee benefit programs"),
    ("15", "Insurance (other than health)"), ("16a", "Interest - mortgage"), ("16b", "Interest - other"),
    ("17", "Legal and professional services"), ("18", "Office expense"), ("19", "Pension and profit-sharing plans"),
    ("20a", "Rent - vehicles, machinery, equipment"), ("20b", "Rent - other business property"),
    ("21", "Repairs and maintenance"), ("22", "Supplies"), ("23", "Taxes and licenses"), ("24a", "Travel"),
    ("24b", "Deductible meals"), ("25", "Utilities"), ("26", "Wages"), ("27a", "Energy efficient commercial bldgs"),
    ("27b", "Other expenses"), ("28", "Total expenses"), ("29", "Tentative profit (loss)"),
    ("30", "Business use of home"), ("31", "Net profit (loss)"),
])


def _schedule_c_page(page) -> dict:
    W = page.width
    ws = page.extract_words()
    left_ids = {"8", "9", "10", "11", "12", "13", "14", "15", "16a", "16b", "17"}
    ids = [w for w in ws if (w["text"] in left_ids and 0.26 * W < w["x0"] < 0.36 * W)
           or (w["text"] in SCHC_LINES and w["text"] not in left_ids and 0.72 * W < w["x0"] < 0.80 * W)]
    amts = [w for w in ws if AMT.match(w["text"]) and "," in w["text"] or re.fullmatch(r"\d+\.\d\d|\d{2,}\.?", w["text"])]
    # amount columns: left (between the left box numbers and the right-hand labels) and right (after the right box numbers)
    amts = [w for w in amts if (0.31 * W < w["x0"] and w["x1"] < 0.47 * W) or w["x0"] > 0.82 * W]
    vals = {}
    for a in amts:
        right = a["x0"] > 0.80 * W
        col = [i for i in ids if (i["x0"] > 0.72 * W) == right]
        if not right:
            col = [i for i in col if i["x1"] < a["x0"]]
        if not col:
            continue
        best = min(col, key=lambda i: abs(i["top"] - a["top"]))
        if abs(best["top"] - a["top"]) <= 7 and best["text"] not in vals:
            v = _num(a["text"])
            if v is not None:
                vals[best["text"]] = v
    # business name: line C, else principal business (line A)
    name = None
    rows = _rows(ws)
    for k, (top, wl) in enumerate(rows):
        t = " ".join(w["text"] for w in wl)
        if t.startswith("C Business name") or t.startswith("A Principal business"):
            nxt = rows[k + 1][1] if k + 1 < len(rows) else []
            cand = " ".join(w["text"] for w in nxt if w["x0"] < 0.7 * W and not re.fullmatch(r"\d{6}", w["text"]))
            if cand and not re.match(r"^(C|D|E|F) ", cand):
                name = name or cand.strip()
    return dict(name=name, lines=vals)


def read_schedule_c(path, extra_passwords=None) -> list[dict]:
    doc, pw = open_pdf(path, extra_passwords)
    with doc:
        flat = [re.sub(r"\s+", " ", page_text(doc, i)) for i in range(len(doc))]
    out = []
    with pdfplumber.open(str(path), password=pw or "") as pdf:
        for i, t in enumerate(flat):
            if "Profit or Loss From Business" in t and "Part II" in t and "Gross receipts" in t:
                r = _schedule_c_page(pdf.pages[i])
                if not r["lines"]:
                    continue
                if any(o["lines"] == r["lines"] for o in out):
                    continue                     # same Schedule C printed twice (client + filing copy)
                r["page"] = i + 1
                r["name"] = r["name"] or f"Business {len(out) + 1}"
                out.append(r)
    return out


# ---------------------------------------------------------------- Schedule E page 1 (prior year)
SCHE_LINES = OrderedDict([
    ("3", "Rents received"), ("4", "Royalties received"), ("5", "Advertising"), ("6", "Auto and travel"),
    ("7", "Cleaning and maintenance"), ("8", "Commissions"), ("9", "Insurance"), ("10", "Legal and other professional fees"),
    ("11", "Management fees"), ("12", "Mortgage interest paid to banks, etc."), ("13", "Other interest"), ("14", "Repairs"),
    ("15", "Supplies"), ("16", "Taxes"), ("17", "Utilities"), ("18", "Depreciation expense or depletion"), ("19", "Other"),
    ("20", "Total expenses"), ("21", "Income or (loss)"), ("22", "Deductible rental real estate loss after limitation (Form 8582)"),
])
SCHE_TYPES = {"1": "Single Family Residence", "2": "Multi-Family Residence", "3": "Vacation/Short-Term Rental", "4": "Commercial",
              "5": "Land", "6": "Royalties", "7": "Self-Rental", "8": "Other"}


def _schedule_e_page(page) -> list[dict]:
    """One Schedule E page 1 -> up to 3 properties (columns A / B / C): address, type, days, lines 3-22."""
    W = page.width
    ws = page.extract_words()
    rows = _rows(ws)
    # column centres from the "A  B  C" header over the amount columns
    hdr = None
    for top, wl in rows:
        letters = [w for w in wl if w["text"] in ("A", "B", "C") and w["x0"] > 0.45 * W]
        if len(letters) == 3:
            hdr = {w["text"]: (w["x0"] + w["x1"]) / 2 for w in letters}
            break
    if not hdr:
        return []
    props = {k: dict(letter=k, name="", type="", fair_days=None, personal_days=None, lines={}) for k in "ABC"}
    in_1a = in_2 = False
    for top, wl in rows:
        t = " ".join(w["text"] for w in wl)
        if re.match(r"^1a\b", t):
            in_1a = True
            continue
        if re.match(r"^1b\b|^Type of Property", t):
            in_1a = False
        if re.match(r"^2\b", t) or "Fair Rental" in t:
            in_2, in_1a = True, False
        if wl and wl[0]["text"] in ("A", "B", "C") and wl[0]["x0"] < 0.08 * W:
            k = wl[0]["text"]
            rest = wl[1:]
            if in_1a:
                props[k]["name"] = " ".join(w["text"] for w in rest if w["x0"] < 0.80 * W).strip()
                tp = [w["text"] for w in rest if w["x0"] >= 0.80 * W and re.fullmatch(r"[1-8]", w["text"])]
                props[k]["type"] = SCHE_TYPES.get(tp[0], "") if tp else props[k]["type"]
            elif in_2:
                nums = [w["text"] for w in rest if re.fullmatch(r"\d{1,3}", w["text"])]
                if nums:
                    props[k]["fair_days"] = int(nums[0])
                if len(nums) > 1:
                    props[k]["personal_days"] = int(nums[1])
            continue
        first_col = min(hdr.values())
        lid = next((w for w in wl if w["text"] in SCHE_LINES and w["x0"] < 0.10 * W), None) or \
            next((w for w in wl if w["text"] in SCHE_LINES and 0.35 * W < w["x0"] and w["x1"] < first_col - 25), None)
        if lid:
            in_2 = False
            box = [w for w in wl if w["text"] == lid["text"] and w["x0"] > 0.35 * W]     # the line box number before the columns
            for w in wl:
                if w["x0"] < 0.45 * W or w is lid or not AMT.match(w["text"]) or not re.search(r"\d", w["text"]) or w in box:
                    continue
                v = _num(w["text"])
                if v is None:
                    continue
                if lid["text"] == "22" or w["text"].startswith("("):
                    v = -abs(v)
                col = min(hdr, key=lambda c: abs(hdr[c] - (w["x0"] + w["x1"]) / 2))
                props[col]["lines"].setdefault(lid["text"], v)
    return [p for p in props.values() if p["lines"] or p["name"]]


def read_schedule_e(path, extra_passwords=None) -> list[dict]:
    """Prior-year Schedule E page 1, every property (continuation pages included)."""
    doc, pw = open_pdf(path, extra_passwords)
    with doc:
        flat = [re.sub(r"\s+", " ", page_text(doc, i)) for i in range(len(doc))]
    out = []
    with pdfplumber.open(str(path), password=pw or "") as pdf:
        for i, t in enumerate(flat):
            if "Supplemental Income and Loss" in t and "Rents received" in t and "Royalties received" in t:
                for p in _schedule_e_page(pdf.pages[i]):
                    if any(o["lines"] == p["lines"] and o["name"] == p["name"] for o in out):
                        continue                 # same page printed twice
                    p["page"] = i + 1
                    p["name"] = p["name"] or f"Property {len(out) + 1}"
                    out.append(p)
    return out


# ---------------------------------------------------------------- prior-year income summary (office template)
def _sched_lines(pdf, flat, must: list[str], keep: dict) -> dict:
    for i, t in enumerate(flat):
        if all(m in t for m in must):
            v = _form_lines(pdf.pages[i], keep)
            if v:
                return v
    return {}


def read_py_income(path, py: dict | None = None, schc: list | None = None) -> dict:
    """Prior-year amounts for the office income-summary rows."""
    doc, pw = open_pdf(path)
    with doc:
        flat = [re.sub(r"\s+", " ", page_text(doc, i)) for i in range(len(doc))]
    out = {}
    with pdfplumber.open(str(path), password=pw or "") as pdf:
        p1 = next((i for i, t in enumerate(flat) if "Individual Income Tax Return" in t and "first name" in t
                   and "Reconciliation" not in t), None)
        f1 = _form_lines(pdf.pages[p1], F1040_P1) if p1 is not None else {}
        p2 = next((i for i, t in enumerate(flat) if p1 is not None and i > p1 and re.search(r"Form 1040 \(20\d\d\)", t)
                   and "25d" in t), None)
        f2 = _form_lines(pdf.pages[p2], F1040_P2) if p2 is not None else {}
        sd = _sched_lines(pdf, flat, ["Capital Gains and Losses", "Short-Term"], OrderedDict([("7", ""), ("15", "")]))
        se1 = _sched_lines(pdf, flat, ["Supplemental Income and Loss", "Part I"], OrderedDict([("26", "")]))
        s1 = _sched_lines(pdf, flat, ["Additional Income and Adjustments to Income", "Part I"], OrderedDict([("9", ""), ("10", "")]))
        se2 = _sched_lines(pdf, flat, ["Income or Loss From Partnerships and S Corporations"], OrderedDict([("32", ""), ("41", "")]))
        s1b = _sched_lines(pdf, flat, ["Adjustments to Income", "Part II", "Student loan interest"], OrderedDict([("21", "")]))
    two = {l["label"]: l["cur"] for l in ((py or {}).get("summary") or {}).get("lines", [])} \
        if (py or {}).get("summary", {}) and (py["summary"].get("source", "").startswith("UltraTax")) else {}

    def pick(*vals):
        for v in vals:
            if v is not None:
                return v
        return None

    out["w2"] = pick(f1.get("1z"), f1.get("1a"), two.get("Wages"))
    out["interest"] = pick(f1.get("2b"), two.get("Taxable interest"))
    out["dividends"] = pick(f1.get("3b"), two.get("Ordinary dividends"))
    out["ira"] = pick(f1.get("4b"), two.get("Taxable IRA distributions"))
    out["pension"] = pick(f1.get("5b"), two.get("Taxable pensions"))
    out["ss"] = pick(f1.get("6b"), two.get("Taxable social security"))
    out["st"] = sd.get("7")
    out["lt"] = sd.get("15")
    cg = pick(f1.get("7"), f1.get("7a"), two.get("Capital gain/loss"))
    if out["st"] is None and out["lt"] is None and cg is not None:
        out["lt_note"] = f"Schedule D not found — capital gain/loss on the 1040: {cg:,.0f}"
    sc = sum((b["lines"].get("31") or 0) for b in (schc or [])) if schc else None
    out["schc"] = pick(sc, two.get("Business income (Sch C)"))
    out["rental"] = pick(se1.get("26"), two.get("Rent & royalty (Sch E p1)"))
    out["other"] = pick(s1.get("9"), two.get("Other income"))
    out["k1"] = pick(se2.get("32"), two.get("Partnership / S corp (K-1s)"))
    out["total_return"] = pick(f1.get("9"), two.get("Total income"))
    out["fit"] = pick(f2.get("25d"), two.get("Withholding"))
    out["capgain_return"] = cg
    out["student_loan"] = pick(s1b.get("21"), two.get("Student loan interest"))
    return out
