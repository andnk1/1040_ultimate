"""handoff.py - what "Upload to 1040" on the K-1 Verification page leaves for the 1040 verification.

Kept in memory while the program runs (one entry per K-1 upload, so several batches of K-1s add up; uploading the
same batch again replaces it) and mirrored to a file in the _work folder, which the program deletes at start-up
(no client data stays on disk).

  payload = {"token", "file", "n", "sections": {int|div|lt|st|rent|ord: [row]}, "k1s": [back-channel record]}
  row     = {"doc", "amt", "comment", "page", "sub"}          -> lines of the 1040 income summary
  record  = {"name", "ein", "page", "amounts": {section: amount}}   -> back channel, never shown to the preparer
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

_LOCK = threading.Lock()
_STORE: dict = {}
_FILE: Path | None = None

# K-1 summary section -> 1040 income summary category
TO_CAT = {"int": "interest", "div": "dividends", "lt": "lt", "st": "st", "rent": "rental", "ord": "k1"}
SUB_LABEL = {"E": "", "A": " — other portfolio income (11A)", "1": " — other income, Sch 1 (11ZZ)"}


def init(work_dir) -> None:
    global _FILE
    _FILE = Path(work_dir) / "k1v_handoff.json"


def _mirror() -> None:
    if not _FILE:
        return
    try:
        if _STORE:
            _FILE.parent.mkdir(parents=True, exist_ok=True)
            _FILE.write_text(json.dumps(list(_STORE.values())), encoding="utf-8")
        elif _FILE.exists():
            _FILE.unlink()
    except OSError:
        pass


def _load() -> None:
    if _STORE or not _FILE or not _FILE.exists():
        return
    try:
        for p in json.loads(_FILE.read_text(encoding="utf-8")):
            _STORE[p["token"]] = p
    except (OSError, ValueError, KeyError):
        pass


def put(payload: dict) -> None:
    with _LOCK:
        _load()
        _STORE[payload["token"]] = payload
        _mirror()


def clear(token: str | None = None, owner: str | None = None) -> None:
    with _LOCK:
        _load()
        if token:
            _STORE.pop(token, None)
        elif owner:
            for t in [t for t, p in _STORE.items() if p.get("owner") == owner]:
                _STORE.pop(t, None)
        else:
            _STORE.clear()
        _mirror()


def payloads(owner: str | None = None) -> list:
    """The uploads that belong to one 1040 run (owner = its token). An upload nobody owns yet (made on the separate
    K-1 page) is taken by the first 1040 run that asks - so K-1s of one client never show up on another client's run."""
    with _LOCK:
        _load()
        out, claimed = [], False
        for p in _STORE.values():
            if owner and not p.get("owner"):
                p["owner"], claimed = owner, True
            if owner is None or p.get("owner") == owner:
                out.append(p)
        if claimed:
            _mirror()
        return out


def set_owner(token: str, owner: str) -> None:
    with _LOCK:
        _load()
        if token in _STORE:
            _STORE[token]["owner"] = owner
            _mirror()


def info(owner: str | None = None) -> dict:
    ps = payloads(owner)
    return dict(batches=len(ps), k1s=sum(p.get("n", 0) for p in ps), files=[p.get("file", "") for p in ps])


def norm(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())


def same_name(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 8 and (a.startswith(b) or b.startswith(a)))


def build_payload(token: str, filename: str, k1s: list, corr: dict, summary: dict, owner: str | None = None) -> dict:
    """summary = build_summary(k1s); corr = {rid: typed correction} from the Income Summary on the K-1 page."""
    def val(rid, fed):
        t = str((corr or {}).get(rid, "") or "").replace("$", "").replace(",", "").replace(" ", "")
        if not t:
            return fed
        neg = (t.startswith("(") and t.endswith(")")) or t.startswith("-")
        t = t.strip("()-")
        try:
            v = float(t)
        except ValueError:
            return fed
        return -v if neg else v

    sections, per_page = {}, {}
    for s in summary["sections"]:
        if s["key"] not in TO_CAT:
            continue
        rows = []
        for r in s["rows"]:
            amt = val(r["rid"], r["amt"])
            if not amt and not r.get("comment"):
                continue
            changed = amt != r["amt"]
            rows.append(dict(doc=r["doc"] + SUB_LABEL.get(r.get("sub") or "E", "") if s["key"] == "ord" else r["doc"],
                             amt=amt, page=r["page"], sub=r.get("sub") or "",
                             comment=(r["comment"] + ("; " if r["comment"] else "") + (f"corrected from {r['amt']:,.0f}" if changed else ""))))
            per_page.setdefault(r["page"], {}).setdefault(s["key"], 0)
            per_page[r["page"]][s["key"]] += amt
        for i, label in enumerate(s["adj"]):               # typed carry-forward / add-back lines
            amt = val(s["adj_rids"][i], 0)
            if amt:
                rows.append(dict(doc=f"K-1 adjustment — {label}", amt=amt, page=0, sub="", comment="typed on the K-1 page"))
        if rows:
            sections[s["key"]] = rows
    recs = [dict(name=k.get("name") or "", ein=k.get("ein") or "", page=k["page"], amounts=per_page.get(k["page"], {}))
            for k in k1s if k.get("form") == "1065"]
    return dict(token=token, file=filename, owner=owner, n=len(recs), sections=sections, k1s=recs)
