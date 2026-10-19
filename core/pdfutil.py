"""pdfutil.py - open PDFs (incl. password-protected), page text, text-layer check.

Password rules (same as PDF_Mask\\k1_summary.py), tried in order:
  1. no password
  2. text after "PW" in the file name ("... PW-2400.pdf" -> 2400)
  3. every other 4+ character letter/digit chunk of the file name
  4. extra passwords passed in
"""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf


def password_candidates(path: Path, extra=None) -> list[str]:
    stem = Path(path).stem
    out = []
    m = re.search(r"PW\s*[-_ ]?\s*([A-Za-z0-9]+)", stem)
    if m:
        out.append(m.group(1))
    out += re.findall(r"[A-Za-z0-9]{4,}", stem)
    out += list(extra or [])
    seen, res = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            res.append(p)
    return res


def open_pdf(path, extra_passwords=None):
    """Returns (doc, password_used or None). Raises ValueError('password') if it can't be opened."""
    doc = pymupdf.open(str(path))
    if not doc.needs_pass:
        return doc, None
    for pw in password_candidates(path, extra_passwords):
        if doc.authenticate(pw):
            return doc, pw
    doc.close()
    raise ValueError("password")


def page_text(doc, i: int) -> str:
    try:
        return doc[i].get_text() or ""
    except Exception:  # noqa: BLE001
        return ""


def has_text(t: str) -> bool:
    return len(re.sub(r"\s+", "", t)) > 40


# ---------------------------------------------------------------- one package, several accounts
_ACCT = [re.compile(r"Account(?:\s+(?:Number|No\.?|#))?\s*:?\s*\n?\s*([0-9][0-9\-]{5,}[0-9])"),
         re.compile(r"End Notes for Account\s+([0-9\-]{6,})")]


def page_accounts(path) -> list:
    """The account number printed on each page (None when the page shows none)."""
    doc, _ = open_pdf(path)
    out = []
    with doc:
        for i in range(len(doc)):
            t = page_text(doc, i)
            acct = None
            for rx in _ACCT:
                m = rx.search(t)
                if m:
                    acct = re.sub(r"\D", "", m.group(1))
                    break
            out.append(acct)
    return out


def split_accounts(path, work_dir) -> list:
    """A brokerage package with 2+ accounts -> one PDF per account (in work_dir): [{account, path, pages}].
    Pages without an account number go with the account before them; leading pages go with the first account.
    Returns [] when the package has one account."""
    accts = page_accounts(path)
    seen = [a for a in dict.fromkeys(a for a in accts if a)]
    if len(seen) < 2 or any(sum(1 for a in accts if a == s) < 2 for s in seen):
        return []
    cur, owner = seen[0], []
    for a in accts:
        cur = a or cur
        owner.append(cur)
    doc, pw = open_pdf(path)
    out = []
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    with doc:
        for s in seen:
            pages = [i for i, o in enumerate(owner) if o == s]
            part = pymupdf.open()
            for i in pages:
                part.insert_pdf(doc, from_page=i, to_page=i)
            p = Path(work_dir) / f"{Path(path).stem} - acct {s[-4:]}.pdf"
            part.save(str(p))
            part.close()
            out.append(dict(account=s, path=str(p), pages=[i + 1 for i in pages]))
    return out
