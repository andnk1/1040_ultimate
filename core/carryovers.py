"""carryovers.py - carryovers from the prior-year return.

Three sources, all shown in the Carryovers box:
  1. UltraTax "Return Carryover Summary" (if printed) - every line: Activity/Form, Unit, activity, description, amount.
     AMT lines are skipped unless the AMT amount differs from the regular amount right above it.
  2. Carryovers read from the forms themselves (CARRYOVER_RULES) - works without the summary page.
     Add new rules to CARRYOVER_RULES as you meet them.
  3. Forms that may carry something over (WARN_FORMS) - if the form is in the return: "Check for the <item>".
"""
from __future__ import annotations

import re
from collections import OrderedDict

import pdfplumber

from .pdfutil import open_pdf, page_text

# ---------------------------------------------------------------- database
# page: every text must be on the page.  lines: IRS line numbers to read (right-hand amount).
# method: special reader.
CARRYOVER_RULES = [
    dict(item="Short-term capital loss carryover", source="Capital Loss Carryover Worksheet, line 8",
         page=["Capital Loss Carryover Worksheet"], lines=["8"]),
    dict(item="Long-term capital loss carryover", source="Capital Loss Carryover Worksheet, line 15",
         page=["Capital Loss Carryover Worksheet"], lines=["15"]),
    dict(item="Passive activity losses — rentals and businesses", source="Form 8582 Part VII, (c) Unallowed loss",
         page=["Allocation of Unallowed Losses"], method="8582_vii"),
    dict(item="Net operating loss — NOL", source="Form 172, line 10",
         page=["172", "Net Operating Loss"], lines=["10"]),
]

# form found in the return -> "Check for the <item>"
WARN_FORMS = [
    ("Excess business loss — §461(l)", [("461", "Limitation on Business Losses")]),
    ("At-risk suspended losses", [("6198", "At-Risk Limitations")]),
    ("Investment interest expense", [("4952", "Investment Interest Expense")]),
    ("Business interest disallowed under §163(j)", [("8990", "Limitation on Business Interest Expense")]),
    ("Partnership excess business interest expense — EBIE", [("8990", "Limitation on Business Interest Expense")]),
    ("Home-office expenses limited by business income", [("8829", "Business Use of Your Home")]),
    ("Qualified business net loss — QBI", [("8995", "Qualified Business Income Deduction"), ("8995-A", "Qualified Business Income Deduction")]),
    ("Qualified REIT/PTP component loss — QBI", [("8995", "Qualified Business Income Deduction"), ("8995-A", "Qualified Business Income Deduction")]),
    ("Credit for prior-year minimum tax — AMT credit", [("8801", "Credit for Prior Year Minimum Tax")]),
    ("General business credits — all applicable credit types", [("3800", "General Business Credit")]),
    ("Passive activity credits", [("8582-CR", "Passive Activity Credit Limitations"), ("3800", "General Business Credit")]),
    ("Nonrefundable adoption credit", [("8839", "Qualified Adoption Expenses")]),
    ("Residential clean energy credit — solar, batteries, etc.", [("5695", "Residential Energy Credit")]),
    ("Mortgage interest credit — Mortgage Credit Certificate", [("8396", "Mortgage Interest Credit")]),
    ("D.C. first-time homebuyer credit — legacy balances", [("8859", "District of Columbia First-Time Homebuyer")]),
    ("Qualified electric vehicle passive credit — very old balances", [("8582-CR", "Passive Activity Credit Limitations"), ("8834", "Qualified Electric Vehicle Credit")]),
    ("S corporation losses/deductions suspended for insufficient basis — §1366(d)", [("7203", "S Corporation Shareholder Stock and Debt Basis")]),
    ("Section 179 deduction limited by business income", [("4562", "Depreciation and Amortization")]),
    ("Qualified conservation contributions", [("8283", "Noncash Charitable Contributions")]),
    ("Foreign housing deduction exceeding its income limit", [("2555", "Foreign Earned Income")]),
]

NUM = re.compile(r"^\(?-?[\d,]+(\.\d+)?\)?$")


def _num(s):
    s = s.replace(",", "").replace("$", "")
    neg = s.startswith("(") or s.startswith("-")
    try:
        v = float(s.strip("()-"))
    except ValueError:
        return None
    return -v if neg else v


def _rows(words, tol=3):
    out = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(out[-1][0] - w["top"]) < tol:
            out[-1][1].append(w)
        else:
            out.append([w["top"], [w]])
    for r in out:
        r[1].sort(key=lambda w: w["x0"])
    return out


# ---------------------------------------------------------------- 1. Return Carryover Summary
def _summary_page(page) -> list[dict]:
    ws = page.extract_words()
    hdr = next((w for w in ws if w["text"].startswith("Activity/Form")), None)
    unit = next((w for w in ws if w["text"] == "Unit" and hdr and abs(w["top"] - hdr["top"]) < 4), None)
    amt_hdr = next((w for w in ws if w["text"] == "Carryover" and hdr and abs(w["top"] - hdr["top"]) < 4), None)
    if not hdr:
        return []
    unit_x = unit["x0"] if unit else hdr["x1"] + 5
    desc_x = (unit["x1"] + 3) if unit else unit_x + 25
    amt_x = (amt_hdr["x0"] - 10) if amt_hdr else page.width * 0.8
    out, form, un, act = [], "", "", ""
    for top, wl in _rows([w for w in ws if w["top"] > hdr["top"] + 4]):
        if re.search(r"^Page \d|Client Copy", " ".join(w["text"] for w in wl)):
            continue
        f = " ".join(w["text"] for w in wl if w["x1"] <= unit_x + 2)
        u = " ".join(w["text"] for w in wl if unit_x - 2 <= w["x0"] < desc_x and w["text"].isdigit())
        dws = [w for w in wl if unit_x - 2 <= w["x0"] < amt_x and not (w["x0"] < desc_x and w["text"].isdigit())]
        d = " ".join(w["text"] for w in dws)
        a = [w for w in wl if w["x0"] >= amt_x and NUM.match(w["text"])]
        amount = _num(a[-1]["text"]) if a else None
        if f:
            form, un, act = f, u, ""
            if amount is None:
                act = d
                continue
        elif u and not d and amount is None:
            un = u
            continue
        if amount is None:
            if d:
                act = (act + " " + d).strip() if not form or act else d
            continue
        if dws and out and dws[0]["x0"] > desc_x + 90 and len(d.split()) <= 2:
            d = out[-1]["description"].rsplit(" - ", 1)[0] + " - " + d      # "...BASIS - TAXPAYER" / "SPOUSE"
        out.append(dict(form=form, unit=un, activity=act, description=d, amount=amount))
    return out


def read_carryover_summary(pdf, flat) -> list[dict]:
    rows = []
    for i, t in enumerate(flat):
        if "Return Carryover Summary" in t:
            for r in _summary_page(pdf.pages[i]):
                r["page"] = i + 1
                rows.append(r)
    # AMT lines: keep only when the AMT amount differs from the regular amount right above
    out = []
    for r in rows:
        if re.search(r"\bAMT\b", r["description"]) and out and out[-1]["amount"] == r["amount"] \
                and out[-1]["form"] == r["form"] and out[-1]["unit"] == r["unit"]:
            continue
        out.append(r)
    return out


# ---------------------------------------------------------------- 2. carryovers read from the forms
def _line_amount(page, line: str):
    """Amount printed to the right of IRS line number `line` (right-hand column)."""
    W = page.width
    for top, wl in _rows(page.extract_words(), tol=4):
        ids = [w for w in wl if w["text"].rstrip(".") == line and w["x0"] > W * 0.5]
        for idw in ids:
            a = [w for w in wl if w["x0"] > idw["x1"] and NUM.match(w["text"]) and any(c.isdigit() for c in w["text"])
                 and w["text"].rstrip(".") != line]
            if a:
                return _num(a[0]["text"].rstrip("."))
    return None


def _8582_vii(page) -> list[dict]:
    """Form 8582 Part VII - one row per activity with its (c) Unallowed loss."""
    ws = page.extract_words()
    rows = _rows(ws)
    start = next((i for i, (t, wl) in enumerate(rows) if "Allocation" in [w["text"] for w in wl] and
                  any(w["text"] == "Unallowed" for w in wl)), None)
    if start is None:
        return []
    # (c) column header
    cx = None
    for t, wl in rows[start:start + 6]:
        for w in wl:
            if w["text"] == "(c)":
                cx = (w["x0"] + w["x1"]) / 2
    out = []
    for t, wl in rows[start + 1:start + 40]:
        s = " ".join(w["text"] for w in wl)
        if re.match(r"^Part VIII|^Form 8582", s):
            break
        nums = [w for w in wl if NUM.match(w["text"]) and ("," in w["text"] or len(w["text"]) > 2)]
        name = " ".join(w["text"] for w in wl if not NUM.match(w["text"]) and w["x0"] < (min(n["x0"] for n in nums) if nums else 0))
        if not nums or not name or name.startswith("("):
            continue
        pick = min(nums, key=lambda w: abs((w["x0"] + w["x1"]) / 2 - cx)) if cx else nums[-2] if len(nums) >= 2 else nums[-1]
        out.append(dict(activity=name.strip(), amount=_num(pick["text"])))
    return out


def read_rule_carryovers(pdf, flat) -> list[dict]:
    out = []
    for rule in CARRYOVER_RULES:
        pages = [i for i, t in enumerate(flat) if all(p in t for p in rule["page"])]
        for i in pages:
            pg = pdf.pages[i]
            if rule.get("method") == "8582_vii":
                for r in _8582_vii(pg):
                    if r["amount"]:
                        out.append(dict(item=rule["item"], source=rule["source"], activity=r["activity"],
                                        amount=r["amount"], page=i + 1))
                continue
            for ln in rule.get("lines", []):
                v = _line_amount(pg, ln)
                if v:
                    out.append(dict(item=rule["item"], source=rule["source"], activity="", amount=v, page=i + 1))
            if any(o["item"] == rule["item"] for o in out):
                break                                   # first page that has it (printed copies repeat)
    return out


# ---------------------------------------------------------------- 3. forms that may carry over
def _form_pages(flat, num: str, title: str) -> list[int]:
    hits = []
    for i, t in enumerate(flat):
        if not re.search(r"OMB No|Sequence No|Department of the Treasury", t):
            continue
        # the form's own footer "Form 8829 (2024)" - a schedule that only mentions the form doesn't count
        if re.search(re.escape(title), t, re.I) and re.search(r"Form\s*" + re.escape(num) + r"\s*\(20\d\d\)", t):
            hits.append(i + 1)
    return hits


def read_carry_checks(flat) -> list[dict]:
    out = []
    for item, forms in WARN_FORMS:
        for num, title in forms:
            pages = _form_pages(flat, num, title)
            if pages:
                out.append(dict(item=item, form="Form " + num, page=pages[0]))
                break
    return out


def read_carryovers(path, extra_passwords=None) -> dict:
    doc, pw = open_pdf(path, extra_passwords)
    with doc:
        flat = [re.sub(r"\s+", " ", page_text(doc, i)) for i in range(len(doc))]
    with pdfplumber.open(str(path), password=pw or "") as pdf:
        summary = read_carryover_summary(pdf, flat)
        rules = read_rule_carryovers(pdf, flat)
    return dict(summary=summary, from_forms=rules, checks=read_carry_checks(flat))
