"""utscreens.py - reads the UltraTax input screens print (PDF) and verifies it line by line.

Two parts (Verify return, with the input screens):
  1. Document verification - every box the program read from a document (and every line typed on screen 1) against
     the UT entry for it, line by line: W-2 box 1 / box 2, 1099-INT / DIV / B boxes (B&D statements), Schedule E lines
     (Rent screens), Schedule C lines (C screen), 1095-A / 1098-T. No totals, no net amounts.
  2. UltraTax entries with no document behind them.
Within $1 ties (UT rounds to whole dollars; some people round the other way).

UT print layout:
  - a screen page has the screen name on line 1 and "<code> (2025)" on line 2.
  - W2 screen: box label rows ("1 Wages, tips   2 Fed W/H") with the amounts on the row below, one W-2 per unit.
  - B&D screen: Interest income / Dividend income (Ordinary, Qualified, Total Capital Gains, Section 1250 ...);
    the payer detail is on the "Federal Statements" page after it - one page can hold several sections
    (Interest Income / Dividend Income / Capital Gains and Losses), each with its own column headers.
  - Rent screen: one property (unit) per screen; Rent-2 / Rent-3 are QBI / vacation pages - not read.
  - other statements ("Other income", "Digital Assets Transactions" ...): one record per entry (upper-case
    description row + continuation rows with amounts), then TOTAL.
"""
from __future__ import annotations

import itertools
import re
from pathlib import Path

import pymupdf

# screen code -> income category (screens not listed are not income data entry: General, Bank, ELF, 2Yr, History ...)
INCOME_SCREENS = {
    "W2": "w2", "B&D": None, "Int": "interest", "Div": "dividends", "1099R": None, "SSA": "ss", "C": "schc",
    "E": None, "F": "schc",
    "Income": "other", "6781": "cg1256", "4797": "other", "K1": "k1", "K1-2": "k1",
    "K1T": "k1", "K1S": "k1", "Unemp": "other", "D": None,
}
# 1095-A / 1098-T: not income - their screens are read for the screen-2 check only
MEMO_SCREENS = {"1095A": "1095a", "1095-A": "1095a", "8962": "1095a", "PTC": "1095a", "Health": "1095a",
                "8863": "1098t", "1098T": "1098t", "1098-T": "1098t", "Educ": "1098t", "Education": "1098t",
                "8889": "1099sa", "HSA": "1099sa", "1099SA": "1099sa", "1099-SA": "1099sa"}
PAYMENT_SCREENS = {"Est": "Federal estimates", "St Pmt": "State payments"}

# statement title -> category
STATEMENTS = [
    (r"digital asset|capital gain|8949|sales of capital|transactions", "cg"),
    (r"1256|straddle|marked to market", "cg1256"),
    (r"other income", "other"),
    (r"interest", "interest"),
    (r"dividend", "dividends"),
    (r"wage", "w2"),
    (r"rent|royalt", "rental"),
    (r"pension|annuit|ira|1099-r", "pension"),
    (r"social security", "ss"),
]
CAT_LBL = {"w2": "W-2 wages", "fit": "Federal withholding", "interest": "Interest", "dividends": "Ordinary dividends",
           "div_q": "Qualified dividends", "div_cg": "Capital gain distributions", "div_1250": "Section 1250 gain",
           "ftax": "Foreign tax paid", "ira": "IRA", "pension": "Pensions",
           "ss": "Social Security", "lt": "Long-term gain / (loss)", "st": "Short-term gain / (loss)",
           "st_proceeds": "Short-term proceeds", "st_cost": "Short-term cost", "st_adj": "Short-term adjustment",
           "lt_proceeds": "Long-term proceeds", "lt_cost": "Long-term cost", "lt_adj": "Long-term adjustment",
           "cg1256": "§1256 contracts (6781)", "schc": "Schedule C", "other": "Other income", "rental": "Rental / royalties",
           "k1": "K-1"}
INCOME_KEYS = {"w2", "interest", "dividends", "ira", "pension", "ss", "lt", "st", "cg1256", "schc", "other", "rental", "k1"}

AMT = re.compile(r"^\(?-?\$?[\d,]*\d(\.\d\d)?\)?$")
SCREEN_HDR = re.compile(r"^(.+?) \((20\d\d)\)$")
TOL = 1.01                        # within $1 ties


def _num(t: str):
    t = t.replace("$", "").replace(",", "")
    neg = t.startswith("(") and t.endswith(")") or t.startswith("-")
    t = t.strip("()-")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _is_amt(t: str) -> bool:
    """A money amount: 1,234 / 88 / (500) - not a form number, date, year or a single digit code."""
    if not AMT.match(t) or t in ("$",):
        return False
    digits = re.sub(r"\D", "", t)
    if len(digits) < 2:
        return False
    if "," not in t and len(digits) == 4 and digits[:2] in ("19", "20"):
        return False                    # a year
    return True


def _rows(page):
    """Words grouped into rows (same baseline), left to right."""
    rows = {}
    for w in page.get_text("words"):
        rows.setdefault(round((w[1] + w[3]) / 2 / 3), []).append(w)
    return [sorted(v, key=lambda w: w[0]) for _, v in sorted(rows.items())]


def _stmt_cat(title: str):
    for pat, cat in STATEMENTS:
        if re.search(pat, title, re.I):
            return cat
    return None


def _record_start(tokens: list) -> bool:
    words = [t for t in tokens if re.search(r"[A-Za-z]{2}", t)]
    if not words or tokens[0].upper() == "TOTAL":
        return False
    return all(w == w.upper() for w in words)


def _statement(page, pno: int, title: str) -> list:
    cat = _stmt_cat(title)
    rows = _rows(page)
    # records start after the title rows; header rows are mixed case, records are upper case
    start = next((i for i, r in enumerate(rows) if " ".join(w[4] for w in r).strip() == title), 1) + 1
    body = rows[start:]
    left = min((r[0][0] for r in body if _record_start([w[4] for w in r])), default=0)
    recs, cur = [], None
    for r in body:
        toks = [w[4] for w in r]
        if toks and toks[0].upper().startswith("TOTAL"):
            cur = None
            continue
        if _record_start(toks) and r[0][0] <= left + 15:      # a new record starts at the left edge
            first = [t for t in toks if not _is_amt(t) and t != "$"]
            if first and re.fullmatch(r"[A-L](/[A-L])?|[TSJ]", first[0]):
                code, first = first[0], first[1:]
            else:
                code = ""
            cur = dict(tokens=list(toks), code=code, desc=" ".join(t for t in first if t not in ("VARIOUS",)), page=pno)
            recs.append(cur)
        elif cur is not None:                                  # continuation row (amounts, state code ...)
            cur["tokens"] += toks
    out = []
    for rec in recs:
        toks = rec["tokens"]
        amts = [t for t in toks if _is_amt(t)]
        if not amts:
            continue
        desc = re.sub(r"(\s\d{1,2})+$", "", rec["desc"]).strip()
        c, box = cat, ""
        if cat == "cg":
            m = re.match(r"^([A-L])(?:/([A-L]))?$", rec["code"])
            c = "lt" if re.search(r"\bLONG\b", desc) or (m and not m.group(2) and m.group(1) in "DEFJKL") else "st"
            box = (m.group(2) if c == "lt" and m.group(2) else m.group(1)) if m else ""      # "B/E": B if short, E if long
        out.append(dict(source="statement", screen=title, label=desc, amount=_num(amts[-1]), cat=c, box=box, page=rec["page"]))
    return out


# ---------------------------------------------------------------- B&D statements: several sections per page, column-aware
# section title -> column header text (the words of a column, both header lines) -> field
BD_SECTIONS = [
    ("interest", r"^Interest Income( \(continued\))?$", [(r"^Interest Income", "interest"), (r"^Fed W/H", "fit")]),
    ("dividends", r"^Dividend Income( \(continued\))?$", [(r"^Ordinary", "dividends"), (r"^Qualified", "div_q"),
                                                          (r"^Total Cap", "div_cg"), (r"^Sec\.? 1250", "div_1250"),
                                                          (r"^Foreign Tax Paid", "ftax"), (r"^Fed W/H", "fit")]),
    ("cg", r"^(Capital Gains and Losses|Sales of Capital Assets)( \(continued\))?$",
     [(r"^Sales", "proceeds"), (r"^Cost", "cost"), (r"^1=S", "term"), (r"^Adj to G/L", "adj"), (r"^Gain", "gain"),
      (r"^Fed W/H", "fit")]),
]
_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$|^VARIOUS$|^INHERIT")


def _columns(pair: list) -> list:
    """Header row pair -> columns [{x, text, field}]: the top row gives each column's left edge, the text under it
    (second row, same x span) completes the column name ("Total" + "Cap Gain")."""
    top = pair[0]
    low = pair[1] if len(pair) > 1 else []
    cols = []
    for i, w in enumerate(top):
        nx = top[i + 1][0] if i + 1 < len(top) else 10 ** 4
        under = [u[4] for u in low if w[0] - 15 <= u[0] < nx - 1]
        cols.append(dict(x=w[0], text=" ".join([w[4]] + under)))
    return cols


def _bd_sections(page, pno: int) -> list:
    """Every record of every B&D section on a statement page -> entries, one per field (interest, ordinary dividends,
    qualified, cap gain distributions, foreign tax, 8949 proceeds / cost / adjustment / gain by term)."""
    rows = _rows(page)
    marks = []
    for i, r in enumerate(rows):
        txt = " ".join(w[4] for w in r).strip()
        for key, pat, fields in BD_SECTIONS:
            if re.match(pat, txt):
                marks.append((i, key, fields, re.sub(r" \(continued\)$", "", txt)))
    out = []
    for n, (i, key, fields, title) in enumerate(marks):
        body = rows[i + 1:(marks[n + 1][0] if n + 1 < len(marks) else len(rows))]
        first = next((k for k, r in enumerate(body) if _record_start([w[4] for w in r])), None)
        if first is None:
            continue
        head = body[:first]
        pairs = [head[k:k + 2] for k in range(0, len(head), 2)]
        cols = []
        for p in pairs:
            cs = _columns(p)
            used = set()
            for c in cs:
                c["field"] = None
                for pat, f in fields:
                    if f not in used and re.match(pat, c["text"]):
                        c["field"] = f
                        used.add(f)
                        break
            cols.append(cs)
        recs, cur = [], None
        for r in body[first:]:
            toks = [w[4] for w in r]
            if toks and toks[0].upper().startswith("TOTAL"):
                cur = None
                continue
            if _record_start(toks):
                cur = [r]
                recs.append(cur)
            elif cur is not None:
                cur.append(r)
        for rec in recs:
            vals, label = {}, []
            for k, r in enumerate(rec):
                cs = cols[k] if k < len(cols) else []
                for w in r:
                    t = w[4]
                    col = max((c for c in cs if c["x"] <= w[0] + 6), key=lambda c: c["x"], default=None)
                    f = col and col["field"]
                    if f == "term" and re.fullmatch(r"[123]", t):
                        vals["term"] = t
                    elif f and f != "term" and (_is_amt(t) or re.fullmatch(r"-?\d", t)) and f not in vals:
                        v = _num(t)
                        if v is not None:
                            vals[f] = v
                    elif k == 0 and t != "$" and not _is_amt(t) and not _DATE.match(t) and not f:
                        label.append(t)
            code = ""
            if label and re.fullmatch(r"[A-L](/[A-L])?", label[0]):
                code, label = label[0], label[1:]
            label = " ".join(x for x in label if not re.fullmatch(r"\d{1,2}", x)).strip()
            if key == "cg":
                term = "lt" if vals.get("term") in ("2", "3") else "st"
                m = re.match(r"^([A-L])(?:/([A-L]))?$", code)
                box = (m.group(2) if term == "lt" and m.group(2) else m.group(1)) if m else ""
                for f in ("gain", "proceeds", "cost", "adj"):
                    if vals.get(f):
                        out.append(dict(source="statement", screen=title, label=label, amount=vals[f],
                                        cat=term if f == "gain" else f"{term}_{f}", box=box, page=pno))
                if vals.get("fit"):
                    out.append(dict(source="statement", screen=title, label=label, amount=vals["fit"], cat="fit", box="", page=pno))
                continue
            for f, v in vals.items():
                if f != "term" and v:
                    out.append(dict(source="statement", screen=title, label=label, amount=v, cat=f, box="", page=pno))
    return out


def _bd_screen(page, pno: int) -> list:
    """B&D screen: Interest income (one amount) and Dividend income (Ordinary / Qualified / Total Capital Gains /
    Section 1250 / Section 1202 columns). These are the totals of the statement when there is one."""
    out, heads = [], None
    W = page.rect.width
    for r in _rows(page):
        toks = [w[4] for w in r]
        txt = " ".join(toks)
        if "Ordinary" in toks and "Qualified" in toks:
            heads = []
            for j, w in enumerate(r):
                if w[4] in ("Ordinary", "Qualified", "Total", "Section"):
                    heads.append((w[0], {"Ordinary": "dividends", "Qualified": "div_q", "Total": "div_cg"}.get(w[4])))
            secs = [h for h in heads if h[1] is None]
            if secs:
                heads = [h if h[1] else (h[0], "div_1250" if h is secs[0] else None) for h in heads]
            continue
        if txt.startswith("Interest income"):
            a = [w for w in r if w[0] >= 0.6 * W and _is_amt(w[4])]
            if a:
                out.append(dict(source="screen", screen="B&D", label="Interest income", amount=_num(a[0][4]), cat="interest", box="", page=pno))
        if txt.startswith("Dividend income") and heads:
            for w in r:
                if not (_is_amt(w[4]) or re.fullmatch(r"\d", w[4])):
                    continue
                h = max((h for h in heads if h[0] <= w[0] + 6), key=lambda h: h[0], default=None)
                v = _num(w[4])
                if h and h[1] and v:
                    out.append(dict(source="screen", screen="B&D", label="Dividend income", amount=v, cat=h[1], box="", page=pno))
    return out


# ---------------------------------------------------------------- W2 screen: box by box
def _w2_screen(page, pno: int) -> list:
    """Box 1 (wages) and box 2 (federal withholding) of the W-2 on this screen. Boxes 3-6, 12, 14 and state are not
    used for the income check."""
    W = page.rect.width
    rows = _rows(page)
    unit = employer = ""
    out = []
    for k, r in enumerate(rows):
        toks = [w[4] for w in r]
        txt = " ".join(toks)
        mu = re.search(r"\bUnit:?\s+(\d+)", txt)
        if mu and not unit:
            unit = mu.group(1)
        if txt.startswith("Employer's name"):
            employer = txt.replace("Employer's name", "").strip()
        labels = []
        for j, w in enumerate(r[:-1]):
            if w[0] >= 0.42 * W and re.fullmatch(r"\d{1,2}", w[4]) and re.match(r"[A-Za-z]", r[j + 1][4]):
                labels.append((w[0], w[4], " ".join(x[4] for x in r[j + 1:j + 4] if not re.fullmatch(r"\d{1,2}", x[4]))))
        if not labels or not any(b in ("1", "2") for _, b, _ in labels) or k + 1 >= len(rows):
            continue
        for w in rows[k + 1]:
            if not _is_amt(w[4]):
                continue
            lab = max((x for x in labels if x[0] <= w[0] + 6), key=lambda x: x[0], default=None)
            if lab and lab[1] in ("1", "2"):
                out.append(dict(source="screen", screen="W2", label=f"Box {lab[1]}", amount=_num(w[4]),
                                cat="w2" if lab[1] == "1" else "fit", box=lab[1], page=pno))
    for e in out:
        e["label"] = " · ".join(x for x in (f"Unit {unit}" if unit else "", employer, e["label"]) if x)
        e["unit"] = unit
    return out


# UT "Rent" screen label -> Schedule E line
RENT_LINES = [(r"^Rent and royalties", "3"), (r"^Advertising", "5"), (r"^Auto", "6"), (r"^Travel", "6"),
              (r"^Cleaning", "7"), (r"^Commissions", "8"), (r"^Insurance", "9"), (r"^Legal", "10"), (r"^Management", "11"),
              (r"^Mortgage interest", "12"), (r"^Other mortgage interest", "12"), (r"^Other interest", "13"), (r"^Repairs", "14"),
              (r"^Supplies", "15"), (r"^Taxes", "16"), (r"^Utilities", "17"), (r"^Depreciation", "18"), (r"^Depletion", "18"),
              (r"^Other$|^Other\s*\(", "19")]
SCHE_LBL = {"3": "Rents received", "4": "Royalties received", "5": "Advertising", "6": "Auto and travel",
            "7": "Cleaning and maintenance", "8": "Commissions", "9": "Insurance", "10": "Legal and other professional fees",
            "11": "Management fees", "12": "Mortgage interest", "13": "Other interest", "14": "Repairs", "15": "Supplies",
            "16": "Taxes", "17": "Utilities", "18": "Depreciation or depletion", "19": "Other - total"}


def _rent_screen(page, pno: int) -> dict:
    """UT Rent screen -> {unit, desc, owner, type, page, lines: {Sch E line: amount}} (screen amounts, whole dollars)."""
    out = dict(unit="", desc="", owner="", type="", page=pno, lines={})
    W = page.rect.width
    for r in _rows(page):
        toks = [w[4] for w in r]
        txt = " ".join(toks)
        mu = re.search(r"\bUnit:?\s+(\d+)", txt)
        if mu and not out["unit"]:
            out["unit"] = mu.group(1)
        m = re.search(r"T,\s*S,\s*J\s+([TSJ])\b", txt)
        if m:
            out["owner"] = m.group(1)
            txt = (txt[:m.start()] + txt[m.end():]).strip()
        if txt.startswith("Property description"):
            out["desc"] = re.sub(r"\s*\bUnit\s+\d+.*$", "", re.sub(r"^Property description\s*", "", txt)).strip()
            continue
        left = [w[4] for w in r if w[0] < 0.6 * W]
        label = " ".join(t for t in left if t not in ("§", "$")).strip()
        amts = [w[4] for w in r if w[0] >= 0.6 * W and _is_amt(w[4])]
        if not amts or not label:
            continue
        for pat, line in RENT_LINES:
            if re.search(pat, label, re.I):
                v = _num(amts[0])
                if v is not None:
                    out["lines"][line] = out["lines"].get(line, 0) + v
                break
    return out


# UT "C" screen label -> Schedule C line (label-based; to confirm on a real print)
C_LINES = [(r"^Gross receipts", "1"), (r"^Returns and allowances", "2"), (r"^Cost of goods sold", "4"), (r"^Other income", "6"),
           (r"^Advertising", "8"), (r"^Car and truck", "9"), (r"^Commissions", "10"), (r"^Contract labor", "11"),
           (r"^Depletion", "12"), (r"^Depreciation", "13"), (r"^Employee benefit", "14"), (r"^Insurance", "15"),
           (r"^Mortgage interest|^Interest.*mortgage", "16a"), (r"^Other interest|^Interest.*other", "16b"),
           (r"^Legal", "17"), (r"^Office expense", "18"), (r"^Pension", "19"), (r"^Rent.*(vehicle|machinery|equipment)", "20a"),
           (r"^Rent.*(other|business property)", "20b"), (r"^Repairs", "21"), (r"^Supplies", "22"), (r"^Taxes", "23"),
           (r"^Travel", "24a"), (r"^(Deductible )?[Mm]eals", "24b"), (r"^Utilities", "25"), (r"^Wages", "26"),
           (r"^Energy efficient", "27a"), (r"^Other expenses", "27b"), (r"^Business use of home|^Home office", "30")]


def _c_screen(page, pno: int) -> dict:
    out = dict(unit="", name="", page=pno, lines={})
    W = page.rect.width
    for r in _rows(page):
        txt = " ".join(w[4] for w in r)
        mu = re.search(r"\bUnit:?\s+(\d+)", txt)
        if mu and not out["unit"]:
            out["unit"] = mu.group(1)
        mn = re.match(r"^(Business name|Name of proprietor|Principal business)\s+(.+)$", txt)
        if mn and not out["name"]:
            out["name"] = mn.group(2).strip()
        label = " ".join(w[4] for w in r if w[0] < 0.6 * W and w[4] not in ("§", "$")).strip()
        amts = [w[4] for w in r if w[0] >= 0.6 * W and _is_amt(w[4])]
        if not amts or not label:
            continue
        for pat, line in C_LINES:
            if re.search(pat, label, re.I):
                v = _num(amts[0])
                if v is not None:
                    out["lines"][line] = out["lines"].get(line, 0) + v
                break
    return out


def read_ut_screens(path: str) -> dict:
    """{file, pages, year, entries: [{screen, label, amount, cat, page, source}], payments, screens, memo, rents, cscreens}"""
    doc = pymupdf.open(path)
    entries, payments, screens, year, memo, rents, cscr = [], [], [], None, [], [], []
    code = None
    for i, page in enumerate(doc):
        lines = [l.strip() for l in page.get_text().split("\n") if l.strip()]
        if not lines:
            continue
        m = next((SCREEN_HDR.match(l) for l in lines[:4] if SCREEN_HDR.match(l)), None)
        if m:
            code, year = m.group(1), year or int(m.group(2))
            screens.append(dict(code=code, name=lines[0], page=i + 1))
            if code == "Rent":                                   # Rent and Royalty Property: one property per screen
                rents.append(_rent_screen(page, i + 1))
                continue
            if code == "W2":
                entries += [dict(e, under="W2") for e in _w2_screen(page, i + 1)]
                continue
            if code == "B&D":
                entries += [dict(e, under="B&D") for e in _bd_screen(page, i + 1)]
                continue
            if code == "C":
                cscr.append(_c_screen(page, i + 1))
                continue
            if code in MEMO_SCREENS:
                for r in _rows(page)[2:]:
                    toks = [w[4] for w in r]
                    for j, t in enumerate(toks):
                        if _is_amt(t) and ("," in t or "." in t) and _num(t):
                            memo.append(dict(screen=code, kind=MEMO_SCREENS[code], amount=_num(t), page=i + 1,
                                             label=" ".join(x for x in toks[:j] if not _is_amt(x)).strip()))
                continue
            if code in INCOME_SCREENS or code in PAYMENT_SCREENS:
                for r in _rows(page)[2:]:
                    toks = [w[4] for w in r]
                    for j, t in enumerate(toks):
                        if not _is_amt(t) or not ("," in t or "." in t):
                            continue
                        label = " ".join(x for x in toks[:j] if not _is_amt(x)).strip() or lines[0]
                        v = _num(t)
                        if not v or (re.match(r"^(19|20)\d\d\b", label) and not label.startswith(str(year))):
                            continue                               # prior-year information on the screen
                        if code in PAYMENT_SCREENS and code not in INCOME_SCREENS:
                            payments.append(dict(screen=code, kind=PAYMENT_SCREENS[code], label=label, amount=v, page=i + 1))
                        elif INCOME_SCREENS.get(code):
                            entries.append(dict(source="screen", screen=code, label=label, amount=v, cat=INCOME_SCREENS[code],
                                                box="", page=i + 1, under=code))
            continue
        if "Federal Statements" not in lines[:4]:
            continue
        if code in MEMO_SCREENS:
            for r in _rows(page)[2:]:
                toks = [w[4] for w in r]
                for j, t in enumerate(toks):
                    if _is_amt(t) and ("," in t or "." in t) and _num(t):
                        memo.append(dict(screen=code, kind=MEMO_SCREENS[code], amount=_num(t), page=i + 1,
                                         label=" ".join(x for x in toks[:j] if not _is_amt(x)).strip()))
            continue
        if code not in INCOME_SCREENS or code in ("W2", "C"):
            continue                                             # Rent / W-2 box 12 / 4562 / 8829 statements: not income entries
        bd = _bd_sections(page, i + 1)
        if bd:
            entries += [dict(e, under=code) for e in bd]
            continue
        k = lines.index("Federal Statements")
        title = lines[k + 1] if k + 1 < len(lines) else ""
        for e in _statement(page, i + 1, title):
            if e.get("cat"):
                entries.append(dict(e, under=code))
    # a screen value that is the total of a statement on the same screen is not an entry of its own
    stm = {}
    for e in entries:
        if e["source"] == "statement":
            stm.setdefault((e.get("under"), e["cat"]), []).append(e)
    keep = []
    for e in entries:
        if e["source"] == "screen" and e["screen"] != "W2":
            same = stm.get((e.get("under"), e["cat"]))
            if same and (e["screen"] == "B&D" or abs(sum(s["amount"] for s in same) - e["amount"]) <= max(1, len(same))):
                continue
        keep.append(e)
    for n, e in enumerate(keep):
        e["id"] = n
    return dict(file=Path(path).name, path=path, pages=len(doc), year=year, entries=keep, payments=payments, screens=screens,
                memo=memo, rents=[x for x in rents if x["lines"] or x["desc"]], cscreens=[x for x in cscr if x["lines"]])


def looks_like_ut_screens(path: str) -> bool:
    try:
        doc = pymupdf.open(path)
        for page in list(doc)[:3]:
            lines = [l.strip() for l in page.get_text().split("\n") if l.strip()]
            if any(SCREEN_HDR.match(l) for l in lines[:4]):
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


# ---------------------------------------------------------------- 1095-A / 1098-T, Schedule E, Schedule C vs UT
def _close(a, b, tol=TOL):
    return a is not None and b is not None and abs(a - b) <= tol


def _compat(row_cat: str, ut_cat: str) -> bool:
    if row_cat == ut_cat:
        return True
    pairs = {("ira", "pension"), ("pension", "ira")}
    return (row_cat, ut_cat) in pairs


def ut_memo(ut: dict, docs: list) -> list:
    """1095-A / 1098-T amounts vs the UT 1095-A / 8962 and 8863 / 1098-T screens (within $1)."""
    from core.verify import memo_items
    out = []
    for it in memo_items(docs):
        cands = [m for m in ut.get("memo") or [] if m["kind"] == it["kind"]]
        hit = next((m for m in cands if abs(m["amount"] - it["amount"]) <= TOL), None)
        x = dict(it, ut=hit["amount"] if hit else None,
                 ut_ref=f'{hit["screen"]} · {hit["label"]} · p. {hit["page"]}' if hit else "")
        x["status"] = "ok" if hit else ("not entered" if cands else "no screen")
        if not cands:
            x["ut_ref"] = "no " + {"1095a": "1095-A / 8962", "1098t": "8863 / 1098-T", "1099sa": "HSA / 8889"}.get(it["kind"], it["kind"]) + " screen in the print"
        out.append(x)
    return out


def _akey(n) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", str(n or "").lower())
    n = re.sub(r"\b(avenue|ave|street|st|drive|dr|road|rd|place|pl|north|n|south|s|east|e|west|w)\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def _fnum(v):
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def ut_sche(ut: dict, sche: list | None) -> list:
    """Schedule E box (each property, each line) vs the UT Rent screens - line by line, within $1.
    Lines 20 / 21 are not on the screen (UT calculates them; depreciation comes from the asset module)."""
    units = list(ut.get("rents") or [])
    out = []
    for i, p in enumerate(sche or []):
        if p.get("placeholder") or not p.get("calculated"):
            continue
        cyv = {k: _fnum(v) for k, v in (p.get("cy") or {}).items() if _fnum(v) is not None}
        cyv.pop("22", None)
        if "4" in cyv:                                     # UT: one "Rent and royalties" line
            cyv["3"] = cyv.get("3", 0) + cyv.pop("4")
        pk = _akey(p.get("name"))
        hit = next((u for u in units if pk and _akey(u["desc"]) and (_akey(u["desc"]) == pk or _akey(u["desc"]).startswith(pk + " ")
                                                                  or pk.startswith(_akey(u["desc"]) + " "))), None) or \
            next((u for u in units if cyv.get("3") and abs(u["lines"].get("3", 0) - cyv["3"]) <= TOL), None)
        if hit:
            units.remove(hit)
        for k in SCHE_LBL:
            if k == "4":
                continue
            a, b = cyv.get(k), (hit or {}).get("lines", {}).get(k)
            if not a and not b:
                continue
            if k == "18" and a and not b:
                st = "asset module"                     # depreciation is not typed on the Rent screen
            else:
                st = "not entered" if hit is None or b is None else ("ok" if a is not None and abs(a - b) <= TOL else "diff")
            out.append(dict(prop=p.get("name") or "", pi=i, unit=(f'Unit {hit["unit"]} · {hit["desc"]}' if hit else ""),
                            page=(hit or {}).get("page"), line=k, box=a, ut=b, status=st))
    left = []
    for u in units:
        for k, v in u["lines"].items():
            left.append(dict(screen="Rent", label=f'Unit {u["unit"]} · {u["desc"]} · line {k} {SCHE_LBL.get(k, "")}',
                             amount=v, page=u["page"], cat="rental", key=f"rent|{u['unit']}|{k}"))
    return out, left


def ut_schc(ut: dict, schc: list | None) -> tuple:
    """Schedule C box (each business, each line as it stands) vs the UT C screens, line by line, within $1.
    A business with the total only: a note, no check."""
    cs = list(ut.get("cscreens") or [])
    out = []
    for i, b in enumerate(schc or []):
        if not b.get("calculated"):
            continue
        name = b.get("name") or (b.get("pl") or {}).get("company") or f"Business {i + 1}"
        if b.get("total_only") or (b.get("totals") or {}).get("totalOnly"):
            out.append(dict(biz=name, bi=i, line="31", label="Net profit (loss) — total only", box=(b.get("totals") or {}).get("31"),
                            ut=None, status="note", unit="", page=None))
            continue
        fin = b.get("final") or {}
        vals = {k: _fnum(v) for k, v in fin.items() if k not in ("3", "5", "7", "28", "29", "31") and _fnum(v)}
        nk = _akey(name)
        hit = next((c for c in cs if nk and _akey(c["name"]) and (nk in _akey(c["name"]) or _akey(c["name"]) in nk)), None) or \
            next((c for c in cs if vals.get("1") and abs(c["lines"].get("1", 0) - vals["1"]) <= TOL), None)
        if hit:
            cs.remove(hit)
        from core.py_return import SCHC_LINES
        for k in SCHC_LINES:
            a, u = vals.get(k), (hit or {}).get("lines", {}).get(k)
            if not a and not u:
                continue
            if k == "13" and a and not u:
                st = "asset module"
            else:
                st = "not entered" if hit is None or u is None else ("ok" if a is not None and abs(a - u) <= TOL else "diff")
            out.append(dict(biz=name, bi=i, line=k, label=SCHC_LINES[k], box=a, ut=u, status=st, page=(hit or {}).get("page"),
                            unit=(f'Unit {hit["unit"]} · {hit["name"]}' if hit else ("no C screen in the print" if not ut.get("cscreens") else ""))))
    left = []
    for c in cs:
        for k, v in c["lines"].items():
            left.append(dict(screen="C", label=f'Unit {c["unit"]} · {c["name"]} · line {k}', amount=v, page=c["page"], cat="schc",
                             key=f"c|{c['unit']}|{k}"))
    return out, left


# ---------------------------------------------------------------- 1. document verification, 2. UT entries with no document
W2_BOX = {"main": "Box 1 Wages, tips, other compensation", "fit": "Box 2 Federal income tax withheld"}
FAM_BOX = {
    "1099int": {"interest": "Box 1 Interest income", "fit": "Box 4 Federal income tax withheld"},
    "1099oid": {"interest": "Box 1 Original issue discount", "fit": "Box 4 Federal income tax withheld"},
    "1099div": {"dividends": "Box 1a Total ordinary dividends", "fit": "Box 4 Federal income tax withheld"},
    "composite": {"interest": "1099-INT box 1 Interest income", "dividends": "1099-DIV box 1a Total ordinary dividends",
                  "st": "1099-B short-term gain / (loss)", "lt": "1099-B long-term gain / (loss)", "fit": "Federal income tax withheld"},
    "1099b": {"st": "Short-term gain / (loss)", "lt": "Long-term gain / (loss)", "fit": "Box 4 Federal income tax withheld"},
    "1099r": {"ira": "Box 2a Taxable amount", "pension": "Box 2a Taxable amount", "fit": "Box 4 Federal income tax withheld"},
    "ssa": {"ss": "Box 5 Net benefits", "fit": "Box 6 Voluntary federal income tax withheld"},
    "1099misc": {"other": "Box 3 Other income", "rental": "Box 1 Rents / box 2 Royalties", "fit": "Box 4 Federal income tax withheld"},
    "1099nec": {"schc": "Box 1 Nonemployee compensation", "other": "Box 1 Nonemployee compensation"},
    "1099g": {"other": "Box 1 Unemployment / box 2 State refund", "fit": "Box 4 Federal income tax withheld"},
}
# detail boxes read from the document that UT has its own entry for
DETAIL_BOXES = [("div_1b", "div_q", "1099-DIV box 1b Qualified dividends"), ("div_2a", "div_cg", "1099-DIV box 2a Total capital gain distr."),
                ("div_7", "ftax", "1099-DIV box 7 Foreign tax paid")]
B_BOXES = [("proceeds", "proceeds", "1d Proceeds"), ("cost", "cost", "1e Cost or other basis"), ("wash", "adj", "1g Wash sale loss disallowed")]


def _fam_by_file(docs):
    return {d["file"]: d for d in docs}


def doc_verify(inc: dict, docs: list, ut: dict, sche: list | None = None, schc: list | None = None) -> dict:
    """lines: one per box / line - {key, group, doc, box, per_doc, per_prep, ut, ut_ref, status, entry, changed, note, ut_note}
    back:  UT entries with no document (UT income entries, Rent / C screen lines, ...)."""
    byf = _fam_by_file(docs)
    lines = []

    def add(**k):
        k.setdefault("ut", None)
        k.setdefault("ut_ref", "")
        k.setdefault("ut_note", "")
        k.setdefault("note", "")
        k.setdefault("per_doc", None)
        k.setdefault("match", None)
        lines.append(k)
        return k

    done_detail = set()
    for s in inc["sections"]:
        for r in s["rows"]:
            if r.get("excluded") or r.get("memo") or r.get("schc") is not None or r.get("sche") is not None:
                continue
            if "Sch D 13" in str(r.get("box") or ""):
                continue                        # 1099-DIV 2a carried to Schedule D line 13 - checked as box 2a below
            d = byf.get(r.get("file")) or {}
            fam = d.get("family", "")
            names = W2_BOX if fam == "w2" else FAM_BOX.get(fam, {})
            lbl = names.get("main") or names.get(s["key"]) or CAT_LBL.get(s["key"], s["label"].replace("Total ", ""))
            if r.get("box"):
                lbl += f' — Form 8949 box {r["box"]}'
            if r.get("added"):
                lbl = "inventory amount" if r.get("inv") else "line added by preparer"
            grp = CAT_LBL.get(s["key"], s["label"].replace("Total ", ""))
            note = r.get("note") or ""
            if r.get("doc_cy") or r.get("cy"):
                add(key=f'{r["id"]}|main', cat=s["key"], group=grp, doc=r["doc"], file=r.get("file", ""), box=lbl,
                    per_doc=r.get("doc_cy"), per_prep=r.get("cy"), note=note, note_edited=bool(r.get("note_edited")),
                    inv=bool(r.get("inv")), added=bool(r.get("added")))
            if r.get("doc_fit") or r.get("fit"):
                add(key=f'{r["id"]}|fit', cat="fit", group="Federal withholding", doc=r["doc"], file=r.get("file", ""),
                    box=names.get("fit", "Federal income tax withheld"), per_doc=r.get("doc_fit"), per_prep=r.get("fit"),
                    note="", note_edited=False, inv=False, added=bool(r.get("added")))
            # detail boxes - once per document
            p = d.get("parsed") if isinstance(d.get("parsed"), dict) else None
            if not p or r.get("added") or r.get("status") in ("none", "excluded"):
                continue
            det = p.get("detail") or {}
            if s["key"] == "dividends" and r["file"] not in done_detail:
                done_detail.add(r["file"])
                for dk, ck, bl in DETAIL_BOXES:
                    v = det.get(dk)
                    if isinstance(v, (int, float)) and v:
                        add(key=f'{r["id"]}|{dk}', cat=ck, group=CAT_LBL[ck], doc=r["doc"], file=r["file"],
                            box=bl if fam == "composite" else bl.replace("1099-DIV ", ""), per_doc=v, per_prep=v)
            if s["key"] in ("st", "lt") and (r["file"], s["key"]) not in done_detail:
                done_detail.add((r["file"], s["key"]))
                b = det.get(f"b_{s['key']}")
                if isinstance(b, dict):
                    for dk, f, bl in B_BOXES:
                        v = b.get(dk)
                        if isinstance(v, (int, float)) and v:
                            ck = f"{s['key']}_{f}"
                            add(key=f'{r["id"]}|{dk}', cat=ck, group=CAT_LBL[ck], doc=r["doc"].split(" — ST ")[0].split(" — LT ")[0],
                                file=r["file"], box=("ST " if s["key"] == "st" else "LT ") + bl, per_doc=v, per_prep=v)
    # Schedule E: the box vs the Rent screens, each property each line
    se, se_left = ut_sche(ut, sche)
    for x in se:
        add(key=f'sche|{x["prop"]}|{x["line"]}', cat="sche", group="Schedule E", doc=x["prop"], file="",
            box=f'Line {x["line"]} {SCHE_LBL.get(x["line"], "")}', per_doc=None, per_prep=x["box"], ut=x["ut"],
            ut_ref=(f'Rent · {x["unit"]} · p. {x["page"]}' if x["unit"] else ""), fixed=x["status"])
    sc, sc_left = ut_schc(ut, schc)
    for x in sc:
        add(key=f'schc|{x["biz"]}|{x["line"]}', cat="schcl", group="Schedule C", doc=x["biz"], file="",
            box=f'Line {x["line"]} {x["label"]}', per_doc=None, per_prep=x["box"], ut=x["ut"],
            ut_ref=(f'C · {x["unit"]} · p. {x["page"]}' if x.get("page") else x["unit"]), fixed=x["status"])
    for x in ut_memo(ut, docs):
        add(key=f'memo|{x["doc"]}|{x["what"]}', cat="memo", group=x["form"], doc=x["doc"], file=x["doc"], box=x["what"],
            per_doc=x["amount"], per_prep=x["amount"], ut=x["ut"], ut_ref=x["ut_ref"],
            fixed="ok" if x["status"] == "ok" else "not entered")

    # ---- match the document lines to UT entries
    ents = [dict(e, used=False) for e in ut["entries"]]
    live = [l for l in lines if "fixed" not in l and l["per_prep"] not in (None, 0)]

    def take(l, es, amt=None):
        for e in es:
            e["used"] = True
        l["ut"] = amt if amt is not None else sum(e["amount"] for e in es)
        l["ut_ref"] = "; ".join(f'{e["screen"]} · {e["label"]} · p. {e["page"]}' for e in es)
        l["match"] = [e["id"] for e in es]

    # 1) one line = one entry
    for l in live:
        e = next((e for e in ents if not e["used"] and _compat(l["cat"], e["cat"]) and _close(e["amount"], l["per_prep"])), None)
        if e:
            take(l, [e])
    # 2) one line = several UT entries (entered in pieces)
    for l in live:
        if l["match"]:
            continue
        cands = [e for e in ents if not e["used"] and _compat(l["cat"], e["cat"])][:14]
        hit = None
        for n in (2, 3, 4):
            for combo in itertools.combinations(cands, n):
                if abs(sum(e["amount"] for e in combo) - l["per_prep"]) <= n * 1.0 + 0.01:
                    hit = combo
                    break
            if hit:
                break
        if hit:
            take(l, list(hit))
            l["ut_note"] = f"entered in {len(hit)} pieces in UT"
    # 3) several lines = one UT entry (§1256 60/40 split, one payer entered once for two document lines ...)
    for e in ents:
        if e["used"]:
            continue
        cats = ("st", "lt") if e["cat"] in ("cg1256", "st", "lt") else (e["cat"],)
        cands = [l for l in live if not l["match"] and l["cat"] in cats][:12]
        for n in (2, 3, 4):
            combo = next((c for c in itertools.combinations(cands, n)
                          if abs(sum(l["per_prep"] for l in c) - e["amount"]) <= n * 1.0 + 0.01), None)
            if combo:
                for l in combo:
                    take(l, [e], l["per_prep"])
                    l["ut_note"] = f'{e["amount"]:,.0f} entered once on {e["screen"]} for {n} lines here'
                break
    # 4) a line that matches nothing in its own category but an unused entry elsewhere -> entered on another line
    for l in live:
        if l["match"] or l["cat"] not in INCOME_KEYS:
            continue
        e = next((e for e in ents if not e["used"] and e["cat"] in INCOME_KEYS and _close(e["amount"], l["per_prep"])), None)
        if e:
            take(l, [e])
            l["ut_note"] = f'entered as {CAT_LBL.get(e["cat"], e["cat"])} in UT'
            l["wrong"] = True
    boxes = {e["id"]: e.get("box") for e in ents}
    for l in lines:                     # Form 8949 box: the document's box pair "(B/H)" vs the box used in UT
        m = re.search(r"\(([A-L])/([A-L])\)", l["doc"])
        bs = {boxes.get(i) for i in (l["match"] or []) if boxes.get(i)}
        if m and bs - {m.group(1), m.group(2)}:
            l["ut_note"] = (l["ut_note"] + "; " if l["ut_note"] else "") + f"8949 box {'/'.join(sorted(bs))} in UT, document says {m.group(1)}/{m.group(2)}"
            l["wrong"] = True

    # ---- status
    for l in lines:
        doc, prep = l["per_doc"], l["per_prep"]
        l["changed"] = doc is not None and prep is not None and abs(doc - prep) > 0.005 or (doc is not None and prep is None and doc != 0)
        if "fixed" in l:
            l["entry"] = l["fixed"]
            if l["entry"] == "asset module":
                l["ut_note"] = "depreciation comes from the UT asset module"
        elif not prep:
            l["entry"] = "ok" if l["ut"] is None else "diff"
        elif l.get("wrong"):
            l["entry"] = "wrong line"
        else:
            l["entry"] = "ok" if l["match"] else "not entered"
        l["no_comment"] = l["changed"] and not (l.get("note_edited") and (l.get("note") or "").strip())
        l["status"] = ("note" if l["entry"] in ("note", "asset module") else "red" if l["entry"] != "ok"
                       else "amber" if l["changed"] else "ok")
        if l["entry"] == "note":
            l["ut_note"] = "Schedule C total entered directly — not checked against the UT screens"
    back = [dict(e, key=f'ut|{e["screen"]}|{e["page"]}|{e["label"]}|{e["cat"]}|{e["amount"]}') for e in ents if not e["used"]]
    back = [dict(b, what=CAT_LBL.get(b["cat"], b["cat"] or "")) for b in back]
    back += [dict(b, what="Schedule E line") for b in se_left] + [dict(b, what="Schedule C line") for b in sc_left]
    return dict(lines=lines, back=back, payments=ut["payments"],
                n_red=sum(l["status"] == "red" for l in lines), n_back=len(back),
                n_amber=sum(l["changed"] for l in lines), n_nocomment=sum(l["no_comment"] for l in lines))
