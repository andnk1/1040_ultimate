"""ut_entry.py - UltraTax entry rules: which K-1 lines the bot types into Source Data Entry (SDE) and which go in by hand.

Decided 2026-11-11 (Lady), reversing "the 1040 knows nothing about Source Data Entry": the 1040 decides, UT Data Entry only
types - it types the CSV's `bot` rows, skips the `hand` rows and never decides again (APPS_ARCHITECTURE.md). UT Data Entry keeps
its Tab maps (where each field is, how to type), not the decisions.

Used only by the K-1 UT page (core/k1v/prep.py builds the rows; screen spec design/k1_prep.md) and its exports: the CSV's
`entry` / `entry_reason`, the by-hand list as Excel and PDF. Turned off with "ut_entry": false in local_settings.json: no Entry
column, no by-hand list or buttons, `entry` / `entry_reason` blank.

The rules live here, in the code (like k1_codes.py). Change a line here, then run tests\\run_tests.bat.
  HAND   {item | box | box+code: reason}   always by hand (Part II items by item, box lines by box, one code by box+code)
  ROWS   {box: rows}                       rows the SDE form has for a code box: the box's lines that would go by bot are
                                           counted in the K-1's order (the page's), the ones beyond are by hand
A code UltraTax doesn't have (k1_codes "in UT" = N) is by hand too. Everything else is Bot.
K1 (liabilities, ending) is Bot: one row on the page, exported as up to three numeric rows K1_nonrecourse / K1_qualified /
K1_recourse (prep.k1_rows), each with K1's entry.
"""
from __future__ import annotations

import datetime as _dt
import io

from .. import settings

ENABLED = settings.UT_ENTRY                         # local_settings.json "ut_entry" (default on)
BOT, HAND = "bot", "hand"
LABEL = {BOT: "Bot", HAND: "By hand"}

NOT_IN_SDE = "Not in Source Data Entry"
GREY = "Grey in Source Data Entry"
CHECKBOX = "Checkbox – Tab can't reach it"
BY_HAND = "By hand"                                 # 13 AE: where it goes in UltraTax - Lady adds it
NOT_IN_UT = "Code not in UltraTax"
OVER = "Only {n} rows in Source Data Entry"

RULES = {
    "1065": dict(
        HAND={
            "G": NOT_IN_SDE, "H1": NOT_IN_SDE, "J": NOT_IN_SDE, "L": NOT_IN_SDE, "M": NOT_IN_SDE, "N": NOT_IN_SDE,
            "9c": GREY, "12": GREY,
            "16": CHECKBOX, "22": CHECKBOX, "23": CHECKBOX,
            "13AE": BY_HAND,
        },
        ROWS={"11": 3, "13": 3, "14": 2, "15": 2, "17": 3, "18": 3, "19": 2, "20": 8},
    ),
}

XLSX_COLUMNS = ["Document", "Partnership", "EIN", "Box", "Code", "Description", "Amount", "Why", "Done"]


def on() -> bool:
    return bool(ENABLED)


def rule(box: str, code: str = "", form: str = "1065") -> str:
    """The fixed by-hand reason of a box / code / Part II item ("" = none)."""
    hand = RULES[form]["HAND"]
    return (hand.get(box + code) if code else "") or hand.get(box) or ""


def decide(rows: list, form: str = "1065") -> list:
    """Sets r["entry"] (bot / hand / "") and r["why"] on one K-1's rows, in the page's order. rows: the K-1 UT rows (kind,
    box, code, block, valid). No entry: a "see statement" row (its lines below have their own) and a line whose red problem
    keeps the K-1 out of the export (it has to be fixed first)."""
    limit = RULES[form]["ROWS"]
    used: dict = {}
    for r in rows:
        r["entry"], r["why"] = "", ""
        if not on() or r.get("kind") == "stmt" or (r.get("block") and r.get("kind") != "info"):
            continue
        box, code = r.get("box") or "", r.get("code") or ""
        why = rule(box, code, form)
        if not why and r.get("valid") == "N":
            why = NOT_IN_UT
        if not why and box in limit:
            used[box] = used.get(box, 0) + 1
            if used[box] > limit[box]:
                why = OVER.format(n=limit[box])
        r["entry"], r["why"] = (HAND, why) if why else (BOT, "")
    return rows


# ------------------------------------------------------------------ the by-hand list (page card, Excel, PDF)
def _amount(r: dict):
    if r["kind"] == "info":
        return "; ".join(r.get("vals") or []) or r["eff"]       # Part II: the value as printed (text, as on the page)
    if r["eff"] == "X":
        return "Checked"
    return r["eff"]


def hand_items(data: dict) -> list:
    """The by-hand lines of the Ready K-1s (the ones exported), in the page's order."""
    if not on():
        return []
    out = []
    for k in data["k1s"]:
        if not k["ready"]:
            continue
        for r in k["rows"]:
            if r.get("entry") == HAND:
                out.append(dict(id="h|" + r["id"], n=k["n"], file=k["file"], name=k["name"], ein=k["ein"], box=r["box"],
                                code=r["code"], desc=r["desc"], amt=_amount(r), why=r["why"]))
    return out


def head(client: str, year, items: list) -> dict:
    return dict(client=client or "", year=year or "", date=_dt.date.today().strftime("%m/%d/%Y"), n=len(items))


def _head_line(h: dict) -> str:
    return " · ".join(x for x in (f"Client: {h['client']}" if h["client"] else "", f"Tax year {h['year']}" if h["year"] else "",
                                   h["date"], f"{h['n']} item{'' if h['n'] == 1 else 's'}") if x)


def _whole(v) -> str:
    return "" if v is None else ("-" if round(v) < 0 else "") + f"{abs(round(v)):,}"


def hand_xlsx(items: list, h: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    wb = Workbook()
    ws = wb.active
    ws.title = "By hand"
    ws["A1"] = f"To enter by hand in UltraTax - K-1 {h['year']}".strip()
    ws["A1"].font = Font(bold=True, size=13, color="003366")
    ws["A2"] = _head_line(h)
    ws.append([])
    ws.append(XLSX_COLUMNS)
    thin = Side(style="thin", color="DFE1E9")
    for c in ws[4]:
        c.font = Font(bold=True, color="4E7874")
        c.fill = PatternFill("solid", fgColor="F7F7FB")
        c.border = Border(bottom=thin)
    for it in items:
        a = it["amt"]
        ws.append([it["file"], it["name"], it["ein"], it["box"], it["code"], it["desc"],
                   round(a) if isinstance(a, (int, float)) else a, it["why"], ""])
        c = ws.cell(row=ws.max_row, column=7)
        if isinstance(a, (int, float)):
            c.number_format = "#,##0;-#,##0"
        else:
            c.alignment = Alignment(horizontal="right")
        ws.cell(row=ws.max_row, column=9).border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for col, w in zip("ABCDEFGHI", (34, 30, 13, 6, 6, 42, 16, 34, 8)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"                                     # the header row stays on screen
    ws.print_options.gridLines = False
    ws.page_setup.orientation = "landscape"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _esc(s) -> str:
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_CSS = """
* { font-family: sans-serif; }
body { font-size: 8.5pt; color: #374151; }
h1 { font-size: 13pt; color: #003366; margin: 0 0 3pt 0; }
p.h { margin: 0 0 9pt 0; color: #374151; }
table { border-collapse: collapse; width: 100%; }
th { text-align: left; color: #4e7874; background-color: #F7F7FB; font-size: 7.5pt; padding: 3pt 4pt; border-bottom: 1px solid #9AA3B2; }
td { padding: 3pt 4pt; border-bottom: 1px solid #DFE1E9; vertical-align: top; }
td.n, th.n { text-align: right; }
td.done { border: 1px solid #9AA3B2; }
"""


def hand_pdf(items: list, h: dict) -> bytes:
    """Landscape (US letter), page numbers at the bottom."""
    import pymupdf
    rows = "".join(
        f"<tr><td>{_esc(it['file'])}</td><td>{_esc(it['name'])}</td><td>{_esc(it['ein'])}</td><td>{_esc(it['box'])}</td>"
        f"<td>{_esc(it['code'])}</td><td>{_esc(it['desc'])}</td>"
        f"<td class='n'>{_esc(_whole(it['amt']) if isinstance(it['amt'], (int, float)) else it['amt'])}</td>"
        f"<td>{_esc(it['why'])}</td><td class='done'>&#160;</td></tr>" for it in items)
    html = (f"<h1>{_esc(('To enter by hand in UltraTax - K-1 ' + str(h['year'])).strip())}</h1><p class='h'>{_esc(_head_line(h))}</p>"
            "<table><tr><th>Document</th><th>Partnership</th><th>EIN</th><th>Box</th><th>Code</th><th>Description</th>"
            f"<th class='n'>Amount</th><th>Why</th><th>Done</th></tr>{rows}</table>")
    page = pymupdf.paper_rect("letter-l")
    where = page + (36, 36, -36, -46)
    buf = io.BytesIO()
    story = pymupdf.Story(html=html, user_css=_CSS)
    w = pymupdf.DocumentWriter(buf)
    more = True
    while more:
        dev = w.begin_page(page)
        more, _ = story.place(where)
        story.draw(dev)
        w.end_page()
    w.close()
    doc = pymupdf.open("pdf", buf.getvalue())
    foot = " · ".join(x for x in (f"UT by hand K-1 {h['year']}".strip(), h["client"]) if x)
    for i, p in enumerate(doc):
        p.insert_text((36, page.height - 24), foot, fontsize=7.5, color=(0.42, 0.45, 0.5))
        t = f"Page {i + 1} of {doc.page_count}"
        p.insert_text((page.width - 36 - pymupdf.get_text_length(t, fontsize=7.5), page.height - 24), t, fontsize=7.5,
                      color=(0.42, 0.45, 0.5))
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out
