"""ai_report.py - the hand-off to the 1040-verification skill.

Written next to the redacted documents (Claude_1040_skill\\<client>\\):
  ai_report.json  - computer-readable: everything the program already did, so the skill doesn't re-read it
  ai_report.md    - the same, for people
Every text in both files goes through the same masking as the documents (names, SSNs, addresses, ...).

What the skill should do with it (also written into the report, "instructions"):
  * trust income rows with status "read" (or "edited" = typed over by the preparer) - don't re-open those documents
  * open only the documents listed in "documents_for_ai" (they are in the same folder, masked)
  * the Karbon organizer is NOT in the folder - its answers are in "karbon"
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

INSTRUCTIONS = [
    "This report was produced by the 1040 Ultimate program before the AI review. Read it first.",
    "Income rows with status 'read' were read by the program from the document (checks passed). Rows with 'edited' were typed over "
    "by the preparer. Treat both as correct - do not re-read those documents.",
    "Rows with status 'partial' or 'not read', and every file in documents_for_ai, need your review. Those files are in this folder "
    "(masked; long documents contain only the pages listed).",
    "Documents with goes_to_ai = false are NOT in this folder on purpose. Do not ask for them unless a finding needs one.",
    "The Karbon organizer is not in the folder: its questions and answers are in 'karbon'.",
    "Carryovers: 'checked' = already reviewed by the preparer.",
    "Still yours to do: carryforward / continuity checks, K-1 basis / at-risk / passive / excess-business-loss limits, "
    "reasonableness and missed deductions / credits.",
]


def build(r: dict, inc: dict, to_ai: dict, mask_results: list | None, ded: dict | None = None) -> dict:
    py = r["py"]
    docs = []
    for d in r["inv"]["docs"]:
        parsed = d.get("parsed")
        amounts = {}
        if isinstance(parsed, dict):
            amounts = {k: round(v, 2) for k, v in parsed.get("amounts", {}).items()}
        elif isinstance(parsed, list):
            amounts = {f"K-1 {k['name']}": {kk: round(v, 2) for kk, v in k["amounts"].items()} for k in parsed}
        docs.append(dict(
            file=d["file"], type=d.get("doc_type"), issuer=d.get("issuer"), tax_year=d.get("year"),
            program_read=d.get("read") or "no", route=d.get("route"), goes_to_ai=bool(to_ai.get(d["path"])),
            pages_for_ai=d.get("ai_page_list") or "all", note=d.get("note", ""), amounts=amounts,
            withholding=(parsed or {}).get("fit") if isinstance(parsed, dict) else None,
            notes=(parsed or {}).get("notes", []) if isinstance(parsed, dict) else [],
            checks=(parsed or {}).get("checks", []) if isinstance(parsed, dict) else []))
    def secs(data):
      out = []
      for s in data["sections"]:
        rows = []
        for x in s["rows"]:
            st = "document inventory" if x.get("inv") else "added by preparer" if x.get("added") else "changed by preparer" if x.get("differs") else ("excluded" if x.get("excluded") else
                                                  ("memo" if x.get("memo") else {"none": "not read"}.get(x.get("status"), x.get("status"))))
            rows.append(dict(document=x["doc"], file=x.get("file", ""), amount_per_document=x.get("doc_cy"), amount=x.get("cy"),
                             withholding_per_document=x.get("doc_fit"), withholding=x.get("fit"), status=st,
                             note=x.get("note") or "",
                             note_by_preparer=bool(x.get("note_edited"))))
        for x in s.get("red", []):
            if x.get("amount") is not None:
                rows.append(dict(document=x["label"], file="", amount_per_document=None, amount=x["amount"], withholding=None,
                                 status="added by preparer", note=x.get("note", ""), note_by_preparer=True))
        out.append(dict(category=s["label"], prior_year_total=s.get("py"), current_year_per_document=s.get("doc_cy"), current_year_total=s.get("cy"),
                        withholding=s.get("fit"), rows=rows))
      return out
    sections = secs(inc)
    ded_sections = secs(ded) if ded else []
    marks = r.get("marks") or {}
    C = r.get("carry") or {}
    carry = dict(
        summary=[dict(c, checked=bool(marks.get(f"cs{i}"))) for i, c in enumerate(C.get("summary", []))],
        from_forms=[dict(c, checked=bool(marks.get(f"cf{i}"))) for i, c in enumerate(C.get("from_forms", []))],
        check_for=[dict(c, checked=bool(marks.get(f"cc{i}"))) for i, c in enumerate(C.get("checks", []))])
    K = r.get("karbon")
    karbon = None
    if K:
        karbon = dict(file=K.get("file"), title=K.get("title"),
                      answered=[dict(question=q["question"], answer=q["answer"], checked=bool(marks.get(f"k{i}")))
                                for i, q in enumerate(K.get("shown", []))],
                      answered_no_or_blank=len(K.get("questions", [])) - len(K.get("shown", [])))
    schc = [dict(name=b.get("name"), schedule_c_lines=b.get("final") or b.get("cy"), typed_by_preparer=b.get("cy"), totals=b.get("totals"),
                 prior_year=b.get("py"),
                 pl=dict(file=(b.get("pl") or {}).get("file"), net_income=(b.get("pl") or {}).get("net_income"),
                         ties=(b.get("pl") or {}).get("ok"),
                         accounts=[dict(account=x["account"], books=x["books"], line=x["line"], amount=x.get("amount"))
                                   for x in (b.get("pl") or {}).get("rows", [])]) if b.get("pl") else None)
            for b in (r.get("schc") or []) if b.get("calculated") or b.get("py")]
    summ = py.get("summary") or {}
    in_folder = [dict(file="redacted_" + Path(m["masked"]).name, original=m["name"], status=m["status"], pages=m.get("pages") or "all",
                      warning=m.get("warn", "")) for m in (mask_results or []) if m.get("masked") and m["status"] in ("masked", "check")]
    return dict(
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"), program="1040 Ultimate", mode=r.get("mode"),
        tax_year=inc.get("cy_year"), prior_year=py.get("year"),
        instructions=INSTRUCTIONS,
        prior_year_return=dict(file=Path(r["form"]["pyret"]).name, software=py.get("software"), pages=py.get("pages"),
                               filing_status=py.get("filing_status"), dependents=py.get("dependents"),
                               two_year_summary=summ.get("lines"), forms_filed=py.get("forms"),
                               payers_entities=[dict(e, received=bool(e.get("received"))) for e in py.get("expected", [])]),
        income_summary=dict(sections=sections, prior_year_total_income=inc.get("py_total"),
                            current_year_per_document=inc.get("doc_total"), current_year_total_income=inc.get("cy_total"),
                            prior_year_withholding=inc.get("py_fit"), current_year_withholding=inc.get("cy_fit"),
                            note=inc.get("total_note")),
        deduction_summary=dict(sections=ded_sections, prior_year_total=(ded or {}).get("py_total"),
                               current_year_total=(ded or {}).get("cy_total")),
        client_comments=(r.get("comments") or {}).get("client", ""),
        received_comments=dict((r.get("comments") or {}).get("recv") or {}, note=(r.get("comments") or {}).get("recv_note", "")),
        schedule_c=schc, schedule_e=r.get("sche") or [], carryovers=carry, karbon=karbon,
        documents=docs, documents_for_ai=in_folder)


def to_markdown(rep: dict) -> str:
    def m(v):
        return "" if v is None else f"{v:,.2f}"
    L = [f"# 1040 Ultimate — AI report ({rep['tax_year']})", f"Generated {rep['generated']}", "", "## Instructions for the AI"]
    L += [f"- {x}" for x in rep["instructions"]]
    if rep.get("client_comments"):
        L += ["", "## Client comments (preparer)", rep["client_comments"]]
    py = rep["prior_year_return"]
    L += ["", f"## Prior-year return ({rep['prior_year']})", f"- File: {py['file']} · {py['software']} · {py['pages']} pages",
          f"- Filing status: {py.get('filing_status') or '?'} · Dependents: {py.get('dependents') if py.get('dependents') is not None else '?'}",
          "- Forms filed: " + ", ".join(f["form"] for f in py.get("forms_filed") or [])]
    inc = rep["income_summary"]
    L += ["", "## Income summary", "Per document = as the program read it; per preparer = what goes on the return.",
          f"| Document | {rep['prior_year']} | {rep['tax_year']} per document | {rep['tax_year']} per preparer | Fed. withholding | Status | Note |",
          "|---|---:|---:|---:|---:|---|---|"]
    for s in inc["sections"]:
        for x in s["rows"]:
            L.append(f"| {x['document']} |  | {m(x.get('amount_per_document'))} | {m(x['amount'])} | {m(x['withholding'])} | {x['status']} | {x['note'].replace('|', '/')} |")
        L.append(f"| **{s['category']}** | **{m(s['prior_year_total'])}** | **{m(s.get('current_year_per_document'))}** | **{m(s['current_year_total'])}** | **{m(s['withholding'])}** |  |  |")
    L.append(f"| **Total Income** | **{m(inc['prior_year_total_income'])}** | **{m(inc.get('current_year_per_document'))}** | **{m(inc['current_year_total_income'])}** | **{m(inc['current_year_withholding'])}** |  | {inc.get('note') or ''} |")
    L.append(f"| Federal withholding | {m(inc['prior_year_withholding'])} |  |  | {m(inc['current_year_withholding'])} |  |  |")
    D = rep.get("deduction_summary") or {}
    if D.get("sections"):
        L += ["", "## Deduction summary", f"| Document | {rep['prior_year']} | {rep['tax_year']} | Status | Note |", "|---|---:|---:|---|---|"]
        for s in D["sections"]:
            for x in s["rows"]:
                L.append(f"| {x['document']} |  | {m(x['amount'])} | {x['status']} | {x['note'].replace('|', '/')} |")
            L.append(f"| **{s['category']}** | **{m(s['prior_year_total'])}** | **{m(s['current_year_total'])}** |  |  |")
    if rep["schedule_c"]:
        L += ["", "## Schedule C (entered by the preparer)"]
        for b in rep["schedule_c"]:
            t = b.get("totals") or {}
            L.append(f"- {b['name']}: gross income {m(t.get('7'))}, expenses {m(t.get('28'))}, home office used {m(t.get('hoUsed'))}, net {m(t.get('31'))}")
    C = rep["carryovers"]
    L += ["", "## Carryovers"]
    for c in C["summary"]:
        L.append(f"- [{'x' if c['checked'] else ' '}] {c['form']} {c['unit']} {c['activity']} — {c['description']}: {m(c['amount'])}")
    for c in C["from_forms"]:
        L.append(f"- [{'x' if c['checked'] else ' '}] {c['item']} {c['activity']}: {m(c['amount'])} ({c['source']})")
    for c in C["check_for"]:
        L.append(f"- [{'x' if c['checked'] else ' '}] Check for the {c['item']} — {c['form']}")
    if not (C["summary"] or C["from_forms"] or C["check_for"]):
        L.append("- No carryover summary page found.")
    K = rep.get("karbon")
    if K:
        L += ["", f"## Karbon organizer ({K['title']})", f"{K['answered_no_or_blank']} questions answered No or left blank (not listed)."]
        for q in K["answered"]:
            L.append(f"- [{'x' if q['checked'] else ' '}] **{q['question']}** — {q['answer'].replace(chr(10), ' / ')}")
    L += ["", "## Documents", "| File | Type | Program read | Goes to AI | Pages for AI | Note |", "|---|---|---|---|---|---|"]
    for d in rep["documents"]:
        L.append(f"| {d['file']} | {d['type']} | {d['program_read']} | {'yes' if d['goes_to_ai'] else 'no'} | "
                 f"{d['pages_for_ai'] if isinstance(d['pages_for_ai'], str) else ', '.join(map(str, d['pages_for_ai']))} | {d['note'].replace('|', '/')} |")
    L += ["", "## In this folder for the AI"]
    L += [f"- {x['file']} (pages: {x['pages'] if isinstance(x['pages'], str) else ', '.join(map(str, x['pages']))}) {x['warning']}" for x in rep["documents_for_ai"]]
    return "\n".join(L) + "\n"


def mask_strings(obj, fn):
    """Applies the masking function to every string in the report."""
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, list):
        return [mask_strings(x, fn) for x in obj]
    if isinstance(obj, dict):
        return {k: mask_strings(v, fn) for k, v in obj.items()}
    return obj


def write(folder: str, rep: dict, mask_fn) -> list[str]:
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    rep = mask_strings(rep, mask_fn)
    (out / "ai_report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (out / "ai_report.md").write_text(mask_fn(to_markdown(rep)), encoding="utf-8")
    return [str(out / "ai_report.json"), str(out / "ai_report.md")]
