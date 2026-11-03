"""formview.py - the form tabs of the Document inventory: W2 = every W-2 side by side, box by box, 6 per tab; 1098-M = every
mortgage 1098 the same way (later: 1099 composite, 1099-R ... = new definitions).

The parsed values are never changed. The preparer's corrections are kept apart in r["formview"][form][<doc path>#<form index>]
= {row key: value}; the effective value = the correction if there is one, else the parsed value. effective_docs() gives the
document list with the corrections applied - everything downstream (income summary, Verify, AI report, Excel) uses it.
Row keys: b1 ... b11 (boxes), ssn / ein / er / er_addr / ctl / ee / ee_addr (boxes a-f), b13stat / b13ret / b13sick, b12:<code>,
b14:<label>, st:<state>:15|16|17 (15 = state ID), lc:<locality>:18|19.
1098 row keys (parse_1098 gives them as they are): b1 ... b9, b11, b10:<description>, ln (lender), br (borrower), acct.
"""
from __future__ import annotations

import re

# Social Security wage base by tax year (SSA)
WAGE_BASE = {2024: 168600, 2025: 176100, 2026: 184500}
SS_RATE = 0.062

W2_12 = {
    "A": "Uncollected social security or RRTA tax on tips",
    "B": "Uncollected Medicare tax on tips",
    "C": "Taxable cost of group-term life insurance over $50,000",
    "D": "Elective deferrals to a section 401(k) cash or deferred arrangement",
    "E": "Elective deferrals under a section 403(b) salary reduction agreement",
    "F": "Elective deferrals under a section 408(k)(6) salary reduction SEP",
    "G": "Elective deferrals and employer contributions to a section 457(b) deferred compensation plan",
    "H": "Elective deferrals to a section 501(c)(18)(D) tax-exempt organization plan",
    "J": "Nontaxable sick pay",
    "K": "20% excise tax on excess golden parachute payments",
    "L": "Substantiated employee business expense reimbursements",
    "M": "Uncollected social security or RRTA tax on taxable cost of group-term life insurance over $50,000 (former employees)",
    "N": "Uncollected Medicare tax on taxable cost of group-term life insurance over $50,000 (former employees)",
    "P": "Excludable moving expense reimbursements paid directly to a member of the U.S. Armed Forces",
    "Q": "Nontaxable combat pay",
    "R": "Employer contributions to an Archer MSA",
    "S": "Employee salary reduction contributions under a section 408(p) SIMPLE plan",
    "T": "Adoption benefits",
    "V": "Income from exercise of nonstatutory stock option(s)",
    "W": "Employer contributions (including employee contributions through a cafeteria plan) to an employee's health savings account (HSA)",
    "Y": "Deferrals under a section 409A nonqualified deferred compensation plan",
    "Z": "Income under a nonqualified deferred compensation plan that fails to satisfy section 409A",
    "AA": "Designated Roth contributions under a section 401(k) plan",
    "BB": "Designated Roth contributions under a section 403(b) plan",
    "DD": "Cost of employer-sponsored health coverage",
    "EE": "Designated Roth contributions under a governmental section 457(b) plan",
    "FF": "Permitted benefits under a qualified small employer health reimbursement arrangement",
    "GG": "Income from qualified equity grants under section 83(i)",
    "HH": "Aggregate deferrals under section 83(i) elections as of the close of the calendar year",
    "II": "Medicaid waiver payments excluded from gross income",
}


def _m(k, box, label):
    return dict(k=k, box=box, label=label, t="money")


# one definition per form: sections of fixed rows, or repeatable groups ("dyn": key prefix) that get one row per key found;
# head=False: no title row (the Box column says it)
DEFS = {
    "w2": dict(label="W-2", sections=[
        dict(title="Boxes 1–20", head=False, rows=[
            _m("b1", "1", "Wages, tips, other compensation"), _m("b2", "2", "Federal income tax withheld"),
            _m("b3", "3", "Social security wages"), _m("b4", "4", "Social security tax withheld"),
            _m("b5", "5", "Medicare wages and tips"), _m("b6", "6", "Medicare tax withheld"),
            _m("b7", "7", "Social security tips"), _m("b8", "8", "Allocated tips"),
            _m("b10", "10", "Dependent care benefits"), _m("b11", "11", "Nonqualified plans")]),
        dict(title="Box 12", head=False, dyn="b12:", box="12", t="money", kind="code12", add="Box 12 code (A … II)",
             none="Box 12 — no codes"),
        dict(title="Box 13", head=False, rows=[dict(k="b13stat", box="13", label="Statutory employee", t="check"),
                                   dict(k="b13ret", box="13", label="Retirement plan", t="check"),
                                   dict(k="b13sick", box="13", label="Third-party sick pay", t="check")]),
        dict(title="Box 14 — Other", head=False, dyn="b14:", box="14", t="money", kind="label", add="Box 14 label",
             none="Box 14 — Other: none"),
        dict(title="State", head=False, dyn="st:", t="money", kind="state", add="State (2 letters)",
             pair={"16": "State wages, tips, etc.", "17": "State income tax"}),
        dict(title="Local", head=False, dyn="lc:", t="money", kind="local", add="Locality name",
             pair={"18": "Local wages, tips, etc.", "19": "Local income tax"}),
    ],
        # column header = person (box e) · first word of the payer (box c); what a change re-calculates; the banners' words
        head=dict(who="ee", payer="er", id="ein", who_miss="Employee name not found on the W-2",
                  payer_miss="Employer name not found on the W-2", payer_lbl="Employer", id_lbl="EIN"),
        feeds=r"^(b1|b2|b12:.*)$", summary="income summary", typed="wages"),
    "1098": dict(label="1098", sections=[
        dict(title="Boxes 1–9", head=False, rows=[
            _m("b1", "1", "Mortgage interest received from payer(s)/borrower(s)"),
            _m("b2", "2", "Outstanding mortgage principal"),
            dict(k="b3", box="3", label="Mortgage origination date", t="text"),
            _m("b4", "4", "Refund of overpaid interest"), _m("b5", "5", "Mortgage insurance premiums"),
            _m("b6", "6", "Points paid on purchase of principal residence"),
            dict(k="b7", box="7", label="Property address same as borrower's address", t="check"),
            dict(k="b8", box="8", label="Address or description of property securing mortgage", t="text"),
            dict(k="b9", box="9", label="Number of properties securing the mortgage", t="text")]),
        dict(title="Box 10 — Other", head=False, dyn="b10:", box="10", t="money", kind="label", add="Box 10 description",
             none="Box 10 — Other: none"),
    ],
        head=dict(who="br", payer="ln", id="acct", who_miss="Borrower name not found on the 1098",
                  payer_miss="Lender name not found on the 1098", payer_lbl="Lender", id_lbl="Account"),
        feeds=r"^(b1|b2|b4|b5|b6|b7|b8|b10:.*)$", summary="deduction summary", typed="mortgage interest"),
}


# ---------------------------------------------------------------- parsed W-2 -> row keys and back
TEXT_KEYS = ("ssn", "ein", "er", "er_addr", "ctl", "ee", "ee_addr")
B13 = (("stat", "b13stat"), ("ret", "b13ret"), ("sick", "b13sick"))


def w2_rows(f: dict) -> dict:
    """One W-2 as parse_w2 gives it ({'1': .., '12': [(code, amt)], 'states': [..], ..}) -> {row key: value}."""
    out = {}
    for k, v in f.items():
        if k == "12":
            for code, a in v or []:
                out[f"b12:{code}"] = round(out.get(f"b12:{code}", 0) + (a or 0), 2)
        elif k == "13":
            out.update({rk: bool(v.get(pk)) for pk, rk in B13})
        elif k == "14":
            for lab, a in v or []:
                out[f"b14:{lab}"] = round(out.get(f"b14:{lab}", 0) + (a or 0), 2)
        elif k == "states":
            for s in v or []:
                g = s.get("st") or "-"
                for b, sk in (("15", "id"), ("16", "w"), ("17", "t")):
                    if s.get(sk) is not None:
                        out[f"st:{g}:{b}"] = s[sk]
        elif k == "locals":
            for s in v or []:
                g = s.get("name") or "-"
                for b, sk in (("18", "w"), ("19", "t")):
                    if s.get(sk) is not None:
                        out[f"lc:{g}:{b}"] = s[sk]
        elif k in ("16", "17"):
            if not f.get("states"):                  # list layout: no state code
                out[f"st:-:{k}"] = v
        elif k in ("18", "19"):
            if not f.get("locals"):
                out[f"lc:-:{k}"] = v
        elif k in TEXT_KEYS:
            out[k] = v
        elif re.fullmatch(r"\d{1,2}", k):
            out["b" + k] = v
    return out


def _back(f: dict, eff: dict) -> dict:
    """Effective row values -> the parse_w2 box dict (what income / Verify read)."""
    g = dict(f)
    for k, v in eff.items():
        m = re.fullmatch(r"b(\d{1,2})", k)
        if m:
            g[m.group(1)] = v
        elif k in TEXT_KEYS:
            g[k] = v
    g["12"] = [(k[4:], v) for k, v in eff.items() if k.startswith("b12:") and v]
    g["14"] = [(k[4:], v) for k, v in eff.items() if k.startswith("b14:") and v]
    if any(rk in eff for _, rk in B13):
        g["13"] = {pk: bool(eff.get(rk)) for pk, rk in B13}
    for pre, name, boxes in (("st", "st", (("15", "id"), ("16", "w"), ("17", "t"))), ("lc", "name", (("18", "w"), ("19", "t")))):
        groups = sorted({k.split(":")[1] for k in eff if k.startswith(pre + ":")})
        rows = [dict({name: None if s == "-" else s}, **{sk: eff.get(f"{pre}:{s}:{b}") for b, sk in boxes}) for s in groups]
        g["states" if pre == "st" else "locals"] = rows
        for b, sk in boxes[-2:]:
            vs = [r[sk] for r in rows if isinstance(r[sk], (int, float))]
            g[b] = round(sum(vs), 2) if vs else None
    return g


def forms_of(d: dict, form: str = "w2") -> list:
    """The forms the program read in one document (detail["boxes"]: one dict per W-2 / 1098)."""
    p = d.get("parsed")
    if d.get("family") != form or d.get("route") in ("skipped", "excluded") or not isinstance(p, dict) or p.get("status") == "none":
        return []
    return (p.get("detail") or {}).get("boxes") or []


def w2_forms(d: dict) -> list:
    return forms_of(d, "w2")


def _w2_redo(d: dict, new: list) -> dict:
    """A W-2 document's parse result again, from its corrected W-2s."""
    p = dict(d["parsed"])
    p["detail"] = dict(p.get("detail") or {}, boxes=new, w2=[(f.get("1") or 0, f.get("2")) for f in new])
    p["amounts"] = dict(p.get("amounts") or {}, w2=round(sum(f.get("1") or 0 for f in new), 2))
    p["fit"] = round(sum(f.get("2") or 0 for f in new), 2)
    p["notes"] = [n for n in p.get("notes") or [] if not n.startswith("Box 12 ")] + \
        [f"Box 12 {c} {v:,.2f}" + (" (employer health coverage — not taxable)" if c == "DD" else "") for f in new for c, v in f.get("12") or []]
    return p


def _m_redo(d: dict, new: list) -> dict:
    """A 1098 document's parse result again (box 1 -> mortgage interest, the comment), from its corrected 1098s."""
    from core.parsers import m1098_result
    return m1098_result([{k: v for k, v in f.items() if v is not None} for f in new])


# form -> (parsed form -> row keys, row keys -> parsed form, the document's result again)
FORMS = {"w2": (w2_rows, _back, _w2_redo),
         "1098": (lambda f: dict(f), lambda f, eff: dict(eff), _m_redo)}


def effective(parsed: dict, edits: dict) -> dict:
    out = dict(parsed)
    out.update(edits or {})
    return out


def effective_docs(r: dict) -> list:
    """The document list with the form-view corrections applied (parsed values untouched in r)."""
    docs = r["inv"]["docs"]
    fvs = r.get("formview") or {}
    if not any(fvs.get(f) for f in FORMS):
        return docs
    out = []
    for d in docs:
        form = d.get("family")
        fv = (fvs.get(form) or {}) if form in FORMS else {}
        forms = forms_of(d, form) if fv else []
        if not forms or not any(f'{d["path"]}#{i}' in fv for i in range(len(forms))):
            out.append(d)
            continue
        rows, back, redo = FORMS[form]
        new = []
        for i, f in enumerate(forms):
            e = fv.get(f'{d["path"]}#{i}')
            new.append(back(f, effective(rows(f), e)) if e else f)
        p = redo(d, new)
        p["formview_edited"] = True
        out.append(dict(d, parsed=p))
    return out


# ---------------------------------------------------------------- page data (the Form view section of the summary page)
PER_TAB = 6                                     # W-2s per tab: W2 = 1-6, W2_2 = 7-12 ... (always 6 columns + Total)
# the Document inventory's tabs after "Summary": W2 first, then these always (alphabetical; "(n)" = documents of that type)
TABS = [("1098", "1098-M"), ("1098t", "1098-T"), ("1099b", "1099-B"), ("composite", "1099-Comp"), ("1099da", "1099-DA"),
        ("1099div", "1099-DIV"), ("1099g", "1099-G"), ("1099int", "1099-INT"), ("1099nec", "1099-NEC"), ("1099r", "1099-R")]
# ... and these only when the client has one (they take their place in the alphabetical order)
TABS_IF = [("1099k", "1099-K"), ("1099misc", "1099-MISC"), ("1099oid", "1099-OID"), ("1099sa", "1099-SA"), ("ssa", "SSA-1099"),
           ("1098e", "1098-E"), ("1095a", "1095-A"), ("5498", "5498")]
BUILT = {"w2", "1098"}                          # the others say "Form view coming soon"


def columns(r: dict, order: list, form: str = "w2") -> list:
    """Every form of that type the program read, one column each, in the inventory's order: {id, form, path, file, num, parsed}.
    The header (person · payer) is made on the page from the parsed names, so a correction there shows at once."""
    rows = FORMS[form][0]
    rank = {p: i for i, p in enumerate(order)}
    cols = []
    for d in sorted(r["inv"]["docs"], key=lambda d: rank.get(d["path"], len(rank))):
        forms = forms_of(d, form)
        m = re.match(r"^\s*(\d+)", d["file"])
        n = m.group(1) if m else str(rank.get(d["path"], len(rank)) + 1)
        for i, f in enumerate(forms):
            cols.append(dict(id=f'{d["path"]}#{i}', form=form, path=d["path"], file=d["file"],
                             num="#" + n + (chr(97 + i) if len(forms) > 1 else ""), parsed=rows(f)))
    return cols


def w2_columns(r: dict, order: list) -> list:
    return columns(r, order, "w2")


def tabs(r: dict, cols: list) -> list:
    """The Document inventory's form tabs (after "Summary"): W2 first, then the form types in alphabetical order. A built form
    gets 6 forms per tab (W2, W2_2 ... / 1098-M, 1098-M_2 ...); n = how many forms (built) / documents of that type; 0 = no number."""
    docs = [d for d in r["inv"]["docs"] if d.get("route") != "skipped"]
    count = lambda fam: sum(1 for d in docs if d.get("family") == fam)

    def chunks(form, label):
        fc = [c for c in cols if c.get("form", "w2") == form]
        out = []
        for k in range(0, max(len(fc), 1), PER_TAB):
            j = k // PER_TAB
            out.append(dict(key=form if j == 0 else f"{form}_{j + 1}", label=label if j == 0 else f"{label}_{j + 1}", form=form,
                            cols=[c["id"] for c in fc[k:k + PER_TAB]], n=len(fc[k:k + PER_TAB])))
        return out
    out = chunks("w2", "W2")
    rest = TABS + [t for t in TABS_IF if count(t[0])]
    for fam, label in sorted(rest, key=lambda t: t[1].lower()):
        if fam in BUILT:
            out += chunks(fam, label)
        else:
            out.append(dict(key=fam, label=label, form=fam, cols=[], n=count(fam), soon=True))
    return out
