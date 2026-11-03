"""
screen_verify.py - 1040 Verification from the UltraTax "Input Screens" print (replaces the return-based check).

For every K-1 item: what was typed on the UltraTax K-1 screens (K1-2 ... K1-6, K1QBI) for that partnership.
  green  - entered = K-1 (within $1)
  red    - not entered / entered at a different amount / K-1 not in UltraTax / entered in UT but not on the K-1
  manual - amount is on a statement (the UT entries for that box are listed), or needs a manual look
  fyi    - not entered in UltraTax on purpose (information only)
Matching K-1 <-> UltraTax unit: full EIN (the input screens show it), then name. Several K-1s / units with the
same EIN are compared in total.
Boxes 1, 2 and 3 are compared with what was typed on K1-2; the K1QBI amounts are shown as information.
"""
from __future__ import annotations

import difflib
import re

from .verify1040_parser import norm
from .verify1040_rules import MAP as OLD_MAP
from .k1_rules import RULES as K1RULES

TOL = 1.0
CODE_BOXES = {"11", "13", "14", "15", "17", "18", "19", "20"}
PASSIVE_BOXES = {k for k, r in K1RULES.items() if r.get("passive")}
STOP = {"lp", "llc", "l", "p", "fund", "a", "series", "of", "the", "inc", "us", "ii", "i", "iii", "iv", "c", "o"}
VALUE_SCREENS = ("K1-2", "K1-3", "K1-4", "K1-5", "K1-6", "K1-7")

# K-1 item -> how to find it on the screens: list of (screen or None, code or None, label start or None)
SPECIAL = {
    "1": dict(qbi="ordinary business income", main=[("K1-2", "1", None)]),
    "2": dict(qbi="rental income", main=[("K1-2", "2", None)]),
    "3": dict(qbi="other rental income", main=[("K1-2", "3", None)]),
    "13H": dict(main=[("K1-3", "13H", None), ("K1-3", None, "investment interest expense - schedule e")]),
    "13AE": dict(main=[("K1-3", None, "portfolio deductions - subject to 2%")]),
}
# K-1 items that preparers type under another code - not an error, just a note (Lady 2026-10-08)
ALTS = {"13AE": ["13ZZ", "13L"], "11C": ["11A"], "17D": ["17C"], "20AK": ["11ZZ"]}

EXPECT = {   # where it should have been typed (shown when nothing was entered)
    "13AE": "Not found — checked K1-3 13ZZ, 13L and Portfolio deductions (2%)",
    "11C": "Not found — checked K1-2 11C and 11A",
    "17D": "Not found — checked K1-5 17D and 17C",
    "20AK": "Not found — checked 20AK and K1-2 11ZZ",
    "13H": "K1-3 · 13H Investment interest expense - Schedule A / - Schedule E (empty)",
}
FYI = {   # not typed in UltraTax on purpose
    "4c": "Total of 4a + 4b — checked through 4a / 4b.",
    "16": "K-3 attached — review the K-3.",
    "19D": "Do not enter — deemed distribution; ties to the K1 liability change.",
    "20A": "UltraTax computes investment income from Box 5 / 6 — not entered separately.",
    "20AA": "§704(c) information — information only.",
    "20AG": "Gross receipts (§448(c) test) — information only.",
    "22": "More than one activity (at-risk) — information only.",
    "23": "More than one activity (passive) — information only.",
}
MANUAL = {
    "18A": "Tax-exempt interest is entered in the box 5 statement dialog — not printed on the input screens.",
    "20Z": "QBI — compare the §199A statement with Screen K1QBI (listed below).",
}


def _codes(code):
    """'15C,D' -> ['15C', '15D']; '13ZZ' -> ['13ZZ']"""
    if not code:
        return []
    m = re.match(r"^(\d{1,2})([A-Z,]+)$", code)
    if m and "," in m.group(2):
        return [m.group(1) + c for c in m.group(2).split(",") if c]
    return [code]


def _tokens(name):
    return {t for t in norm(name).split() if t not in STOP}


def _score(a, b):
    ta, tb = _tokens(a), _tokens(b)
    return max(len(ta & tb) / max(1, min(len(ta), len(tb))), difflib.SequenceMatcher(None, norm(a), norm(b)).ratio())


def _ein(s):
    d = re.sub(r"\D", "", s or "")
    return d if len(d) == 9 else ""


def _fmt(v):
    return f"{v:,.0f}" if v == round(v) else f"{v:,.2f}"


def _where(fs):
    out = []
    for f in fs:
        out.append(f"{f['screen']} · {(f['code'] + ' ') if f['code'] and f['code'] != '-' else ''}{f['label']}".strip())
    return " + ".join(dict.fromkeys(out))


def _val(f):
    return f["fed"] if f["fed"] not in (None, 0) else None


def group_match(k1s, units):
    """-> list of (k1 list, unit list, how)"""
    by_ein_k, by_ein_u, loose_k = {}, {}, []
    for k in k1s:
        e = _ein(k.get("ein"))
        if e:
            by_ein_k.setdefault(e, []).append(k)
        else:
            loose_k.append(k)
    for u in units:
        by_ein_u.setdefault(_ein(u.get("ein")), []).append(u)
    out, used_u = [], set()
    for e, ks in by_ein_k.items():
        us = by_ein_u.get(e, [])
        if us:
            out.append((ks, us, "EIN"))
            used_u.update(id(u) for u in us)
        else:
            loose_k.extend(ks)
    for k in loose_k:     # EIN not read on the K-1, or no UT unit with that EIN -> name
        d4 = re.sub(r"\D", "", k.get("ein") or "")
        if len(d4) == 4:      # redacted K-1: only the last 4 digits printed
            c4 = [u for u in units if id(u) not in used_u and _ein(u.get("ein")).endswith(d4)]
            e4 = {_ein(u.get("ein")) for u in c4}
            if len(e4) == 1:
                out.append(([k], c4, "EIN last 4"))
                used_u.update(id(u) for u in c4)
                continue
        best, sc = None, 0
        for u in units:
            if id(u) in used_u:
                continue
            s = _score(k.get("name", ""), u.get("name", ""))
            if s > sc:
                best, sc = u, s
        if best is not None and sc >= (0.75 if not _ein(k.get("ein")) else 0.85):
            same = [u for u in units if _ein(u.get("ein")) == _ein(best.get("ein")) and id(u) not in used_u]
            how = "name" if not _ein(k.get("ein")) else f"name — EIN differs: K-1 {k.get('ein')}, UltraTax {best.get('ein')}"
            out.append(([k], same, how))
            used_u.update(id(u) for u in same)
        else:
            out.append(([k], [], None))
    orphans = [u for u in units if id(u) not in used_u]
    return out, orphans


# 1120-S codes UltraTax doesn't print next to a 1065 line
S_EXTRA = {"17V": "20Z", "18": "22", "19": "23"}


def to_1065(k, pairs):
    """Schedule K-1 (1120-S): renumber each box to the 1065 code of the same UltraTax line (from the 1120S code
    column on the input screens, e.g. 1120-S 4 -> 5, 12ZZ -> 13ZZ, 15A -> 17A); the 1120-S box stays for display."""
    m = {}
    for c1, c0 in pairs:
        a, b = _codes(c1), _codes(c0)
        for i, x in enumerate(a):
            if b and (b[i] if i < len(b) else b[-1]):
                m.setdefault(x, b[i] if i < len(b) else b[-1])
    m.update({x: y for x, y in S_EXTRA.items() if x not in m})
    src = k.get("lines") or []
    k = dict(k, lines=[])
    for l in src:
        new = m.get(l["key"]) or m.get(l["box"]) if not l.get("code") else m.get(l["key"])
        if not new and l.get("code") and l["box"] in m:      # code not printed in UT: renumber the box only
            new = m[l["box"]] + l["code"]
        new = new or l["key"]
        box = re.match(r"\d+", new).group(0)
        k["lines"].append(dict(l, key=new, box=box, code=new[len(box):] or None, s_key=l["key"], s_box=l["box"], s_code=l.get("code")))
    return k



def _type_item(ks, us):
    k = ks[0]
    ut_g = {"1": "General", "2": "Limited"}.get((us[0].get("partner") or "").strip()[:1], "")
    if k.get("form") == "1120-S":
        ut_g = ""
    pcode = (us[0].get("passive") or "").strip()[:1]
    ut_p = {"1": "Other passive", "2": "Rental real estate (active participation)", "3": "No limitation",
            "4": "Real estate professional"}.get(pcode, "blank (= other passive)")
    has = sorted({l["key"] for kk in ks for l in kk["lines"] if l["box"] in PASSIVE_BOXES and not l.get("code") and l.get("amt")})
    it = dict(key="Type", box="Partner / passive type", code=None, amt=None, check=False, stmt=False, kind="type",
              form="K1 · G Type of partner / K1-2 · Passive activity code", entered=None, note=None, group=None,
              k1_total=None, page=None, row=None, manual=False, ut_type=f"{ut_g or '?'} · {ut_p}",
              k1_type=("S corporation shareholder" if k.get("form") == "1120-S" else
                       (k.get("G") or "?") + (" partner" if k.get("G") else "") + (" · PTP" if k.get("ptp") else "")))
    msgs, st = [], "green"
    if k.get("G") and ut_g and k["G"] != ut_g:
        st = "red"
        msgs.append(f"K-1 says {k['G']} partner, UT screen K1 has {ut_g}.")
    boxes = ", ".join("Box " + b for b in has)
    if not has:
        if st == "green":
            st = "fyi"
        msgs.append("Portfolio items only (no box 1, 2, 3 or 10) — passive code doesn't change the return.")
    elif k.get("G") == "Limited" and pcode in ("3", "4"):
        st = "red"
        msgs.append(f"Limited partner with {boxes} — expected passive (code 1 or 2), UT has {ut_p}.")
    elif k.get("G") == "General" and st != "red":
        st = "amber"
        msgs.append(f"General partner with {boxes} — passive unless the client materially participates; confirm.")
    else:
        msgs.append(f"{boxes} — UT passive code: {ut_p}.")
    it.update(status=st, msg=" ".join(msgs))
    return it


def verify_screens(k1s: list, scr: dict) -> dict:
    units = list(scr["units"].values())
    k1s = [k if k.get("form") == "1065" else to_1065(k, scr.get("pairs", [])) for k in k1s if k.get("form") in ("1065", "1120-S")]
    groups, orphans = group_match(k1s, units)
    cards, counts = [], dict(green=0, amber=0, red=0, fyi=0, manual=0, cant=0)
    for ks, us, how in sorted(groups, key=lambda g: (g[0][0].get("name") or "~").lower()):
        fields = [f for u in us for f in u["fields"]]
        valf = [f for f in fields if f["screen"] in VALUE_SCREENS and _val(f) is not None]
        used = set()
        items = []
        lines = [l for k in ks for l in k["lines"] if (l.get("amt") not in (None, 0)) or l.get("check") or l.get("stmt")]
        if us and lines:
            items.append(_type_item(ks, us))
        # K-1 amounts per key (several K-1 pages with the same EIN are added)
        order, per = [], {}
        for l in lines:
            if l["key"] not in per:
                order.append(l["key"])
                per[l["key"]] = dict(l, amt=None if l.get("amt") is None else 0.0, manual=False, n=0)
            p = per[l["key"]]
            if l.get("amt") is not None:
                p["amt"] = (p["amt"] or 0) + l["amt"]
            p["manual"] = p["manual"] or bool(l.get("manual"))
            p["stmt"] = p.get("stmt") or l.get("stmt")
            p["n"] += 1
        # boxes that have a "See statement" line on the K-1 -> UT entries in those boxes belong to the statement
        stmt_boxes = {per[k]["box"] for k in order if per[k].get("amt") is None and per[k].get("stmt") and not per[k].get("check")}

        def find(key):
            sp = SPECIAL.get(key)
            if sp:
                out = []
                for scrn, code, lab in sp["main"]:
                    out += [f for f in fields if f["screen"] == scrn and (code is None or code in _codes(f["code"]))
                            and (lab is None or f["label"].lower().startswith(lab))]
                return out
            return [f for f in fields if f["screen"] in VALUE_SCREENS and key in _codes(f["code"])]

        # 13AE typed as 13ZZ or 13L, 11C typed as 11A: find it there (alone, or added to the K-1's own amount for that code)
        resolved, alt_into = {}, {}
        for key, alts in ALTS.items():
            if not us or key not in per or per[key].get("amt") is None or any(_val(f) for f in find(key)):
                continue
            amt = per[key]["amt"]
            for a in alts:
                af = [f for f in valf if a in _codes(f["code"])]
                if not af:
                    continue
                tot = sum(_val(f) for f in af)
                own = per[a]["amt"] if a in per and per[a].get("amt") is not None else 0
                exp = own + sum(x for _, x in alt_into.get(a, [])) + amt
                same = (lambda x, y: abs(abs(x) - abs(y)) <= TOL) if key.startswith(("13", "17")) else (lambda x, y: abs(x - y) <= TOL)
                if same(tot, exp):          # typed together with the K-1's own amount for that code
                    resolved[key] = (a, af)
                    alt_into.setdefault(a, []).append((key, amt))
                    break
                if own and same(tot, amt):  # typed there instead of the K-1's own amount
                    resolved[key] = (a, af)
                    break

        for key in order:
            l = per[key]
            it = dict(key=key, box=l.get("s_box", l["box"]), code=l.get("s_code", l.get("code")), amt=l.get("amt"), check=l.get("check"), stmt=l.get("stmt"),
                      kind="verify", form="", entered=None, note=None, group=None, k1_total=None, page=None, row=None,
                      manual=l["manual"])
            notes = [f"Total of {l['n']} K-1s with this EIN"] if len(ks) > 1 and l["n"] > 1 else []
            if l.get("s_key") and l["s_key"] != key:
                notes.append(f"1120-S box {l['s_key']} = UltraTax line {key}")
            is_fyi = key not in MANUAL and key not in SPECIAL and (key in FYI or (OLD_MAP.get(key, {}).get("kind") == "fyi" and key != "20B"))
            nocode = l["box"] in CODE_BOXES and not l.get("code")
            if is_fyi:
                it.update(kind="fyi", status="fyi", msg=FYI.get(key) or OLD_MAP[key].get("why", ""))
                fs = find(key)
                if fs and any(_val(f) for f in fs) and key not in ("4c",):
                    used.update(id(f) for f in fs)
                    it.update(status="manual", entered=sum(_val(f) or 0 for f in fs), form=_where(fs),
                              msg="Entered in UT — " + it["msg"])
            elif key == "20B":
                fs = find(key)
                used.update(id(f) for f in fs)
                if any(_val(f) for f in fs):
                    it.update(status="manual", entered=sum(_val(f) or 0 for f in fs), form=_where(fs),
                              msg="Entered in UT (Form 4952), but it shouldn't be — already included in Box 13 AE.")
                else:
                    it.update(kind="fyi", status="fyi", msg="Do not enter — already included in Box 13 AE (Portfolio deductions).")
            elif not us:
                it.update(status="red", msg="K-1 not found in UltraTax")
            elif l.get("amt") is None or nocode:
                fs = [f for f in valf if f["code"] and f["code"] != "-" and re.match(r"\d+", f["code"])
                      and re.match(r"\d+", f["code"]).group(0) == l["box"] and id(f) not in used]
                used.update(id(f) for f in fs)
                if key in MANUAL:
                    fs += [f for f in fields if f["screen"] == "K1QBI" and _val(f) is not None] if key == "20Z" else []
                what = "Code not read on the K-1" if nocode and l.get("amt") is not None else "Amount is on the statement"
                it.update(kind="manual", status="manual",
                          msg=MANUAL.get(key) or (f"{what} — compare with the UT entries for box {l['box']}" if fs else
                                                  f"{what} — nothing entered in UT for box {l['box']}"))
                if fs:
                    it["note"] = "UT: " + "; ".join(f"{f['screen']} {f['code'] or ''} {f['label']} {_fmt(_val(f))}".replace("  ", " ") for f in fs)
                    it["entered"] = sum(_val(f) for f in fs) if all(f["screen"] != "K1QBI" for f in fs) else None
            elif key in MANUAL:
                it.update(kind="manual", status="manual", msg=MANUAL[key])
            elif key in resolved:
                a, af = resolved[key]
                used.update(id(f) for f in af)
                lab = af[0]["label"]
                it.update(status="green", msg=f"Entered in UT under {a} ({lab})", form=_where(af), entered=l["amt"], page=af[0]["page"])
                notes.append(f"Note: {key} is typed as {a} {lab}" + (f" — together with the K-1's own {a}" if a in per else ""))
            else:
                sp = SPECIAL.get(key, {})
                fs = find(key)
                used.update(id(f) for f in fs)
                main = sum(_val(f) or 0 for f in fs) if fs else None
                cmp_v, src = main, fs
                if sp.get("qbi"):   # information only: what was typed on Screen K1QBI
                    q = [f for f in fields if f["screen"] == "K1QBI" and f["label"].lower().startswith(sp["qbi"]) and _val(f) is not None]
                    if q:
                        qv = sum(_val(f) for f in q)
                        notes.append("K1QBI: " + " + ".join(_fmt(_val(f)) for f in q) + (f" = {_fmt(qv)}" if len(q) > 1 else "")
                                     + ("" if abs(qv - l["amt"]) <= TOL else " — differs from the K-1"))
                parts = [f for f in fs if _val(f) is not None]
                if len(parts) > 1 and not sp.get("qbi"):
                    notes.append("UT: " + "; ".join(f"{f['label']} {_fmt(_val(f))}" for f in parts))
                it.update(form=_where(src or fs) or f"Box {key}", entered=cmp_v if (cmp_v or None) is not None else None,
                          page=(src or fs or [{}])[0].get("page"))
                absmode = l["box"] in ("12", "13", "21") or key in ("13H", "13AE")
                plus = alt_into.get(key, [])
                exp = l["amt"] + sum((abs(x) if absmode else x) for _, x in plus) if not absmode else abs(l["amt"]) + sum(abs(x) for _, x in plus)
                if plus:
                    notes.append(f"UT {key} also includes " + ", ".join(f"K-1 {k} {_fmt(x)}" for k, x in plus) + f" — compared with {_fmt(exp)}")
                if not cmp_v and key not in EXPECT and not any(key in _codes(c) for _, c in scr.get("codes", [])):
                    # UltraTax has no input line with this code -> warning, not an error
                    it.update(status="cant", msg=f"No UltraTax entry with code {key}", form="No input line with this code on the UltraTax K-1 screens")
                elif not cmp_v:
                    it.update(status="red", msg="Not entered in UT", form=EXPECT.get(key) or f"Not typed on the UltraTax screens (code {key})")
                elif (abs(abs(cmp_v) - abs(exp)) if absmode else abs(cmp_v - exp)) > TOL:
                    it.update(status="red", msg="Entered amount differs from the K-1")
                else:
                    it.update(status="green", msg="Entered as on the K-1")
            if notes:
                it["note"] = " · ".join(([it["note"]] if it.get("note") else []) + notes)
            counts[it["status"]] += 1
            items.append(it)
        # UT entries with a K-1 code that are not on the K-1
        for f in valf:
            if id(f) in used or not f["code"] or f["code"] == "-" or not re.match(r"\d", f["code"]):
                continue
            box = re.match(r"\d+", f["code"]).group(0)
            if box in stmt_boxes:
                continue
            it = dict(key=f["code"], box=f["code"], code=None, amt=None, check=False, stmt=False, kind="verify",
                      form=_where([f]), entered=_val(f), note=None, group=None, k1_total=None, page=f["page"], row=None,
                      manual=False, extra=True, status="red", msg="Entered in UT but not on the K-1")
            counts["red"] += 1
            items.append(it)
        # hint: a K-1 item not entered + a UT entry of the same amount under another code
        extras = [x for x in items if x.get("extra")]
        for x in items:
            if x["status"] == "red" and not x.get("extra") and x.get("amt") and not x.get("entered"):
                for e in extras:
                    if e.get("entered") and abs(abs(e["entered"]) - abs(x["amt"])) <= TOL:
                        x["note"] = ((x.get("note") or "") + " · " if x.get("note") else "") + f"UT has the same amount as {e['form']}"
                        e["note"] = f"Same amount as K-1 box {x['key']} — entered under the wrong code?"
        # entries not on the face of the K-1: red when the K-1 has no statement, else check against the statement
        has_stmt = any(l.get("stmt") for l in lines)
        for e in extras:
            if has_stmt and not e.get("note"):
                e.update(status="manual", msg="Entered in UT, not on the face of the K-1 — check it against the K-1 statement")
                counts["red"] -= 1
                counts["manual"] += 1
        k = ks[0]
        ent = None
        if us:
            ent = dict(name=us[0]["name"], ein4=_ein(us[0]["ein"])[-4:], ein=us[0]["ein"],
                       unit=", ".join(str(u["unit"]) for u in us), passive=us[0].get("passive", ""), how=how)
        cards.append(dict(page=", ".join(str(x["page"]) for x in ks), name=k.get("name") or f"(name not read — page {k['page']})",
                          ein=k.get("ein", ""), form=k.get("form", ""), entity=ent, items=items, empty=not lines))
    orph = [dict(name=u["name"], ein4=_ein(u["ein"])[-4:], unit=u["unit"]) for u in orphans
            if any(f["screen"] in VALUE_SCREENS and _val(f) is not None and f["code"] for f in u["fields"])]
    return dict(cards=cards, counts=counts, orphans=orph, n_ent=len(units),
                not_found=sum(1 for c in cards if not c["entity"]), source="screens")
