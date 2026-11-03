"""
screen_parser.py - reads the UltraTax "Input Screens" print (File > Print > Input screens) for the K-1 screens.

Every K-1 screen page (K1, K1-2 ... K1-7, K1QBI) shows exactly what was typed, by unit:
  header:  Screen: K1-2 Unit: 36 ...   / Name of entity / EIN (screen K1)
  rows:    1065 code | 1120S code | label | Federal | State, if different
Typed values are printed in their own font (the font of the unit number at the top right); labels in other fonts.

Returns {"units": {unit: {"unit", "name", "ein", "type", "partner", "passive", "fields": [...]}}, "pages": n}
field = {"screen", "code", "code_s", "label", "fed", "state", "text", "page"}
"""
from __future__ import annotations

import re

import pdfplumber
import pypdfium2 as pdfium

NUM = re.compile(r"^\(?-?[\d,]*\d(\.\d+)?\)?$")
CODE = re.compile(r"^(\d{1,2}[a-cA-Z]{0,3}(,[A-Z]{1,3})*|-)$")
SCREENS = ("K1", "K1-2", "K1-3", "K1-4", "K1-5", "K1-6", "K1-7", "K1QBI")
HDR = re.compile(r"Screen:\s*(K1(?:-\d|QBI)?)\s+Unit:\s*(\d+)")


def _num(t):
    t = t.replace(",", "")
    neg = t.startswith("(") or t.startswith("-")
    v = float(t.strip("()-"))
    return -v if neg else v


def _lines(words, tol=3.0):
    out = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(out[-1][0] - w["top"]) <= tol:
            out[-1][1].append(w)
        else:
            out.append([w["top"], [w]])
    for l in out:
        l[1].sort(key=lambda w: w["x0"])
    return out


def _page(pg, pi):
    words = pg.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False)
    txt = " ".join(w["text"] for w in words if w["top"] < 30)
    m = HDR.search(txt)
    if not m:
        return None
    screen, unit = m.group(1), int(m.group(2))
    # data font = font of the unit number printed at the top right
    top_right = [w for w in words if w["top"] < 60 and w["x0"] > 480 and w["text"].isdigit()]
    if not top_right:
        return None
    dfont = top_right[0]["fontname"]
    head_y = top_right[0]["top"] + 3
    # column headers: each "Federal" header line, with the x of "State," on that line (none -> federal only)
    fedh = [w for w in words if w["text"] == "Federal" and w["fontname"] != dfont]
    sth = [w for w in words if w["text"] == "State," and w["fontname"] != dfont]
    hdrs = [(f["top"], next((s["x0"] for s in sth if abs(s["top"] - f["top"]) < 4), 9999)) for f in fedh]
    res = dict(screen=screen, unit=unit, name="", ein="", fields=[], page=pi, codes=set(), pairs=set())
    for top, ws in _lines(words):
        data = [w for w in ws if w["fontname"] == dfont and top > head_y]
        lab = [w for w in ws if w["fontname"] != dfont]
        c0 = next((w["text"] for w in lab if w["x0"] < 52 and CODE.match(w["text"])), "")
        c1 = next((w["text"] for w in lab if 52 <= w["x0"] < 92 and CODE.match(w["text"])), "")
        if c0 and c0 != "-":
            res["codes"].add((screen, c0))     # input lines that exist on this screen (typed or not)
        if c1 and c1 != "-":
            res["pairs"].add((c1, c0))         # 1120-S code -> 1065 code (same UT line)
        if not data:
            continue
        ltxt = " ".join(w["text"] for w in lab)
        if ltxt.startswith("Name of entity"):
            res["name"] = " ".join(w["text"] for w in data if w["x1"] < 470)
            continue
        if ltxt.startswith("EIN"):
            res["ein"] = " ".join(w["text"] for w in data if w["x1"] < 470)
            continue
        code = next((w["text"] for w in lab if w["x0"] < 52 and CODE.match(w["text"])), "")
        code_s = next((w["text"] for w in lab if 52 <= w["x0"] < 92 and CODE.match(w["text"])), "")
        label = " ".join(w["text"] for w in lab if w["x1"] < data[0]["x0"]
                         and not (w["x0"] < 92 and CODE.match(w["text"]) and w["text"] in (code, code_s)))
        st = sorted([h for h in hdrs if h[0] < top])
        state_x = st[-1][1] if st else 9999
        fed = [w for w in data if w["x1"] < state_x + 5]
        sta = [w for w in data if w["x1"] >= state_x + 5]
        f = dict(screen=screen, code=code, code_s=code_s, label=label, page=pi,
                 text=" ".join(w["text"] for w in data), fed=None, state=None)
        if len(fed) == 1 and NUM.match(fed[0]["text"]):
            f["fed"] = _num(fed[0]["text"])
        if len(sta) == 1 and NUM.match(sta[0]["text"]):
            f["state"] = _num(sta[0]["text"])
        res["fields"].append(f)
    return res


def parse_screens(path: str) -> dict:
    want = []
    doc = pdfium.PdfDocument(path)
    n = len(doc)
    for i in range(n):
        q = doc[i].get_textpage().get_text_range()
        if re.search(r"Screen:\s*K1(?:-\d|QBI)?\s+Unit:", q):
            want.append(i)
    doc.close()
    units: dict = {}
    qbi_pages = []
    codes, pairs = set(), set()
    with pdfplumber.open(path) as pdf:
        for i in want:
            r = _page(pdf.pages[i], i + 1)
            if not r or r["screen"] not in SCREENS:
                continue
            codes |= r["codes"]
            pairs |= r["pairs"]
            if r["screen"] == "K1QBI":     # K1QBI has its own unit numbers -> attach by entity name later
                qbi_pages.append(r)
                continue
            u = units.setdefault(r["unit"], dict(unit=r["unit"], name="", ein="", type="", partner="", passive="",
                                                 fields=[], screens=[]))
            u["name"] = u["name"] or r["name"]
            u["ein"] = u["ein"] or r["ein"]
            u["screens"].append(r["screen"])
            for f in r["fields"]:
                l = f["label"].lower()
                if r["screen"] == "K1" and l.startswith("type of entity"):
                    u["type"] = f["text"]
                elif r["screen"] == "K1" and "type of partner" in l:
                    u["partner"] = f["text"]
                elif r["screen"] == "K1-2" and "passive activity code" in l:
                    u["passive"] = f["text"]
                u["fields"].append(f)
    by_name = {}
    for u in units.values():
        by_name.setdefault(u["name"].strip().upper(), []).append(u)
    for r in qbi_pages:
        cands = by_name.get(r["name"].strip().upper()) or []
        u = cands[0] if cands else units.get(r["unit"])
        if u is None:
            continue
        u["screens"].append("K1QBI")
        for f in r["fields"]:
            f["qbi_unit"] = r["unit"]
            u["fields"].append(f)
    return {"units": units, "pages": n, "codes": sorted(codes), "pairs": sorted(pairs)}


if __name__ == "__main__":
    import sys, time
    t = time.time()
    r = parse_screens(sys.argv[1])
    print(len(r["units"]), "units", round(time.time() - t, 1), "s")
    for u in list(r["units"].values())[:3]:
        print(u["unit"], u["name"], u["ein"], u["type"], u["partner"], u["passive"], u["screens"])
        for f in u["fields"]:
            print("   ", f["screen"], f["code"] or "·", "|", f["label"][:70], "|", f["fed"], f["state"], "|", f["text"][:40])
