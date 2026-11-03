"""
verify1040_parser.py - reads the UltraTax 1040 print package for K-1 verification.

Source used: "Form K-1 Reconciliation Worksheet" pages (one set per partnership entered in UltraTax).
Each row has: Current Year Amount (what was entered from the K-1), PY suspended / disallowed columns
(basis, at-risk, passive) and the Tax Return amount.

Not read on purpose: Partner's Basis Worksheet (different starting basis than the K-1), AMT pages
(except AMT page 1 for box 17 adjustments), QBI reconciliation pages.
"""
from __future__ import annotations

import re
import pdfplumber
import pypdfium2 as pdfium

NUM = re.compile(r"^\(?-?[\d,]+(\.\d+)?\)?$")
# right edge (x1) of each amount column on the worksheet (letter-size landscape, UltraTax 2025)
COLS = [("cur", 245), ("py_basis", 317), ("dis_basis", 395), ("py_atrisk", 484), ("dis_atrisk", 549),
        ("py_passive", 627), ("dis_passive", 705), ("tax", 783)]
FORM_NO = {6251.0, 4797.0, 4952.0, 1040.0, 8582.0}   # form numbers that sneak into amount columns


def _num(s: str) -> float:
    return float(s.replace(",", "").replace("(", "-").replace(")", ""))


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9%]+", " ", (s or "").lower()).strip()


def parse_return(path: str) -> dict:
    """Returns {"entities": [ {name, ein4, unit, passive, rows:[...]} ], "pages": n}."""
    ents: dict = {}
    order: list = []
    last = None
    # quick text pass (pypdfium2 comes with pdfplumber) to find the worksheet pages, then read only those
    want, qbi_pages = [], []
    doc = pdfium.PdfDocument(path)
    n = len(doc)
    for i in range(n):
        q = doc[i].get_textpage().get_text_range()
        # QBI worksheet candidates - loose test (text order differs between pypdfium2 versions); confirmed below
        if "Reconciliation" in q and ("Qualified Business Income" in q or "K1QBI" in q):
            qbi_pages.append(i)
        if "Reconciliation Worksheet" in q and "Qualified Business Income" not in q and \
                ("AMT Version" not in q or "Page 1" in q):
            want.append(i)
    doc.close()
    with pdfplumber.open(path) as pdf:
        for i in want:
            pi, p = i + 1, pdf.pages[i]
            t = p.extract_text() or ""
            if "K-1 Reconciliation Worksheet" not in t or "Qualified Business Income" in t:
                continue
            m = re.search(r"K-1 Reconciliation Worksheet - (.+)", t)
            title = m.group(1).strip() if m else ""
            amt = "AMT Version" in title
            if amt and "Page 1" not in title:
                continue
            m = re.search(r"Entity Name\s*(.+?)\s*EIN\s+(\S*\d{4})", t)
            if m:
                key = (m.group(1).strip(), m.group(2)[-4:])
                if key not in ents:
                    u = re.search(r"K1 Unit\s+(\d+)", t)
                    pa = re.search(r"\n(OTHER PASSIVE|NOT PASSIVE|[A-Z ]*PASSIVE[A-Z ]*)\n", t)
                    ents[key] = dict(name=key[0], ein4=key[1], unit=u.group(1) if u else "",
                                     passive=pa.group(1).strip() if pa else "", rows=[], pages=[])
                    order.append(key)
                last = key
            if last is None:
                continue
            ent = ents[last]
            ent["pages"].append(pi)
            ws = p.extract_words()
            body = sorted([w for w in ws if w["top"] > 125], key=lambda w: (w["top"], w["x0"]))
            rows: list = []
            for w in body:
                if rows and abs(rows[-1][0] - w["top"]) < 5:
                    rows[-1][1].append(w)
                else:
                    rows.append([w["top"], [w]])
            for _, wl in rows:
                label = " ".join(w["text"] for w in wl if w["x1"] < 200 and not (NUM.match(w["text"]) and w["x0"] > 110))
                vals = {}
                for w in wl:
                    if w["x1"] > 200 and NUM.match(w["text"]):
                        v = _num(w["text"])
                        if v in FORM_NO and "," not in w["text"]:
                            continue
                        c = min(COLS, key=lambda c: abs(c[1] - w["x1"]))[0]
                        vals[c] = v
                if not vals or not label:
                    continue
                ent["rows"].append(dict(page=pi, title=title, amt=amt, label=label, n=norm(label), **vals))
        # QBI worksheet ("K-1 Reconciliation Worksheet - Qualified Business Income"): Screen K1QBI Amount per row
        for i in qbi_pages:
            p = pdf.pages[i]
            t = p.extract_text() or ""
            head = re.sub(r"\s+", " ", t[:600])
            if not re.search(r"Reconciliation Worksheet\s*-\s*Qualified Business Income", head) or \
                    re.search(r"Qualified Business Income\s*-\s*Totals", head) or "AMT" in head:
                continue
            m = re.search(r"Entity Name\s*(.+?)\s*EIN\s+(\S*\d{4})", t)
            if not m:
                continue
            key = (m.group(1).strip(), m.group(2)[-4:])
            ent = ents.get(key) or next((e for k, e in ents.items() if k[1] == key[1]), None)
            if ent is None:
                continue
            _read_qbi(p, ent, i + 1)
    return {"entities": [ents[k] for k in order], "pages": n,
            "qbi_count": sum(1 for k in order if ents[k].get("qbi"))}


def _read_qbi(p, ent, pi):
    ws = p.extract_words()
    hdr = [w for w in ws if w["text"] == "Amount"]
    sch = [w for w in ws if w["text"] == "K-1" and hdr and abs(w["top"] - hdr[0]["top"]) < 4]
    if hdr and sch:
        top0 = hdr[0]["top"] + 6
        a_k1qbi, a_sched = hdr[0]["x1"], sch[0]["x1"]
    else:   # header words split differently - UltraTax 2025 landscape layout
        lab = next((w for w in ws if w["text"].startswith("Ordinary")), None)
        if lab is None:
            return
        top0, a_k1qbi, a_sched = lab["top"] - 4, 210.0, 287.0
    stop = next((w["top"] for w in ws if w["text"] == "Total" and w["x0"] < 60 and w["top"] > top0), 9999)
    rows: list = []
    for w in sorted([w for w in ws if top0 < w["top"] < stop], key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0] - w["top"]) < 5:
            rows[-1][1].append(w)
        else:
            rows.append([w["top"], [w]])
    q = ent.setdefault("qbi", {})
    for _, wl in rows:
        label = " ".join(w["text"] for w in wl if w["x1"] < a_k1qbi - 40 and not NUM.match(w["text"]))
        vals = {}
        for w in wl:
            if NUM.match(w["text"]) and w["x1"] > a_k1qbi - 40:
                d = {"k1qbi": abs(w["x1"] - a_k1qbi), "sched": abs(w["x1"] - a_sched)}
                c = min(d, key=d.get)
                if d[c] < 30:
                    vals[c] = _num(w["text"])
        if label and vals:
            q[norm(label)] = dict(label=label, page=pi, **vals)


if __name__ == "__main__":
    import sys
    r = parse_return(sys.argv[1])
    for e in r["entities"]:
        print(f'{e["name"]} ***{e["ein4"]} unit {e["unit"]} {e["passive"]} pages {e["pages"]}')
        for row in e["rows"]:
            print("   ", row["page"], ("AMT " if row["amt"] else "") + row["label"],
                  {k: v for k, v in row.items() if k in dict(COLS)})
