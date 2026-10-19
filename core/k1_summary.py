"""k1_summary.py - K-1 box -> income-summary section (copied from C:\\dev\\K-1_interpretation\\k1_summary.py)."""
from __future__ import annotations


def _amts(k):
    """box+code -> summed amount, plus statement-only keys."""
    a, stmt_only, stmt = {}, [], set()
    for l in k["lines"]:
        key = l["box"] + (l.get("code") or "")
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
    put("lt", ["9a", "10"], c)
    put("st", ["8"])
    put("rent", ["2", "3", "7"], [f"Includes royalties {_money(a['7'])} (box 7)"] if a.get("7") else [])

    gp_keys = ["4c"] if a.get("4c") else ["4a", "4b"]
    b11 = [x for x in a if x.startswith("11")]
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
    put("ord", ["1"] + gp_keys + b11, c)
    return out
