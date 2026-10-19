"""
k1_parser.py - read Schedule K-1 (Form 1065) pages from a PDF.
(Copy of C:\\dev\\K-1_interpretation\\k1_parser.py for 1040 Ultimate - only change: optional PDF password.)

Layout-independent: finds the printed box labels on each page (their position
differs by software vendor) and assigns each filled-in value to the box whose
label sits directly above it. Checkmarks are read from "X" characters in the
data font or from drawn X lines (IRS fillable-form style).
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field, asdict

import pdfplumber

# ---------------------------------------------------------------- patterns
AMOUNT_RE = re.compile(r"^\(?-?\$?[\d,]*\d(\.\d*)?\)?\.?$")
CODE_RE = re.compile(r"^([A-Z]{1,3})(\*)?$")

# Part III box labels (lower-case phrase that starts the printed label)
PART3 = [
    ("1", r"ordinary business income"),
    ("2", r"net rental real estate"),
    ("3", r"other net rental"),
    ("4a", r"guaranteed payments for services"),
    ("4b", r"guaranteed payments for capital"),
    ("4c", r"total guaranteed payments"),
    ("5", r"interest income"),
    ("6a", r"ordinary dividends"),
    ("6b", r"qualified dividends"),
    ("6c", r"dividend equivalents"),
    ("7", r"royalties"),
    ("8", r"net short-term capital"),
    ("9a", r"net long-term capital"),
    ("9b", r"collectibles"),
    ("9c", r"unrecaptured section 1250"),
    ("10", r"net section 1231"),
    ("11", r"other income"),
    ("12", r"section 179 deduction"),
    ("13", r"other deductions"),
    ("22", r"more than one activity for at-risk"),
    ("23", r"more than one activity for passive"),
    ("14", r"self-employment earnings"),
    ("15", r"^(15\s*)?credits"),
    ("16", r"schedule k-3 is attached|^16$"),
    ("17", r"alternative min"),
    ("18", r"tax-exempt income"),
    ("19", r"^(19\s*)?distributions"),
    ("20", r"^(20\s*)?other information"),
    ("21", r"foreign taxes paid"),
]
CODE_BOXES = {"11", "13", "14", "15", "17", "18", "19", "20"}
RIGHT_COL = {"14", "15", "16", "17", "18", "19", "20", "21"}

# Part I/II row labels at the left margin
ROW_LABELS = ["A", "B", "C", "D", "E", "F", "G", "H1", "H2", "I1", "I2", "J",
              "K1", "K2", "K3", "L", "M", "N"]

# word just to the right of a checkbox -> meaning
CHECK_WORDS = {
    "general": ("G", "General"), "limited": ("G", "Limited"),
    "domestic": ("H1", "Domestic"), "foreign": ("H1", "Foreign"),
    "yes": ("M", "Yes"), "no": ("M", "No"),
    "sale": ("J_dec", "Sale"), "exchange": ("J_dec", "Exchange"),
    "final": ("final", True), "amended": ("amended", True),
}


@dataclass
class Line:
    box: str
    code: str | None = None
    amt: float | None = None
    stmt: bool = False       # marked * or STMT
    check: bool = False      # checkbox-only box (16, 22, 23)
    raw: str = ""

    @property
    def key(self):
        return self.box + (self.code or "")


@dataclass
class K1:
    page: int
    form: str = ""
    year: int | None = None
    name: str = ""
    final: bool = False
    amended: bool = False
    ptp: bool = False
    G: str | None = None
    H1: str | None = None
    I1: str = ""
    ein: str = ""
    address: list = field(default_factory=list)
    tax_begin: str = ""
    tax_end: str = ""
    J: dict = field(default_factory=dict)
    J_dec: str | None = None
    K1: dict = field(default_factory=dict)
    K2: bool = False
    K3: bool = False
    M: str | None = None
    N: list | None = None
    L: dict = field(default_factory=dict)
    lines: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d["lines"] = [dict(asdict(l), key=l.key) for l in self.lines]
        return d


# ---------------------------------------------------------------- helpers
def parse_amount(t: str) -> float | None:
    t = t.strip().replace("$", "")
    if not AMOUNT_RE.match(t):
        return None
    neg = t.startswith("(") or t.startswith("-")
    t = t.strip("()-").rstrip(".")
    try:
        v = float(t.replace(",", ""))
    except ValueError:
        return None
    return -v if neg else v


def _is_data_font(fontname: str, has_courier: bool) -> bool:
    if has_courier:
        return "Courier" in fontname
    # IRS fillable / flattened forms: labels use embedded subset fonts (ABCDEF+Name),
    # typed values use a standard (non-subset) font.
    return "+" not in fontname


def _segments(words, gap=14):
    """Group label words into same-line segments split at large x gaps."""
    rows = {}
    for w in words:
        rows.setdefault(round(w["top"]), []).append(w)
    # merge rows within 1.5pt
    keys = sorted(rows)
    merged = []
    for k in keys:
        if merged and k - merged[-1][0] <= 1.5:
            merged[-1][1].extend(rows[k])
        else:
            merged.append([k, list(rows[k])])
    segs = []
    for _, ws in merged:
        ws.sort(key=lambda w: w["x0"])
        cur = [ws[0]]
        for w in ws[1:]:
            if w["x0"] - cur[-1]["x1"] > gap:
                segs.append(cur)
                cur = [w]
            else:
                cur.append(w)
        segs.append(cur)
    out = []
    for s in segs:
        out.append({"text": " ".join(w["text"] for w in s), "x0": s[0]["x0"],
                    "x1": s[-1]["x1"], "top": min(w["top"] for w in s), "words": s})
    return out


def _group_lines(words, tol=3.5):
    words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines = []
    for w in words:
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in lines]


# ---------------------------------------------------------------- page
def parse_page(pg, page_no: int) -> K1 | None:
    text = pg.extract_text() or ""
    if not re.search(r"Schedule\s*K-1", text, re.I):
        return None
    k = K1(page=page_no)
    if re.search(r"\(Form\s*1065\)", text):
        k.form = "1065"
    elif re.search(r"1120-?S", text):
        k.form = "1120-S"
    elif re.search(r"\(Form\s*1041\)", text):
        k.form = "1041"
    m = re.search(r"Schedule K-1 \(Form 1065\) (20\d\d)", text) or re.search(r"\b(20\d\d)\b", text)
    if m:
        k.year = int(m.group(1))
    if k.form != "1065":
        k.warnings.append(f"Form type {k.form or 'unknown'} — only Form 1065 rules are built.")
        return k

    has_courier = any("Courier" in c["fontname"] for c in pg.chars)
    words = pg.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False)
    data = [w for w in words if _is_data_font(w["fontname"], has_courier)
            and 55 < w["top"] < 755 and w["text"].strip("​ ")]
    labels = [w for w in words if not _is_data_font(w["fontname"], has_courier)
              and "Dingbat" not in w["fontname"]]
    segs = _segments(labels)

    # --- Part III anchors
    anchors = {}
    for box, pat in PART3:
        for s in segs:
            t = s["text"].lower()
            t2 = re.sub(r"^\d{1,2}[abc]?\s*", "", t)
            if re.search(pat, t2) or re.search(pat, t):
                if s["x0"] > 290 and box not in anchors:
                    anchors[box] = s
                    break
    lx = [anchors[b]["x0"] for b in anchors if b not in RIGHT_COL]
    rx = [anchors[b]["x0"] for b in anchors if b in RIGHT_COL]
    if len(lx) < 8 or len(rx) < 4:
        k.warnings.append("Couldn't locate Part III box labels — layout not recognised; check this K-1 manually.")
        return k
    left_x = statistics.median(lx) - 10
    right_x = statistics.median(rx) - 15

    # --- Part I/II row anchors (bold letters at the left margin)
    rows = {}
    for w in labels:
        if w["text"] in ROW_LABELS and w["x0"] < 60 and w["text"] not in rows:
            rows[w["text"]] = w["top"]
    row_order = sorted(rows.items(), key=lambda kv: kv[1])

    def row_of(top):
        best = None
        for name, t in row_order:
            if t <= top + 6:
                best = name
        return best

    def p3_box(x, top):
        col = [b for b in anchors if (b in RIGHT_COL) == (x >= right_x)]
        best, bt = None, -1
        for b in col:
            t = anchors[b]["top"]
            if t <= top + 3 and t > bt:
                best, bt = b, t
        return best

    # --- checkmarks: X in data font + drawn X lines
    marks = []
    for w in data:
        if w["text"] in ("X", "x", "✓", "✔"):
            marks.append(((w["x0"] + w["x1"]) / 2, w["top"] + 3, w))
    seen = set()
    for l in pg.lines:
        wdt, hgt = abs(l["x1"] - l["x0"]), abs(l["bottom"] - l["top"])
        if 2 < wdt < 10 and 2 < hgt < 10:
            c = (round((l["x0"] + l["x1"]) / 2), round((l["top"] + l["bottom"]) / 2))
            if c not in seen:
                seen.add(c)
                marks.append((c[0], c[1] - 2, None))
    mark_words = {id(m[2]) for m in marks if m[2] is not None}

    for mx, mtop, _ in marks:
        # word immediately to the right on the same line
        right_words = [w for w in labels if 0 <= w["x0"] - mx < 30 and abs(w["top"] - mtop) < 7]
        right_words.sort(key=lambda w: w["x0"])
        rw = right_words[0]["text"].lower().strip(".,") if right_words else ""
        if mtop < 75 and rw in ("final", "amended"):
            setattr(k, rw, True)
            continue
        if mx >= left_x:
            b = p3_box(mx, mtop)
            if b in ("16", "22", "23"):
                k.lines.append(Line(box=b, check=True))
            continue
        row = row_of(mtop)
        if rw in CHECK_WORDS and CHECK_WORDS[rw][0] in ("G", "H1", "M", "J_dec"):
            attr, val = CHECK_WORDS[rw]
            if attr == "M" and row != "M":
                continue
            setattr(k, attr, val)
        elif row == "D":
            k.ptp = True
        elif row in ("K2", "K3"):
            setattr(k, row, True)

    # --- partnership name (row B), entity type (I1)
    def region(r1, r2, xmax):
        t1 = rows.get(r1)
        t2 = rows.get(r2, t1 + 40 if t1 else None)
        if t1 is None:
            return []
        return [w for w in data if t1 - 4 <= w["top"] < t2 - 4 and w["x0"] < xmax and id(w) not in mark_words]

    name_lines = _group_lines(region("B", "C", left_x + 12))
    nm = []
    for ln in name_lines[:2]:
        t = " ".join(w["text"] for w in ln).strip()
        if not t or re.match(r"^\d", t) or re.search(r"\b(SUITE|STE|PO BOX|P\.O\.)\b", t, re.I):
            break
        nm.append(t)
    k.name = " ".join(nm)
    # address = the remaining printed lines under the name (nothing if redacted)
    k.address = [" ".join(w["text"] for w in ln).strip() for ln in name_lines[len(nm):]]
    k.address = [a for a in k.address if a]

    # EIN (Part I, item A) — whatever is printed: full, last 4, or nothing
    ein_w = [w for w in region("A", "B", left_x) if re.search(r"\d", w["text"])]
    k.ein = " ".join(w["text"] for w in ein_w).strip()

    # tax year beginning / ending (header, above Part I) -> mm/dd/yy; blank if not printed
    top_a = rows.get("A", 160)
    dates = sorted([w for w in data if w["top"] < top_a - 10
                    and re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", w["text"])], key=lambda w: (w["top"], w["x0"]))
    def mmddyy(t):
        m_, d_, y_ = t.split("/")
        return f"{int(m_):02d}/{int(d_):02d}/{y_[-2:]}"
    if len(dates) >= 1:
        k.tax_begin = mmddyy(dates[0]["text"])
    if len(dates) >= 2:
        k.tax_end = mmddyy(dates[1]["text"])
    i1 = region("I1", "I2", left_x)
    k.I1 = " ".join(w["text"] for w in i1).title()

    # --- J percentages
    jw = [w for w in region("J", "K1", left_x) if re.match(r"^\d+(\.\d+)?%?$", w["text"])]
    rowlab = {w["text"].lower(): w["top"] for w in labels
              if w["text"].lower() in ("profit", "loss", "capital") and rows.get("J", 0) < w["top"] < rows.get("K1", 999)}
    if jw and rowlab:
        xs = sorted(w["x0"] for w in jw)
        split = (xs[0] + xs[-1]) / 2 if xs[-1] - xs[0] > 40 else None
        for rname, rt in rowlab.items():
            vals = sorted([w for w in jw if abs(w["top"] - rt) < 6], key=lambda w: w["x0"])
            beg = end = None
            for w in vals:
                v = float(w["text"].rstrip("%"))
                if split is None or w["x0"] < split:
                    beg = v
                else:
                    end = v
            k.J[rname.capitalize()] = [beg, end]

    # --- K1 liabilities
    kw = [(w, parse_amount(w["text"])) for w in region("K1", "K2", left_x)]
    kw = [(w, v) for w, v in kw if v is not None]
    ktop, k2top = rows.get("K1", 0), rows.get("K2", 999)
    kl = {}
    for w in labels:
        if ktop < w["top"] < k2top:
            t = w["text"]
            if t == "Nonrecourse" and "Nonrecourse" not in kl:
                kl["Nonrecourse"] = w["top"]
            elif t == "Qualified" and "Qualified nonrecourse financing" not in kl:
                kl["Qualified nonrecourse financing"] = w["top"]
            elif t.startswith("Recourse") and "Recourse" not in kl:
                kl["Recourse"] = w["top"]
    endh = [w["x0"] for w in labels if w["text"] == "Ending" and ktop - 2 < w["top"] < k2top]
    ksplit = endh[0] - 40 if endh else 230
    for t in ("Nonrecourse", "Qualified nonrecourse financing", "Recourse"):
        beg = end = 0.0
        if t in kl:
            for w, v in kw:
                if -4 < w["top"] - kl[t] < 12 if t == "Qualified nonrecourse financing" else abs(w["top"] - kl[t]) < 6:
                    if w["x0"] < ksplit:
                        beg = v
                    else:
                        end = v
        k.K1[t] = [beg, end]

    # --- N
    nw = [(w, parse_amount(w["text"])) for w in region("N", "ZZZ", left_x)]
    nw = [(w, v) for w, v in nw if v is not None]
    if nw:
        nl = sorted([w["top"] for w in labels if w["text"] in ("Beginning", "Ending") and w["top"] > rows.get("N", 999)])
        beg = end = 0.0
        for w, v in nw:
            if len(nl) >= 2 and abs(w["top"] - nl[1]) < abs(w["top"] - nl[0]):
                end = v
            else:
                beg = v
        k.N = [beg, end]

    # --- L capital account analysis
    lt, mt = rows.get("L"), rows.get("M")
    if lt is not None:
        mt = mt or lt + 100
        lsegs = [sg for sg in segs if lt - 2 <= sg["top"] < mt - 2 and sg["x0"] < left_x]
        pats = [("Beginning capital account", r"beginning capital"), ("Capital contributed during the year", r"capital contributed"),
                ("Current year net income (loss)", r"current year"), ("Other increase (decrease)", r"other increase"),
                ("Withdrawals and distributions", r"withdrawals"), ("Ending capital account", r"ending capital")]
        ltops = {}
        for name, pat in pats:
            for sg in lsegs:
                if re.search(pat, sg["text"].lower()):
                    ltops[name] = sg["top"]
                    break
        lw = [(w, parse_amount(w["text"])) for w in data if lt - 2 <= w["top"] < mt - 4 and w["x0"] < left_x]
        lw = [(w, v) for w, v in lw if v is not None]
        for name in ltops:
            best = None
            for w, v in lw:
                d = abs(w["top"] - ltops[name])
                if d < 7 and (best is None or d < best[0]):
                    best = (d, v)
            val = best[1] if best else 0.0
            if name == "Withdrawals and distributions":
                val = abs(val)
            k.L[name] = val

    # --- Part III values
    p3 = [w for w in data if w["x0"] >= left_x and id(w) not in mark_words]
    cells = {}
    for w in p3:
        b = p3_box(w["x0"], w["top"])
        if b:
            cells.setdefault(b, []).append(w)
    for b, ws in cells.items():
        for ln in _group_lines(ws):
            toks = [w["text"] for w in ln]
            raw = " ".join(toks)
            stmt = any("*" in t for t in toks) or any(t.upper() == "STMT" for t in toks)
            code, amt = None, None
            after_stmt = False
            for t in toks:
                tt = t.replace("*", "")
                if not tt:
                    continue
                if tt.upper() == "STMT":
                    after_stmt = True
                    continue
                if after_stmt and re.fullmatch(r"\d{1,2}", tt):
                    after_stmt = False  # statement reference number, e.g. "STMT 1"
                    continue
                cm = CODE_RE.match(tt)
                if cm and b in CODE_BOXES and code is None:
                    code = cm.group(1)
                    continue
                v = parse_amount(tt)
                if v is not None:
                    amt = v
            if b in ("22", "23"):
                if stmt or amt is not None:
                    k.lines.append(Line(box=b, check=True, stmt=True, raw=raw))
                continue
            if b in CODE_BOXES and code is None and amt is not None:
                # amount on its own line under a code (continuation) -> attach to previous code line
                prev = [l for l in k.lines if l.box == b and l.code]
                if prev and prev[-1].amt is None:
                    prev[-1].amt = amt
                    prev[-1].stmt = prev[-1].stmt or stmt
                    continue
                k.warnings.append(f"Box {b}: amount {raw} has no code — check the K-1.")
            if amt is None and not stmt and code is None:
                continue
            k.lines.append(Line(box=b, code=code, amt=amt, stmt=stmt, raw=raw))

    # de-duplicate checkbox lines
    uniq, seenk = [], set()
    for l in k.lines:
        sig = (l.box, l.code, l.amt, l.check)
        if l.check and sig in seenk:
            continue
        seenk.add(sig)
        uniq.append(l)
    order = [b for b, _ in PART3]
    k.lines = sorted(uniq, key=lambda l: (order.index(l.box) if l.box in order else 99))
    return k


def parse_pdf(path, password: str | None = None) -> list[K1]:
    out = []
    with pdfplumber.open(path, password=password or "") as pdf:
        for i, pg in enumerate(pdf.pages, start=1):
            k = parse_page(pg, i)
            if k is not None:
                out.append(k)
    return out


if __name__ == "__main__":
    import json, sys
    for k in parse_pdf(sys.argv[1]):
        print(json.dumps(k.to_dict()))
