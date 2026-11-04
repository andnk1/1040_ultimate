"""docid.py - saved work is keyed by the document's fingerprint, not its name (pending item 7, 2026-11-03).

Each document gets an id when the documents are scanned (inventory.scan_files): d["did"] = the first 16 characters of the SHA-1
of the file's contents (+ "~<last 4>" for one account of a split brokerage package). Same file = same id, whatever its name or
folder. Every place that saves work per document uses it:
  income / deduction lines  "<category>|<id>" (+ "|<8949 box / Schedule 1 line>")   edits, ticks "inc|...", comments
  Verify lines              "v|<line id>|main|fit|<box>", "memo|<id>|<what>", "rp|<line id>", "rm|<id>|<what>"
  inventory state           invstate verified / amt / notes by id; inventory amounts "inv|<id>"
  form tabs                 formview[form]["<id>#<form index>"]
  AI ticks                  to_ai: by path while the program runs, by id in the work-in-progress file

The work-in-progress file keeps a table id -> {file, tfp} (tfp = fingerprint of the document's text). When it is loaded:
  - a saved id that is not among the documents, with a document of the same file name now:
      same text  -> the same document re-saved (e.g. Acrobat Save): the work moves to the new id, "matched by name — check"
      other text -> the document was replaced: the work stays with the old version (kept in the file, not shown),
                    "This document was replaced — your previous ticks and comments were on the old version"
    The note shows on the inventory line until the document is ticked Verified.
  - an older work-in-progress file (no table: keys built from file names / paths) is converted once, matching by file name.
"""
from __future__ import annotations

from pathlib import Path

RESAVED = "matched by name — check (the file changed since your work was saved; same text)"
REPLACED = "This document was replaced — your previous ticks and comments were on the old version"


def fps(r: dict) -> dict:
    """The id table saved with the work: the documents of this run + the ids of earlier versions kept from the loaded file."""
    out = dict(r.get("fps_kept") or {})
    for d in r["inv"]["docs"]:
        if d.get("did"):
            out[d["did"]] = dict(file=d["file"], tfp=d.get("tfp"))
    return out


def to_ai_out(r: dict) -> dict:
    """AI ticks for the file: by id (documents), by path (prior-year return, Karbon, client summary)."""
    by_path = {d["path"]: d["did"] for d in r["inv"]["docs"] if d.get("did")}
    return {by_path.get(p, p): v for p, v in (r.get("to_ai") or {}).items()}


# ---------------------------------------------------------------- loading
def upgrade(r: dict, data: dict, summaries) -> dict:
    """The loaded work-in-progress data with its keys on this run's document ids. summaries(r) -> (inc, ded) of the fresh read."""
    data = dict(data)
    docs = [d for d in r["inv"]["docs"] if d.get("did")]
    notes = dict(data.get("docnotes") or {})
    if isinstance(data.get("fps"), dict):
        saved = data["fps"]
        now = {d["did"] for d in docs}
        remap = {}
        for old, info in saved.items():
            if old in now:
                continue
            name = (info.get("file") or "").lower()
            cand = next((d for d in docs if d["file"].lower() == name and d["did"] not in saved), None)
            if not cand:
                continue                                      # document not in this run: its work stays in the file
            if info.get("tfp") and cand.get("tfp") and info["tfp"] != cand["tfp"]:
                notes[cand["did"]] = REPLACED
            else:
                remap[old] = cand["did"]
                notes[cand["did"]] = RESAVED
        if remap:
            data = _rekey(data, lambda k: _swap(k, remap))
            ver = ((data.get("invstate") or {}).get("verified") or {})
            for new in remap.values():
                ver.pop(new, None)                            # verify it again
        r["fps_kept"] = {k: v for k, v in saved.items() if k not in now and k not in remap}
    else:
        data = _from_v1(r, data, summaries)
    by_did = {d["did"]: d["path"] for d in docs}
    data["to_ai"] = {by_did.get(k, k): v for k, v in (data.get("to_ai") or {}).items()} if data.get("to_ai") is not None else None
    data["docnotes"] = notes
    return data


def _swap(k: str, remap: dict) -> str:
    for old, new in remap.items():
        if old in k:
            k = k.replace(old, new)
    return k


def _rekey(data: dict, fn) -> dict:
    """Every per-document key in the work (edits, ticks / comments, inventory state, form tabs, AI ticks, notes) through fn."""
    out = dict(data)
    for k in ("edits", "marks", "to_ai", "docnotes"):
        if isinstance(out.get(k), dict):
            out[k] = {fn(x): v for x, v in out[k].items()}
    if isinstance(out.get("invstate"), dict):
        st = dict(out["invstate"])
        for k in ("verified", "amt", "notes"):
            if isinstance(st.get(k), dict):
                st[k] = {fn(x): v for x, v in st[k].items()}
        out["invstate"] = st
    if isinstance(out.get("formview"), dict):
        out["formview"] = {f: ({fn(x): v for x, v in cols.items()} if isinstance(cols, dict) else cols)
                           for f, cols in out["formview"].items()}
    return out


def _from_v1(r: dict, data: dict, summaries) -> dict:
    """An older work-in-progress file: keys built from file names / paths -> ids, matched by file name (once)."""
    docs = [d for d in r["inv"]["docs"] if d.get("did")]
    by_name = {}
    for d in sorted(docs, key=lambda d: d.get("route") == "skipped"):        # a duplicate never wins over the document
        for n in (d["file"], Path(d["path"]).name, Path(d.get("orig_path") or d["path"]).name):
            by_name.setdefault(n.lower(), d)
    did_of = lambda name: (by_name.get(Path(name).name.lower()) or {}).get("did")
    inc, ded = summaries(r)
    rows = [(s["key"], x) for summ in (inc, ded) for s in summ["sections"] for x in s["rows"] if x.get("did")]
    exact = {f'{sec}|{x["file"]}|{x["doc"]}': x["id"] for sec, x in rows}
    reds = {x["label"]: x["id"] for summ in (inc, ded) for s in summ["sections"] for x in s.get("red") or []}
    by_doc = {x["doc"]: x["id"] for _, x in rows}

    def row(old: str) -> str:
        if old.startswith(("red|", "inv|free|")):
            return old
        if old.startswith("inv|"):
            did = did_of(old[4:])
            return "inv|" + did if did else old
        if old in exact:
            return exact[old]
        parts = old.split("|", 2)
        if len(parts) != 3:
            return old
        sec, file, doc = parts
        cands = [x for s, x in rows if s == sec and x["file"] == file]
        if len(cands) == 1:
            return cands[0]["id"]
        tail = doc.rsplit(" — ", 1)[-1]                  # several rows of one document: the 8949 box / line at the end
        hit = [x for x in cands if x["doc"].endswith(" — " + tail) or x["doc"].endswith(tail)]
        return hit[0]["id"] if len(hit) == 1 else old

    def mark(k: str) -> str:
        if k.startswith("n|"):
            return "n|" + mark(k[2:])
        if k.startswith("inc|"):
            return "inc|" + row(k[4:])
        if k.startswith("v|"):
            rest = k[2:]
            if rest.startswith("memo|"):
                _, file, what = (rest.split("|", 2) + ["", ""])[:3]
                did = did_of(file)
                return f"v|memo|{did}|{what}" if did else k
            if rest.startswith(("sche|", "schc|", "ut|")):
                return k
            rid, _, suf = rest.rpartition("|")
            return f"v|{row(rid)}|{suf}" if rid else k
        if k.startswith("rp|"):
            d = k[3:]
            return "rp|" + (by_doc.get(d) or reds.get(d) or d)
        if k.startswith("rm|"):
            _, file, what = (k.split("|", 2) + ["", ""])[:3]
            did = did_of(file)
            return f"rm|{did}|{what}" if did else k
        return k

    out = dict(data)
    if isinstance(out.get("edits"), dict):
        out["edits"] = {row(k): v for k, v in out["edits"].items()}
    if isinstance(out.get("marks"), dict):
        out["marks"] = {mark(k): v for k, v in out["marks"].items()}
    if isinstance(out.get("invstate"), dict):
        st = dict(out["invstate"])
        for k in ("verified", "amt", "notes"):
            if isinstance(st.get(k), dict):
                st[k] = {(did_of(x) or x): v for x, v in st[k].items()}
        out["invstate"] = st
    if isinstance(out.get("formview"), dict):
        fv = {}
        for f, cols in out["formview"].items():
            if isinstance(cols, dict):
                cols = {(f"{did_of(k.rpartition('#')[0])}#{k.rpartition('#')[2]}" if did_of(k.rpartition("#")[0]) else k): v
                        for k, v in cols.items()}
            fv[f] = cols
        out["formview"] = fv
    if isinstance(out.get("to_ai"), dict):                  # paths -> the documents' ids (the return / Karbon keep their path)
        out["to_ai"] = {(did_of(p) or p): v for p, v in out["to_ai"].items()}
    return out
