"""pl.py - a business P&L (QuickBooks-style) -> Schedule C lines.

Reads CSV, Excel (.xlsx) or PDF. The layout is the QuickBooks "Profit and Loss" report:
section headers (Income / Cost of Goods Sold / Expenses / Other Income / Other Expenses), one row per account
(name + amount), parent accounts with or without their own amount, "Total for ..." subtotals, Gross Profit,
Net Operating Income, Net Other Income and Net Income. Everything after "Net Income" (the preparer's own notes
such as "N/D" or "Meals addback") is ignored.

Check: income - COGS - expenses + other income - other expenses must equal the Net Income printed on the
report; if it doesn't (or nothing can be read) the screen shows an error with both numbers.

Each account gets a suggested Schedule C line (first matching rule wins - adapted from the 1120 Mapping app)
and a return amount (meals: 50% of books). Both are only suggestions - the preparer changes them on screen.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

SECTIONS = {
    "income": "income", "revenue": "income", "ordinary income/expenses": None,
    "cost of goods sold": "cogs", "cost of sales": "cogs", "cogs": "cogs",
    "expenses": "expense", "expense": "expense", "operating expenses": "expense",
    "other income": "other_income", "other expenses": "other_expense", "other expense": "other_expense",
}
INCOME_LIKE = {"income", "other_income"}
SKIP = re.compile(r"^(total\b|gross profit|net operating income|net other income|net ordinary income)", re.I)
NET = re.compile(r"^net\s+income\b", re.I)
SECTION_LBL = {"income": "Income", "cogs": "Cost of goods sold", "expense": "Expenses",
               "other_income": "Other income", "other_expense": "Other expenses"}

# Schedule C lines the P&L can map to (+ two "not on Schedule C" choices)
MAP_LINES = [
    ("1", "1 Gross receipts or sales"), ("2", "2 Returns and allowances"), ("4", "4 Cost of goods sold"),
    ("6", "6 Other income"), ("8", "8 Advertising"), ("9", "9 Car and truck expenses"), ("10", "10 Commissions and fees"),
    ("11", "11 Contract labor"), ("12", "12 Depletion"), ("13", "13 Depreciation and section 179"),
    ("14", "14 Employee benefit programs"), ("15", "15 Insurance (other than health)"), ("16a", "16a Interest - mortgage"),
    ("16b", "16b Interest - other"), ("17", "17 Legal and professional services"), ("18", "18 Office expense"),
    ("19", "19 Pension and profit-sharing plans"), ("20a", "20a Rent - vehicles, machinery, equipment"),
    ("20b", "20b Rent - other business property"), ("21", "21 Repairs and maintenance"), ("22", "22 Supplies"),
    ("23", "23 Taxes and licenses"), ("24a", "24a Travel"), ("24b", "24b Meals (50%)"), ("25", "25 Utilities"),
    ("26", "26 Wages"), ("27b", "27b Other expenses (Part V)"), ("30", "30 Business use of home"),
    ("nd", "Not deductible (N/D)"), ("x", "Not on Schedule C (personal / owner)"),
]
MAP_LBL = dict(MAP_LINES)

RULES_EXP = [
    ("meal", "24b"), ("entertainment", "nd"), ("travel", "24a"), ("airfare", "24a"), ("hotel", "24a"), ("lodging", "24a"),
    ("taxi", "24a"), ("shared ride", "24a"), ("uber", "24a"), ("lyft", "24a"),
    ("parking", "9"), ("toll", "9"), ("gas & fuel", "9"), ("fuel", "9"), ("vehicle", "9"), ("auto", "9"), ("mileage", "9"),
    ("charit", "nd"), ("donation", "nd"), ("contribution", "nd"), ("penalt", "nd"), ("fines", "nd"), ("political", "nd"),
    ("owner", "x"), ("draw", "x"), ("personal", "x"),
    ("advertis", "8"), ("marketing", "8"), ("promotion", "8"), ("sponsor", "8"),
    ("merchant", "27b"), ("bank", "27b"),
    ("commission", "10"), ("contract labor", "11"), ("contractor", "11"), ("subcontract", "11"),
    ("depletion", "12"), ("depreciation", "13"), ("amortization", "13"),
    ("health insurance", "14"), ("employee benefit", "14"), ("benefits", "14"),
    ("insurance", "15"), ("mortgage interest", "16a"), ("interest", "16b"),
    ("legal", "17"), ("accounting", "17"), ("bookkeeping", "17"), ("professional", "17"), ("tax prep", "17"),
    ("pension", "19"), ("401", "19"), ("retirement", "19"), ("profit sharing", "19"),
    ("equipment rent", "20a"), ("equipment lease", "20a"), ("vehicle lease", "20a"), ("machinery", "20a"),
    ("rent", "20b"), ("lease", "20b"),
    ("repair", "21"), ("maintenance", "21"),
    ("office", "18"), ("software", "18"), ("postage", "18"), ("printing", "18"), ("stationery", "18"),
    ("small tools", "22"), ("tools", "22"), ("supplies", "22"), ("materials", "22"),
    ("payroll tax", "23"), ("taxes", "23"), ("license", "23"), ("permit", "23"),
    ("utilit", "25"), ("phone", "25"), ("internet", "25"), ("electric", "25"), ("water", "25"), ("telephone", "25"),
    ("salar", "26"), ("wage", "26"), ("payroll", "26"),
]
RULES_INC = [("refund", "2"), ("return", "2"), ("discount", "2"), ("interest", "6"), ("reward", "6"), ("other income", "6")]


def suggest(account: str, section: str) -> str:
    a = account.lower()
    if section == "cogs":
        return "4"
    if section in INCOME_LIKE:
        for k, t in RULES_INC:
            if k in a:
                return t
        return "6" if section == "other_income" else "1"
    for k, t in RULES_EXP:
        if k in a:
            return t
    return "27b"


def _amt(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s in ("-", "--"):
        return None
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = s.strip("()-").replace("$", "").replace(",", "").strip()
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


# ---------------------------------------------------------------- readers -> [(name, amount or None)]
def _lines_csv(path) -> tuple[list, str | None]:
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    rows = [r for r in csv.reader(io.StringIO(raw)) if any(c.strip() for c in r)]
    return _from_grid(rows)


def _lines_xlsx(path) -> tuple[list, str | None]:
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows = [["" if v is None else v for v in r] for r in ws.iter_rows(values_only=True)]
    return _from_grid([r for r in rows if any(str(c).strip() for c in r)])


def _from_grid(rows) -> tuple[list, str | None]:
    """Name = first non-empty text cell; amount = the 'Total' column (or the last numeric column)."""
    company = next((str(r[0]).strip() for r in rows if r and str(r[0]).strip()), None)
    tcol = None
    for r in rows[:8]:
        for i, c in enumerate(r):
            if str(c).strip().lower() == "total":
                tcol = i
    out = []
    for r in rows:
        name = next((str(c).strip() for c in r if str(c).strip() and _amt(c) is None), "")
        if not name:
            continue
        if tcol is not None and tcol < len(r):
            v = _amt(r[tcol])
        else:
            nums = [_amt(c) for c in r[1:] if _amt(c) is not None]
            v = nums[-1] if nums else None
        out.append((name, v))
    return out, company


def _lines_pdf(path, pw=None) -> tuple[list, str | None]:
    from .pdfutil import open_pdf
    doc, _ = open_pdf(path, [pw] if pw else None)
    out, company = [], None
    with doc:
        tx = None
        for page in doc:
            words = page.get_text("words")
            if company is None:
                first = sorted(words, key=lambda w: (w[1], w[0]))
                company = " ".join(w[4] for w in first if abs(w[1] - first[0][1]) < 3) if first else None
            if tx is None:
                t = [w for w in words if w[4].lower() == "total"]
                tx = t[0][2] if t else None
            rows = []
            for w in sorted(words, key=lambda w: (round(w[1]), w[0])):
                if rows and abs(rows[-1][0] - w[1]) <= 3:
                    rows[-1][1].append(w)
                else:
                    rows.append([w[1], [w]])
            for _, ws in rows:
                ws.sort(key=lambda w: w[0])
                nums = [w for w in ws if _amt(w[4]) is not None and re.search(r"\d\.\d\d|\d,\d{3}", w[4])]
                if tx is not None:
                    nums = [w for w in nums if abs(w[2] - tx) < 60] or nums
                name = " ".join(w[4] for w in ws if w not in nums).strip()
                if not name:
                    continue
                out.append((name, _amt(nums[-1][4]) if nums else None))
    return out, company


# ---------------------------------------------------------------- P&L
def read_pl(path) -> dict:
    """dict(file, company, rows=[{account, section, books, line, amount}], net_income, computed, ok, error)"""
    p = Path(path)
    ext = p.suffix.lower()
    try:
        if ext == ".csv":
            lines, company = _lines_csv(p)
        elif ext in (".xlsx", ".xlsm"):
            lines, company = _lines_xlsx(p)
        elif ext == ".pdf":
            lines, company = _lines_pdf(p)
        else:
            return dict(file=p.name, error=f"{p.suffix} files can't be read — use a CSV, Excel (.xlsx) or PDF P&L.", rows=[])
    except Exception as e:  # noqa: BLE001
        return dict(file=p.name, error=f"Couldn't read the P&L: {type(e).__name__}: {e}", rows=[])
    section, rows, net = None, [], None
    for name, v in lines:
        low = name.lower().rstrip(":").strip()
        if v is None and low in SECTIONS:
            section = SECTIONS[low] or section
            continue
        if NET.match(low):
            if v is not None:
                net = v
                break                                  # the preparer's own lines below Net Income are not accounts
            continue
        if v is None or SKIP.match(low) or section is None:
            continue
        name = re.sub(r"^\d{3,}\s+", "", name).strip()
        rows.append(dict(account=name, section=section, books=round(v, 2)))
    for r in rows:
        r["line"] = suggest(r["account"], r["section"])
        r["amount"] = round(r["books"] / 2, 2) if r["line"] == "24b" else r["books"]
    sign = {"income": 1, "other_income": 1, "cogs": -1, "expense": -1, "other_expense": -1}
    computed = round(sum(sign[r["section"]] * r["books"] for r in rows), 2)
    err = None
    if not rows:
        err = "No accounts found — this doesn't look like a Profit and Loss report. Use the CSV / Excel export instead."
    elif net is None:
        err = f"'Net Income' not found on the report — can't check the total (accounts add up to {computed:,.2f})."
    elif abs(computed - net) > 0.01:
        err = (f"The accounts read add up to {computed:,.2f} but the report's Net Income is {net:,.2f} "
               f"(difference {net - computed:,.2f}). Check the rows below, or use the CSV / Excel export.")
    return dict(file=p.name, company=(company or "").strip(), rows=rows, net_income=net, computed=computed,
                ok=err is None, error=err)


# ---------------------------------------------------------------- downloads (same CSV style as 1120 Mapping)
def _sum_lines(rows) -> dict:
    t = {}
    for r in rows:
        t[r["line"]] = t.get(r["line"], 0) + float(r.get("amount") or 0)
    return t


def workpaper_csv(biz: dict, lines: dict, final: dict) -> str:
    """Every Schedule C line in form order: from the P&L, as entered (final), plus the P&L check."""
    from .py_return import SCHC_LINES
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Schedule C Line", "Description", "From P&L", "Schedule C amount"])
    for k, lbl in SCHC_LINES.items():
        w.writerow([k, lbl, f"{lines.get(k, 0):.2f}" if k in lines else "", f"{float(final.get(k) or 0):.2f}"])
    nd = lines.get("nd", 0)
    xx = lines.get("x", 0)
    w.writerow([])
    w.writerow(["", "Not deductible (N/D)", f"{nd:.2f}", ""])
    w.writerow(["", "Not on Schedule C", f"{xx:.2f}", ""])
    pl = biz.get("pl") or {}
    w.writerow([])
    w.writerow(["", "Total Summary:", "", ""])
    w.writerow(["", "Net Income per P&L", f"{float(pl.get('net_income') or 0):.2f}", ""])
    w.writerow(["", "Accounts read (books)", f"{float(pl.get('computed') or 0):.2f}", ""])
    w.writerow(["", "Difference - if different than 0, check the P&L", f"{float(pl.get('net_income') or 0) - float(pl.get('computed') or 0):.2f}", ""])
    w.writerow(["", "Net profit (loss) - line 31", "", f"{float(final.get('31') or 0):.2f}"])
    return out.getvalue()


def other_expenses_csv(rows) -> str:
    """Part V - itemized support for line 27b, alphabetized."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["P&L Account", "Amount"])
    tot = 0.0
    for r in sorted((r for r in rows if r["line"] == "27b"), key=lambda r: r["account"].lower()):
        w.writerow([r["account"], f"{float(r.get('amount') or 0):.2f}"])
        tot += float(r.get("amount") or 0)
    w.writerow(["Total Other Expenses (line 27b)", f"{tot:.2f}"])
    return out.getvalue()


def book_tax_csv(rows) -> str:
    """Accounts where the Schedule C amount differs from books (meals 50%, N/D, personal, typed changes)."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["P&L Account", "Section", "Books", "Schedule C line", "Schedule C amount", "Difference"])
    for r in rows:
        on = 0.0 if r["line"] in ("nd", "x") else float(r.get("amount") or 0)
        if abs(on - r["books"]) > 0.005:
            w.writerow([r["account"], SECTION_LBL.get(r["section"], r["section"]), f"{r['books']:.2f}", MAP_LBL.get(r["line"], r["line"]),
                        f"{on:.2f}", f"{r['books'] - on:.2f}"])
    return out.getvalue()
