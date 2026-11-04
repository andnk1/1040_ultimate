"""parsers.py - read the amounts from the client's documents (2025 column of the income summary).

Each parser returns
    dict(status="read" | "partial" | "none",
         amounts={category: value},           # categories of the income summary
         detail={field: value},                # box-level values (shown in the document table / AI report)
         notes=[...],                          # placed in the Notes column
         checks=[...])                         # failed internal checks -> status "partial"
Categories: w2 interest dividends ira pension ss st lt schc other rental k1

Generic 1099 reader: finds the IRS box number + label (e.g. "1a Total Ordinary Dividends") and takes the first
amount after it. Works for the dot-leader layout (Fidelity / National Financial), the box-per-line layout (Schwab),
and the "1a- Total ordinary dividends" layout (Robinhood / M1 / Apex).
1099-B: "Total Short-term" / "Total Long-term" summary rows, or the per-category rows
("Short-term transactions for which basis is reported to the IRS" ...). Gain must equal proceeds - cost + wash sale.
"""
from __future__ import annotations

import re
from collections import OrderedDict

import pdfplumber

from .pdfutil import open_pdf, page_text

NUM = re.compile(r"(?<![\d/,])(\(?-?\$?\s?[\d,]*\d\.\d{2}\)?)(?![\d/%])")


def _n(s: str) -> float:
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    neg = s.startswith("(") or s.startswith("-")
    v = float(s.strip("()-"))
    return -v if neg else v


def _texts(path, pw=None, maxpages=None):
    doc, pw = open_pdf(path, [pw] if pw else None)
    with doc:
        n = len(doc)
        return [page_text(doc, i) for i in range(n if maxpages is None else min(n, maxpages))], pw


# ---------------------------------------------------------------- 1099 (composite and single forms)
B = r"(?<![\w.$,])"           # start of a box number
FIELDS = OrderedDict([
    ("div_1a", B + r"1a\W{0,6}Total\s+Ordinary\s+Dividends"),
    ("div_1b", B + r"1b\W{0,6}Qualified\s+Dividends"),
    ("div_2a", B + r"2a\W{0,6}Total\s+Capital\s+Gain\s+Distr"),
    ("div_3", B + r"3\W{0,6}Nondividend\s+Distributions"),
    ("div_5", B + r"5\W{0,6}Section\s+199A\s+Dividends"),
    ("div_7", B + r"7\W{0,6}Foreign\s+Tax\s+Paid"),
    ("div_12", B + r"12\W{0,6}Exempt[- ]Interest\s+Dividends"),
    ("int_1", B + r"1\W{0,6}Interest\s+Income"),
    ("int_2", B + r"2\W{0,6}Early\s+Withdrawal\s+Penalty"),
    ("int_3", B + r"3\W{0,6}Interest\s+on\s+U\.?\s?S\.?\s+(Savings\s+Bonds|Treas)"),
    ("int_6", B + r"6\W{0,6}Foreign\s+Tax\s+Paid"),
    ("int_8", B + r"8\W{0,6}Tax[- ]Exempt\s+Interest"),
    ("oid_1", B + r"1\W{0,6}Original\s+Issue\s+Discount"),
    ("misc_2", B + r"2\W{0,6}Royalties"),
    ("misc_3", B + r"3\W{0,6}Other\s+Income"),
    ("misc_8", B + r"8\W{0,6}Substitute\s+Payments"),
    ("s1256_11", B + r"11\W{0,6}Aggregate\s+profit\s+or\s+\(loss\)"),
])
STOP_BEFORE_NUM = re.compile(r"\n\s*\d{1,2}[a-f]?\s*-\s+[A-Z]|\n\s*\d{1,2}[a-f]?\s{2,}[A-Z][a-z]")


def _after(text: str, pos: int, window: int = 260):
    seg = text[pos:pos + window]
    m = NUM.search(seg)
    if not m:
        return None
    # a different box label between the label and the amount -> the amount belongs to that box
    s = STOP_BEFORE_NUM.search(seg[:m.start()])
    if s:
        return None
    return _n(m.group(1))


FIT = re.compile(B + r"4\W{0,6}Federal\s+Income\s+Tax\s+Withheld", re.I)


def _fit(text: str) -> float:
    """Box 4 federal income tax withheld - every form section on the page (DIV, INT, MISC, B, OID, R ...)."""
    tot = 0.0
    for m in FIT.finditer(text):
        # the amount must follow directly (dot leaders, "$", line breaks only) - on 1099-B detail pages
        # the label is just a column header followed by security names
        n = re.match(r"[\s.$]{0,400}?(\(?-?[\d,]*\d\.\d{2}\)?)", text[m.end():m.end() + 420])
        if n and n.group(0)[:n.start(1)].count("\n") <= 3:
            tot += _n(n.group(1))
    return tot


def _fields(text: str) -> dict:
    out = {}
    for k, pat in FIELDS.items():
        m = re.search(pat, text, re.I)
        if m:
            v = _after(text, m.end())
            if v is not None:
                out[k] = v
    return out


B_TOTAL = [("st", r"Total\s+Short[- ]term"), ("lt", r"Total\s+Long[- ]term"), ("und", r"Total\s+Undetermined[- ]term")]
B_ROWS = [("st", r"Short[- ]term\s+transactions\s+for\s+(which\s+basis|covered|noncovered)[^\n]*"),
          ("lt", r"Long[- ]term\s+transactions\s+for\s+(which\s+basis|covered|noncovered)[^\n]*"),
          ("und", r"(Transactions\s+for\s+which\s+basis\s+is\s+not\s+reported\s+to\s+the\s+IRS\s+and\s+Term\s+is\s+Unknown|Undetermined\s+transactions[^\n]*)")]


def _nums_after(text, pos, k=6, window=400):
    seg = text[pos:pos + window]
    return [_n(x) for x in NUM.findall(seg)[:k]]


def _b_summary(text: str) -> dict:
    """{'st': (proceeds, cost, wash, gain), ...} from the 1099-B summary block of one page."""
    res = {}
    for key, pat in B_TOTAL:
        m = re.search(pat, text, re.I)
        if m:
            v = _nums_after(text, m.end(), 5)
            if len(v) >= 5:
                res[key] = dict(proceeds=v[0], cost=v[1], md=v[2], wash=v[3], gain=v[4])
    if res:
        return res
    for key, pat in B_ROWS:
        for m in re.finditer(pat, text, re.I):
            v = _nums_after(text, m.end(), 5)
            if len(v) >= 5:
                r = res.setdefault(key, dict(proceeds=0, cost=0, md=0, wash=0, gain=0))
                for i, f in enumerate(("proceeds", "cost", "md", "wash", "gain")):
                    r[f] += v[i]
    return res


# Schwab-style 1099-B: the overall totals are "Total Short-Term / Long-Term Sales Price of Stocks, Bonds, etc."
# Columns: proceeds | cost | market discount | wash sale | gain ; "--" = empty column (counts as 0)
GRAND_B = [("st", r"Total\s+Short[- ]Term\s+Sales\s+Price\s+of\s+Stocks"), ("lt", r"Total\s+Long[- ]Term\s+Sales\s+Price\s+of\s+Stocks")]
MISSING_B = [("st", r"Total\s+Short[- ]Term\s*\(Cost\s+basis\s+is\s+missing[^)]*\)"),
             ("lt", r"Total\s+Long[- ]Term\s*\(Cost\s+basis\s+is\s+missing[^)]*\)")]
TOK = re.compile(r"\(?-?[\d,]*\d\.\d{2}\)?|(?<![\w-])--(?![\w-])")


def _cols_after(text, pos, k=5, window=320):
    toks = TOK.findall(text[pos:pos + window])[:k]
    return [0.0 if t == "--" else _n(t) for t in toks]


def _grand_b(texts) -> tuple[dict, dict]:
    """({'st': {...}, 'lt': {...}}, {'st': proceeds with missing basis, ...}) from the Sales Price totals, if printed."""
    res, miss = {}, {}
    for t in texts:
        for key, pat in GRAND_B:
            m = re.search(pat, t, re.I)
            if m and key not in res:
                v = _cols_after(t, m.end())
                if len(v) == 5:
                    res[key] = dict(proceeds=v[0], cost=v[1], md=v[2], wash=v[3], gain=v[4])
        for key, pat in MISSING_B:
            m = re.search(pat, t, re.I)
            if m and key not in miss:
                v = _cols_after(t, m.end(), 2)
                if v:
                    miss[key] = v[0]
    return res, miss


# Interactive Brokers-style 1099-B: one "Box / Description / Amount" summary per section
#   "Covered Securities: Short-Term - Summary", "... Long-Term - Summary", "Noncovered Securities - Summary"
# term comes from box 2 (Short-term / Long-term / Not determined); no gain column -> gain = 1d - 1e + 1f + 1g
IB_HEAD = re.compile(r"(?:Non)?covered\s+Securities[^\n]*?-\s*Summary", re.I)
IB_END = re.compile(r"Section\s+1256|Regulated\s+Future|IMPORTANT\s+TAX\s+INFORMATION", re.I)


def _box_val(seg, box, label):
    m = re.search(r"(?<![\w.])" + box + r"\s*\n\s*" + label + r"[^\n]*\n\s*(\(?-?[\d,]*\d\.\d{2}\)?)", seg, re.I)
    return _n(m.group(1)) if m else None


IB_BOXES: list = []


def _ib_b(texts) -> dict:
    IB_BOXES.clear()
    res = {}
    for t in texts:
        heads = list(IB_HEAD.finditer(t))
        for i, h in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(t)
            e = IB_END.search(t, h.end(), end)
            seg = t[h.end(): e.start() if e else end]
            proceeds = _box_val(seg, "1d", r"Proceeds")
            if proceeds is None:
                continue
            tm = re.search(r"Type\s+of\s+gain\s+or\s+loss\s*\n\s*(Short|Long|Not|Undetermined|Unknown)", seg, re.I)
            word = tm.group(1).lower() if tm else h.group(0).lower()
            key = "st" if "short" in word else "lt" if "long" in word else "und"
            cost = _box_val(seg, "1e", r"Cost") or 0.0
            md = _box_val(seg, "1f", r"Accrued\s+market") or 0.0
            wash = _box_val(seg, "1g", r"Wash\s+sale") or 0.0
            r = res.setdefault(key, dict(proceeds=0, cost=0, md=0, wash=0, gain=0))
            for f, v in (("proceeds", proceeds), ("cost", cost), ("md", md), ("wash", wash)):
                r[f] += v
            r["gain"] += proceeds - cost + md + wash
            bx = re.search(r"check\s+box\s+on\s+Form\s+8949\s*\n\s*([A-LX])\b", seg)
            if bx:
                IB_BOXES.append((bx.group(1), proceeds, proceeds - cost + md + wash))
        if res:
            break                          # the summary is printed once; later pages are details
    # drop sections with nothing in them (IB prints all three even when empty)
    return {k: v for k, v in res.items() if any(abs(x) > 0.004 for x in v.values())} or ({"st": res["st"]} if "st" in res else {})


# ---------------------------------------------------------------- Form 8949 box of each 1099-B summary row
BOX_TERM = {**{b: "st" for b in "ABCGHI"}, **{b: "lt" for b in "DEFJKL"}, "X": "und"}
BOX_PATTERNS = [
    # Schwab: "Total Short-Term (Cost basis is reported to the IRS)" | "(Cost basis is missing and not reported ...)"
    (re.compile(r"Total\s+Short[- ]Term\s*\(Cost\s+basis\s+is\s+reported[^)]*\)", re.I), "A", "cols"),
    (re.compile(r"Total\s+Short[- ]Term\s*\(Cost\s+basis\s+is\s+(?:missing|not\s+reported)[^)]*\)", re.I), "B", "cols"),
    (re.compile(r"Total\s+Long[- ]Term\s*\(Cost\s+basis\s+is\s+reported[^)]*\)", re.I), "D", "cols"),
    (re.compile(r"Total\s+Long[- ]Term\s*\(Cost\s+basis\s+is\s+(?:missing|not\s+reported)[^)]*\)", re.I), "E", "cols"),
    # National / Fidelity / M1: "Short-term transactions for which basis is (not) reported" / "for (non)covered tax lots"
    (re.compile(r"Short[- ]term\s+transactions\s+for\s+(?:which\s+basis\s+is\s+reported|covered)[^\n]*", re.I), "A", "nums"),
    (re.compile(r"Short[- ]term\s+transactions\s+for\s+(?:which\s+basis\s+is\s+not\s+reported|noncovered)[^\n]*", re.I), "B", "nums"),
    (re.compile(r"Long[- ]term\s+transactions\s+for\s+(?:which\s+basis\s+is\s+reported|covered)[^\n]*", re.I), "D", "nums"),
    (re.compile(r"Long[- ]term\s+transactions\s+for\s+(?:which\s+basis\s+is\s+not\s+reported|noncovered)[^\n]*", re.I), "E", "nums"),
    # Robinhood: "A (basis reported to the IRS)", "J (cost or other basis reported ...)", "C (Form 1099-B not received)"
    (re.compile(r"(?m)^([A-L])\s+\((?:basis|cost|Form)[^)]*\)"), None, "nums"),
]


def _box_rows(texts) -> list:
    """[(box, proceeds, gain)] - first summary row per box, in the order found."""
    rows, seen = [], set()
    for t in texts:
        for pat, box, how in BOX_PATTERNS:
            for m in pat.finditer(t):
                bx = box or m.group(1)
                if bx in seen:
                    continue
                v = _cols_after(t, m.end(), 5) if how == "cols" else _nums_after(t, m.end(), 5)
                if len(v) < 5:
                    continue
                seen.add(bx)
                rows.append((bx, v[0], v[4]))
    return rows


def _pick_boxes(rows, b: dict) -> dict:
    """{'st': [(box, gain, proceeds)], 'lt': [...]} - only when the box rows add up to the term's total gain."""
    out = {}
    for term in ("st", "lt", "und"):
        tot = (b.get(term) or {}).get("gain")
        if tot is None:
            continue
        mine = [(bx, g, pr) for bx, pr, g in rows if BOX_TERM.get(bx) == term]
        for grp in (mine, [r for r in mine if r[0] in "ABCDEFX"], [r for r in mine if r[0] in "GHIJKL"]):
            if grp and abs(sum(g for _, g, _ in grp) - tot) <= 1.0:
                out[term] = [r for r in grp if abs(r[1]) > 0.004 or abs(r[2]) > 0.004] or grp[:1]
                break
    return out


MARGIN = re.compile(r"Margin\s+Interest\s+Paid\s*\n?\s*\$?\s*([\d,]*\d\.\d{2})", re.I)


def parse_1099(path, pw=None, maxpages=12) -> dict:
    texts, _ = _texts(path, pw, maxpages)
    found, bsum, seen, fit = {}, {}, [], 0.0
    for t in texts:
        # form / summary pages only - detail pages repeat box labels as column headers
        if not re.search(r"OMB\s*No|Copy\s*B|Summary\s+Information|Tax\s+Summary|Summary\s+of", t, re.I):
            continue
        f = _fields(t)
        b = _b_summary(t) if re.search(r"Short[- ]term|Long[- ]term", t, re.I) and re.search(r"Proceeds", t, re.I) else {}
        sig = (tuple(sorted(f.items())), tuple(sorted((k, tuple(sorted(v.items()))) for k, v in b.items())))
        if (f or b) and sig in seen:
            continue                     # same form printed twice (copies)
        seen.append(sig)
        fit += _fit(t)
        for k, v in f.items():
            found[k] = found.get(k, 0) + v
        for k, v in b.items():
            r = bsum.setdefault(k, dict(proceeds=0, cost=0, md=0, wash=0, gain=0))
            for f2 in r:
                r[f2] += v.get(f2, 0)
    all_texts, _ = _texts(path, pw, None) if maxpages else (texts, None)
    grand, missing = _grand_b(all_texts)
    if grand:
        bsum = grand                      # Schwab: the overall Sales Price totals replace the per-category rows
    elif not bsum:
        bsum = _ib_b(all_texts)           # Interactive Brokers: box-by-box section summaries
    rows = [(bx, pr, g) for bx, pr, g in IB_BOXES] if bsum and IB_BOXES else _box_rows(all_texts)
    IB_BOXES.clear()
    res = _amounts_1099(found, bsum, " ".join(texts), missing, _pick_boxes(rows, bsum))
    res["fit"] = round(fit, 2)
    mm = MARGIN.search(" \n".join(all_texts))
    if mm and _n(mm.group(1)):
        res["notes"].append(f"Margin interest paid {_n(mm.group(1)):,.2f} (investment interest expense — Form 4952 / Schedule A; not income)")
    return res


def _amounts_1099(f: dict, b: dict, text: str, missing: dict | None = None, boxes: dict | None = None) -> dict:
    notes, checks = [], []
    a = {}
    up = text.upper()
    # a form section is "printed" when its header is there (not just named in an intro / table of contents)
    has = {x: bool(re.search(r"(FORM\s*" + x + r"\b|20\d\d\s+" + x + r"\b)", up)) for x in ("1099-DIV", "1099-INT", "1099-B", "1099-MISC", "1099-OID")}
    interest = f.get("int_1", 0) + f.get("int_3", 0) + f.get("oid_1", 0)
    if any(k in f for k in ("int_1", "int_3", "oid_1")):
        a["interest"] = interest
    if f.get("int_3"):
        notes.append(f"Interest includes US savings bonds / Treasury {f['int_3']:,.2f} (box 3 — state-exempt)")
    if "div_1a" in f:
        a["dividends"] = f["div_1a"]
        if f.get("div_1b"):
            notes.append(f"Qualified dividends {f['div_1b']:,.2f}")
        if f.get("div_1b", 0) > f["div_1a"] + 0.01:
            checks.append("1b qualified dividends is more than 1a")
    st = b.get("st", {}).get("gain")
    lt = b.get("lt", {}).get("gain")
    missing = missing or {}
    for k, r in b.items():
        term = {"st": "ST", "lt": "LT", "und": "Undetermined"}.get(k, k)
        nob = missing.get(k, 0)           # proceeds of lots with no cost basis: no gain is reported for them
        calc = r["proceeds"] - nob - r["cost"] + r["wash"] + r["md"]
        if abs(calc - r["gain"]) > 1.0 and abs(r["proceeds"] - nob - r["cost"] + r["wash"] - r["gain"]) > 1.0:
            checks.append(f"1099-B {term}: gain {r['gain']:,.2f} ≠ proceeds − cost + wash ({calc:,.2f})")
        if r.get("wash"):
            notes.append(f"{term}: wash sale loss disallowed {r['wash']:,.2f} (already added back in the gain)")
        if nob:
            notes.append(f"{term}: proceeds {nob:,.2f} with cost basis missing — no gain/loss reported for them; get the basis")
    if st is not None:
        a["st"] = st
    if lt is not None:
        a["lt"] = lt
    if f.get("div_2a"):
        a["lt"] = a.get("lt", 0) + f["div_2a"]
        notes.append(f"LT includes capital gain distributions {f['div_2a']:,.2f} (1099-DIV 2a → Sch D line 13)")
    if f.get("s1256_11"):
        v = f["s1256_11"]
        a["lt"] = a.get("lt", 0) + 0.6 * v
        a["st"] = a.get("st", 0) + 0.4 * v
        notes.append(f"§1256 contracts {v:,.2f} split 60% LT / 40% ST (Form 6781)")
    und = b.get("und", {}).get("gain")
    if und:
        a["st"] = a.get("st", 0) + und
        notes.append(f"ST includes {und:,.2f} noncovered / term not determined (treated as short-term) — confirm holding period and basis")
    if f.get("misc_3") or f.get("misc_8"):
        a["other"] = f.get("misc_3", 0) + f.get("misc_8", 0)
        if f.get("misc_8"):
            notes.append(f"Other income includes substitute payments {f['misc_8']:,.2f} (1099-MISC 8)")
    if f.get("misc_2"):
        a["rental"] = f["misc_2"]
        notes.append(f"Royalties {f['misc_2']:,.2f} (1099-MISC 2) → Schedule E")
    if f.get("int_8") or f.get("div_12"):
        notes.append(f"Tax-exempt interest {f.get('int_8', 0) + f.get('div_12', 0):,.2f} (memo — not in total)")
    if f.get("div_3"):
        notes.append(f"Nondividend distributions {f['div_3']:,.2f} (basis reduction — memo)")
    ft = f.get("div_7", 0) + f.get("int_6", 0)
    if ft:
        notes.append(f"Foreign tax paid {ft:,.2f} (Form 1116 / direct credit)")
    # sections printed but not read
    missing = []
    if has["1099-DIV"] and "div_1a" not in f:
        missing.append("1099-DIV")
    if has["1099-INT"] and "int_1" not in f:
        missing.append("1099-INT")
    if has["1099-B"] and not b and "PROCEEDS" in up:
        missing.append("1099-B summary")
    if missing:
        checks.append("not read: " + ", ".join(missing))
    status = "none" if not a and not f else ("partial" if checks else "read")
    # one income-summary row per Form 8949 box (plus capital gain distributions / §1256)
    boxes = boxes or {}
    parts = {}
    for term in ("st", "lt"):
        if term not in a:
            continue
        pl = []
        if term in b:
            if boxes.get(term):
                pl += [(f"({bx})", g) for bx, g, _ in boxes[term]]
            else:
                pl.append(("", b[term]["gain"]))
        if term == "st" and b.get("und", {}).get("gain"):
            pl += [(f"({bx}) term unknown", g) for bx, g, _ in boxes["und"]] if boxes.get("und") else [("term unknown", b["und"]["gain"])]
        if term == "lt" and f.get("div_2a"):
            pl.append(("Sch D 13 cap gain distr.", f["div_2a"]))
        if f.get("s1256_11"):
            pl.append(("6781 §1256 " + ("40%" if term == "st" else "60%"), (0.4 if term == "st" else 0.6) * f["s1256_11"]))
        if pl and abs(sum(v for _, v in pl) - a[term]) <= 1.0:
            parts[term] = pl
    return dict(status=status, amounts=a, detail=dict(f, **{f"b_{k}": v for k, v in b.items()}), notes=notes, checks=checks,
                parts=parts)


# ---------------------------------------------------------------- W-2
# W-2 boxes by their IRS names (Form W-2): only amounts under / beside these labels are read - payroll summaries
# ("Gross Wages", "Taxable Wages", "Box 1 of W-2" ...) are ignored.
W2_BOXES = [("1", r"Wages,?\s*tips"), ("2", r"Federal\s+income\s+tax\s+withheld"), ("3", r"Social\s+security\s+wages"),
            ("4", r"Social\s+security\s+tax\s+withheld"), ("5", r"Medicare\s+wages"), ("6", r"Medicare\s+tax\s+withheld"),
            ("16", r"State\s+wages"), ("17", r"State\s+income\s+tax")]
W2_AMT = re.compile(r"^\$?-?[\d,]*\d\.\d\d$")
# the other boxes (2026-11-01, ADP "W-2 and Earnings Summary" + the IRS layout): box letter / number + IRS box name; the value is
# read from the box's cell = below the label down to the next box label in that column (box 14: also right of the label)
W2_MORE = [("a", r"Employee.?s\s+(social\s+security|SSA|SSN|soc)"), ("b", r"Employer(.?s)?\s+(identification|FED|federal|ID\b|EIN)"),
           ("c", r"Employer.?s\s+name"), ("d", r"Control\s+number"), ("e", r"Employee.?s\s+(first\s+)?name"),
           ("f", r"Employee.?s\s+address"), ("7", r"Social\s+security\s+tips"), ("8", r"Allocated\s+tips"),
           ("10", r"Dependent\s+care"), ("11", r"Non\s*-?\s*qualified"), ("13", r"Stat"), ("14", r"Other"),
           ("15", r"State\b(?!\s+(wages|income))"), ("18", r"Local\s+wages"), ("19", r"Local\s+income\s+tax"), ("20", r"Locality")]
W2_MARK = {"X", "x", "✓", "✔", "☒", "☑"}


def _w2_labels(words) -> list[dict]:
    """Every box label on the page (box letter / number + its IRS name): {box, x, y, x1, words}. Boxes 12a-d count as labels too
    (they are the edges of the cells beside them)."""
    out = []
    for n in words:
        m = re.fullmatch(r"(?i)(e/f|[a-f]|\d{1,2}[a-d]?)(.*)", n[4])
        if not m:
            continue
        box, glued = m.group(1).lower(), m.group(2)
        row = sorted([w for w in words if w is not n and abs(w[1] - n[1]) < 4 and w[0] > n[2] - 1], key=lambda w: w[0])
        seq, last = [], n[2]
        for w in row:
            if w[0] - last > 12 or W2_AMT.match(w[4]) or re.fullmatch(r"\d{1,2}[a-d]?", w[4]):   # an amount / the next box
                break
            seq.append(w)
            last = w[2]
        txt = (glued + " " + " ".join(w[4] for w in seq)).strip()
        name = "12" if re.fullmatch(r"12[a-d]", box) else None
        box = "e" if box == "e/f" else box
        for b, pat in W2_BOXES + W2_MORE:
            if name is None and b == box and txt and re.match(pat, txt, re.I):
                name = b
        if name:
            out.append(dict(box=name, x=n[0], y=n[1], x1=seq[-1][2] if seq else n[2], h=max(n[3] - n[1], 3), words=[n] + seq))
    # boxes a-f printed without their letter ("Employer's name, address, and ZIP code" - the IRS blank as payroll services print
    # it): the IRS name at the start of a phrase (no word just before it on the row); only for boxes not found with their letter
    have = {l["box"] for l in out}
    for n in words:
        if not re.match(r"(?i)(Employ|Control)", n[4]):
            continue
        if any(w is not n and abs(w[1] - n[1]) < 4 and -1 <= n[0] - w[2] < 12 for w in words):
            continue
        row = sorted([w for w in words if abs(w[1] - n[1]) < 4 and w[0] >= n[0]], key=lambda w: w[0])
        seq, last = [], n[0]
        for w in row:
            if w[0] - last > 12 or W2_AMT.match(w[4]) or (seq and re.fullmatch(r"\d{1,2}[a-d]?", w[4])):   # an amount / the next box
                break
            seq.append(w)
            last = w[2]
        txt = " ".join(w[4] for w in seq)
        b = next((b for b, pat in W2_MORE if b in "abcdef" and re.match(pat, txt, re.I)), None)
        if b and b not in have:
            out.append(dict(box=b, x=n[0], y=n[1], x1=seq[-1][2], h=max(n[3] - n[1], 3), words=seq, bare=True))
    return out


def _w2_cell(words, lab, labs, x1, y1, same_row=False) -> list[list]:
    """The lines (words sorted by x) in a label's box: right edge = the next label on its row (else the copy's edge), bottom =
    the next label below it in its column."""
    bot = min([l["y"] for l in labs if l["y"] > lab["y"] + 5 and -12 <= l["x"] - lab["x"] < 60] + [y1, lab["y"] + 80])
    right = min([l["x"] for l in labs if l is not lab and lab["y"] - 6 < l["y"] < bot - 4 and l["x"] > lab["x1"] - 2] + [x1])
    bot = min([l["y"] for l in labs if l["y"] > lab["y"] + 5 and lab["x"] - 12 <= l["x"] < right - 2] + [bot])
    skip = {id(w) for l in labs for w in l["words"]}
    right = right - 6 if right < x1 else right               # amounts end at the next box's label: they start a little left of it
    ws = [w for w in words if id(w) not in skip and lab["x"] - 8 <= w[0] < right
          and ((same_row and abs(w[1] - lab["y"]) < 4 and w[0] >= lab["x1"]) or lab["y"] + 3 < w[1] < bot - 4)]
    out, last = [], lab["y"]
    for ln in _rows(ws):                                     # the box ends at a gap of 5+ label heights (text printed under the form)
        if ln[0][1] - last > 5 * lab["h"]:
            break
        out.append(ln)
        last = ln[0][1]
    return out


def _w2_more(words, labs, x0, x1, y0, y1) -> dict:
    """Boxes a-f, 7, 8, 10, 11, 13, 14, 15-20 of one W-2 copy (its area: x0-x1, y0-y1)."""
    labs = [l for l in labs if x0 <= l["x"] < x1 and y0 <= l["y"] < y1]
    def first(b):                                            # the top one; on the same row (within 4pt) the leftmost
        ls = [l for l in labs if l["box"] == b]
        top = min((l["y"] for l in ls), default=None)
        return min((l for l in ls if l["y"] - top < 4), key=lambda l: l["x"], default=None)
    cell = lambda l, same=False: _w2_cell(words, l, labs, x1, y1, same) if l else []
    text = lambda ln: " ".join(w[4] for w in ln if not W2_AMT.match(w[4])).strip()        # text boxes: amounts left out
    amt = lambda ln: next((_n(w[4].lstrip("$")) for w in ln if W2_AMT.match(w[4])), None)
    out = {}
    lines = [text(ln) for ln in cell(first("a"))]
    m = re.search(r"[\dX*•]{3}-?[\dX*•]{2}-?\d{4}", " ".join(lines))
    if m:
        out["ssn"] = m.group(0)
    m = re.search(r"\b\d{2}-\d{7}\b", " ".join(text(ln) for ln in cell(first("b"))))
    if m:
        out["ein"] = m.group(0)
    lines = [t for t in (text(ln) for ln in cell(first("c"))) if t and not re.search(r"(?i)\bbatch\s*#", t)]
    if lines:
        k = next((i for i, t in enumerate(lines) if i and re.match(r"(?i)(\d|P\.?\s?O\.?\s+BOX)", t)), len(lines))
        out["er"] = " ".join(lines[:k])
        if lines[k:]:
            out["er_addr"] = ", ".join(lines[k:])
    lines = [text(ln) for ln in cell(first("d"))[:2]]
    if any(lines):
        out["ctl"] = " ".join(t for t in lines if t)
    lines = [t for t in (text(ln) for ln in cell(first("e"))) if t]
    if lines:
        out["ee"] = lines[0]
    addr = lines[1:] or [t for t in (text(ln) for ln in cell(first("f"))) if t]
    if addr:
        out["ee_addr"] = ", ".join(addr)
    for b in ("7", "8", "10", "11"):
        v = next((amt(ln) for ln in cell(first(b)) if amt(ln) is not None), None)
        if v is not None:
            out[b] = v
    l13 = first("13")
    if l13:                                                  # an X under Stat emp / Ret. plan / 3rd party sick pay, by position
        right = min([l["x"] for l in labs if l is not l13 and abs(l["y"] - l13["y"]) < 6 and l["x"] > l13["x1"] - 2] + [x1])
        heads = []
        for w in words:
            if abs(w[1] - l13["y"]) < 12 and l13["x"] <= w[0] < right:
                for key, pat in (("stat", r"stat"), ("ret", r"ret"), ("sick", r"3rd|third")):
                    i = re.search(pat, w[4], re.I)
                    if i:
                        heads.append((w[0] + (w[2] - w[0]) * i.start() / max(len(w[4]), 1), key))
        heads = sorted({k: x for x, k in sorted(heads, reverse=True)}.items(), key=lambda kv: kv[1])
        out["13"] = dict(stat=False, ret=False, sick=False)
        for w in words:
            if w[4] in W2_MARK and l13["y"] + 3 < w[1] < l13["y"] + 30 and l13["x"] - 4 <= w[0] < right and heads:
                cx = (w[0] + w[2]) / 2
                out["13"][next((k for k, x in reversed(heads) if x <= cx + 2), heads[0][0])] = True
    items, pend = [], None
    for ln in cell(first("14"), True):                       # "35000.00 401A-TAX" (ADP: amount first) or "NY SDI 123.45"
        a = amt(ln)
        lab = " ".join(w[4] for w in ln if not W2_AMT.match(w[4])).strip()
        if a is None:
            pend = lab or pend
            continue
        items.append(((lab or pend or "Other"), a))
        pend = None
    if items:
        out["14"] = items
    # 15-17 / 18-20: one row per line with an amount (the i-th line of each box); text lines past them are the copy's footer
    amts = lambda b: [a for a in (amt(ln) for ln in cell(first(b))) if a is not None]
    w16, t17 = amts("16"), amts("17")
    st = [text(ln) for ln in cell(first("15"))]
    st = [s for s in st if re.match(r"[A-Z]{2}\b", s)] or (st if w16 or t17 else [])
    st = st[:max(len(w16), len(t17), 1)]
    states = []
    for i in range(max(len(st), len(w16), len(t17))):
        s = st[i] if i < len(st) else ""
        m = re.match(r"([A-Z]{2})\b\s*(.*)", s)
        row = dict(st=m.group(1) if m else None, id=(m.group(2) if m else s) or None,
                   w=w16[i] if i < len(w16) else None, t=t17[i] if i < len(t17) else None)
        if any(v is not None for v in row.values()):
            states.append(row)
    if states:
        out["states"] = states
    w18, t19 = amts("18"), amts("19")
    loc = [text(ln) for ln in cell(first("20"))][:max(len(w18), len(t19))]       # a locality without amounts: not kept
    locs = []
    for i in range(max(len(loc), len(w18), len(t19))):
        row = dict(name=(loc[i] if i < len(loc) else "").replace(":", " ") or None,
                   w=w18[i] if i < len(w18) else None, t=t19[i] if i < len(t19) else None)
        if any(v is not None for v in row.values()):
            locs.append(row)
    if locs:
        out["locals"] = locs
    return out


def _w2_page(page) -> list[dict]:
    """One page -> every W-2 copy on it: [{box: amount}], box 12 codes in '12'."""
    words = page.get_text("words")
    lines = {}
    for w in words:
        lines.setdefault((w[5], w[6]), []).append(w)
    labels = []
    for ws in lines.values():
        ws.sort(key=lambda w: w[0])
        txt = " ".join(w[4] for w in ws)
        for box, pat in W2_BOXES:
            if re.match(r"^\s*(?:box\s*)?" + box + r"[.:\-]?\s+" + pat, txt, re.I):
                labels.append(dict(box=box, x=ws[0][0], y=ws[0][1], x1=ws[-1][2]))
                break
        if re.match(r"^\s*(?:box\s*)?12[a-d]?\b", txt, re.I) and re.search(r"instructions|code|12", txt, re.I):
            labels.append(dict(box="12", x=ws[0][0], y=ws[0][1], x1=ws[-1][2]))
    # box number and box name as separate text pieces on the same row (ADP and other payroll layouts): "1" + "Wages, tips ..."
    have = {(l["box"], round(l["x"]), round(l["y"])) for l in labels}
    for n in words:
        if not re.fullmatch(r"\d{1,2}", n[4]):
            continue
        row = sorted([w for w in words if abs(w[1] - n[1]) < 3 and w[0] > n[2] - 1], key=lambda w: w[0])
        seq, last = [], n[2]
        for w in row:
            if w[0] - last > 12:
                break
            seq.append(w)
            last = w[2]
        if not seq or seq[0][0] - n[2] > 12:
            continue
        txt = " ".join(w[4] for w in seq)
        for box, pat in W2_BOXES:
            if n[4] == box and re.match(pat, txt, re.I) and (box, round(n[0]), round(n[1])) not in have:
                labels.append(dict(box=box, x=n[0], y=n[1], x1=seq[-1][2]))
                break
    if not any(l["box"] == "1" for l in labels):
        return []
    amts = [w for w in words if W2_AMT.match(w[4])]
    used, vals = set(), []
    # a copy = one "1 Wages" label; its boxes are the labels between it and the next copy's "1 Wages"
    # copies side by side on the same row (payroll prints: 3-4 copies per page) are split by x as well
    ones = sorted([l for l in labels if l["box"] == "1"], key=lambda l: (l["y"], l["x"]))
    more = _w2_labels(words)
    rows_y = sorted({o["y"] for o in ones})
    rows_y = [y for i, y in enumerate(rows_y) if not i or y - rows_y[i - 1] > 4]
    for k, one in enumerate(ones):
        y0 = one["y"] - 5
        y1 = min([o["y"] - 5 for o in ones if o["y"] > one["y"] + 4] or [1e9])
        x0 = one["x"] - 5
        x1 = min([o["x"] - 5 for o in ones if abs(o["y"] - one["y"]) <= 4 and o["x"] > one["x"] + 4] or [1e9])
        # box 12 labels: the IRS blank prints "12a" a little left of the "1" label - one that close to the next copy's "1" is that copy's
        others = [o for o in ones if o is not one and abs(o["y"] - one["y"]) <= 4]
        mine = [l for l in labels if y0 <= l["y"] < y1 and (x0 <= l["x"] < x1 if l["box"] != "12" else
                (x0 - 40 <= l["x"] < x1 and not any(0 < o["x"] - l["x"] <= 40 for o in others)))]
        amts_all = amts
        amts = [a for a in amts_all if x0 - 15 <= a[0] < x1 - 15]
        out = {}
        for l in sorted(mine, key=lambda l: (l["y"], l["x"])):
            if l["box"] == "12":
                codes = [w for w in words if re.fullmatch(r"[A-HJ-NP-Z]{1,2}", w[4]) and 0 < w[1] - l["y"] < 60 and w[1] < y1 and -10 < w[0] - l["x"] < 160]
                # the word "Code" printed one letter per line (IRS blank): its "C" is not a code
                codes = [c for c in codes if not any(o[4] in ("o", "O") and abs(o[0] - c[0]) < 2 and 0 < o[1] - c[1] < 6 for o in words)]
                for c in codes:
                    a = next((a for a in amts if abs(a[1] - c[1]) < 4 and a[0] > c[0] and id(a) not in used), None)
                    if a:
                        used.add(id(a))
                        out.setdefault("12", []).append((c[4], _n(a[4].lstrip("$"))))
                continue
            # the amount: on the label's row to the right, else the first one below it in the label's column
            right = [a for a in amts if id(a) not in used and abs(a[1] - l["y"]) < 4 and a[0] > l["x1"] - 2]
            nxt = min([m["y"] for m in more if m["y"] > l["y"] + 5 and abs(m["x"] - l["x"]) < 40] + [y1])   # not past the next box
            below = [a for a in amts if id(a) not in used and 0 < a[1] - l["y"] < 60 and a[1] < nxt and -15 < a[0] - l["x"] < 150]
            peers = [m for m in mine if m is not l and abs(m["y"] - l["y"]) < 4]          # labels side by side on the same row
            below = [a for a in below if all(abs(a[0] - l["x"]) <= abs(a[0] - m["x"]) + 3 for m in peers)]   # +3: halfway ties
            cand = sorted(right, key=lambda a: a[0])[:1] or sorted(below, key=lambda a: (a[1], abs(a[0] - l["x"])))[:1]
            if cand and l["box"] not in out:
                used.add(id(cand[0]))
                out[l["box"]] = _n(cand[0][4].lstrip("$"))
        # the other boxes: the copy's whole area - its column (to the next copy on the row, else past box 2 / 4 / 6) and its
        # band of rows (ADP prints c / d / e above box 1 on the reference copy, below it on the filing copies)
        peers = sorted([o for o in ones if abs(o["y"] - one["y"]) <= 4], key=lambda o: o["x"])
        i = peers.index(one)
        r = next(j for j, y in enumerate(rows_y) if abs(y - one["y"]) <= 4)
        ey0 = rows_y[r] - 5 if r else 0
        ey1 = rows_y[r + 1] - 5 if r + 1 < len(rows_y) else 1e9
        # where a copy starts: its leftmost box label (the IRS blank prints boxes a-f and 7-11 left of box 1), else its box 1;
        # only labels past the copy before it (right of its box 2 / 4 / 6 column)
        def bound(j):
            prev = max([l["x1"] for l in labels if l["box"] in ("2", "4", "6") and ey0 <= l["y"] < ey1
                        and peers[j - 1]["x"] <= l["x"] < peers[j]["x"]] + [peers[j - 1]["x"] + 40])
            return min([l["x"] for l in more if ey0 <= l["y"] < ey1 and prev < l["x"] < peers[j]["x"]] + [peers[j]["x"]]) - 5
        ex0 = bound(i) if i else 0
        edge = [l["x1"] + 8 for l in mine if l["box"] in ("2", "4", "6")]
        ex1 = bound(i + 1) if i + 1 < len(peers) else (x1 if x1 < 1e9 else (max(edge) if edge else 1e9))
        for b, v in _w2_more(words, more, ex0, ex1, ey0, ey1).items():
            out.setdefault(b, v)
        # 16 / 17 = the state rows (one row per state, read box by box); the first-amount-below read can reach text under the form
        for b, k in (("16", "w"), ("17", "t")):
            vs = [s[k] for s in out.get("states") or [] if s.get(k) is not None]
            if vs:
                out[b] = round(sum(vs), 2)
            else:
                out.pop(b, None)
        if out.get("1") is None:
            out.pop("1", None)
            if (out.get("12") or out.get("14")) and not any(out.get(b) for b in ("2", "3", "4", "5", "6", "16", "17")):
                out["overflow"] = True                       # "ADDITIONAL W-2 FOR BOX 12 OR 14 OVERFLOW" (ADP): no box 1
                vals.append(out)
        else:
            vals.append(out)
        amts = amts_all
    return vals


def parse_w2(path, pw=None) -> dict:
    """W-2 by its IRS box names only. Copies B / C / 2 with the same amounts count once; different W-2s add up."""
    doc, pw = open_pdf(path, [pw] if pw else None)
    forms = []
    key = lambda f: (f.get("1"), f.get("2"), f.get("3"), f.get("5"))
    with doc:
        for page in doc:
            got = _w2_page(page)
            for f in [f for f in got if not f.get("overflow")]:
                same = next((g for g in forms if key(g) == key(f)), None)
                if same is None:
                    forms.append(f)
                else:                                        # another copy of the same W-2: fills boxes the first copy missed
                    full = lambda rows: sum(v is not None for r in rows or [] for v in r.values())
                    for b, v in f.items():
                        if b in ("states", "locals") and full(v) > full(same.get(b)):
                            same[b] = v
                        else:
                            same.setdefault(b, v)
            over = next((f for f in got if f.get("overflow")), None)     # the copies on an overflow page are alike: one is enough
            if over and forms:                               # -> the W-2 before it with the same EIN / SSN, else the last one
                to = next((g for g in reversed(forms) if g.get("ein") == over.get("ein") and g.get("ssn") == over.get("ssn")), forms[-1])
                for b in ("12", "14"):
                    for item in over.get(b) or []:
                        if item not in (to.get(b) or []):
                            to.setdefault(b, []).append(item)
    if not forms:                                            # list layout: "1 Wages, tips, other compensation ..... 1,234.56"
        for f in _list_boxes(path, W2_BOXES, pw):
            g = {k: _lnum(v) for k, v in f.items() if _lnum(v) is not None}
            key = (g.get("1"), g.get("2"), g.get("3"), g.get("5"))
            if g.get("1") is not None and all(key != (x.get("1"), x.get("2"), x.get("3"), x.get("5")) for x in forms):
                forms.append(g)
    if not forms:
        return dict(status="none", amounts={}, detail={}, notes=[],
                    checks=["W-2 box 1 (Wages, tips, other compensation) not found with its IRS box name — enter it by hand"])
    if len(forms) == 1 and not forms[0].get("12"):          # list layout box 12: "12a D ........ 2,567.90"
        doc2, _ = open_pdf(path, [pw] if pw else None)
        with doc2:
            for i in range(min(len(doc2), 4)):
                for ws in _rows(doc2[i].get_text("words")):
                    m = re.match(r"^(?:Box\s*)?12[a-d]?[.:)\-]?\s+(?:Code\s+)?([A-HJ-NP-Z]{1,2})\b[\s.:_-]*\$?([\d,]*\d\.\d\d)$",
                                 " ".join(w[4] for w in ws).strip())
                    if m and (m.group(1), _n(m.group(2))) not in (forms[0].get("12") or []):
                        forms[0].setdefault("12", []).append((m.group(1), _n(m.group(2))))
    tot = sum(f["1"] for f in forms)
    wh = sum(f.get("2") or 0 for f in forms)
    notes = [f"{len(forms)} different W-2s in this file"] if len(forms) > 1 else []
    for f in forms:
        for code, v in f.get("12") or []:
            notes.append(f"Box 12 {code} {v:,.2f}" + (" (employer health coverage — not taxable)" if code == "DD" else ""))
    return dict(status="read", amounts=dict(w2=tot), detail=dict(w2=[(f["1"], f.get("2")) for f in forms], boxes=forms), notes=notes,
                checks=[], fit=round(wh, 2))


# ---------------------------------------------------------------- Koinly (IRS forms) / 1099-DA
KOINLY_LINE_BOX = {"1a": "A/G", "1b": "A/G", "2": "B/H", "3": "C/I", "8a": "D/J", "8b": "D/J", "9": "E/K", "10": "F/L"}


def koinly_8949_group(path, pw=None):
    """'da' when the Koinly 8949 checks a 1099-DA box (G-L), 'b' for A-F, None if no box is marked."""
    doc, _ = open_pdf(path, [pw] if pw else None)
    with doc:
        for page in doc:
            ws = page.get_text("words")
            boxes = [(w[1], w[4][1]) for w in ws if re.fullmatch(r"\([A-L]\)", w[4])]
            for w in ws:
                if w[4] in ("X", "x", "✓", "✔") and w[0] < 0.15 * page.rect.width:
                    hit = [b for y, b in boxes if abs(y - w[1]) < 4]
                    if hit:
                        return "da" if hit[0] in "GHIJKL" else "b"
    return None


NUM_RE = r"\(?-?[\d,]+\.\d{1,2}\)?"


def _sched_d(pg) -> dict:
    """Schedule D read like a 1099-B: one row per Form 8949 box, from the lines that carry 1099-B / 1099-DA sales only -
    1a / 1b, 2, 3 (short-term) and 8a / 8b, 9, 10 (long-term). Lines 4-6 and 11-14 come from other documents (K-1s, carryovers,
    capital gain distributions) and the totals 7 / 15 are not lines - both left out. Columns (d) proceeds, (e) cost,
    (g) adjustments, (h) gain by the column headers."""
    W = pg.width
    ws = pg.extract_words()
    heads = {}
    for w in ws:
        if w["text"] in ("(d)", "(e)", "(g)", "(h)") and w["text"] not in heads:
            heads[w["text"]] = (w["x0"] + w["x1"]) / 2
    lbl = [w for w in ws if w["x0"] < 0.1 * W and w["text"] in KOINLY_LINE_BOX]
    nums = [w for w in ws if w["x0"] > 0.4 * W and re.fullmatch(NUM_RE, w["text"])]
    val = lambda t: _n(t if "." in t else t + ".00")
    lines, parts, notes, checks, pn = [], {"st": [], "lt": []}, [], [], {}
    m = lambda v: f"({abs(v):,.2f})" if v < 0 else f"{v:,.2f}"
    for x in lbl:
        row = [w for w in nums if 0 <= w["top"] - x["top"] < 16]
        if not row:
            continue
        col = {}
        for w in row:
            c = min(heads, key=lambda h: abs(heads[h] - (w["x0"] + w["x1"]) / 2)) if heads else "(h)"
            if not heads and w is not max(row, key=lambda w: w["x1"]):
                continue
            col[c] = val(w["text"])
        d, e, g, h = (col.get(k) for k in ("(d)", "(e)", "(g)", "(h)"))
        if h is None and d is not None and e is not None:
            h = round(d - e + (g or 0), 2)
        if h is None:
            continue
        term = "st" if x["text"] in ("1a", "1b", "2", "3") else "lt"
        box = KOINLY_LINE_BOX[x["text"]]
        if d is not None and e is not None and abs(d - e + (g or 0) - h) > 1:
            checks.append(f"Line {x['text']}: proceeds − cost + adjustments = {d - e + (g or 0):,.2f}, column (h) shows {h:,.2f}")
        if not any(abs(v or 0) > 0.004 for v in (d, e, g, h)):
            continue                                        # a line printed with 0.00 everywhere
        parts[term].append((f"({box})", h))
        lines.append(x["text"])
        bits = [f"proceeds {m(d)}" if d is not None else "", f"cost {m(e)}" if e is not None else "",
                f"adjustments {m(g)}" if g else "", f"gain {m(h)}"]
        txt = f"Schedule D line {x['text']}: " + " · ".join(b for b in bits if b)
        notes.append(f"{term.upper()}: {txt}")
        pn[f"({box})"] = (pn[f"({box})"] + "; " if f"({box})" in pn else "") + txt
    st, lt = round(sum(v for _, v in parts["st"]), 2), round(sum(v for _, v in parts["lt"]), 2)
    return dict(status="partial" if checks else "read", amounts=dict(st=st, lt=lt), detail=dict(lines=lines), checks=checks,
                notes=notes or ["Schedule D lines 1a–3 / 8a–10 are 0"], parts={k: v for k, v in parts.items() if v}, part_notes=pn)


def _sched_1(pg) -> dict:
    """Schedule 1: only line 8v (digital assets received as ordinary income) and line 8z (other income, the type listed) - each
    its own Other income row. The amount sits left of the line's number box ("8v"), on its row."""
    ws = pg.extract_words()
    parts, part_notes = [], {}
    for ln, what in (("8v", "digital assets received as ordinary income"), ("8z", "other income")):
        lab = next((w for w in ws if w["text"] == ln and w["x0"] > 0.4 * pg.width), None)
        if not lab:
            continue
        cy = (lab["top"] + lab["bottom"]) / 2
        amt = [w for w in ws if re.fullmatch(NUM_RE, w["text"]) and w["x0"] > lab["x1"] and abs((w["top"] + w["bottom"]) / 2 - cy) < 10]
        if not amt:
            continue
        v = _n(amt[0]["text"])
        kind = ""
        if ln == "8z":                                      # "z Other income. List type and amount: <type>"
            a = next((w for w in ws if w["text"].lower().startswith("amount:") and 0 <= cy - w["top"] < 30), None)
            if a:
                kind = " ".join(w["text"] for w in ws if a["top"] - 3 <= w["top"] <= lab["bottom"] + 2 and w["x1"] < lab["x0"] - 2
                                and (w["top"] > a["top"] + 3 or w["x0"] > a["x1"]) and w is not amt[0]
                                and not re.fullmatch(r"[.\s]+", w["text"])).strip()
        parts.append((f"line {ln}", v))
        part_notes[f"line {ln}"] = f'Entered as "Other income" — Schedule 1 line {ln}: {what}' + (f" ({kind})" if kind else "")
    return dict(status="read", amounts=dict(other=round(sum(v for _, v in parts), 2)), detail=dict(lines=[p[0] for p in parts]),
                notes=['Entered as "Other income" — Schedule 1 lines 8v / 8z' + ("" if parts else " are blank")], checks=[],
                parts=dict(other=parts) if parts else {}, part_notes=part_notes)


def parse_koinly(path, doc_type: str, pw=None) -> dict:
    """Crypto tax reports printed as the IRS forms (Koinly or any other program): Schedule D, Schedule 1, Form 8949."""
    doc, pw = open_pdf(path, [pw] if pw else None)
    with doc:
        flat = [re.sub(r"\s+", " ", page_text(doc, i)) for i in range(len(doc))]
    with pdfplumber.open(str(path), password=pw or "") as pdf:
        if "Schedule D" in doc_type:
            i = next((i for i, t in enumerate(flat) if "Capital Gains and Losses" in t), None)
            if i is None:
                return dict(status="none", amounts={}, detail={}, notes=[], checks=["Schedule D page not found"])
            return _sched_d(pdf.pages[i])
        if "Schedule 1" in doc_type:
            i = next((i for i, t in enumerate(flat) if "Additional Income" in t), None)
            if i is None:
                return dict(status="none", amounts={}, detail={}, notes=[], checks=["Schedule 1 page not found"])
            return _sched_1(pdf.pages[i])
    return dict(status="none", amounts={}, detail={}, notes=[], checks=["Form 8949 — detail of Schedule D, not added"])


# ---------------------------------------------------------------- 1099-R / SSA-1099 (single forms)
# box 7 distribution codes (Instructions for Forms 1099-R and 5498) -> (meaning, taxable?, usual income tax treatment)
R_CODES = {
    "1": ("Early distribution, no known exception", True, "generally taxable, plus possible 10% penalty (Form 5329)"),
    "2": ("Early distribution, exception applies", True, "generally taxable; the exception removes the early withdrawal penalty"),
    "3": ("Disability", True, "generally taxable; no early withdrawal penalty"),
    "4": ("Death / beneficiary distribution", True, "generally taxable for traditional accounts; Roth treatment varies"),
    "5": ("Prohibited transaction", True, "generally taxable, except recoverable basis"),
    "6": ("Section 1035 insurance / annuity exchange", False, "generally a nontaxable qualifying exchange"),
    "7": ("Normal distribution", True, "generally taxable, except basis, rollovers or other exclusions"),
    "8": ("Excess contributions / earnings returned", True, "taxable portion belongs to the form's tax year; returned after-tax contributions generally aren't taxable"),
    "9": ("Cost of current life insurance protection", True, "generally taxable"),
    "A": ("Eligible lump-sum distribution", True, "potentially taxable; special calculation may apply (Form 4972)"),
    "B": ("Designated Roth account, such as Roth 401(k)", True, "depends: qualified distributions tax-free; otherwise earnings may be taxable"),
    "C": ("Reportable death benefits under §6050Y", True, "depends on the applicable death-benefit exclusion"),
    "D": ("Nonqualified annuity / life insurance distribution", True, "taxable gain portion; possible NIIT"),
    "E": ("EPCRS corrective distribution", True, "depends on the correction"),
    "F": ("Charitable gift annuity", True, "may contain taxable income and tax-free basis"),
    "G": ("Direct rollover", False, "usually nontaxable; pretax money rolled into a Roth account is taxable"),
    "H": ("Direct rollover from a designated Roth account to a Roth IRA", False, "nontaxable"),
    "J": ("Early Roth IRA distribution", True, "depends: contributions generally tax-free; earnings may be taxable (Form 8606)"),
    "K": ("Traditional IRA assets without a readily available FMV", True, "does not establish taxability; review the accompanying code"),
    "L": ("Plan loan treated as distribution", True, "generally taxable"),
    "M": ("Qualified plan loan offset", True, "generally taxable unless properly rolled over"),
    "N": ("Recharacterization of same-year IRA contribution", False, "nontaxable transfer"),
    "P": ("Excess contributions / earnings taxable in prior year", True, "taxable portion belongs to the prior year, not the current year"),
    "Q": ("Qualified Roth IRA distribution", False, "nontaxable"),
    "R": ("Recharacterization of prior-year IRA contribution", False, "nontaxable transfer"),
    "S": ("Early SIMPLE IRA distribution within the first two years", True, "generally taxable; possible 25% penalty"),
    "T": ("Roth IRA distribution; penalty exception applies", True, "depends: verify the five-year requirement"),
    "U": ("ESOP dividends", True, "generally taxable"),
    "W": ("Contract charges for qualified long-term care insurance", False, "generally nontaxable"),
    "Y": ("Intended qualified charitable distribution (QCD)", False, "nontaxable to the extent the QCD requirements are met"),
}


def _r_extras(page) -> dict:
    """Distribution code(s) (box 7a), IRA/SEP/SIMPLE (7b) and 2b check boxes, by position on the IRS layout."""
    words = page.get_text("words")
    find = lambda t, nxt=None: next((w for i, w in enumerate(words) if w[4] == t and (nxt is None or
                                     any(x[4].startswith(nxt) and abs(x[1] - w[1]) < 3 for x in words))), None)
    out = {}
    a7 = find("7a", "Dist") or find("7", "Dist")
    if a7:
        x0, y0 = a7[0], a7[1]
        # a code, not the next box's label ("10 Amount allocable ..."): no word right after it on the same row
        label_no = lambda w: any(abs(x[1] - w[1]) < 3 and 0 <= x[0] - w[2] < 12 and re.match(r"[A-Za-z]", x[4]) for x in words)
        toks = [w for w in words if x0 - 3 <= w[0] <= x0 + 48 and y0 + 15 <= w[1] <= y0 + 40
                and re.fullmatch(r"[0-9A-Z]{1,2}", w[4]) and not label_no(w)]
        if toks:
            out["code"] = "".join(sorted({c for w in toks for c in w[4]}, key=lambda c: (c.isalpha(), c)))
    b7 = find("7b", "IRA") or find("IRA/") or find("IRA/SEP/SIMPLE")
    if b7:
        out["ira"] = any(b7[0] <= w[0] <= b7[0] + 48 and b7[1] + 15 <= w[1] <= b7[1] + 40 and w[4] in ("X", "x", "✓", "✔", "■")
                         for w in words)
    b2 = find("2b", "Taxable")
    if b2:
        marks = [w for w in words if w[4] in ("X", "x", "✓", "✔", "■") and b2[1] - 3 <= w[1] <= b2[1] + 30 and w[0] > b2[0]]
        out["not_determined"] = any(w[0] < b2[0] + 100 for w in marks)
        out["total_dist"] = any(w[0] >= b2[0] + 100 for w in marks)
    return out


def parse_1099r(path, pw=None) -> dict:
    """IRS-layout 1099-R by position first, then the text reader (brokers' substitute forms)."""
    doc, _ = open_pdf(path, [pw] if pw else None)
    seen, tot, ex = [], {}, {}
    with doc:
        for page in doc:
            for c in _page_copies(page, "r"):
                b = {k: v for k, v in c.items() if abs(v) > 0.004}
                if not b or b in seen:
                    continue                           # Copy B / C / 2 with the same amounts count once
                seen.append(b)
                for k, v in b.items():
                    tot[k] = tot.get(k, 0) + v
                for k, v in _r_extras(page).items():
                    ex.setdefault(k, v)
    if seen:
        return _r_result(tot.get("1"), tot.get("2a"), ex.get("code"), ex.get("ira"), tot.get("4", 0), tot,
                         ex.get("not_determined"), ex.get("total_dist"), len(seen))
    lst = _list_boxes(path, R_LIST, pw)                   # list layout: "1 Gross distribution ....... 10,579.22"
    if lst and any(_lnum(f.get("1")) is not None or _lnum(f.get("2a")) is not None for f in lst):
        num = lambda f, k: _lnum(f.get(k)) if f.get(k) and re.search(r"\d\.\d\d|,", f.get(k)) else None
        tot = {}
        for f in lst:
            for k in ("1", "2a", "3", "4", "5"):
                if num(f, k) is not None:
                    tot[k] = tot.get(k, 0) + num(f, k)
        f0 = lst[0]
        code = re.sub(r"[^0-9A-Z]", "", (f0.get("7") or "").upper()) or None
        ira = f0.get("ira")
        ira = None if ira is None else str(ira).strip().upper() in ("X", "YES", "Y", "TRUE")
        return _r_result(tot.get("1"), tot.get("2a"), code, ira, tot.get("4", 0), tot, forms=len(lst))
    return _parse_1099r_text(path, pw)


R_LIST = [("1", r"Gross\s+distribution"), ("2a", r"Taxable\s+amount"), ("3", r"Capital\s+gain"), ("4", r"Federal\s+income\s+tax"),
          ("5", r"Employee\s+contrib"), ("7", r"Distribution\s+code"), ("ira", r"IRA\s*/\s*SEP\s*/\s*SIMPLE")]


def _r_result(gross, taxable, code, ira, fit, boxes, not_det=False, total=False, forms=1) -> dict:
    """Taxable amount -> summary (IRA or pension); code description in the note; non-taxable amounts in the note."""
    notes, checks = [], []
    cat = "ira" if ira else "pension"
    codes = [c for c in (code or "")]
    descs = [f"Code {c}: {R_CODES[c][0]} — {R_CODES[c][2]}" if c in R_CODES else f"Code {c}: not a known 1099-R code — check" for c in codes]
    taxable_code = all(R_CODES.get(c, ("", True, ""))[1] for c in codes) if codes else True
    if gross is None and taxable is None:
        return dict(status="none", amounts={}, detail={}, notes=[], checks=["1099-R amounts not found"])
    if not taxable_code:
        amt = taxable or 0.0
        nontax = (gross or 0) - (taxable or 0)
        notes.append(f"Not taxable {nontax:,.2f} (gross {gross or 0:,.2f})")
    elif taxable is not None:
        amt = taxable
        if gross is not None and gross - taxable > 0.004:
            notes.append(f"Not taxable {gross - taxable:,.2f} (gross {gross:,.2f} − taxable {taxable:,.2f})")
    else:
        amt = gross or 0.0
        notes.append(f"Box 2a blank — gross {gross or 0:,.2f} used" + (" (2b: taxable amount not determined)" if not_det else "") + " — confirm basis")
        checks.append("taxable amount not shown")
    # always: IRA/SEP/SIMPLE box and the distribution code(s) with their meaning
    notes.insert(0, "IRA/SEP/SIMPLE: checked (IRA distributions)" if ira else
                 "IRA/SEP/SIMPLE: not checked (pensions and annuities)" if ira is False else
                 "IRA/SEP/SIMPLE: box not read — placed under pensions, confirm")
    notes[1:1] = descs or ["Box 7 distribution code: not read — check the form"]
    if not code:
        checks.append("distribution code not read")
    if "P" in codes:
        checks.append("code P — taxable in the prior year, not this year")
    if not_det and taxable is not None:
        notes.append("2b: taxable amount not determined (checked) — confirm basis / Form 8606")
    if total:
        notes.append("Total distribution")
    if boxes.get("3"):
        notes.append(f"Box 3 capital gain {boxes['3']:,.2f} (included in 2a)")
    if boxes.get("5"):
        notes.append(f"Box 5 employee contributions / Roth / premiums {boxes['5']:,.2f} (not taxable)")
    if forms > 1:
        notes.append(f"{forms} different 1099-Rs in this file — added together")
    return dict(status="partial" if checks else "read", amounts={cat: amt}, detail=dict(gross=gross, taxable=taxable, code=code, boxes=boxes),
                fit=round(fit or 0, 2), notes=notes, checks=checks)


def _parse_1099r_text(path, pw=None) -> dict:
    texts, _ = _texts(path, pw, 6)
    t = "\n".join(texts)
    g = re.search(B + r"1\W{0,6}Gross\s+distribution", t, re.I)
    tx = re.search(B + r"2a\W{0,6}Taxable\s+amount", t, re.I)
    gross = _after(t, g.end()) if g else None
    taxable = _after(t, tx.end()) if tx else None
    code = re.search(r"(?:Distribution\s+code\(?s?\)?|Dist\.?\s+code\(?s?\)?)[\s.:_]{0,120}([0-9A-Z]{1,2})\b", t)
    ira = bool(re.search(r"IRA/\s?SEP/\s?SIMPLE\W{0,20}(X|☒|✔)", t))
    fw = re.search(B + r"4\W{0,6}Federal\s+income\s+tax\s+withheld", t, re.I)
    return _r_result(gross, taxable, code.group(1) if code else None, ira or None,
                     (_after(t, fw.end()) or 0) if fw else 0, {})


def parse_ssa(path, pw=None) -> dict:
    texts, _ = _texts(path, pw, 4)
    t = "\n".join(texts)
    m = re.search(r"Box\s*5\.?\s*Net\s+Benefits\s+for\s+20\d\d", t, re.I)
    v = _after(t, m.end(), 400) if m else None
    if v is None:
        return dict(status="none", amounts={}, detail={}, notes=[], checks=["SSA-1099 box 5 not found"])
    w = re.search(r"Box\s*6\.?\s*Voluntary\s+Federal\s+Income\s+Tax\s+Withheld", t, re.I)
    return dict(status="read", amounts=dict(ss=v), detail=dict(box5=v), fit=(_after(t, w.end(), 300) or 0) if w else 0,
                notes=["Net benefits (box 5) — taxable part figured on the return"], checks=[])


# ---------------------------------------------------------------- list layout ("1 Gross Distribution ........ 450.49")
# Many W-2 / 1099-R / 1099-SA prints list the IRS boxes one per line instead of the IRS table: box number, the IRS box name,
# leader dots, the value at the end of the line. Read only lines whose box number AND IRS name match.
LIST_VAL = re.compile(r"(\(?-?\$?\s?[\d,]*\d(?:\.\d{2})?\)?|[A-Z0-9]{1,3}|X|Yes|No|HSA|MSA|MA MSA|Archer MSA)$", re.I)


def _list_boxes(path, spec, pw=None, max_pages=8) -> list:
    """spec: [(box, IRS name regex)] -> one dict per form found {box: raw value text} (copies with the same values once)."""
    doc, _ = open_pdf(path, [pw] if pw else None)
    forms = []
    with doc:
        for i in range(min(len(doc), max_pages)):
            cur = {}
            for ws in _rows(doc[i].get_text("words")):
                txt = " ".join(w[4] for w in ws).strip()
                for box, pat in spec:
                    pre = (re.escape(box) + r"[.:)\-]?\s+") if re.fullmatch(r"\d{1,2}[a-z]?", box) else r"(?:\d{1,2}[a-z]?[.:)\-]?\s+)?"
                    m = re.match(r"^(?:Box\s*)?" + pre + r"(?:" + pat + r")[^\n]*?[\s.:$_-]+(?P<v>\S+(?:\s?MSA)?)$", txt, re.I)
                    if m and LIST_VAL.match(m.group("v")):
                        if box in cur:                    # the next form starts
                            if cur not in forms:
                                forms.append(cur)
                            cur = {}
                        cur[box] = m.group("v")
                        break
            if cur and cur not in forms:
                forms.append(cur)
    return forms


def _lnum(v):
    try:
        return _n(str(v).replace("$", "").replace(" ", ""))
    except Exception:  # noqa: BLE001
        return None


# 1099-SA (HSA / Archer MSA / MA MSA distributions) - not income by itself: Form 8889 decides; a note on the inventory
SA_CODES = {"1": ("Normal distribution", "not taxable if used for qualified medical expenses (Form 8889)"),
            "2": ("Excess contributions", "earnings are taxable (Form 8889)"),
            "3": ("Disability", "taxable if not used for qualified medical expenses; no additional 20% tax"),
            "4": ("Death distribution other than code 6", "see Form 8889 — taxable to the estate / nonspouse beneficiary"),
            "5": ("Prohibited transaction", "the account is treated as distributed — taxable"),
            "6": ("Death distribution after the year of death to a nonspouse beneficiary", "taxable (FMV on date of death)")}
SA_SPEC = [("1", r"Gross\s+distribution"), ("2", r"Earnings\s+on\s+excess"), ("3", r"Distribution\s+code"),
           ("4", r"FMV\s+on\s+date\s+of\s+death|Fair\s+market\s+value"), ("5", r"(HSA|Account\s+type|Archer)")]


def parse_1099sa(path, pw=None) -> dict:
    forms = _list_boxes(path, SA_SPEC, pw)
    if not forms:                                           # IRS table layout
        doc, _ = open_pdf(path, [pw] if pw else None)
        with doc:
            for page in doc:
                for c in _page_copies(page, "sa"):
                    f = {k: f"{v:.2f}" for k, v in c.items()}
                    t = page.get_text()
                    m = re.search(r"Distribution\s+code\W{0,40}?\b([1-6])\b", t, re.I)
                    if m:
                        f["3"] = m.group(1)
                    for kind in ("Archer MSA", "MA MSA", "HSA"):
                        if re.search(r"(X|☒|✔)\s*" + kind + r"|" + kind + r"\s*(X|☒|✔)", t):
                            f["5"] = kind
                            break
                    if f.get("1") and f not in forms:
                        forms.append(f)
    if not forms or not any(_lnum(f.get("1")) for f in forms):
        return dict(status="none", amounts={}, detail={}, notes=[], checks=["1099-SA box 1 gross distribution not found"])
    parts, gross = [], 0.0
    for f in forms:
        g = _lnum(f.get("1")) or 0.0
        gross += g
        code = (f.get("3") or "").strip()
        meaning = SA_CODES.get(code)
        p = f"1099-SA: box 1 gross distribution {g:,.2f}"
        if _lnum(f.get("2")):
            p += f" · box 2 earnings on excess contributions {_lnum(f['2']):,.2f}"
        p += f" · code {code}: {meaning[0]} — {meaning[1]}" if meaning else " · distribution code not read — check"
        if _lnum(f.get("4")):
            p += f" · box 4 FMV on date of death {_lnum(f['4']):,.2f}"
        p += f" · {f.get('5') or 'account type not read'}"
        parts.append(p)
    note = "; ".join(parts) + " — not income by itself: Form 8889 (taxable only if not used for qualified medical expenses)"
    return dict(status="read", amounts={}, detail=dict(gross=round(gross, 2), forms=forms), notes=[], checks=[],
                inv_note=note, memo_only=True)


# ---------------------------------------------------------------- dispatcher
# ---------------------------------------------------------------- single IRS-template 1099s (MISC / NEC)
# The payer's software prints the amounts inside the box, under the box label - read them by position.
BOXES = {
    "misc": [("1", r"Rents"), ("2", r"Royalties"), ("3", r"Other\s+income"), ("4", r"Federal\s+income\s+tax"),
             ("5", r"Fishing\s+boat"), ("6", r"Medical\s+and"), ("8", r"Substitute\s+payments"), ("9", r"Crop\s+insurance"),
             ("10", r"Gross\s+proceeds"), ("11", r"Fish\s+purchased"), ("12", r"Section\s+409A"),
             ("15", r"Nonqualified\s+deferred"), ("16", r"State\s+tax"), ("18", r"State\s+income")],
    "nec": [("1a", r"Nonemployee\s+compensation"), ("1", r"Nonemployee\s+compensation"), ("1b", r"Cash\s+tips"),
            ("1d", r"Overtime\s+compensation"), ("3", r"Excess\s+golden"), ("4", r"Federal\s+income\s+tax"),
            ("5", r"State\s+tax"), ("7", r"State\s+income")],
}
BOXES["sa"] = [("1", r"Gross\s+distribution"), ("2", r"Earnings\s+on\s+excess"), ("4", r"FMV\s+on\s+date")]
BOXES["r"] = [("1", r"Gross\s+distribution"), ("2a", r"Taxable\s+amount"), ("3", r"Capital\s+gain"),
              ("4", r"Federal\s+income"), ("5", r"Employee\s+contrib"), ("9b", r"Total\s+employee"),
              ("14", r"State\s+tax"), ("16", r"State\s+distribution")]
BOXES["e"] = [("1", r"Student\s+loan\s+interest")]
BOX_DESC = {"misc": {"5": "Fishing boat proceeds", "6": "Medical and health care payments", "9": "Crop insurance proceeds",
                     "10": "Gross proceeds paid to an attorney", "11": "Fish purchased for resale", "12": "Section 409A deferrals",
                     "15": "Nonqualified deferred compensation"},
            "nec": {"1b": "Cash tips", "1d": "Overtime compensation", "3": "Excess golden parachute payments"}}
AMT_W = re.compile(r"^\$?\(?-?[\d,]*\d\.\d{2}\)?$")


def _page_boxes(page, kind) -> dict:
    """All the box amounts on the page (one copy). Several copies on one page: use _page_copies."""
    cs = _page_copies(page, kind)
    return cs[0] if cs else {}


def _page_copies(page, kind) -> list:
    """Every copy printed on the page (Copy B / C / 2 ... stacked or side by side) -> [{box: amount}], one dict per copy."""
    words = page.get_text("words")                     # x0, y0, x1, y1, text, block, line, word
    lines = {}
    for w in words:
        lines.setdefault((w[5], w[6]), []).append(w)
    labels = []
    for ws in lines.values():
        ws.sort(key=lambda w: w[0])
        txt = " ".join(w[4] for w in ws)
        for box, pat in BOXES[kind]:
            m = re.match(r"\s*" + re.escape(box) + r"\.?\s+" + pat, txt, re.I)
            if m:
                labels.append((box, ws[0][0], ws[0][1]))
                break
    if not labels:
        return []
    first = BOXES[kind][0][0]
    anchors = sorted([l for l in labels if l[0] == first], key=lambda l: (l[2], l[1]))
    regions = []
    for a in anchors or [(first, -1e9, -1e9)]:
        y0 = a[2] - 5
        y1 = min([o[2] - 5 for o in anchors if o[2] > a[2] + 4] or [1e9])
        x0 = a[1] - 20
        x1 = min([o[1] - 20 for o in anchors if abs(o[2] - a[2]) <= 4 and o[1] > a[1] + 4] or [1e9])
        regions.append((x0, x1, y0, y1))
    if len(regions) == 1:
        regions = [(-1e9, 1e9, -1e9, 1e9)]
    out = []
    for x0, x1, y0, y1 in regions:
        labs = [l for l in labels if x0 <= l[1] < x1 and y0 <= l[2] < y1]
        got = {}
        for w in words:
            if not AMT_W.match(w[4]) or not (x0 <= w[0] < x1 + 20 and y0 <= w[1] < y1):
                continue
            cands = [(round((w[1] - ly) / 14), w[0] - lx, box) for box, lx, ly in labs if ly - 3 <= w[1] <= ly + 60 and -8 <= w[0] - lx <= 140]
            if cands:
                box = min(cands)[2]                    # nearest label above, then the nearest column to the left
                got[box] = got.get(box, 0) + _n(w[4].lstrip("$"))
        if got:
            out.append(got)
    return out


def parse_1099_form(path, kind, pw=None) -> dict:
    """1099-MISC / 1099-NEC on the IRS layout. Copies (A, 1, B, 2 ...) with the same amounts count once."""
    doc, _ = open_pdf(path, [pw] if pw else None)
    seen, tot = [], {}
    with doc:
        for page in doc:
            for c in _page_copies(page, kind):
                b = {k: v for k, v in c.items() if abs(v) > 0.004}
                if not b or b in seen:
                    continue
                seen.append(b)
                for k, v in b.items():
                    tot[k] = tot.get(k, 0) + v
    a, notes = {}, []
    if not seen:
        return dict(status="none", amounts={}, detail={}, notes=[], checks=[f"1099-{kind.upper()} amounts not found"], fit=0.0)
    if kind == "misc":
        if tot.get("1") or tot.get("2"):
            a["rental"] = tot.get("1", 0) + tot.get("2", 0)
            if tot.get("1"):
                notes.append(f"Rents {tot['1']:,.2f} (box 1) → Schedule E")
            if tot.get("2"):
                notes.append(f"Royalties {tot['2']:,.2f} (box 2) → Schedule E")
        if tot.get("3") or tot.get("8"):
            a["other"] = tot.get("3", 0) + tot.get("8", 0)
            if tot.get("8"):
                notes.append(f"Other income includes substitute payments {tot['8']:,.2f} (box 8)")
        for bx, desc in BOX_DESC["misc"].items():
            if tot.get(bx):
                notes.append(f"Box {bx} {desc} {tot[bx]:,.2f} — not included, check where it goes")
    else:
        nec = tot.get("1a", 0) + tot.get("1", 0)
        if nec:
            a["schc"] = nec
        oth = []
        for bx, desc in BOX_DESC["nec"].items():
            if tot.get(bx):
                oth.append(f"Box {bx} {desc} {tot[bx]:,.2f}")
        if oth:
            a["other"] = sum(tot[bx] for bx in BOX_DESC["nec"] if tot.get(bx))
            notes.append('Entered as "Other income" — ' + "; ".join(oth))
    if not a:
        notes.append("All amounts 0 on this form")
    if len(seen) > 1:
        notes.append(f"{len(seen)} different forms in this file — added together")
    return dict(status="read", amounts=a, detail=dict(boxes=tot, forms=len(seen)), notes=notes, checks=[],
                fit=round(tot.get("4", 0), 2))


# ---------------------------------------------------------------- 1099-INT, any layout: label and amount on the same row
INT_ROWS = [("int_1", "1", r"Interest\s+income"), ("int_2", "2", r"Early\s+withdrawal\s+penalty"),
            ("int_3", "3", r"Interest\s+on\s+U\.?\s?S\.?\s+Savings\s+Bonds"), ("fit", "4", r"Federal\s+income\s+tax\s+withheld"),
            ("int_5", "5", r"Investment\s+expenses"), ("int_6", "6", r"Foreign\s+tax\s+paid"),
            ("int_8", "8", r"Tax[- ]exempt\s+interest"), ("int_9", "9", r"Specified\s+private\s+activity"),
            ("int_10", "10", r"Market\s+discount"), ("int_11", "11", r"Bond\s+premium\s*$"),
            ("int_12", "12", r"Bond\s+premium\s+on\s+Treasury"), ("int_13", "13", r"Bond\s+premium\s+on\s+tax[- ]exempt")]


def _rows(words, tol=3.5):
    rows = []
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        if rows and abs(rows[-1][0] - w[1]) <= tol:
            rows[-1][1].append(w)
        else:
            rows.append([w[1], [w]])
    return [sorted(r[1], key=lambda w: w[0]) for r in rows]


def parse_1099int_rows(path, pw=None) -> dict:
    """Substitute 1099-INTs (banks): each box label on the left, its amount at the right end of the same row."""
    doc, _ = open_pdf(path, [pw] if pw else None)
    seen, tot = [], {}
    with doc:
        for page in doc:
            got = {}
            for ws in _rows(page.get_text("words")):
                amts = [w for w in ws if AMT_W.match(w[4])]
                if not amts:
                    continue
                txt = " ".join(w[4] for w in ws if w[0] < amts[-1][0]).strip()
                for key, box, pat in INT_ROWS:
                    if key in got:
                        continue
                    if re.match(r"(?:box\s*)?" + box + r"[.)]?\s+" + pat, txt, re.I) or re.fullmatch(pat, txt, re.I):
                        got[key] = _n(amts[-1][4].lstrip("$"))
                        break
            if "int_1" in got and got not in seen:
                seen.append(got)
                for k, v in got.items():
                    tot[k] = tot.get(k, 0) + v
    if not seen:
        return dict(status="none", amounts={}, detail={}, notes=[], checks=["1099-INT box 1 not found"], fit=0.0)
    fit = tot.pop("fit", 0.0)
    res = _amounts_1099({k: v for k, v in tot.items()}, {}, "", {})
    res["checks"] = [c for c in res["checks"] if "not read" not in c]
    res["status"] = "read"
    if tot.get("int_2"):
        res["notes"].append(f"Early withdrawal penalty {tot['int_2']:,.2f} (Schedule 1 line 18 — adjustment)")
    if tot.get("int_5"):
        res["notes"].append(f"Investment expenses {tot['int_5']:,.2f} (box 5)")
    if tot.get("int_11") or tot.get("int_12") or tot.get("int_13"):
        res["notes"].append("Bond premium " + ", ".join(f"box {k[4:]} {tot[k]:,.2f}" for k in ("int_11", "int_12", "int_13") if tot.get(k)))
    if tot.get("int_9"):
        res["notes"].append(f"Private activity bond interest {tot['int_9']:,.2f} (AMT item)")
    if len(seen) > 1:
        res["notes"].append(f"{len(seen)} different 1099-INTs in this file — added together")
    res["fit"] = round(fit, 2)
    return res


def parse_1098e(path, pw=None) -> dict:
    """1098-E box 1 (student loan interest) -> Deduction summary. Box 2 checked = box 1 excludes origination fees /
    capitalized interest (pre-9/1/2004 loans)."""
    doc, _ = open_pdf(path, [pw] if pw else None)
    seen, tot, box2 = [], 0.0, False
    with doc:
        for page in doc:
            b = _page_boxes(page, "e")
            if not b.get("1"):
                for ws in _rows(page.get_text("words")):
                    amts = [w for w in ws if AMT_W.match(w[4])]
                    txt = " ".join(w[4] for w in ws)
                    if amts and re.search(r"Student\s+loan\s+interest", txt, re.I):
                        b = {"1": _n(amts[-1][4].lstrip("$"))}
                        break
            if b.get("1") and b not in seen:
                seen.append(b)
                tot += b["1"]
                ws = page.get_text("words")
                lab = next((w for w in ws if re.fullmatch(r"2\.?", w[4]) and any(x[4] == "If" and abs(x[1] - w[1]) < 3 for x in ws)), None)
                if lab and any(x[4] in ("X", "x", "✓", "✔", "■") and abs(x[1] - lab[1]) < 25 and x[0] > lab[0] for x in ws):
                    box2 = True
    if not seen:
        return dict(status="none", amounts={}, detail={}, notes=[], checks=["1098-E box 1 not found"])
    notes = ["Schedule 1 line 21 — max 2,500; phases out with income"]
    notes.append("Box 2 checked — box 1 excludes origination fees / capitalized interest (may add them)" if box2
                 else "Box 2 not checked")
    if len(seen) > 1:
        notes.append(f"{len(seen)} different 1098-Es in this file — added together")
    return dict(status="read", amounts=dict(student_loan=round(tot, 2)), detail=dict(box1=tot, box2=box2), notes=notes, checks=[])


# ---------------------------------------------------------------- 1098 (mortgage interest)
# box number + its IRS name (box 10 = "Other" on the IRS blank; lenders print their own name, e.g. "Real estate taxes")
M_BOXES = [("1", r"Mortgage\s+interest"), ("2", r"Outstanding\s+mortgage"), ("3", r"Mortgage(\s+origination|$)"),
           ("4", r"Refund\s+of\s+overpaid"), ("5", r"Mortgage\s+insurance"), ("6", r"Points\s+paid"),
           ("7", r"(The|If)\s+(the\s+)?address"), ("8", r"Address\s+or\s+description"), ("9", r"Number\s+of\s+properties"),
           ("10", r"[A-Za-z]"), ("11", r"Mortgage(\s+acquisition|$)")]
M_FOOT = re.compile(r"(?i)Form\s+1098|www\.irs\.gov|Cat\.\s*No\.|keep\s+for\s+your\s+records|Department\s+of\s+the\s+Treasury")
M_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
M_MARKS = {"X", "x", "✓", "✔", "■", "☒", "☑"}


def _m_labels(words) -> list[dict]:
    """The 1098 box labels on the page: {box, x, y, x1, h, words, text, marks}. A one-letter word between the box number and
    its name is a check mark (box 7 on the IRS blank: the ✓ prints between "7" and "If address ...")."""
    out = []
    for n in words:
        if not re.fullmatch(r"\d{1,2}", n[4]) or n[4] not in dict(M_BOXES):
            continue
        row = sorted([w for w in words if w is not n and abs(w[1] - n[1]) < 4 and w[0] > n[2] - 1], key=lambda w: w[0])
        seq, marks, last = [], [], n[2]
        for w in row:
            if not seq and len(w[4]) == 1 and not w[4].isalpha() and w[0] - last < 25:
                marks.append(w)                                   # a check mark, not text
                last = w[2]
                continue
            if w[0] - last > (25 if not seq else 12) or W2_AMT.match(w[4]) or re.fullmatch(r"\d{1,2}", w[4]):
                break
            seq.append(w)
            last = w[2]
        txt = " ".join(w[4] for w in seq)
        if txt and re.match(dict(M_BOXES)[n[4]], txt, re.I) and (n[4] != "10" or len(seq) <= 4):
            out.append(dict(box=n[4], x=n[0], y=n[1], x1=seq[-1][2], h=max(n[3] - n[1], 3), words=[n] + seq + marks,
                            text=txt, marks=[w[4] for w in marks]))
    return out


def _m_cell(words, lab, labs, x1, y1) -> list[list]:
    """The lines in a 1098 box: down to the next label in its column, right edge = the next label beside it, or a box on the
    right that reaches down past this label (the IRS blank's box 8 sits beside boxes 9 / 10)."""
    col = lambda l: [o["y"] for o in labs if o["y"] > l["y"] + 5 and abs(o["x"] - l["x"]) < 40]
    bot = min(col(lab) + [y1, lab["y"] + 110])
    ends = lambda l: min(col(l) + [y1])
    right = min([l["x"] for l in labs if l is not lab and l["x"] > lab["x1"] - 2 and l["y"] < bot - 4 and ends(l) > lab["y"] + 4]
                + [x1])
    foot = [ln[0][1] for ln in _rows(words) if ln[0][1] > lab["y"] + 3 and M_FOOT.search(" ".join(w[4] for w in ln))]
    bot = min([bot] + foot[:1])                                # the form's footer line ("Form 1098 ... Department of the Treasury")
    skip = {id(w) for l in labs for w in l["words"]}
    ws = [w for w in words if id(w) not in skip and lab["x"] - 8 <= w[0] < right - 4 and lab["y"] + 3 < w[1] < bot - 3]
    out, last = [], None
    for ln in _rows(ws):                 # the box ends at a gap of 4+ label heights (text printed under it)
        if last is not None and ln[0][1] - last > 4 * lab["h"]:
            break
        out.append(ln)
        last = ln[0][1]
    return out


def _m_name(words, pat, colR) -> tuple[str, list]:
    """Lender / borrower block (left column): the first line under the label = the name, the next lines = the address."""
    lab = next((w for w in words if re.fullmatch(pat, w[4]) and w[0] < colR
                and any(abs(x[1] - w[1]) < 4 and x[0] > w[2] and re.match(r"(?i)name", x[4]) for x in words)), None)
    if not lab:
        return "", []
    ws = [w for w in words if lab[1] + 3 < w[1] < lab[1] + 60 and lab[0] - 20 <= w[0] < colR - 4]
    lines = [" ".join(w[4] for w in ln) for ln in _rows(ws)]
    lines = [t for t in lines if not re.search(r"(?i)\b(telephone|province|postal|ZIP code|street address|including apt)\b|^name\b", t)]
    lines = [t for t in lines if not re.search(r"(?i)RECIPIENT|PAYER|BORROWER|LENDER|\bTIN\b", t)]
    return (lines[0] if lines else ""), lines[1:]


def _m_page(page) -> list[dict]:
    """Every 1098 printed on the page (one per box-1 label) -> [{row key: value}] (the form view's row keys: b1 ... b9,
    b10:<description>, b11, ln = lender, br = borrower, acct)."""
    words = page.get_text("words")
    labs = _m_labels(words)
    anchors = sorted([l for l in labs if l["box"] == "1"], key=lambda l: l["y"])
    if not anchors:
        return []
    W = page.rect.width
    out = []
    for i, a in enumerate(anchors):
        y0 = a["y"] - 130 if i else -1e9
        y1 = anchors[i + 1]["y"] - 130 if i + 1 < len(anchors) else 1e9
        ls = [l for l in labs if y0 <= l["y"] < y1]
        first = lambda b: min((l for l in ls if l["box"] == b), key=lambda l: l["y"], default=None)
        cell = lambda b: _m_cell(words, first(b), ls, W, y1) if first(b) else []
        txt = lambda ln: " ".join(w[4] for w in ln if not W2_AMT.match(w[4]))
        amt = lambda b: next((_n(w[4].lstrip("$")) for ln in cell(b) for w in ln if W2_AMT.match(w[4])), None)
        f = {}
        for b in ("1", "2", "4", "5", "6"):
            v = amt(b)
            if v is not None:
                f["b" + b] = v
        for b in ("3", "11"):
            v = next((w[4] for ln in cell(b) for w in ln if M_DATE.match(w[4])), None)
            if v:
                f["b" + b] = v
        if first("7"):
            f["b7"] = bool(first("7")["marks"]) or any(w[4] in M_MARKS for ln in cell("7") for w in ln)
        if first("8"):
            l8 = first("8")
            rows = _m_cell(words, dict(l8, x1=l8["x1"]), ls, min(W, l8["x1"] + 24), y1)    # the legend beside it isn't the address
            lines = [t for t in (txt(ln).strip() for ln in rows)
                     if t and not re.search(r"(?i)\(see instructions\)|^securing|^mortgage$|^instructions\)|^acquisition|^date$", t)]
            if lines:
                f["b8"] = ", ".join(lines)
        v = next((w[4] for ln in cell("9") for w in ln if re.fullmatch(r"\d{1,3}", w[4])), None)
        if v:
            f["b9"] = v
        l10 = first("10")
        if l10:
            ln10 = cell("10")
            a10 = amt("10")
            k = next((i for i, ln in enumerate(ln10) if any(W2_AMT.match(w[4]) for w in ln)), len(ln10))
            desc = " ".join(t for t in (txt(ln).replace("$", "").strip() for ln in ln10[:k + 1]) if t) or l10["text"]
            if a10 is not None:
                f[f"b10:{desc}"] = a10
        colR = min([l["x"] for l in ls if l["box"] in ("1", "2")] + [W / 2 + 40])
        ln_, _ = _m_name(words, r"RECIPIENT.S/LENDER.S", colR)
        br, _ = _m_name(words, r"PAYER.S/BORROWER.S", colR)
        if ln_:
            f["ln"] = ln_
        if br:
            f["br"] = br
        acl = next((w for w in words if w[4] == "Account" and any(abs(x[1] - w[1]) < 4 and x[0] > w[2] and x[4].startswith("number")
                                                                    for x in words)), None)
        if acl:
            ws = [w for w in words if acl[1] + 3 < w[1] < acl[1] + 25 and acl[0] - 8 <= w[0] < acl[0] + 200]
            r0 = _rows(ws)
            if r0:
                f["acct"] = " ".join(w[4] for w in r0[0])
        if any(k != "b7" and k.startswith("b") for k in f):
            out.append(f)
    return out


def m1098_result(forms: list) -> dict:
    """The 1098s of one document (row-key dicts) -> the parse result: box 1 -> Deduction summary (mortgage interest); boxes 2,
    4, 5, 6, 8 and 10 go in the comment (box 4 / 5 / 6 only when not 0)."""
    if not forms:
        return dict(status="none", amounts={}, detail={}, notes=[], checks=["1098 box 1 not found"])
    notes = []
    for f in forms:
        parts = []
        if f.get("b2") is not None:
            parts.append(f"Box 2 outstanding principal {f['b2']:,.2f}")
        for b, what in (("b4", "refund of overpaid interest"), ("b5", "mortgage insurance premiums"), ("b6", "points paid")):
            if f.get(b):
                parts.append(f"Box {b[1:]} {what} {f[b]:,.2f}")
        if f.get("b8"):
            parts.append(f"Box 8 property: {f['b8']}")
        elif f.get("b7"):
            parts.append("Box 7: property = borrower's address")
        for k, v in f.items():
            if k.startswith("b10:") and v:
                parts.append(f"Box 10 {k[4:]} {v:,.2f}")
        if parts:
            notes.append((f"{f['ln']}: " if len(forms) > 1 and f.get("ln") else "") + " · ".join(parts))
    if len(forms) > 1:
        notes.append(f"{len(forms)} different 1098s in this file — added together")
    tot = round(sum(f.get("b1") or 0 for f in forms), 2)
    return dict(status="read", amounts=dict(mortgage=tot), detail=dict(boxes=forms), notes=notes,
                checks=[] if any(f.get("b1") is not None for f in forms) else ["1098 box 1 not found"])


def parse_1098(path, pw=None) -> dict:
    """1098 (mortgage interest): the lender's print or the IRS blank. Copies (A / B / C) with the same amounts count once."""
    doc, _ = open_pdf(path, [pw] if pw else None)
    forms = []
    with doc:
        for page in doc:
            for f in _m_page(page):
                key = (f.get("b1"), f.get("b2"), f.get("b3"), f.get("acct"))
                old = next((o for o in forms if (o.get("b1"), o.get("b2"), o.get("b3"), o.get("acct")) == key), None)
                if old is None:
                    forms.append(f)
                else:                                   # another copy: boxes it missed are filled from this one
                    for k, v in f.items():
                        old.setdefault(k, v)
    return m1098_result(forms)


# ---------------------------------------------------------------- 1095-A / 1098-T (not income: a note + screen 2 checks)
BOXES["t"] = [("1", r"Payments\s+received"), ("4", r"Adjustments\s+made"), ("5", r"Scholarships\s+or\s+grants"),
              ("6", r"Adjustments\s+to\s+scholarships"), ("10", r"Ins")]
T_TEXT = {"1": r"payments\s+received\s+for\s+qualified\s+tuition|payments\s+received", "5": r"scholarships\s+or\s+grants",
          "4": r"adjustments\s+made\s+for\s+a\s+prior\s+year", "6": r"adjustments\s+to\s+scholarships"}
T_CHECKS = {"7": r"academic\s+period\s+beginning|January\s*[–-]\s*March", "8": r"at\s+least\s+half-?\s*time",
            "9": r"graduate\s+student"}
CHECK_MARKS = ("X", "x", "✓", "✔", "■", "☒")


def _checked(ws_all, pat) -> bool:
    """A check box ticked on the label's row (an X / ✓ near the label)."""
    for ws in _rows(ws_all):
        txt = " ".join(w[4] for w in ws)
        if re.search(pat, txt, re.I) and any(w[4] in CHECK_MARKS for w in ws):
            return True
    return False


def parse_1098t(path, pw=None) -> dict:
    """1098-T box 1 (payments), 5 (scholarships), 4 / 6 (adjustments), 7 / 8 / 9 checks -> a note only (education credits)."""
    doc, _ = open_pdf(path, [pw] if pw else None)
    boxes, checks = {}, set()
    with doc:
        for page in doc:
            b = _page_boxes(page, "t")
            ws_all = page.get_text("words")
            if not b.get("1") and not b.get("5"):                  # school statements: "Payments received ... 12,400.00"
                for ws in _rows(ws_all):
                    txt = " ".join(w[4] for w in ws)
                    amts = [w for w in ws if AMT_W.match(w[4])]
                    m = re.match(r"Box\s*(\d{1,2})\b(?!\.)", txt, re.I)       # "Box 1 (Paymt rec for qual tuition ...) 38,132.00"
                    if m and amts and m.group(1) in ("1", "4", "5", "6", "10") and m.group(1) not in b:
                        b[m.group(1)] = _n(amts[-1][4].lstrip("$"))
                        continue
                    for bx, pat in T_TEXT.items():
                        if amts and bx not in b and re.search(pat, txt, re.I):
                            b[bx] = _n(amts[-1][4].lstrip("$"))
                            break
            if not b.get("1") and not b.get("5"):                  # rotated / list statements: "Box 1 (Paymt rec ...)\n38,132.00"
                for m in re.finditer(r"Box\s*(\d{1,2})\s*\([^\n]*\n\s*\$?(-?[\d,]*\d\.\d{2})", page.get_text()):
                    if m.group(1) in ("1", "4", "5", "6", "10") and m.group(1) not in b:
                        b[m.group(1)] = _n(m.group(2))
            for k, v in b.items():
                if v and k not in boxes:
                    boxes[k] = v
            if "Instructions for Student" not in page.get_text():    # the instructions page mentions every box
                for bx, pat in T_CHECKS.items():
                    if _checked(ws_all, pat):
                        checks.add(bx)
    if not boxes:
        return dict(status="none", amounts={}, detail={}, notes=[], checks=["1098-T box 1 / box 5 not found"])
    parts = [f"box 1 {boxes.get('1', 0):,.2f}", f"box 5 {boxes.get('5', 0):,.2f}"]
    for bx in ("4", "6"):
        if boxes.get(bx):
            parts.append(f"box {bx} {boxes[bx]:,.2f}")
    parts += [{"7": "box 7 (next-year term)", "8": "half-time", "9": "graduate"}[c] for c in sorted(checks)]
    note = "1098-T: " + " · ".join(parts)
    if boxes.get("5", 0) > boxes.get("1", 0):
        note += " — scholarships exceed tuition: possible taxable scholarship"
    return dict(status="read", amounts={}, detail=dict(box1=boxes.get("1", 0), box5=boxes.get("5", 0), boxes=boxes, checks=sorted(checks)),
                notes=[], checks=[], inv_note=note, memo_only=True)


def parse_1095a(path, pw=None) -> dict:
    """1095-A Part III line 33 (annual totals), column C = advance payment of premium tax credit -> a note only."""
    doc, _ = open_pdf(path, [pw] if pw else None)
    c_total, months = None, []
    with doc:
        for page in doc:
            ws_all = page.get_text("words")
            rows = _rows(ws_all)
            # column C: x of the "C." heading (Monthly advance payment of premium tax credit)
            cx = None
            for ws in rows:
                txt = " ".join(w[4] for w in ws)
                if re.search(r"advance\s+payment", txt, re.I) or re.search(r"\bC\.\s+Monthly", txt):
                    w = next((w for w in ws if w[4] in ("C.", "C")), None) or ws[0]
                    cx = w[0]
            for ws in rows:
                txt = " ".join(w[4] for w in ws)
                amts = [w for w in ws if AMT_W.match(w[4]) or re.fullmatch(r"-?[\d,]*\d\.\d{2}", w[4])]
                if not amts:
                    continue
                if re.match(r"^33\b|Annual\s+Totals?", txt, re.I):
                    if cx is not None:
                        pick = [w for w in amts if w[0] >= cx - 15]
                        c_total = _n(pick[-1][4].lstrip("$")) if pick else (_n(amts[-1][4].lstrip("$")) if len(amts) >= 3 else c_total)
                    elif len(amts) >= 3:
                        c_total = _n(amts[-1][4].lstrip("$"))
                elif re.match(r"^(2[1-9]|3[0-2])\b", txt) and len(amts) >= 3:
                    months.append(_n(amts[-1][4].lstrip("$")))
    if c_total is None and months:
        c_total = round(sum(months), 2)
    if c_total is None:
        return dict(status="none", amounts={}, detail={}, notes=[], checks=["1095-A line 33 column C not found"])
    note = f"1095-A: advance PTC {c_total:,.2f} (line 33C)"
    return dict(status="read", amounts={}, detail=dict(aptc=c_total), notes=[], checks=[], inv_note=note, memo_only=True)


# ---------------------------------------------------------------- "BOX n:" statements (e.g. Coinbase futures 1099-B / 1099-INT)
BOX_ROW_MAP = {
    "1099-B": {"11": "s1256_11"},
    "1099-INT": {"1": "int_1", "3": "int_3", "4": "fit", "6": "int_6", "8": "int_8"},
    "1099-DIV": {"1A": "div_1a", "1B": "div_1b", "2A": "div_2a", "3": "div_3", "4": "fit", "7": "div_7", "12": "div_12"},
    "1099-MISC": {"2": "misc_2", "3": "misc_3", "4": "fit", "8": "misc_8"},
}


def parse_box_rows(path, pw=None) -> dict:
    """Statements that print one 'BOX n: label .... amount' row per box, grouped under a 1099-x heading."""
    doc, _ = open_pdf(path, [pw] if pw else None)
    found, fit, sect = {}, 0.0, None
    with doc:
        for page in doc:
            for ws in _rows(page.get_text("words")):
                txt = " ".join(w[4] for w in ws)
                h = re.match(r"(1099-(?:B|INT|DIV|MISC))\b", txt, re.I)
                if h:
                    sect = h.group(1).upper()
                m = re.match(r"BOX\s+(\w+):", txt, re.I)
                amts = [w for w in ws if AMT_W.match(w[4]) or re.fullmatch(r"-?[\d,]*\d\.\d{2}", w[4])]
                if not (m and amts and sect):
                    continue
                key = BOX_ROW_MAP.get(sect, {}).get(m.group(1).upper())
                if not key:
                    continue
                v = _n(amts[-1][4].lstrip("$"))
                if key == "fit":
                    fit += v
                elif key not in found:
                    found[key] = v
    if not found:
        return dict(status="none", amounts={}, detail={}, notes=[], checks=["box amounts not found"], fit=0.0)
    res = _amounts_1099(found, {}, "", {})
    res["checks"] = [c for c in res["checks"] if "not read" not in c]
    res["status"] = "read"
    res["fit"] = round(fit, 2)
    return res


# "1a. TOTAL ORDINARY DIVIDENDS ....... $17,826.93" - a summary page that lists each form's boxes one per row, often two
# forms side by side (Morgan Stanley stock plan: 1099-DIV left, 1099-B right). The column's form = the heading above it.
LIST_MAP = dict(BOX_ROW_MAP)
LIST_MAP["1099-DIV"] = dict(BOX_ROW_MAP["1099-DIV"], **{"5": "div_5"})
LIST_MAP["1099-B"] = {"1D": "b_proceeds", "1E": "b_cost", "1G": "b_wash", "4": "fit", "11": "s1256_11"}
_BOXTOK = re.compile(r"^(\d{1,2}[a-hA-H]?)[.:]$")


def parse_box_list(path, pw=None) -> dict:
    doc, _ = open_pdf(path, [pw] if pw else None)
    found, fit, heads = {}, 0.0, []
    with doc:
        for page in doc:
            heads = []
            for ws in _rows(page.get_text("words")):
                txt = " ".join(w[4] for w in ws)
                for m in re.finditer(r"FORM\s+(1099)[\s-]*(DIV|INT|B|MISC)\b", txt, re.I):
                    # x of the heading: the word "FORM" before this match
                    pos = len(txt[:m.start()].split())
                    heads = [h for h in heads if abs(h[0] - ws[pos][0]) > 30] + [(ws[pos][0], "1099-" + m.group(2).upper())]
                if not heads:
                    continue
                starts = [i for i, w in enumerate(ws) if _BOXTOK.match(w[4]) and i + 1 < len(ws) and re.match(r"[A-Za-z]", ws[i + 1][4])]
                for k, i in enumerate(starts):
                    seg = ws[i:(starts[k + 1] if k + 1 < len(starts) else len(ws))]
                    amts = [w for w in seg if re.fullmatch(r"\(?-?\$?[\d,]*\d\.\d{2}\)?", w[4])]
                    if not amts:
                        continue
                    sect = max((h for h in heads if h[0] <= seg[0][0] + 60), key=lambda h: h[0], default=None)
                    if not sect:
                        continue
                    key = LIST_MAP.get(sect[1], {}).get(_BOXTOK.match(seg[0][4]).group(1).upper())
                    if not key:
                        continue
                    v = _n(amts[0][4].replace("$", ""))
                    if key == "fit":
                        fit += v
                    elif key not in found:
                        found[key] = v
    if not found:
        return dict(status="none", amounts={}, detail={}, notes=[], checks=["box list not found"], fit=0.0)
    b, extra = {}, []
    pr, co, wa = found.pop("b_proceeds", 0.0), found.pop("b_cost", 0.0), found.pop("b_wash", 0.0)
    if pr or co:                                            # summary only: no term on this page
        b["und"] = dict(proceeds=pr, cost=co, wash=wa, md=0.0, gain=round(pr - co + wa, 2))
        extra.append("1099-B summary only (no short / long-term split on it) — check the transaction detail")
    res = _amounts_1099(found, b, "", {})
    res["checks"] = [c for c in res["checks"] if "not read" not in c] + extra
    res["status"] = "partial" if extra else "read"
    res["fit"] = round(fit, 2)
    if not (pr or co):
        res["notes"].append("1099-B: no sales (proceeds 0)")
    return res


def parse_document(d: dict) -> dict | None:
    fam = d.get("family")
    path = d.get("path")
    try:
        if fam in ("1099misc", "1099nec"):
            kind = fam[4:]
            r = parse_1099_form(path, kind)
            if r["status"] == "none" and kind == "misc":
                r2 = parse_1099(path)              # brokerage-style 1099-MISC (label then amount in the text)
                return r2 if r2.get("amounts") else r
            return r
        if fam == "1099int":
            r = parse_1099(path)
            if r["status"] != "read" or "int_1" not in r.get("detail", {}):
                r2 = parse_1099int_rows(path)
                if r2["status"] == "read":
                    return r2
            return r
        if fam in ("composite", "1099div", "1099b", "1099oid", "1099da"):
            r = parse_1099(path)
            if r["status"] == "none":
                r2 = parse_box_rows(path)
                if r2["status"] == "read":
                    return r2
            if r["status"] != "read":                  # "1a. TOTAL ORDINARY DIVIDENDS ... $x" summary pages
                r3 = parse_box_list(path)
                if r3["status"] != "none" and r3.get("amounts"):
                    return r3
            return r
        if fam == "w2":
            return parse_w2(path)
        if fam == "koinly":
            return parse_koinly(path, d.get("doc_type", ""))
        if fam == "1099r":
            return parse_1099r(path)
        if fam == "1098e":
            return parse_1098e(path)
        if fam == "1098":
            return parse_1098(path)
        if fam == "1098t":
            return parse_1098t(path)
        if fam == "1095a":
            return parse_1095a(path)
        if fam == "1099sa":
            return parse_1099sa(path)
        if fam == "ssa":
            return parse_ssa(path)
    except Exception as e:  # noqa: BLE001
        return dict(status="none", amounts={}, detail={}, notes=[], checks=[f"couldn't read: {type(e).__name__}: {e}"])
    return None
