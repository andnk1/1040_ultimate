"""handoff.py - the package "Add to Income Summary" on the K-1 Verification page sends to its 1040 run (pending item 5,
2026-11-03). Nothing reaches the income summary until the preparer adds it; adding again replaces the package.

  package = {"added": "2026-11-04 14:05", "n": K-1s, "files": [K-1 file names], "sig": what the K-1 page held when added,
             "rows": [row]}
  row     = {"key", "cat", "doc", "amt", "corr", "comment", "page", "file", "ein", "name"}
            key  = "k1|<EIN>|<line>" (else the partnership's name, else the file's fingerprint + the page in the file) - the
                   line's ticks / corrected amounts / comments on the income summary stay with it when the K-1s are read again,
                   re-added or the file is renamed
            amt  = the amount read (with the statement amounts) -> per document
            corr = the correction typed on the K-1 page's totals tab -> corrected amount (None = no correction)
The 1040 keeps the package in its work in progress (key "k1"). FORMS = the K-1 forms that go to the income summary (1065 now;
1120-S joins the same route later - pending item 6).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

FORMS = ("1065",)
# K-1 summary section -> 1040 income summary category
TO_CAT = {"int": "interest", "div": "dividends", "lt": "lt", "st": "st", "rent": "rental", "ord": "k1"}
SUB_LABEL = {"E": "", "A": " — other portfolio income (11A)", "1": " — other income, Sch 1 (11ZZ)"}


def _num(v):
    t = str(v if v is not None else "").replace("$", "").replace(",", "").replace(" ", "")
    if not t:
        return None
    neg = (t.startswith("(") and t.endswith(")")) or t.startswith("-")
    try:
        x = float(t.strip("()-"))
    except ValueError:
        return None
    return -x if neg else x


def _who(k: dict, fid: str) -> str:
    """The K-1's identity in a line key: its EIN, else its name, else the file's fingerprint + the page in that file."""
    ein = re.sub(r"\D", "", k.get("ein") or "")
    if len(ein) == 9:
        return ein
    name = re.sub(r"[^A-Z0-9]", "", (k.get("name") or "").upper())
    return "n:" + name if name else f"p:{fid}#{(k.get('page') or 0) % 1000}"


def signature(k1s: list, state: dict | None) -> str:
    """What the K-1 page holds that changes the income summary lines (the K-1s read + statement amounts, 11 S / 11 ZZ ticks,
    corrections) - compared with the package to say "changed since added"."""
    st = state or {}
    keep = {k: st.get(k) for k in ("stmt", "stmtDone", "sch11", "s11s", "corr")}
    keep.update({k: st[k] for k in ("pcorr", "dup", "plines") if st.get(k)})   # K-1 Prep: box corrections, count / don't count, added lines
    lines = [(k.get("page"), k.get("ein"), k.get("name"), [(l.get("key"), l.get("amt")) for l in k.get("lines") or []])
             for k in k1s if k.get("form") in FORMS]
    return hashlib.sha1(json.dumps([lines, keep], sort_keys=True, default=str).encode()).hexdigest()[:16]


def build_package(k1s: list, corr: dict, summary: dict, files: list, sig: str = "", fids: list | None = None,
                  box_corr: dict | None = None, box_rows: dict | None = None) -> dict:
    """summary = build_summary(k1s) (with the statement amounts); corr = {rid: typed correction} from the K-1 page's totals tab;
    files = the run's K-1 file names (file n holds pages 1000*n ...); fids = their fingerprints (same order);
    box_corr = {rid: amount} - the lines moved by a box correction typed on K-1 Prep (prep.summary_corr): the corrected
    amount of the line unless the totals tab has its own correction; box_rows = the corrected summary's rows (a line that
    exists only once corrected)."""
    box_corr = box_corr or {}
    summary = {"sections": [dict(s, rows=list(s["rows"])) for s in summary["sections"]]}
    have = {r["rid"] for s in summary["sections"] for r in s["rows"]}
    for rid in box_corr:                                         # nothing read on that line, an amount once corrected
        if rid not in have and rid in (box_rows or {}):
            sec, r = box_rows[rid]
            next(s for s in summary["sections"] if s["key"] == sec)["rows"].append(dict(r, amt=0))
    by_page = {k["page"]: k for k in k1s if k.get("form") in FORMS}
    at = lambda lst, page: lst[page // 1000] if 0 <= (page or 0) // 1000 < len(lst) else ""
    file_of = lambda page: at(files, page)
    fid_of = lambda page: at(fids or [], page) or at(files, page)
    rows = []
    for s in summary["sections"]:
        if s["key"] not in TO_CAT:
            continue
        for r in s["rows"]:
            k = by_page.get(r["page"]) or {}
            c = _num((corr or {}).get(r["rid"]))
            if c is None and r["rid"] in box_corr:
                c = box_corr[r["rid"]]
            if not r["amt"] and c is None and not r.get("comment"):
                continue
            line = r["rid"].rsplit("|", 1)[0]                     # "int", "ord|E", "lt1256" ... (the rid without its page)
            f = file_of(r["page"])
            doc = r["doc"] + SUB_LABEL.get(r.get("sub") or "E", "") if s["key"] == "ord" else r["doc"]
            rows.append(dict(key=f"k1|{_who(k, fid_of(r['page']))}|{line}", cat=TO_CAT[s["key"]], doc=doc, amt=r["amt"],
                             corr=c if c is not None and abs(c - r["amt"]) > 0.005 else None, comment=r.get("comment") or "",
                             page=r["page"], file=f, ein=k.get("ein") or "", name=k.get("name") or ""))
        for i, label in enumerate(s["adj"]):                     # carry-forward / add-back lines typed on the K-1 page
            c = _num((corr or {}).get(s["adj_rids"][i]))
            if c:
                rows.append(dict(key=f"k1|adj|{s['key']}|{i}", cat=TO_CAT[s["key"]], doc=f"K-1 adjustment — {label}", amt=None,
                                 corr=c, comment="typed on the K-1 page", page=0, file="", ein="", name=""))
    seen = {}
    for x in rows:                                               # the same K-1 twice (two copies, same EIN): keep keys apart
        seen[x["key"]] = seen.get(x["key"], 0) + 1
        if seen[x["key"]] > 1:
            x["key"] += f"#{seen[x['key']]}"
    return dict(added=datetime.now().strftime("%Y-%m-%d %H:%M"), n=len(by_page), files=list(files), sig=sig, rows=rows)
