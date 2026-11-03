"""verify1040_excel.py - Excel output for the 1040 verification (one row per K-1 item)."""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

FILL = {"green": "E3F4EA", "amber": "FEF3E2", "red": "FDE2E2", "fyi": "EFEFF7", "manual": "E8EEF8", "cant": "FEF3E2"}
LABEL = {"green": "OK", "amber": "Confirm", "red": "Missing / differs", "fyi": "FYI", "manual": "Check manually", "cant": "No UT entry"}
NAVY = "003366"


def write_verification_xlsx(res: dict, k1name: str, retname: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Verification"
    ws["A1"] = "K-1 → 1040 Verification"
    ws["A1"].font = Font(bold=True, size=14, color=NAVY)
    c = res["counts"]
    ws["A2"] = (f"K-1s: {k1name} · UltraTax Input Screens: {retname} · OK {c['green']} · Confirm {c['amber']} · "
                f"Missing/differs {c['red']} · Check manually {c['manual']} · No UT entry {c.get('cant', 0)} · FYI {c['fyi']}")
    hdr = ["Partnership (K-1)", "EIN", "UltraTax entity", "UT unit", "Box", "K-1 amount", "Status",
           "Entered in UT", "Where in UltraTax", "Message", "Reviewer comment"]
    ws.append([])
    ws.append(hdr)
    for i, h in enumerate(hdr, 1):
        cell = ws.cell(4, i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=NAVY)
    for card in res["cards"]:
        e = card["entity"]
        base = [card["name"], card["ein"], e["name"] if e else "NOT FOUND IN ULTRATAX", e["unit"] if e else ""]
        if card["empty"]:
            ws.append(base + ["", None, "No amounts", None, "", "No amounts on this K-1 — nothing to verify", ""])
            continue
        for it in card["items"]:
            amt = it["amt"] if it["amt"] is not None else ("Checked" if it.get("check") else "" if it.get("extra") else "See statement")
            if it["kind"] == "type":
                amt, it = it["k1_type"], dict(it, entered=it["ut_type"])
            msg = it["msg"] + (f" (K-1 total {it['k1_total']:,.0f})" if it.get("k1_total") is not None else "") + \
                (f" — {it['note']}" if it.get("note") else "") + (" (added from statement)" if it.get("manual") else "")
            ws.append(base + [it["key"], amt, LABEL[it["status"]], it.get("entered"),
                              it.get("form", "") + (f" (p. {it['page']})" if it.get("page") else ""), msg, ""])
            r = ws.max_row
            ws.cell(r, 7).fill = PatternFill("solid", fgColor=FILL[it["status"]])
    if res["orphans"]:
        ws.append([])
        ws.append(["Entered in UltraTax, but no matching K-1 in the package:"])
        ws.cell(ws.max_row, 1).font = Font(bold=True, color="8B0000")
        for o in res["orphans"]:
            ws.append([o["name"], f"***{o['ein4']}", o["name"], o["unit"]])
    widths = [38, 12, 34, 8, 7, 14, 16, 14, 44, 60, 30]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=5):
        for cell in row:
            if cell.column in (6, 8) and isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0;-#,##0'
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in (9, 10))
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:K{ws.max_row}"
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
