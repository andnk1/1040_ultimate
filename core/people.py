"""people.py - pre-fill the masking tabs from the prior-year Form 1040 page 1.

Only the obvious is pre-filled: SSNs (taxpayer, spouse, dependents - shown as 123-45-6789) and city + ZIP.
Names, street address, phones, e-mails, accounts are typed by the user.
Works on the IRS form layout (UltraTax, Intuit, ...). Everything is editable on screen.
"""
from __future__ import annotations

import re

import pdfplumber

from .pdfutil import open_pdf, page_text

SSN = re.compile(r"\d{3}[-\s]?\d{2}[-\s]?\d{4}")


def _rows(words, tol=3):
    out = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(out[-1][0] - w["top"]) < tol:
            out[-1][1].append(w)
        else:
            out.append([w["top"], [w]])
    for r in out:
        r[1].sort(key=lambda w: w["x0"])
    return out


def _txt(ws):
    return " ".join(w["text"] for w in ws).strip()


def _value_row(rows, i, maxgap=20, xmax=None):
    """First row under rows[i] that holds values (not another label). Only the left part (x < xmax) is looked at."""
    top = rows[i][0]
    for t, wl in rows[i + 1:i + 4]:
        if t - top > maxgap:
            break
        wl = [w for w in wl if xmax is None or w["x0"] < xmax]
        if not wl:
            continue
        s = _txt(wl)
        if re.search(r"first name|Home address|City, town|Foreign country|Presidential|Check here|spouse.s if filing", s, re.I):
            continue
        return wl
    return None


def _ssn_from(ws):
    s = " ".join(w["text"] for w in ws)
    m = SSN.search(s)
    return m.group(0) if m else ""


def read_people(path) -> list[dict]:
    doc, pw = open_pdf(path)
    with doc:
        flat = [re.sub(r"\s+", " ", page_text(doc, i)) for i in range(min(len(doc), 60))]
    p1 = next((i for i, t in enumerate(flat) if "Individual Income Tax Return" in t and "first name" in t and "Reconciliation" not in t), None)
    people = [dict(role="Taxpayer", first="", last="", ssn="", address="", city="", phone="", email="", ein="", accounts="", other="")]
    if p1 is None:
        return people
    with pdfplumber.open(str(path), password=pw or "") as pdf:
        page = pdf.pages[p1]
        W = page.width
        rows = _rows(page.extract_words())
        labels = {}
        for i, (t, wl) in enumerate(rows):
            s = _txt(wl)
            if "Your first name" in s:
                labels["tp"] = i
                labels["last_x"] = next((w["x0"] for w in wl if w["text"] == "Last"), W * 0.37)
                labels["ssn_x"] = next((w["x0"] for k, w in enumerate(wl) if w["text"] == "Your" and k > 0), W * 0.76)
            elif re.search(r"spouse.s first name|use.s first name", s) and "sp" not in labels:
                labels["sp"] = i
            elif s.startswith("Home address"):
                labels["addr"] = i
                labels["apt_x"] = next((w["x0"] for w in wl if w["text"].startswith("Apt")), W * 0.68)
            elif s.startswith("City, town"):
                labels["city"] = i
                labels["state_x"] = next((w["x0"] for w in wl if w["text"] == "State"), W * 0.5)
                labels["zip_x"] = next((w["x0"] for w in wl if w["text"] == "ZIP"), W * 0.61)
        lx, sx = labels.get("last_x", W * 0.37), labels.get("ssn_x", W * 0.76)

        def person(i, role):
            wl = _value_row(rows, i, xmax=W * 0.95) if i is not None else None
            if not wl:
                return None
            first = _txt([w for w in wl if w["x0"] < lx - 2])
            last = _txt([w for w in wl if lx - 2 <= w["x0"] < sx - 10])
            ssn = _ssn_from([w for w in wl if w["x0"] >= sx - 10])
            if not (first or last or ssn):
                return None
            return dict(role=role, first=first, last=last, ssn=ssn)

        tp = person(labels.get("tp"), "Taxpayer")
        if tp:
            people[0].update(tp)
        sp = person(labels.get("sp"), "Spouse")
        if sp:
            people.append(dict(people[0], **sp, address="", city=""))
        if "addr" in labels:
            wl = _value_row(rows, labels["addr"], xmax=W * 0.75)
            if wl:
                people[0]["address"] = _txt([w for w in wl if w["x0"] < W * 0.8])
        if "city" in labels:
            wl = _value_row(rows, labels["city"], xmax=W * 0.75)
            if wl:
                city = _txt([w for w in wl if w["x0"] < labels["state_x"] - 2])
                zipc = _txt([w for w in wl if labels["zip_x"] - 5 <= w["x0"] < W * 0.8])
                people[0]["city"] = "; ".join(x for x in (city, zipc) if x)
        people += _dependents(rows, W)
    # Pre-fill only the obvious: SSNs (as 123-45-6789) and city + ZIP. Names, addresses etc. are typed by the user.
    out = []
    for p in people:
        d = re.sub(r"\D", "", p.get("ssn") or "")
        ssn = f"{d[:3]}-{d[3:5]}-{d[5:]}" if len(d) == 9 else ""
        city = p.get("city") or ""
        city = city if re.search(r"\b\d{5}(-\d{4})?\b", city) else ""
        q = dict(role=p["role"], ssn=ssn, city=city)
        for k in ("first", "last", "address", "phone", "email", "ein", "accounts", "other"):
            q[k] = ""
        if p["role"] == "Taxpayer" or ssn or city:
            out.append(q)
    for i, q in enumerate([q for q in out if q["role"].startswith("Dependent")]):
        q["role"] = f"Dependent {i + 1}"
    return out


def _dependents(rows, W) -> list[dict]:
    """Dependents' SSNs from Form 1040 page 1 ("Dependents (see instructions): ... (2) Social security number").
    Soft look: every SSN-shaped number in the dependents block, whatever the layout (2024 rows or 2025 columns)."""
    start = next((i for i, (t, wl) in enumerate(rows) if _txt(wl).startswith("Dependents")), None)
    if start is None:
        return []
    out = []
    for t, wl in rows[start:start + 14]:
        s = _txt(wl)
        if start != rows.index([t, wl]) and re.search(r"\b1a\b|^Income\b|Attach Form", s):
            break
        for m in re.finditer(r"(?<![\d,.$])(\d{3}[-\s]?\d{2}[-\s]?\d{4})(?![\d,.])", s):
            out.append(dict(role=f"Dependent {len(out) + 1}", first="", last="", ssn=m.group(1)))
    return out
