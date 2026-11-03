"""
k1_summary.py - internal Income Summary built from the K-1s (same layout as the office template),
plus the Excel export (Income Summary, Carryforwards, K-1 Detail).

Mapping (K-1 boxes -> summary lines):
  Interest Income            box 5
  Dividends Income           box 6a
  Long-Term Capital Gains    box 9a + box 10 (§1231, flagged) + 11S ticked Long-term; 60% of box 11C on its own row
  Short Term Cap. Gains      box 8 + 11S ticked Short-term; 40% of box 11C (§1256) on its own row
  Rental & Royalties         boxes 2 + 3 + 7
  K-1s Ordinary Income       3 subtotals:
                               Schedule E = box 1 + guaranteed payments (4c, or 4a+4b) + box 11 (other codes, and 11ZZ unless "Schedule 1" is ticked)
                                            - 13ZZ (UltraTax deducts it as a K-1 loss on Schedule E)
                               Other portfolio income (loss) = 11A
                               Other income (loss) - 1040, Sch 1 = 11ZZ when "Schedule 1" is ticked on the K-1 Interpreter (line flag sch1)
W-2, IRA, Pension, Social Security and Schedule C are not K-1 items; they stay as blank lines.
Carryforwards are NOT added to income - they get their own sheet.
"""
from __future__ import annotations

from io import BytesIO

SECTIONS = [
    # key, total label, from K-1s?, red adjustment lines placed just above the total
    ("w2", "Total W-2 Income", False, []),
    ("int", "Total Interest Income", True, []),
    ("div", "Total Dividends Income", True, []),
    ("ira", "Total IRA Distributions", False, []),
    ("pen", "Total Pension and annuities", False, []),
    ("ss", "Total Social Security Benefits", False, []),
    ("lt", "Total Long-Term Capital Gains", True, ["add back disallowed losses"]),
    ("st", "Total Short Term Cap. Gains", True, ["add back disallowed losses"]),
    ("sch_c", "Total Schedule C", False, []),
    ("rent", "Total Rental & Royalties Gain/ Loss", True, []),
    ("ord", "Total K-1s Ordinary Income", True, ["minus losses carried over from prior years", "Add back disallowed losses"]),
]
BLANK_ROWS = 3  # empty lines for sections with no documents
# subtotals inside "Total K-1s Ordinary Income"
ORD_SUBS = [("E", "Schedule E"), ("A", "Other portfolio income (loss)"), ("1", "Other income (loss) - 1040, Sch 1")]


def _amts(k):
    """box+code -> summed amount, plus statement-only keys."""
    a, stmt_only, stmt = {}, [], set()
    for l in k["lines"]:
        key = l["box"] + (l.get("code") or "")
        if key == "11S" and l.get("s11") in ("ST", "LT"):   # ticked Short-term / Long-term on the K-1 Interpreter
            key = "11S_" + l["s11"]
        if l.get("check"):
            continue
        if l.get("amt") is None:
            if l.get("stmt"):
                stmt_only.append(key)
            continue
        a[key] = a.get(key, 0) + l["amt"]
        if l.get("stmt"):
            stmt.add(key)
    return a, stmt_only, stmt


def _money(v):
    return f"{v:,.0f}"  # no $ sign — easy to copy-paste into UltraTax


def k1_section_rows(k):
    """Return {section_key: (amount, [comments])} for one K-1."""
    a, stmt_only, stmt = _amts(k)
    out = {}

    def put(sec, keys, extra_comments=()):
        amt = sum(a.get(x, 0) for x in keys)
        com = list(extra_comments)
        com += [f"Box {x} per statement (*) — verify" for x in keys if x in stmt and a.get(x)]
        com += [f"Box {x} is on a statement only — not included" for x in stmt_only if x in keys or x.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") in keys]
        if amt or com:
            out[sec] = (amt, com)

    put("int", ["5"])
    put("div", ["6a"], [f"Includes qualified dividends {_money(a['6b'])} (6b)"] if a.get("6b") else [])
    c = [f"Includes §1231 {_money(a['10'])} (box 10) — check 5-yr nonrecaptured §1231 losses"] if a.get("10") else []
    if a.get("9b"):
        c.append(f"9a includes collectibles {_money(a['9b'])} (9b)")
    if a.get("9c"):
        c.append(f"9a includes unrecaptured §1250 {_money(a['9c'])} (9c)")
    c1256 = a.get("11C", 0)   # Section 1256 contracts: 60% long-term / 40% short-term (Form 6781) - own rows
    put("lt", ["9a", "10"], c)
    put("st", ["8"])
    if c1256:
        st_part = round(c1256 * 0.4)            # rounded like Form 6781 lines 8 / 9
        lt_part = round(c1256 * 0.6)
        out["st_1256"] = (st_part, [f"40% of §1256 contracts {_money(c1256)} (box 11C) — Form 6781 line 8"])
        out["lt_1256"] = (lt_part, [f"60% of §1256 contracts {_money(c1256)} (box 11C) — Form 6781 line 9"])
    for sec, k11, word in (("lt", "11S_LT", "long-term"), ("st", "11S_ST", "short-term")):   # 11S ticked ST / LT
        if a.get(k11):
            amt, com = out.get(sec, (0, []))
            out[sec] = (amt + a[k11], com + [f"Includes box 11 S {_money(a[k11])} ({word}, ticked on the K-1 Interpreter)"])
    put("rent", ["2", "3", "7"], [f"Includes royalties {_money(a['7'])} (box 7)"] if a.get("7") else [])

    gp_keys = ["4c"] if a.get("4c") else ["4a", "4b"]
    sch1 = any(l.get("sch1") for l in k["lines"] if l["box"] == "11" and l.get("code") == "ZZ")
    b11 = [x for x in a if x.startswith("11") and x not in ("11A", "11C") and "_" not in x and not (x == "11ZZ" and sch1)]
    c = []
    if any(a.get(x) for x in gp_keys):
        c.append(f"Includes guaranteed payments {_money(sum(a.get(x, 0) for x in gp_keys))} ({'/'.join(gp_keys)}) — review SE tax")
    for x in b11:
        c.append(f"Includes box 11 code {x[2:] or '?'} {_money(a[x])} — check code / form")
    if "11" in stmt_only:
        c.append("Box 11 on a statement only — not included")
    if k.get("G") == "General":
        c.append("General partner — review SE tax (14A)")
    if a.get("12"):
        c.append(f"§179 deduction {_money(a['12'])} (box 12) not included — partner-level limits")
    if a.get("13ZZ"):
        c.append(f"Includes 13ZZ ({_money(abs(a['13ZZ']))}) — UltraTax deducts it as a K-1 loss on Schedule E")
    put("ord_E", ["1"] + gp_keys + b11 + ["13ZZ"], c)
    if "ord_E" in out and a.get("13ZZ"):   # 13ZZ is a deduction: subtract it
        amt, com = out["ord_E"]
        out["ord_E"] = (amt - a["13ZZ"] - abs(a["13ZZ"]), com)
    if a.get("11A"):
        out["ord_A"] = (a["11A"], ["Box 11 A — other portfolio income"] + (["per statement (*) — verify"] if "11A" in stmt else []))
    if sch1 and a.get("11ZZ"):
        out["ord_1"] = (a["11ZZ"], ["Box 11 ZZ — Schedule 1 ticked"])
    return out


def build_summary(k1s):
    """k1s: list of K1 dicts (to_dict). Returns sections with alphabetical document rows."""
    ks = sorted([k for k in k1s if k.get("form") == "1065"], key=lambda k: (k.get("name") or "").lower())
    per = [(k, k1_section_rows(k)) for k in ks]
    sections = []
    for key, label, from_k1, adj in SECTIONS:
        rows, subs = [], None
        doc = lambda k: "K-1 " + (k.get("name") or f"page {k['page']}")
        if from_k1 and key == "ord":
            subs = []
            for sk, slabel in ORD_SUBS:
                srows = []
                for k, secs in per:
                    if f"ord_{sk}" in secs:
                        amt, com = secs[f"ord_{sk}"]
                        srows.append({"doc": doc(k), "page": k["page"], "amt": amt, "comment": "; ".join(com),
                                      "sub": sk, "rid": f"ord|{sk}|{k['page']}"})
                subs.append({"key": sk, "label": slabel, "rows": srows, "total": sum(r["amt"] for r in srows)})
                rows += srows
        elif from_k1:
            for k, secs in per:
                if key in secs:
                    amt, com = secs[key]
                    rows.append({"doc": doc(k), "page": k["page"], "amt": amt, "comment": "; ".join(com),
                                 "rid": f"{key}|{k['page']}"})
                if key + "_1256" in secs:   # box 11C share on its own row, right under the K-1's own row
                    amt, com = secs[key + "_1256"]
                    rows.append({"doc": doc(k) + " — §1256 (11C)", "page": k["page"], "amt": amt, "comment": "; ".join(com),
                                 "rid": f"{key}1256|{k['page']}"})
        sections.append({"key": key, "label": label, "from_k1": from_k1, "adj": adj, "rows": rows, "subs": subs,
                         "adj_rids": [f"{key}|adj|{i}" for i in range(len(adj))],
                         "total": sum(r["amt"] for r in rows)})
    total = sum(s["total"] for s in sections)
    return {"sections": sections, "total_income": total}


# ------------------------------------------------------------------ Excel
def write_xlsx(k1s, ut=None, pcomments=None, items=None, filename="", corr=None):
    """Return xlsx bytes. ut / pcomments: {page: text}. items: {item_id: {v, c}}.
    corr: {row id: number} — Correction column typed on the totals tab (blank = same as Federal)."""
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    ut = {str(k): v for k, v in (ut or {}).items()}
    pcomments = {str(k): v for k, v in (pcomments or {}).items()}
    items = items or {}
    S = build_summary(k1s)

    def _num(v):
        try:
            t = str(v).replace(",", "").replace("$", "").strip()
            if not t:
                return None
            neg = t.startswith("(") and t.endswith(")")
            t = t.strip("()")
            return -float(t) if neg else float(t)
        except (TypeError, ValueError):
            return None
    corr = {str(k): _num(v) for k, v in (corr or {}).items()}
    corr = {k: v for k, v in corr.items() if v is not None}

    F = "Arial"
    f_norm = Font(name=F, size=10)
    f_bold = Font(name=F, size=10, bold=True)
    f_red = Font(name=F, size=10, color="FF0000")
    f_blue = Font(name=F, size=10, color="0000FF")
    f_head = Font(name=F, size=10, bold=True)
    f_title = Font(name=F, size=12, bold=True, color="003366")
    grey = PatternFill("solid", fgColor="EDEDED")
    yellow = PatternFill("solid", fgColor="FEF3E2")   # orange (input cells) — no yellow
    hdr = PatternFill("solid", fgColor="DCE6F1")
    thin = Side(style="thin", color="000000")
    med = Side(style="medium", color="000000")
    money = '#,##0;-#,##0;"-"'

    wb = Workbook()
    ws = wb.active
    ws.title = "Income Summary"
    ws.column_dimensions["A"].width = 62
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 60
    ws.column_dimensions["E"].width = 50
    ws.column_dimensions["F"].width = 10

    ws["A1"] = "Internal Income Summary" + (f" — {filename}" if filename else "")
    ws["A1"].font = f_title
    r = 3
    for col, t in zip("ABCDEF", ["Document/s", "Federal", "Correction", "Comment", "Comment 2", "UT #"]):
        c = ws[f"{col}{r}"]
        c.value, c.font, c.fill = t, f_head, hdr
        c.border = Border(bottom=thin)
        c.alignment = Alignment(horizontal="center" if col in "BC" else "left")
    r += 1
    total_cells = []

    def vborders(row):
        for col in "BC":
            ws[f"{col}{row}"].border = Border(left=med, right=med)

    def doc_row(d):
        nonlocal r
        if d:
            ws[f"A{r}"] = d["doc"]
            pc = pcomments.get(str(d["page"]), "")
            if pc:
                ws[f"E{r}"] = pc
                ws[f"E{r}"].alignment = Alignment(wrap_text=True, vertical="top")
            if ut.get(str(d["page"])):
                ws[f"F{r}"] = ut[str(d["page"])]
                ws[f"F{r}"].alignment = Alignment(horizontal="center")
            ws[f"B{r}"] = d["amt"]
            ws[f"B{r}"].font = f_blue
            if d["comment"]:
                ws[f"D{r}"] = d["comment"]
        ws[f"A{r}"].font = f_norm
        ws[f"B{r}"].number_format = money
        if d and d.get("rid") in corr:
            ws[f"C{r}"] = corr[d["rid"]]
            ws[f"C{r}"].font = Font(name=F, size=10, bold=True, color="C00000")   # user's correction
        else:
            ws[f"C{r}"] = f"=B{r}"
        ws[f"C{r}"].number_format = money
        ws[f"D{r}"].font = Font(name=F, size=9, color="7F6000")
        ws[f"E{r}"].font = Font(name=F, size=9, color="003366")
        ws[f"F{r}"].font = f_norm
        vborders(r)
        r += 1

    def total_row(label, b, c, light=False):
        nonlocal r
        ws[f"A{r}"] = label
        ws[f"B{r}"] = b
        ws[f"C{r}"] = c
        for col in "ABCDEF":
            ws[f"{col}{r}"].fill = PatternFill("solid", fgColor="F5F5F5") if light else grey
            ws[f"{col}{r}"].border = Border(bottom=thin)
            ws[f"{col}{r}"].font = f_bold
        for col in "BC":
            ws[f"{col}{r}"].number_format = money
            ws[f"{col}{r}"].border = Border(left=med, right=med, bottom=thin)
        r += 1
        return r - 1

    for s in S["sections"]:
        r += 1  # spacer like the template
        vborders(r - 1)
        parts = []          # cells that add up to the section total
        if s.get("subs"):
            for sb in s["subs"]:
                st0 = r
                for d in (sb["rows"] or [None]):
                    doc_row(d)
                parts.append(total_row("  Subtotal — " + sb["label"], f"=SUM(B{st0}:B{r-1})", f"=SUM(C{st0}:C{r-1})", light=True))
            terms_b = [f"B{x}" for x in parts]
            terms_c = [f"C{x}" for x in parts]
            a0 = r
        else:
            a0 = r
            for d in (s["rows"] or [None] * BLANK_ROWS):
                doc_row(d)
        for i, a in enumerate(s["adj"]):
            ws[f"A{r}"] = a
            ws[f"A{r}"].font = f_red
            for col in "BC":
                ws[f"{col}{r}"].fill = yellow
                ws[f"{col}{r}"].number_format = money
            rid = s["adj_rids"][i]
            if rid in corr:
                ws[f"C{r}"] = corr[rid]
                ws[f"C{r}"].font = Font(name=F, size=10, bold=True, color="C00000")
            ws[f"D{r}"] = "Enter manually — carryforwards are not added automatically (see Carryforwards tab)"
            ws[f"D{r}"].font = Font(name=F, size=9, color="7F6000")
            vborders(r)
            r += 1
        if s.get("subs"):
            if r > a0:
                terms_b.append(f"SUM(B{a0}:B{r-1})")
                terms_c.append(f"SUM(C{a0}:C{r-1})")
            tb, tc = "=" + "+".join(terms_b), "=" + "+".join(terms_c)
        else:
            tb, tc = f"=SUM(B{a0}:B{r-1})", f"=SUM(C{a0}:C{r-1})"
        total_cells.append(total_row(s["label"], tb, tc))
    r += 1
    ws[f"A{r}"] = "Total Income"
    ws[f"B{r}"] = "=" + "+".join(f"B{x}" for x in total_cells)
    ws[f"C{r}"] = "=" + "+".join(f"C{x}" for x in total_cells)
    for col in "ABCDEF":
        ws[f"{col}{r}"].fill = grey
        ws[f"{col}{r}"].font = f_bold
        ws[f"{col}{r}"].border = Border(top=thin, bottom=med)
    for col in "BC":
        ws[f"{col}{r}"].number_format = money
    r += 2
    for line in ["Legend: blue = amounts read from the K-1s · Correction = Federal unless changed on the totals tab (your numbers in bold red) ·",
                 "orange cells = enter manually (disallowed / carried-over losses). Blank lines (W-2, IRA, Pension, SS, Schedule C) are for non-K-1 documents.",
                 "Mapping: Interest = box 5 · Dividends = 6a · LT = 9a + 10 + 11S (Long-term ticked), 60% of 11C on its own row · ST = 8 + 11S (Short-term ticked), 40% of 11C on its own row · Rental & Royalties = 2 + 3 + 7 · K-1 Ordinary: Schedule E = 1 + guaranteed payments + box 11 (other codes; 11ZZ unless Schedule 1 is ticked) − 13ZZ · Other portfolio = 11A · Sch 1 = 11ZZ with Schedule 1 ticked."]:
        ws[f"A{r}"] = line
        ws[f"A{r}"].font = Font(name=F, size=8, italic=True, color="666666")
        r += 1
    ws.freeze_panes = "A4"

    # ---------------- Carryforwards
    cf = wb.create_sheet("Carryforwards")
    heads = ["Document", "UT #", "On 8582?", "Current-yr passive net (box 1/2/3/10)",
             "Prior-yr unallowed — Non-QBI (pre-2018)", "Prior-yr unallowed — For QBI & Regular", "Prior-yr unallowed — AMT",
             "§179 carryover", "Capital loss carryover", "EBIE carryforward (13K)", "Notes"]
    widths = [58, 8, 10, 18, 18, 18, 16, 14, 16, 16, 40]
    cf["A1"] = "Carryforwards — for reference only; NOT added to the Income Summary"
    cf["A1"].font = f_title
    for i, (h, w) in enumerate(zip(heads, widths), start=1):
        c = cf.cell(row=3, column=i, value=h)
        c.font, c.fill = f_head, hdr
        c.alignment = Alignment(wrap_text=True, vertical="top")
        cf.column_dimensions[get_column_letter(i)].width = w
    cf.row_dimensions[3].height = 42
    rr = 4
    for k in sorted([k for k in k1s if k.get("form") == "1065"], key=lambda k: (k.get("name") or "").lower()):
        a, _, _ = _amts(k)
        pas = sum(a.get(x, 0) for x in ("1", "2", "3", "10"))
        cf.cell(row=rr, column=1, value="K-1 " + (k.get("name") or "")).font = f_norm
        cf.cell(row=rr, column=2, value=ut.get(str(k["page"]), "")).font = f_norm
        cf.cell(row=rr, column=3, value="Yes" if pas else "No").font = f_norm
        c = cf.cell(row=rr, column=4, value=pas if pas else None)
        c.number_format, c.font = money, f_blue
        for col in range(5, 11):
            c = cf.cell(row=rr, column=col)
            c.fill, c.number_format = yellow, money
        note = []
        if a.get("12"):
            note.append(f"Box 12 §179 {_money(a['12'])} this year")
        if a.get("13K"):
            note.append(f"13K EBIE {_money(a['13K'])} this year")
        cf.cell(row=rr, column=11, value="; ".join(note)).font = Font(name=F, size=9)
        rr += 1
    last = rr - 1
    cf.cell(row=rr, column=1, value="Total").font = f_bold
    for col in range(4, 11):
        L = get_column_letter(col)
        c = cf.cell(row=rr, column=col, value=f"=SUM({L}4:{L}{last})")
        c.number_format, c.font, c.fill = money, f_bold, grey
    cf.cell(row=rr + 2, column=1, value="Yellow = enter from the prior-year return (8582 worksheets, Form 4562 line 13, Schedule D carryover worksheet, Form 8990).").font = Font(name=F, size=8, italic=True, color="666666")
    cf.freeze_panes = "B4"

    # ---------------- K-1 Detail
    dt = wb.create_sheet("K-1 Detail")
    heads = ["Document", "UT #", "PDF page", "Box", "Code", "Amount", "Statement", "Comment 2 (partnership comment)", "EIN", "Tax year"]
    widths = [58, 8, 9, 7, 7, 16, 11, 60, 14, 20]
    for i, (h, w) in enumerate(zip(heads, widths), start=1):
        c = dt.cell(row=1, column=i, value=h)
        c.font, c.fill = f_head, hdr
        dt.column_dimensions[get_column_letter(i)].width = w
    rr = 2
    for k in sorted(k1s, key=lambda k: (k.get("name") or "").lower()):
        first = True
        for l in k["lines"]:
            if l.get("amt") == 0 and not l.get("stmt"):
                continue
            vals = ["K-1 " + (k.get("name") or ""), ut.get(str(k["page"]), ""), k["page"], l["box"], l.get("code") or "",
                    l.get("amt") if not l.get("check") else None, "Yes" if l.get("stmt") else ("Checked" if l.get("check") else ""),
                    pcomments.get(str(k["page"]), "") if first else "",
                    (k.get("ein") or "") if first else "",
                    (f"{k.get('tax_begin','')} – {k.get('tax_end','')}" if (k.get("tax_begin") or k.get("tax_end")) else "") if first else ""]
            for i, v in enumerate(vals, start=1):
                c = dt.cell(row=rr, column=i, value=v)
                c.font = f_norm
            dt.cell(row=rr, column=6).number_format = money
            first = False
            rr += 1
    dt.freeze_panes = "A2"
    dt.auto_filter.ref = f"A1:J{max(rr - 1, 1)}"

    from copy import copy
    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for c in row:
                if c.font is not None and c.font.name != F:
                    nf = copy(c.font)
                    nf.name = F
                    c.font = nf

    wb.calculation.fullCalcOnLoad = True  # Excel computes the formulas when the file opens
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
