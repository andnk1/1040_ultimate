"""prep.py - K-1 UT (called K-1 Prep until 2026-11-11): the verified K-1 lines for UltraTax data entry (list of 2026-11-05,
items 1 and 6).

One verified set, two deliverables: "Add to Income Summary" (handoff.py) and "Export for UT data entry" (the CSV of
APPS_ARCHITECTURE.md, read by the separate UT Data Entry app). Bot / By hand (what UltraTax's Source Data Entry can take) is
decided by ut_entry.py, not here; only what can be fixed on the document side shows as a red problem:

  * box E (partner's identifying number) matches neither / both of taxpayer and spouse (last 4 digits);
  * a code UltraTax doesn't have (the line is still exported, valid_in_ut = N);
  * a box that needs a code, a code that is not one of the box's, a box not on the 1065 K-1, a missing amount;
  * "see statement" with no line under it ("Missing amount - see statement") - cleared only by adding a line;
  * a copy of the same K-1.
Every red problem except "Code not in UltraTax" keeps the K-1 out of the export. Screen spec: design/k1_prep.md.

K-1 copies (item 6): same partnership EIN + same partner (box E) + same year.
  same amounts      -> a copy: the later one is not counted ("copy of page X - not counted");
  different amounts -> "check": count / don't count per K-1 (an Amended tick pre-selects the amended one);
  another partner   -> both count.
Not counted = left out of the Interpreter's totals, "Add to Income Summary", the K-1 entry check and the export.

What the K-1 Prep page saves (in the K-1 run's state, written to the K-1 work file) - PREP_KEYS, owned by this page: the
Interpreter's own whole-state save never changes them:
  pcorr  {line id: typed amount}   corrected amount of one box line (wins over the amount read; also moves the income
                                   summary line's corrected amount, unless the totals tab has its own correction)
  pticks {line id: true}           verified ticks
  dup    {page: "count" | "skip"}  the choice on a "check" K-1
  people {"tp": last 4, "sp": last 4}   taxpayer / spouse (default: the prior-year return)
  plines {page: [{"n", "under", "box", "code", "amt"}]}   lines added on K-1 Prep: under a "see statement" line (under = its
                                   line id; box fixed, code from a dropdown) or free ("+ Add line": under = "", box and code
                                   typed). They are statement amounts like the ones typed on the Interpreter: complete ones
                                   are merged into the K-1 everywhere (Interpreter, totals, Add to Income Summary, the entry
                                   check, the export). Kept under K-1 Prep's own key so the Interpreter's whole-state save
                                   (another tab) can't wipe them.
Line id = "<page>|<box+code>|<n>" (n-th line with that box + code as read from the PDF), set once when the K-1 is read;
"<page>|+|<n>" for an added line, "<page>|i|<j>" for a statement amount typed on the Interpreter, "<page>|II|<item>" for a
Part II item.
"""
from __future__ import annotations

import copy
import csv
import io
import re

from . import k1_codes, ut_entry
from ..inventory import natural_key
from .handoff import FORMS, _num

PREP_KEYS = ("pcorr", "pticks", "dup", "people", "plines")
CHECK_BOXES = ("16", "22", "23")
NOT_IN_UT = "Code not in UltraTax"                 # the one red problem that doesn't keep the K-1 out of the export
CSV_COLUMNS = ["form", "doc_id", "payer_ein", "payer_name", "recipient_id", "box", "code", "amount", "valid_in_ut", "entry",
               "entry_reason", "note"]


# ------------------------------------------------------------------ line ids
def assign_lids(k: dict) -> dict:
    """Gives every line read from the PDF its id (kept by the statement-amount merge, here and in the browser)."""
    seen = {}
    for l in k.get("lines") or []:
        key = l.get("key") or (l["box"] + (l.get("code") or ""))
        n = seen.get(key, 0)
        seen[key] = n + 1
        l["lid"] = f"{k['page']}|{key}|{n}"
    return k


# ------------------------------------------------------------------ copies (item 6)
def _digits(s) -> str:
    return re.sub(r"\D", "", s or "")


def _last4(s) -> str:
    d = _digits(s)
    return d[-4:] if len(d) >= 4 else ""


def _amounts(k: dict) -> tuple:
    return tuple(sorted((l["box"] + (l.get("code") or ""), None if l.get("amt") is None else round(l["amt"], 2), bool(l.get("check")))
                        for l in k.get("lines") or [] if not l.get("manual")))


def find_copies(k1s: list, choice: dict | None = None) -> dict:
    """k1s as read (no statement amounts). -> {page: {"kind": "copy" | "check", "of": [pages], "counted": bool,
    "chosen": bool, "red": bool}}; a K-1 that is not in the result counts."""
    choice = choice or {}
    groups: dict = {}
    for k in k1s:
        ein = _digits(k.get("ein"))
        if len(ein) == 9:
            groups.setdefault((k.get("form"), ein, _last4(k.get("E")), k.get("year")), []).append(k)
    out = {}
    for g in groups.values():
        if len(g) < 2:
            continue
        g = sorted(g, key=lambda k: k["page"])
        same: dict = {}
        for k in g:
            same.setdefault(_amounts(k), []).append(k)
        firsts = [c[0] for c in same.values()]
        for c in same.values():
            for k in c[1:]:
                out[k["page"]] = dict(kind="copy", of=[c[0]["page"]], counted=False, chosen=False, red=False)
        if len(firsts) < 2:
            continue
        amended = [k for k in firsts if k.get("amended")]
        marks = {}
        for k in firsts:
            ch = choice.get(str(k["page"]))
            chosen = ch in ("count", "skip")
            counted = ch == "count" if chosen else (k is amended[0] if len(amended) == 1 else True)
            marks[k["page"]] = dict(kind="check", of=[o["page"] for o in firsts if o is not k], counted=counted, chosen=chosen)
        twice = sum(1 for m in marks.values() if m["counted"]) > 1
        for m in marks.values():
            m["red"] = twice and not m["chosen"]            # still to decide: more than one of them counts
        out.update(marks)
    return out


def counted(k1s: list, state: dict | None) -> list:
    """The K-1s that count (copies and "don't count" K-1s left out)."""
    marks = find_copies(k1s, (state or {}).get("dup"))
    return [k for k in k1s if (marks.get(k["page"]) or {}).get("counted", True)]


# ------------------------------------------------------------------ statement amounts + corrections
def manual_of(state: dict | None) -> dict:
    """The statement amounts kept in the K-1 page's state -> {page: [[box+code, amount], ...]} (same as allManual() on the page)."""
    out: dict = {}
    for src in ("stmtDone", "stmt"):
        for pg, ent in ((state or {}).get(src) or {}).items():
            for e in ent or []:
                if isinstance(e, (list, tuple)) and len(e) >= 2 and (e[0] or e[1]):
                    out.setdefault(str(pg), []).append([e[0], e[1]])
    return out


# ------------------------------------------------------------------ lines added on K-1 Prep (plines)
def split_key(key: str) -> tuple:
    """"20AJ" -> ("20", "AJ"), "9a" -> ("9a", ""): box = digits + a lower-case a-c, code = the rest (upper case)."""
    m = re.match(r"(\d+[a-c]?)(.*)$", key or "")
    return (m.group(1), m.group(2)) if m else (key or "", "")


def norm_box(b) -> str:
    b = str(b or "").strip()
    m = re.fullmatch(r"(\d+)([A-Ca-c]?)", b)
    return m.group(1) + m.group(2).lower() if m else b.upper()


def norm_code(c) -> str:
    return re.sub(r"\s+", "", str(c or "")).upper()


def _amt_text(v) -> str:
    x = _num(v)
    return "" if x is None else (f"{x:.2f}".rstrip("0").rstrip(".") or "0")


def line_problem(box: str, code: str, amt, has_amount: bool = True) -> tuple:
    """-> (problem, blocks): the checks of every line (read, from a statement or typed). blocks = the K-1 is not exported."""
    if not box:
        return "Enter a box", True
    if not k1_codes.known(box):
        return f"Box {box} is not on the 1065 K-1", True
    if box in k1_codes.CODE_BOXES:
        if not code:
            return f"Box {box} needs a code", True
        if not k1_codes.known(box, code):
            return f"{code} is not a code for box {box}", True
    elif code:
        return f"{code} is not a code for box {box}", True
    if has_amount and box not in CHECK_BOXES and not amt:
        return "Missing amount", True
    if code and k1_codes.in_ut(box, code) == "N":
        return NOT_IN_UT, False
    return "", False


def plines_of(state: dict | None) -> dict:
    """{page: [line, ...]} as saved (K-1 Prep's added lines)."""
    p = (state or {}).get("plines")
    return {str(k): [x for x in v if isinstance(x, dict)] for k, v in p.items() if isinstance(v, list)} if isinstance(p, dict) else {}


def plines_entries(state: dict | None) -> dict:
    """The complete added lines as statement amounts {page: [[box+code, amount, "p<n>"], ...]} - merged into the K-1 like the
    Interpreter's (a line with a red problem that keeps the K-1 out, or a checkbox box, is left out)."""
    out: dict = {}
    for pg, lst in plines_of(state).items():
        for x in lst:
            box, code, v = x.get("box") or "", x.get("code") or "", _num(x.get("amt"))
            if box in CHECK_BOXES or line_problem(box, code, v)[1]:
                continue
            out.setdefault(pg, []).append([box + code, _amt_text(v), f"p{x.get('n')}"])
    return out


def all_manual(run: dict) -> dict:
    """Every statement amount of the run: typed on the Interpreter + added on K-1 Prep -> {page: [[box+code, amount], ...]}."""
    st = run.get("state") or {}
    m = {pg: [list(e[:2]) for e in ent] for pg, ent in (run.get("manual") or manual_of(st)).items()}
    for pg, ent in plines_entries(st).items():
        m.setdefault(pg, []).extend([e[0], e[1]] for e in ent)
    return m


def effective(run: dict) -> list:
    """The run's K-1s with the statement amounts (Interpreter + K-1 Prep), the 11 S (short / long-term) and 11 ZZ (Schedule 1)
    ticks - what the Interpreter shows."""
    from .web import merge_manual
    st = run.get("state") or {}
    ks = merge_manual(run.get("k1s") or [], all_manual(run), run.get("flags") or st.get("s11s") or {})
    sch = st.get("sch11") or {}
    out = []
    for k in ks:
        if sch.get(str(k["page"])) == "1" and any(l["box"] == "11" and l.get("code") == "ZZ" for l in k["lines"]):
            k = copy.deepcopy(k)
            for l in k["lines"]:
                if l["box"] == "11" and l.get("code") == "ZZ":
                    l["sch1"] = True
        out.append(k)
    return out


def apply_corr(k1s: list, pcorr: dict | None) -> list:
    """The K-1s with the box corrections typed on K-1 Prep in place of the amounts read (the amount read is kept in "read")."""
    if not pcorr:
        return k1s
    out = []
    for k in k1s:
        hit = [(i, _num(pcorr.get(l.get("lid")))) for i, l in enumerate(k.get("lines") or [])
               if l.get("lid") and not l.get("check") and l.get("amt") is not None]
        hit = [(i, v) for i, v in hit if v is not None and abs(v - k["lines"][i]["amt"]) > 0.005]
        if hit:
            k = copy.deepcopy(k)
            for i, v in hit:
                k["lines"][i]["read"], k["lines"][i]["amt"] = k["lines"][i]["amt"], v
        out.append(k)
    return out


def for_check(run: dict) -> list:
    """What the K-1 entry check compares with the UltraTax input screens: counted K-1s, statement amounts, box corrections."""
    st = run.get("state") or {}
    return apply_corr(counted(effective(run), st), st.get("pcorr"))


def summary_corr(k1s: list, pcorr: dict | None, build_summary) -> tuple:
    """Box corrections -> income summary lines. k1s = the K-1s the summary is built from (with line ids).
    -> ({rid: corrected amount} for the lines a correction moves, {rid: (section key, row)} of the corrected summary)."""
    if not pcorr:
        return {}, {}
    rows = lambda s: {r["rid"]: (sec["key"], r) for sec in s["sections"] for r in sec["rows"]}
    base, cor = rows(build_summary(k1s)), rows(build_summary(apply_corr(k1s, pcorr)))
    out = {}
    for rid in set(base) | set(cor):
        b = base[rid][1]["amt"] if rid in base else 0
        c = cor[rid][1]["amt"] if rid in cor else 0
        if abs(c - b) > 0.005:
            out[rid] = c
    return out, cor


# ------------------------------------------------------------------ the K-1 Prep page
def _partner(k: dict, people: dict) -> dict:
    tp, sp = _last4(people.get("tp")), _last4(people.get("sp"))
    e = _last4(k.get("E"))
    if not tp and not sp:
        return dict(who="", ok=True, msg="")                 # nobody to match yet (the page asks for the taxpayer SSN)
    if not e:
        return dict(who="No match", ok=False, msg="Box E not read — check the K-1")
    hits = [w for w, v in (("Taxpayer", tp), ("Spouse", sp)) if v and v == e]
    if len(hits) == 1:
        return dict(who=hits[0], ok=True, msg="")
    if hits:
        return dict(who="Matches both", ok=False, msg=f"Box E {k.get('E')} matches both the taxpayer and the spouse")
    return dict(who="No match", ok=False, msg=f"Box E {k.get('E')} matches neither the taxpayer nor the spouse")


def _whole(v) -> str:
    """Whole dollars with commas, a minus sign for negatives (screen)."""
    return "" if v is None else ("-" if round(v) < 0 else "") + f"{abs(round(v)):,}"


def _pct(v) -> str:
    return "" if v is None else f"{v:.8f}".rstrip("0").rstrip(".") + "%"


def part2(k: dict) -> list:
    """Part II items as printed -> [(item, description, [screen lines], export text)], in form order; an item not read is left
    out (K1 / N when every amount is zero). K1 is one row on the page; the export splits it (k1_rows)."""
    out = []
    if k.get("G"):
        out.append(("G", "Partner type", [k["G"]], k["G"]))
    if k.get("H1"):
        out.append(("H1", "Domestic / foreign partner", [k["H1"]], k["H1"]))
    J = k.get("J") or {}
    jl = [(n, J[n]) for n in ("Profit", "Loss", "Capital") if isinstance(J.get(n), (list, tuple)) and len(J[n]) == 2]
    if jl:
        out.append(("J", "Share of profit, loss and capital (beginning → ending)",
                    [f"{n} {_pct(b)} → {_pct(e)}" for n, (b, e) in jl],
                    "; ".join(f"{n} {_pct(b)} -> {_pct(e)}" for n, (b, e) in jl)))
    K = k.get("K1") or {}
    kl = [(s, K[n]) for n, s in (("Nonrecourse", "Nonrecourse"), ("Qualified nonrecourse financing", "Qualified nonrecourse"),
                                 ("Recourse", "Recourse")) if isinstance(K.get(n), (list, tuple)) and len(K[n]) == 2]
    if any(b or e for _, (b, e) in kl):
        out.append(("K1", "Share of liabilities - ending", [f"{s} {_whole(e)}" for s, (_, e) in kl],
                    "; ".join(f"{s} {_amt_text(e)}" for s, (_, e) in kl)))
    L = k.get("L") or {}
    if "Beginning capital account" in L or "Ending capital account" in L:
        b, e = L.get("Beginning capital account"), L.get("Ending capital account")
        out.append(("L", "Capital account (beginning → ending)", [f"{_whole(b)} → {_whole(e)}"], f"{_amt_text(b)} -> {_amt_text(e)}"))
    if k.get("M"):
        out.append(("M", "Contributed property with a built-in gain (loss)", [k["M"]], k["M"]))
    N = k.get("N")
    if isinstance(N, (list, tuple)) and len(N) == 2 and (N[0] or N[1]):
        out.append(("N", "Net unrecognized section 704(c) gain (loss) (beginning → ending)", [f"{_whole(N[0])} → {_whole(N[1])}"],
                    f"{_amt_text(N[0])} -> {_amt_text(N[1])}"))
    return out


# K1 liabilities in the CSV: three numeric rows, the field names of UT Data Entry's Tab map (Lady, 2026-11-11)
K1_FIELDS = (("Nonrecourse", "K1_nonrecourse", "Nonrecourse"),
             ("Qualified nonrecourse financing", "K1_qualified", "Qualified nonrecourse financing"),
             ("Recourse", "K1_recourse", "Recourse"))


def k1_rows(k: dict) -> list:
    """Item K1 for the export: [(box, ending amount, note)], one per liability type; an ending amount of 0 (or not read) is
    left out."""
    K = k.get("K1") or {}
    out = []
    for key, box, name in K1_FIELDS:
        v = K.get(key)
        if isinstance(v, (list, tuple)) and len(v) == 2 and v[1]:
            out.append((box, float(v[1]), f"Share of liabilities - ending: {name}"))
    return out


def _rows(k: dict, st: dict, interp: list) -> list:
    """One K-1 card's table: Part II items, then the lines as read (printed as zero: not shown), each "see statement" line with
    the lines under it (typed on the Interpreter, read-only here, then the ones added here), the Interpreter's amounts with no
    "see statement" line of their box, then the free lines ("+ Add line"). k = the K-1 as read (no statement amounts)."""
    pg = k["page"]
    pcorr, ticks = st.get("pcorr") or {}, st.get("pticks") or {}
    plines = plines_of(st).get(str(pg)) or []
    rows = []

    def add(r):
        r.update(tick=bool(ticks.get(r["id"])))
        for key, v in (("missing", False), ("corr", ""), ("changed", False), ("valid", ""), ("note", ""), ("amt", None)):
            r.setdefault(key, v)
        rows.append(r)

    def desc(box, code):
        return (k1_codes.desc(box, code) or k1_codes.box_name(box)) if box else ""

    def interp_row(j, box, code, a):
        v = _num(a)
        p, b = line_problem(box, code, v)
        add(dict(id=f"{pg}|i|{j}", kind="interp", box=box, code=code, desc=desc(box, code), eff=v, problem=p, block=b,
                 valid=k1_codes.valid_in_ut(box, code), note="from statement"))

    def added_row(x, fixed):
        box, code, v = x.get("box") or "", x.get("code") or "", _num(x.get("amt"))
        p, b = line_problem(box, code, v)
        add(dict(id=f"{pg}|+|{x.get('n')}", kind="add", n=x.get("n"), fixed=fixed, box=box, code=code, desc=desc(box, code),
                 typed=str(x.get("amt") or ""), eff="X" if box in CHECK_BOXES else v, problem=p, block=b,
                 valid=k1_codes.valid_in_ut(box, code), note="from statement" if fixed else "added line"))

    for item, label, lines, text in part2(k):
        add(dict(id=f"{pg}|II|{item}", kind="info", box=item, code="", desc=label, vals=lines, eff=text, problem="", block=False,
                 **(dict(parts=k1_rows(k)) if item == "K1" else {})))

    face = [l for l in k.get("lines") or [] if l.get("check") or l.get("amt") != 0]
    lid = lambda l: l.get("lid") or f"{pg}|{l['box'] + (l.get('code') or '')}|x"
    stmts = [l for l in face if l.get("amt") is None and not l.get("check")]
    under, loose = {}, []
    for j, e in enumerate(interp):
        if not isinstance(e, (list, tuple)) or len(e) < 2 or not e[0] or _num(e[1]) in (None, 0):
            continue
        box, code = split_key(e[0])
        cand = [l for l in stmts if l["box"] == box]
        hit = next((l for l in cand if (l.get("code") or "") == code), cand[0] if cand else None)
        (under.setdefault(lid(hit), []) if hit else loose).append((j, box, code, e[1]))
    stmt_ids = {lid(l) for l in stmts}

    for l in face:
        box, code, amt, i = l["box"], l.get("code") or "", l.get("amt"), lid(l)
        if l.get("check"):
            p, b = line_problem(box, code, None, has_amount=False)
            add(dict(id=i, kind="check", box=box, code=code, desc=desc(box, code), eff="X", problem=p, block=b,
                     valid=k1_codes.valid_in_ut(box, code)))
        elif amt is None:                                    # "see statement" with no amount
            mine = [x for x in plines if x.get("under") == i]
            missing = not under.get(i) and not mine
            add(dict(id=i, kind="stmt", box=box, code=code, desc=k1_codes.box_name(box) or f"Box {box}",
                     problem="Missing amount - see statement" if missing else "", block=missing, missing=missing,
                     pick=code if k1_codes.known(box, code) else ""))
            for s in under.get(i, []):
                interp_row(*s)
            for x in mine:
                added_row(x, True)
        else:
            corr = str(pcorr.get(i) or "")
            cv = _num(corr)
            changed = cv is not None and abs(cv - amt) > 0.005
            p, b = line_problem(box, code, amt)
            add(dict(id=i, kind="line", box=box, code=code, desc=desc(box, code), amt=amt, corr=corr, changed=changed,
                     eff=cv if changed else amt, problem=p, block=b, valid=k1_codes.valid_in_ut(box, code),
                     note=f"corrected (read {amt:.2f})" if changed else ""))
    for s in loose:
        interp_row(*s)
    for x in plines:
        if x.get("under") not in stmt_ids:
            added_row(x, False)
    return rows


def build(run: dict, people_default: dict | None = None, fids: list | None = None, client: str = "") -> dict:
    """Everything the K-1 UT page shows (Form 1065 K-1s, by document: numbered names first in number order, then A-Z; K-1s in
    one PDF by page), with Bot / By hand (ut_entry.py) and the by-hand list."""
    st = run.get("state") or {}
    people = {**{"tp": "", "sp": ""}, **{k: _last4(v) for k, v in (people_default or {}).items()},
              **{k: _last4(v) for k, v in (st.get("people") or {}).items() if k in ("tp", "sp")}}
    marks = find_copies(run.get("k1s") or [], st.get("dup"))
    files = run.get("files") or []
    where = lambda p: f"PDF page {p % 1000}" + (f" of {files[p // 1000][1]}" if len(files) > 1 and p // 1000 < len(files) else "")
    marks = {p: dict(m, of_label=", ".join(where(o) for o in m["of"])) for p, m in marks.items()}
    fname = lambda k: files[k["page"] // 1000][1] if k["page"] // 1000 < len(files) else ""
    ks = sorted([k for k in run.get("k1s") or [] if k.get("form") in FORMS], key=lambda k: (natural_key(fname(k)), k["page"]))
    interp = run.get("manual") or manual_of(st)
    out = []
    for n, k in enumerate(ks):
        fi = k["page"] // 1000
        m = marks.get(k["page"])
        p = _partner(k, people)
        rows = ut_entry.decide(_rows(k, st, interp.get(str(k["page"])) or []))
        problems = []
        if m and m["kind"] == "copy":
            status = ["off", "Copy — not counted"]
        elif m and not m["counted"]:
            status = ["off", "Not counted"]
        else:
            if not p["ok"]:
                problems.append(p["msg"])
            if m and m["red"]:
                problems.append("Check: same partnership and partner, different amounts — count or don't count")
            if not _last4(people.get("tp")):
                status = ["todo", "Taxpayer SSN needed"]
            elif problems or any(r["block"] and not r["missing"] for r in rows):
                status = ["no", "Problem"]
            elif any(r["missing"] for r in rows):
                status = ["todo", "Statement to finish"]
            else:
                status = ["ready", "Ready"]
        out.append(dict(n=n + 1, page=k["page"], pdf_page=k["page"] % 1000, file=files[fi][1] if fi < len(files) else "",
                        doc_id=f"{(fids or [])[fi] if fi < len(fids or []) else ''}#{k['page'] % 1000}",
                        name=k.get("name") or "", ein=k.get("ein") or "", E=k.get("E") or "", year=k.get("year"),
                        amended=bool(k.get("amended")), final=bool(k.get("final")), partner=p, dup=m, status=status,
                        problems=problems, rows=rows, ready=status[0] == "ready",
                        nlines=sum(1 for r in rows if r["kind"] in ("line", "check", "interp", "add")),
                        nred=sum(1 for r in rows if r["problem"])))
    count = lambda s: sum(1 for k in out if k["status"][0] == s)
    d = dict(client=client, people=people, k1s=out, n=len(out), ready=count("ready"), todo=count("todo"), prob=count("no"),
             off=count("off"), n1120=sum(1 for k in run.get("k1s") or [] if k.get("form") == "1120-S"),
             codes=k1_codes.codes_by_box(), ut_entry=ut_entry.on())
    d["hand"] = ut_entry.hand_items(d)
    for it in d["hand"]:
        it["tick"] = bool((st.get("pticks") or {}).get(it["id"]))
    return d


def save(run: dict, d: dict) -> None:
    """A change on the K-1 Prep page: {"pcorr": {id: amount | ""}, "pticks": {id: bool}, "dup": {page: "count" | "skip" | ""},
    "people": {"tp": ..., "sp": ...}, "pline": {"op": "add" | "set" | "del", ...}} - only the entries sent are changed;
    {} changes nothing (the Save button: the K-1 work file is written again)."""
    st = run.get("state")
    if not isinstance(st, dict):
        st = run["state"] = {}
    if isinstance(d.get("pline"), dict):
        _pline(st, d["pline"])
    for key in PREP_KEYS:
        if key == "plines":
            continue
        ch = d.get(key)
        if not isinstance(ch, dict):
            continue
        cur = st.get(key) if isinstance(st.get(key), dict) else {}
        for k, v in ch.items():
            if key == "people":
                v = _last4(v) if k in ("tp", "sp") else None
                if v is None:
                    continue
                cur[k] = v                                   # "" = typed empty (e.g. no spouse): kept, it overrides the default
                continue
            if key == "pcorr":
                v = str(v or "").strip()
            elif key == "dup":
                v = v if v in ("count", "skip") else ""
            if v:
                cur[str(k)] = v
            else:
                cur.pop(str(k), None)
        st[key] = cur


def _pline(st: dict, op: dict) -> None:
    """add {"page", "under" (a "see statement" line id, or "" = free line), "box", "code"} / set {"page", "n", "box" | "code" |
    "amt"} / del {"page", "n"} - one line added on K-1 Prep."""
    pls = plines_of(st)
    page = str(op.get("page") or "")
    if not page:
        return
    lst = pls.get(page) or []
    if op.get("op") == "add":
        n = max([x.get("n") or 0 for x in lst] or [0]) + 1
        lst.append(dict(n=n, under=str(op.get("under") or ""), box=norm_box(op.get("box")), code=norm_code(op.get("code")), amt=""))
    else:
        hit = next((x for x in lst if str(x.get("n")) == str(op.get("n"))), None)
        if hit is None:
            return
        if op.get("op") == "del":
            lst.remove(hit)
            (st.get("pticks") or {}).pop(f"{page}|+|{hit.get('n')}", None)
        elif op.get("op") == "set":
            if "box" in op:
                hit["box"] = norm_box(op["box"])
            if "code" in op:
                hit["code"] = norm_code(op["code"])
            if "amt" in op:
                t = str(op["amt"] or "").strip()
                hit["amt"] = _amt_text(t) if _num(t) is not None else t
    if lst:
        pls[page] = lst
    else:
        pls.pop(page, None)
    st["plines"] = pls


def keep_prep_keys(old: dict | None, new: dict) -> dict:
    """The Interpreter saves its whole state: what K-1 Prep owns stays as the server has it."""
    for key in PREP_KEYS:
        new.pop(key, None)
        if isinstance(old, dict) and key in old:
            new[key] = old[key]
    return new


# ------------------------------------------------------------------ the export (APPS_ARCHITECTURE.md: the CSV)
def export_rows(data: dict) -> list:
    """One row per verified line of every Ready K-1, in the page's order: the Part II items (value as printed, as text; K1 as up
    to three numeric rows K1_nonrecourse / K1_qualified / K1_recourse, ending amounts, zero left out), the lines
    read (corrected amount when there is one, else per document), the statement lines and the added lines; a copy once.
    By-hand lines are exported too: entry = hand + entry_reason (blank with the "ut_entry" setting off)."""
    out = []
    for k in data["k1s"]:
        if not k["ready"]:
            continue
        for r in k["rows"]:
            if r["kind"] == "stmt":
                continue                                     # "see statement": its lines follow
            head = ["1065", k["doc_id"], k["ein"], k["name"], k["E"]]
            if r["kind"] == "info" and r["box"] == "K1":     # liabilities, ending: up to three numeric rows (k1_rows)
                out += [head + [box, "", f"{v:.2f}", "", r.get("entry", ""), r.get("why", ""), note]
                        for box, v, note in r.get("parts") or []]
                continue
            if r["kind"] == "info":
                amt = r["eff"]
            else:
                amt = "X" if r["eff"] == "X" else f"{r['eff']:.2f}"
            note = r["desc"] if r["kind"] == "info" else r["note"]
            out.append(head + [r["box"], r["code"], amt, r["valid"], r.get("entry", ""), r.get("why", ""), note])
    return out


def export_csv(data: dict) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    w.writerows(export_rows(data))
    return buf.getvalue().encode("utf-8")
