"""income.py - the office income summary (Google Sheet template layout).

Columns: Document/s | <PY year> | <CY year> Federal | ST#1 | ST#2 | ST#3 | Notes
Rows per category: one row per document that feeds it, then the category total.
PY amounts come from the prior-year return (totals only). CY amounts come from the documents
(document parsers = next step; for now the rows list the documents with blank amounts).
State columns repeat the federal amount for now.
"""
from __future__ import annotations

from pathlib import Path

CATS = [
    # key, total label, red rows above the total
    ("w2", "Total W-2 Income", []),
    ("interest", "Total Interest Income", []),
    ("dividends", "Total Dividends Income", []),
    ("ira", "Total IRA Distributions", []),
    ("pension", "Total Pension and annuities", []),
    ("ss", "Total Social Security Benefits", []),
    ("lt", "Total Long-Term Capital Gains", [("add back disallowed losses", "")]),
    ("st", "Total Short Term Cap. Gains", [("add back disallowed losses", "")]),
    ("schc", "Total Schedule C", []),
    ("other", "Total Other Income", []),
    ("rental", "Total Rental & Royalties Gain/ Loss", []),
    ("k1", "Total K-1s Ordinary Income", [("minus losses carried over from prior years", ""),
                                          ("Add back disallowed losses", "Due to passive loss limitation or basis limitation")]),
]

# document family -> categories it feeds
FEEDS = {
    "w2": ["w2"], "1099int": ["interest"], "1099da_": [], "1099oid": ["interest"], "1099div": ["dividends"],
    "1099b": ["st", "lt"], "composite": ["interest", "dividends", "st", "lt", "other", "rental"], "1099r": ["ira", "pension"],
    "ssa": ["ss"], "koinly": ["st", "lt", "other"], "1099da": ["st", "lt"],
    "1099nec": ["schc", "other"], "1099k": ["schc"], "1099misc": ["other", "rental"], "1099g": ["other"],
    "k1p": ["interest", "dividends", "lt", "st", "rental", "k1"], "k1s": ["k1"], "k1t": ["k1"], "k1x": ["k1"],
}
NOTES = {
    "1099r": "IRA or pension — check box 7 code and the IRA/SEP/SIMPLE box",
    "1099nec": "Schedule C income if self-employed", "1099misc": "Entered as \"Other income\" (box 3) — box 1/2 rents & royalties, box 7 → Schedule C",
    "1099g": "Entered as \"Other income\" — unemployment / state refund (check the prior-year itemizing)",
    "1099k": "Schedule C or personal sales — confirm",

}


def _disp(d) -> str:
    name = Path(d["file"]).stem
    return (d.get("issuer") + " — " if d.get("issuer") and d["issuer"].lower() not in name.lower() else "") + name


def build_income_summary(py_income: dict, docs: list, schc: list | None, py_year, cy_year, edits: dict | None = None,
                         added: list | None = None, cats=None, feeds=None, sche: list | None = None, k1: dict | None = None) -> dict:
    """2024 (PY): category totals from the prior-year 1040, for comparison only.
       2025 (CY): one row per document with the amount the program read; K-1s = the K-1 section's package (k1: rows keyed
       by EIN + line - the amount read is per document, a correction typed on the K-1 page the corrected amount)."""
    koinly_d = any(x.get("family") == "koinly" and "Schedule D" in x.get("doc_type", "") and x.get("route") != "skipped" for x in docs)
    CATS_, FEEDS_ = cats or CATS, feeds or FEEDS
    sections = []
    inv_files = {a.get("file") for a in (added or []) if a.get("inv") and a.get("file")}
    for key, label, red in CATS_:
        rows = []
        for d in docs:
            fam = d.get("family")
            if d.get("route") == "skipped" or key not in FEEDS_.get(fam, []):
                continue
            if fam == "koinly" and "8949" in d.get("doc_type", "") and koinly_d:
                continue                                    # Schedule D carries the totals; the 8949 is its detail
            parsed = d.get("parsed")
            excluded = d.get("route") == "excluded"
            amts = (parsed or {}).get("amounts", {})
            st = (parsed or {}).get("status", "none")
            if excluded:
                rows.append(dict(doc=_disp(d), file=d["file"], did=d.get("did"), cy=None, note=d.get("note", ""), status="excluded", excluded=True))
                continue
            if parsed is None or st == "none":
                if d["file"] in inv_files:                   # amount entered on the document inventory instead
                    continue
                if key == FEEDS_[fam][0] or (fam == "koinly" and key in ("st", "other")):
                    if fam == "koinly" and (("Schedule 1" in d.get("doc_type", "")) != (key == "other")):
                        continue
                    why = "; ".join((parsed or {}).get("checks", [])) or "not read by the program yet"
                    rows.append(dict(doc=_disp(d), file=d["file"], did=d.get("did"), cy=None, note="NOT READ — " + why + " (AI review)",
                                     status="none", excluded=False))
                continue
            if key in amts and (amts[key] or fam == "1099r" or key == FEEDS_[fam][0] and not any(amts.values())):
                gen = [n for n in parsed.get("notes", []) if "wash sale" not in n]
                # notes that belong to one category sit on that row (Schedule E -> rental, "Other income" -> other)
                own = {"rental": [n for n in gen if "Schedule E" in n and "rental" in amts],
                       "other": [n for n in gen if "Other income" in n and "other" in amts],
                       "st": [n for n in gen if n.startswith(("ST:", "ST includes")) and "st" in amts],
                       "lt": [n for n in gen if n.startswith(("LT:", "LT includes")) and "lt" in amts]}
                moved = {n for v in own.values() for n in v}
                note = "; ".join([n for n in gen if n not in moved] if key == _first_key(amts) else []) 
                if own.get(key):
                    note = "; ".join(own[key] + ([note] if note else []))
                if key in ("st", "lt"):                    # wash sale: comment on the ST / LT row it belongs to
                    w = ((parsed.get("detail") or {}).get(f"b_{key}") or {}).get("wash") if isinstance((parsed.get("detail") or {}).get(f"b_{key}"), dict) else None
                    if w:
                        note = (f"Wash sale loss disallowed {w:,.2f} — already included in the gain"
                                + ("; " + note if note else ""))
                if not any(amts.values()) and fam != "1099r":
                    note = "All amounts 0 on this form"
                if parsed.get("checks") and key == _first_key(amts):
                    note = "CHECK — " + "; ".join(parsed["checks"]) + ("; " + note if note else "")
                if key == "other" and 'Other income' not in note:
                    note = ('Entered as "Other income"' + ("; " + note if note else ""))
                parts = (parsed.get("parts") or {}).get(key) if key in ("st", "lt", "other") else None
                if parts and len(parts) >= 1 and parts[0][0]:
                    pn = parsed.get("part_notes") or {}     # a comment per row (Schedule D line / Schedule 1 line)
                    chk = "CHECK — " + "; ".join(parsed["checks"]) if parsed.get("checks") and key == _first_key(amts) else ""
                    for i, (lb, v) in enumerate(parts):    # one row per Form 8949 box / Schedule 1 line
                        n = "; ".join(x for x in [chk if i == 0 else "", pn.get(lb, "")] if x) if pn else (note if i == 0 else "")
                        row = dict(doc=f'{_disp(d)} — {dict(st="ST ", lt="LT ").get(key, "")}{lb}', file=d["file"], did=d.get("did"), part=lb, cy=v,
                                   note=n, status=st, excluded=False)
                        if key != "other":
                            row["box"] = lb
                        rows.append(row)
                else:
                    rows.append(dict(doc=_disp(d), file=d["file"], did=d.get("did"), cy=amts[key], note=note, status=st, excluded=False))
        for x in (k1 or {}).get("rows") or []:             # the K-1 section's package ("Add to Income Summary")
            if x.get("cat") == key:
                rows.append(dict(doc=x["doc"], file="k1v:" + (x.get("file") or ""), cy=x.get("amt"), k1corr=x.get("corr"),
                                 note=x.get("comment") or "", status="read", excluded=False, id=x["key"]))
        if key == "schc":
            biz = [(i, b.get("name") or (b.get("pl") or {}).get("company") or f"Business {i + 1}") for i, b in enumerate(schc or [])
                   if b.get("py") or b.get("calculated")]
            path_of = {d["file"]: d.get("path") for d in docs}
            groups = {i: [] for i, _ in biz}
            loose = []
            for r in rows:                                 # 1099-NEC / 1099-K: memo, grouped under the business they belong to
                r["memo"] = True
                owner = _match_business(path_of.get(r["file"]), biz)
                names = [n for i, n in biz if owner is None or i == owner]
                dup = ("check for duplicates, may be included on Schedule C for " + " or ".join(names)) if names else \
                      "no Schedule C business yet — enter it in the Schedule C box"
                r["note"] = ("memo — " + dup + "; " + r["note"]).rstrip("; ")
                (groups[owner] if owner in groups else loose).append(r)
            out = []
            for i, n in sorted(biz, key=lambda x: x[1].lower()):
                b = schc[i]
                tonly = bool(b.get("total_only"))
                out.append(dict(doc=n, file="", cy=(b.get("totals") or {}).get("31") if b.get("calculated") else None,
                                note=("Total entered directly in the Schedule C box (no line detail) — not checked against the UT input screens"
                                      if tonly else "From the Schedule C box (Calculate)"), schc=i, status="read", excluded=False,
                                total_only=tonly))
                out += sorted(groups[i], key=lambda r: r["doc"].lower())
            rows = out + sorted(loose, key=lambda r: r["doc"].lower())
        if key == "rental":
            props = [(i, p.get("name") or f"Property {i + 1}", p) for i, p in enumerate(sche or []) if p.get("py") or p.get("calculated")]
            if props:
                fam_of = {d["file"]: d.get("family") for d in docs}
                for r in rows:                             # 1099-MISC / composite rents & royalties: on Schedule E already
                    if fam_of.get(r.get("file")) in ("1099misc", "composite") and not r.get("memo"):
                        r["memo"] = True
                        r["note"] = ("memo — check for duplicates, may be included on Schedule E; " + (r.get("note") or "")).rstrip("; ")
                out = [dict(doc=n, file="", cy=(p.get("totals") or {}).get("net") if p.get("calculated") else None,
                            note=(p.get("totals") or {}).get("note") or "From the Schedule E box (Calculate)", sche=i,
                            status="read", excluded=False) for i, n, p in props]
                rows = out + rows
        for r in rows:
            if r.get("id"):
                continue                                    # K-1 lines: EIN + line
            # a document's line = category + the document's fingerprint id (+ the 8949 box / Schedule 1 line when one document
            # gives several rows) - a renamed file or a better issuer keeps its ticks / corrections; K-1 section, Schedule C / E rows: by name
            r["id"] = f'{key}|{r["did"]}' + (f'|{r["part"]}' if r.get("part") else "") if r.get("did") else f'{key}|{r["file"]}|{r["doc"]}'
        for a in (added or []):
            if a.get("sec") != key:
                continue
            if a.get("inv"):                               # amount typed on the document inventory = per document (correctable here)
                rows.append(dict(doc=a.get("doc", ""), file=a.get("file", ""), cy=a.get("cy"), note=a.get("note", ""),
                                 status="inventory", excluded=False, inv=True, id=a["id"]))
            else:                                          # lines typed in by the preparer (+): corrected amount only
                rows.append(dict(doc=a.get("doc", ""), file=a.get("file", ""), cy=a.get("cy"), fit=a.get("fit"), note=a.get("note", ""),
                                 status="added", excluded=False, added=True, inv=False, id=a["id"]))
        reds = [(l, n, None) for l, n in red]
        sections.append(dict(key=key, label=label, rows=rows, red=reds, py=py_income.get(key), note=py_income.get(key + "_note", "")))

    # federal withholding: once per document, on its first row in the summary
    fit_by_file = {d["file"]: d["parsed"].get("fit") for d in docs if isinstance(d.get("parsed"), dict) and d["parsed"].get("fit")}   # 0 = none -> blank
    done = set()
    for sec in sections:
        for r in sec["rows"]:
            if r.get("added"):
                continue
            r["fit"] = None
            if r["file"] in fit_by_file and r["file"] not in done and not r["excluded"] and r.get("schc") is None and not r.get("inv"):
                r["fit"] = fit_by_file[r["file"]]
                done.add(r["file"])
    # per document = every source, fixed: what the program read, the Schedule C / E box (Calculate), the K-1 section, the amount
    # typed on the document inventory. Corrected amount = per document unless the preparer typed over it (that wins).
    # A correction keeps the per-document amount it was typed over (edits[id]["base"] / ["base_fit"]); when per document changes
    # later, the line is "stale" (document amount changed since your correction - re-confirm).
    for sec in sections:
        for r in sec["rows"]:
            prog = not r.get("added") and r.get("status") not in ("none", "excluded")
            r["doc_cy"] = r["cy"] if prog else None
            r["doc_fit"] = r.get("fit") if prog else None
            if r.get("k1corr") is not None:                 # corrected on the K-1 page -> corrected amount
                r["cy"] = r["k1corr"]
            e = (edits or {}).get(r["id"])
            if e:
                r["read_cy"], r["read_fit"] = r["cy"], r.get("fit")
                if "cy" in e:
                    r["cy"] = e["cy"]
                    r["edited"] = True
                    if "base" in e and _moved(e["base"], r["doc_cy"]):
                        r["stale"] = True
                if "fit" in e:
                    r["fit"] = e["fit"]
                    r["edited"] = True
                    if "base_fit" in e and _moved(e["base_fit"], r["doc_fit"]):
                        r["stale"] = True
                if "note" in e:                      # comment typed over / added to by the preparer
                    r["read_note"], r["note"], r["note_edited"] = r["note"], e["note"], True
            r["differs"] = (abs((r["doc_cy"] or 0) - (r["cy"] or 0)) > 0.005
                            or abs((r["doc_fit"] or 0) - (r.get("fit") or 0)) > 0.005)
        for r in sec["rows"]:
            r["source"] = ("added by preparer" if r.get("added") else
                           ("changed by preparer" if r.get("edited") else "document inventory") if r.get("inv") else
                           "entered by preparer" if r.get("edited") and r.get("status") == "none"
                           else "changed by preparer" if r.get("edited") else "read by program")
        # red rows (add back disallowed losses ...): the amount typed in counts as typed (negative lowers the total)
        reds = []
        for i, (lbl, nt, amt) in enumerate(sec["red"]):
            rid = f'red|{sec["key"]}|{i}'
            e = (edits or {}).get(rid) or {}
            reds.append(dict(id=rid, label=lbl, note=e.get("note", nt), amount=e.get("cy", amt), orig_note=nt))
        sec["red"] = reds
        live = [r for r in sec["rows"] if not r["excluded"] and not r.get("memo")]
        vals = [r["cy"] for r in live if r["cy"] is not None] + [x["amount"] for x in reds if x["amount"] is not None]
        sec["cy"] = sum(vals) if vals else None
        sec["fit"] = sum(r["fit"] for r in live if r["fit"] is not None) if any(r["fit"] is not None for r in live) else None
        dv = [r["doc_cy"] for r in live if r.get("doc_cy") is not None]
        sec["doc_cy"] = sum(dv) if dv else None
        df = [r["doc_fit"] for r in live if r.get("doc_fit") is not None]
        sec["doc_fit"] = sum(df) if df else None

    py_total = sum(s["py"] or 0 for s in sections)
    cy_total = sum(s["cy"] or 0 for s in sections)
    cy_schc = next(((s["cy"] or 0) for s in sections if s["key"] == "schc"), 0)
    ret_total = py_income.get("total_return")
    total_note = ""
    if ret_total is not None and abs(ret_total - py_total) > 1:
        total_note = (f"{py_year} return total income {ret_total:,.0f} — difference {ret_total - py_total:,.0f} "
                      "is income not in these rows (4797, alimony, unemployment, capital-loss limit …)")
    cy_fit = sum(s["fit"] or 0 for s in sections)
    doc_total = sum(s.get("doc_cy") or 0 for s in sections)
    doc_fit = sum(s.get("doc_fit") or 0 for s in sections)
    qd = sum((d["parsed"].get("detail") or {}).get("div_1b", 0) or 0 for d in docs
             if isinstance(d.get("parsed"), dict) and d.get("route") not in ("skipped", "excluded"))
    return dict(sections=sections, qd=round(qd, 2), py_total=py_total, cy_total=cy_total, cy_total_wo_schc=cy_total - cy_schc,
                py_fit=py_income.get("fit"), cy_fit=cy_fit, doc_total=doc_total, doc_fit=doc_fit,
                py_year=py_year, cy_year=cy_year, total_note=total_note)


_TXT: dict = {}
_SUFFIX = {"LLC", "INC", "CORP", "CO", "LTD", "PLLC", "PA", "PC", "LP", "LLP", "THE", "AND", "&", "COMPANY", "CORPORATION", "GROUP"}


def _match_business(path, biz):
    """Index of the business whose name is printed on the 1099 (recipient), else None."""
    if not path or not biz:
        return None
    if path not in _TXT:
        try:
            from .pdfutil import open_pdf, page_text
            doc, _ = open_pdf(path)
            with doc:
                _TXT[path] = " ".join(page_text(doc, i) for i in range(min(len(doc), 6))).upper()
        except Exception:  # noqa: BLE001
            _TXT[path] = ""
    import re as _re
    txt = _re.sub(r"[^A-Z0-9 ]", " ", _TXT[path])
    hits = []
    for i, n in biz:
        toks = [t for t in _re.sub(r"[^A-Z0-9 ]", " ", n.upper()).split() if t not in _SUFFIX and len(t) >= 3]
        if toks and all(_re.search(r"\b" + t + r"\b", txt) for t in toks):
            hits.append(i)
    if len(hits) == 1:
        return hits[0]
    if not hits and len(biz) == 1:
        return biz[0][0]
    return None


def _moved(base, now) -> bool:
    """The per-document amount a correction was typed over is no longer the per-document amount."""
    if base is None or now is None:
        return (base is None) != (now is None)
    return abs(base - now) > 0.005


def per_doc(inc: dict, ded: dict | None = None) -> dict:
    """{line id: (per document, per document withholding)} - what a correction is typed over."""
    return {r["id"]: (r.get("doc_cy"), r.get("doc_fit")) for summ in (inc, ded or {"sections": []})
            for s in summ["sections"] for r in s["rows"]}


def stamp_edits(new: dict, old: dict, docs_now: dict) -> dict:
    """Corrections from the page: each keeps the per-document amount it was typed over ("base" / "base_fit"). A correction that
    didn't change keeps its base (so a later change of per document shows as stale); a new / changed one takes the current one."""
    out = {}
    for rid, e in (new or {}).items():
        if not isinstance(e, dict):
            continue
        e = {k: v for k, v in e.items() if k not in ("base", "base_fit")}
        prev = (old or {}).get(rid) or {}
        dc, df = docs_now.get(rid, (None, None))
        for k, b in (("cy", "base"), ("fit", "base_fit")):
            if k not in e:
                continue
            if k in prev and prev[k] == e[k] and b in prev:
                e[b] = prev[b]
            elif rid in docs_now:
                e[b] = dc if k == "cy" else df
        out[rid] = e
    return out


def _first_key(amts: dict):
    for k, _, _ in CATS:
        if amts.get(k):
            return k
    return next(iter(amts), None)


# ---------------------------------------------------------------- deduction summary (same layout, separate table; not in UT)
DED_CATS = [
    ("student_loan", "Total Student Loan Interest", []),
    ("mortgage", "Total Mortgage Interest", []),
]
DED_FEEDS = {"1098e": ["student_loan"], "1098": ["mortgage"]}


def build_deduction_summary(py_income: dict, docs: list, py_year, cy_year, edits=None, added=None) -> dict:
    d = build_income_summary(py_income, docs, None, py_year, cy_year, edits, added, cats=DED_CATS, feeds=DED_FEEDS)
    for sec in d["sections"]:
        for r in sec["rows"]:
            r["fit"] = None
    if len(d["sections"]) == 1:                  # one kind of deduction: its total is the total (no separate subtotal)
        d["sections"][0]["label"] = "Total Deductions"
    return d
