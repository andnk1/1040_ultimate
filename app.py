"""1040 Ultimate - internal return-review tool (CFO Associates).

    python app.py        -> opens http://127.0.0.1:5067

Screens
  1. Create summary  - prior-year return + the client's documents -> income summary, document inventory,
                       expected vs received, forms filed / carryovers, Schedule C entry
     (Verify return = the same + the current-year return - later)
  2. Mask info for AI agent - pick documents, enter what to mask (one tab per person),
                       mask, then save the redacted set ("redacted_" + name) and/or a plain copy of the originals
  3. AI review       - later
Everything runs on this computer; nothing is uploaded. Internal use only - contains client data.
"""
from __future__ import annotations

import json
from datetime import datetime
import re
import os
import shutil
import sys
import threading
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from core.inventory import scan_files, list_folder, ROUTE_LBL, summary_pages_for  # noqa: E402
from core.py_return import read_prior_return, read_schedule_c, read_schedule_e, read_py_income, match_expected, SCHC_LINES, SCHE_LINES  # noqa: E402
from core.income import build_income_summary, build_deduction_summary, CATS, DED_CATS                                     # noqa: E402
from core.parsers import parse_document, koinly_8949_group  # noqa: E402
from core.pdfutil import split_accounts  # noqa: E402
from core.pl import read_pl, MAP_LINES as PL_MAP_LINES, workpaper_csv, other_expenses_csv, book_tax_csv  # noqa: E402
from core.verify import read_cy_return, run_checks, review_xlsx, master_load, master_save  # noqa: E402
from core.carryovers import read_carryovers                                      # noqa: E402
from core.karbon import read_karbon, answered                                    # noqa: E402
from core.people import read_people                                              # noqa: E402
from core.masking import collect_values, mask_files, save_redacted, save_copies, MASKABLE, ALWAYS_MASK, mask_text, _text_patterns  # noqa: E402
from core.utscreens import read_ut_screens, looks_like_ut_screens, doc_verify  # noqa: E402
import core.safe_pdf as safe_pdf                                                 # noqa: E402
import core.wip as wip_mod                                                        # noqa: E402
from core.settings import START_FOLDERS                                            # noqa: E402
from core.ai_report import build as build_report, write as write_report                                      # noqa: E402

PORT = int(os.environ.get("U1040_PORT", "5067"))
WORK = HERE / "_work"            # masked copies while the program runs (deleted at start-up)
app = Flask(__name__, template_folder=str(HERE / "templates"), static_folder=str(HERE / "static"))
RUNS: dict = {}
# first place the Browse buttons look (the first one that exists on this computer)
DEFAULT_DIRS = START_FOLDERS + [str(HERE / "Return_Info")]     # start folders come from local_settings.json


# ---------------------------------------------------------------- native Windows dialogs
_DIALOG_PY = r"""
import json, sys, tkinter as tk
from tkinter import filedialog
kind, init, title = sys.argv[1], sys.argv[2], sys.argv[3]
root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True); root.lift(); root.focus_force()
if kind == "folder":
    v = filedialog.askdirectory(parent=root, initialdir=init, title=title or "Choose a folder")
elif kind == "files":
    v = list(filedialog.askopenfilenames(parent=root, initialdir=init, title=title or "Choose documents"))
elif kind == "sheet":
    v = filedialog.askopenfilename(parent=root, initialdir=init, title=title or "Choose the Schedule E sheet",
                                   filetypes=[("Schedule E sheet", "*.xlsx *.xlsm *.csv"), ("All files", "*.*")])
elif kind == "pl":
    v = filedialog.askopenfilename(parent=root, initialdir=init, title=title or "Choose the P&L (CSV, Excel or PDF)",
                                   filetypes=[("P&L", "*.csv *.xlsx *.xlsm *.pdf"), ("All files", "*.*")])
else:
    v = filedialog.askopenfilename(parent=root, initialdir=init, title=title or "Choose the prior-year return",
                                   filetypes=[("PDF", "*.pdf"), ("All files", "*.*")])
root.destroy()
print(json.dumps(v))
"""
_DIALOG_LOCK = threading.Lock()


def _dialog(kind: str, start: str = "", title: str = ""):
    """Native Windows dialog, run in its own small Python process (tkinter is not safe in Flask's threads)."""
    import subprocess
    import sys
    init = start or next((d for d in DEFAULT_DIRS if os.path.isdir(d)), str(HERE))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if not _DIALOG_LOCK.acquire(blocking=False):
        return None                                   # a file window is already open - never queue a second one
    try:
        out = subprocess.run([sys.executable, "-c", _DIALOG_PY, kind, init, title or ""], capture_output=True,
                             text=True, encoding="utf-8", creationflags=flags, timeout=3600).stdout.strip()
        v = json.loads(out.splitlines()[-1]) if out else ""
    except Exception:  # noqa: BLE001
        v = ""
    finally:
        _DIALOG_LOCK.release()
    if isinstance(v, list):
        return [os.path.normpath(x) for x in v]
    return os.path.normpath(v) if v else ""


@app.route("/browse")
def browse():
    kind = request.args.get("kind", "file")
    start = request.args.get("start", "")
    if kind == "folderfiles":                       # add every file in a folder
        folder = _dialog("folder", start, "Add all documents in a folder")
        if folder is None:
            return jsonify(busy=True, paths=[])
        return jsonify(paths=list_folder(folder) if folder else [])
    v = _dialog(kind, start)
    if v is None:
        return jsonify(busy=True, paths=[], path="")
    return jsonify(paths=v if isinstance(v, list) else ([v] if v else []), path=v if isinstance(v, str) else "")


# ---------------------------------------------------------------- 1. summary
@app.route("/")
def home():
    return render_template("home.html", mode=request.args.get("mode", "summary"), error=None, form={}, docs=[])


def _step(msg):
    """Progress in the run.bat window (so a slow / stuck step shows where it is)."""
    print(f"  [{datetime.now():%H:%M:%S}] {msg}", flush=True)


@app.route("/debug/stacks")
def debug_stacks():
    """Where every thread is right now (open this in another tab while a run looks stuck). Code lines only - no client data."""
    import sys
    import traceback
    from flask import Response
    names = {t.ident: t.name for t in threading.enumerate()}
    out = []
    for tid, frame in sys._current_frames().items():
        out.append(f"--- thread {names.get(tid, tid)}")
        out += [l.rstrip() for l in traceback.format_stack(frame)
                if "1040_ultimate" in l or "core" in l or "app.py" in l or "site-packages" not in l]
    return Response("\n".join(out), mimetype="text/plain")


EMPTY_PY = dict(file="", pages=0, year=None, software="", summary=None, filing_status=None, dependents=None, forms=[],
                expected=[], carryovers=[], warnings=[])


@app.route("/run", methods=["POST"])
def run():
    """Everything is optional: prior-year return, documents, Karbon, UT input screens, work in progress (.json)."""
    _step("Run check received")
    mode = request.form.get("mode", "summary")
    form = {k: (request.form.get(k) or "").strip().strip('"') for k in ("pyret", "karbon", "utscreens", "wip")}
    try:
        doc_list = [d for d in json.loads(request.form.get("docs") or "[]") if isinstance(d, dict) and d.get("path")]
    except ValueError:
        doc_list = []

    def back(msg):
        return render_template("home.html", mode=mode, error=msg, form=form, docs=doc_list)
    wip_data, moved = None, []
    if form["wip"]:
        if not Path(form["wip"]).is_file():
            return back("The work-in-progress file wasn't found.")
        try:
            wip_data = wip_mod.load(form["wip"])
        except (OSError, ValueError) as e:
            return back(f"Couldn't read the work-in-progress file: {e}")
        wf = wip_data.get("form") or {}
        if form["pyret"] and wf.get("pyret") and Path(form["pyret"]).name.lower() != Path(wf["pyret"]).name.lower():
            return back(f"This work in progress belongs to {wip_data.get('client') or 'another client'} "
                        f"(prior-year return {Path(wf['pyret']).name}) — you picked {Path(form['pyret']).name}. "
                        "Clear one of them and run again.")
        folder = str(Path(form["wip"]).parent)
        for k in ("pyret", "karbon", "utscreens"):           # the paths saved with the work (unless picked now)
            form[k] = form[k] or wf.get(k, "")
            if form[k] and not Path(form[k]).is_file():
                (new,), notes = wip_mod.relink([form[k]], folder)
                if notes:
                    form[k] = new
                    moved += notes
        if not doc_list:
            doc_list = [d for d in (wip_data.get("docs") or []) if d.get("path")]
            fixed, notes = wip_mod.relink([d["path"] for d in doc_list], folder)
            for d, p in zip(doc_list, fixed):
                d["path"] = p
            moved += notes
    docs_on = [d["path"] for d in doc_list if d.get("on", True)]
    _step(f"checking the files ({len(docs_on)} documents)")
    # every PDF is opened once in a separate process first: a PDF that makes the reader hang can't freeze the program
    for k, lbl in (("pyret", "prior-year return"), ("karbon", "Karbon organizer"), ("utscreens", "UT input screens")):
        if form[k] and Path(form[k]).is_file() and form[k].lower().endswith(".pdf"):
            _step(f"   opening the {lbl}")
            res = safe_pdf.probe(form[k], pages=0, timeout=90)
            _step(f"      {res.get('pages', '?')} pages" + (" — STUCK " + res["stuck"] if res.get("stuck") else ""))
            if res.get("stuck"):
                return back(safe_pdf.stuck_message(form[k], res))
    stuck_docs = []
    for pth in docs_on:
        if Path(pth).is_file() and pth.lower().endswith(".pdf"):
            _step(f"   opening {Path(pth).name}")
            res = safe_pdf.probe(pth, pages=0, timeout=60)
            if res.get("stuck"):
                _step(f"      STUCK {res['stuck']} — left out")
                stuck_docs.append(pth)
    docs_on = [p for p in docs_on if p not in stuck_docs]
    if form["pyret"]:
        if not Path(form["pyret"]).is_file():
            return back("The prior-year return file wasn't found.")
        if not _looks_like_1040(form["pyret"]):
            return back(f"\"{Path(form['pyret']).name}\" doesn't look like a tax return — choose the prior-year 1040 (full print package), "
                        "or leave it empty.")
    if form["karbon"] and not Path(form["karbon"]).is_file():
        return back("The Karbon organizer file wasn't found.")
    if form["utscreens"] and not Path(form["utscreens"]).is_file():
        return back("The UltraTax input screens file wasn't found.")
    if form["utscreens"] and not looks_like_ut_screens(form["utscreens"]):
        return back(f"\"{Path(form['utscreens']).name}\" doesn't look like the UltraTax input screens print.")
    _step("Run check started")
    if form["pyret"]:
        try:
            _step("reading the prior-year return: summary")
            py = read_prior_return(form["pyret"])
            _step("prior-year return: Schedule C / E, income, carryovers")
            schc_py = read_schedule_c(form["pyret"])
            sche_py = read_schedule_e(form["pyret"])
            py_inc = read_py_income(form["pyret"], py, schc_py)
            carry = read_carryovers(form["pyret"])
        except Exception as e:  # noqa: BLE001
            return back(f"Couldn't read the prior-year return: {e}")
    else:
        py, schc_py, sche_py, py_inc = json.loads(json.dumps(EMPTY_PY)), [], [], {}
        carry = dict(summary=[], from_forms=[], checks=[])
    paths = [p for p in docs_on if os.path.normcase(p) != os.path.normcase(form["utscreens"] or "-")]
    _step(f"scanning {len(paths)} documents")
    inv = scan_files(paths, py_year=py.get("year"), py_return=form["pyret"] or None)
    _split_packages(inv)
    ut = None
    if form["utscreens"]:
        _step("reading the UT input screens")
        try:
            ut = read_ut_screens(form["utscreens"])
        except Exception:  # noqa: BLE001
            ut = None
    if not py.get("year"):                                    # no prior-year return: the tax year from the documents
        years = [d.get("year") for d in inv["docs"] if isinstance(d.get("year"), int)]
        cy = max(set(years), key=years.count) if years else ((ut or {}).get("year") or datetime.now().year - 1)
        py["year"], py["no_return"] = cy - 1, not form["pyret"]
        for d in inv["docs"]:                                 # the tax-year flag needs the year
            d["year_flag"] = bool(d.get("year")) and isinstance(d.get("year"), int) and d["year"] != cy and d.get("route") in ("program", "ai")
    kpath = form["karbon"] or next((d["path"] for d in inv["docs"] if d["family"] == "karbon"), "")
    try:
        karbon = read_karbon(kpath) if kpath else None
    except Exception as e:  # noqa: BLE001
        karbon = dict(title="", questions=[], error=str(e))
    if karbon is not None:
        karbon["file"] = Path(kpath).name
        karbon["shown"] = answered(karbon)
    _step("reading the amounts on each document")
    read_amounts(inv)
    match_expected(py["expected"], inv["docs"])
    token = uuid.uuid4().hex[:12]
    schc = [dict(name=b["name"], py=b["lines"], cy={}) for b in schc_py]
    sche = [dict(name=p["name"], py=p["lines"], cy={}, info=dict(type=p.get("type", ""), fair_days=p.get("fair_days"),
                                                                personal_days=p.get("personal_days"))) for p in sche_py]
    r = RUNS[token] = dict(mode=mode, form=form, py=py, inv=inv, schc_py=schc_py, schc=schc, sche_py=sche_py, sche=sche, py_inc=py_inc,
                           docs=paths, doc_list=doc_list, mask=None, carry=carry, edits={}, karbon=karbon, marks={}, comments={},
                           cy_year=(py.get("year") or 0) + 1 if py.get("year") else None, moved=moved,
                           stuck=[f"{Path(p).name} — the PDF reader got stuck on it, left out; open it in Acrobat and save a copy, then add the copy"
                                  for p in stuck_docs])
    r["client"] = _client_label(form, paths)
    r["to_ai"] = default_to_ai(r)
    if form["utscreens"]:
        _load_ut(r, form["utscreens"])
    if wip_data:                                              # the saved work on top of the fresh read
        for k in wip_mod.KEYS:
            if wip_data.get(k) is not None:
                r[k] = wip_data[k]
        if wip_data.get("cy_path") and Path(wip_data["cy_path"]).is_file():
            r["cy_path"] = wip_data["cy_path"]
            try:
                r["cy_ret"] = read_cy_return(wip_data["cy_path"])
            except Exception:  # noqa: BLE001
                r["cy_ret"] = None
        if wip_data.get("ut_path") and not form["utscreens"] and Path(wip_data["ut_path"]).is_file():
            _load_ut(r, wip_data["ut_path"])
        r["wip_path"], r["wip_loaded"] = form["wip"], wip_data.get("saved", "")
    else:
        folder = wip_mod.default_folder(form)
        r["wip_path"] = wip_mod.new_path(folder, r) if folder else None
    _step("saving the work in progress")
    wip_mod.save(r)
    _step("done")
    return redirect(url_for("summary", token=token))


def _split_packages(inv):
    """A brokerage package with 2+ accounts (e.g. Ameriprise consolidated) -> one document per account."""
    out = []
    for d in inv["docs"]:
        if d.get("family") in ("composite", "1099b", "1099div", "1099int") and d["path"].lower().endswith(".pdf"):
            try:
                parts = split_accounts(d["path"], WORK / "accounts")
            except Exception:  # noqa: BLE001
                parts = []
            if parts:
                _step(f"   {d['file']}: {len(parts)} accounts — read separately")
                for p in parts:
                    pg = p["pages"]
                    out.append(dict(d, path=p["path"], orig_path=d["path"], account=p["account"],
                                    file=f"{Path(d['file']).stem} — acct …{p['account'][-4:]}{Path(d['file']).suffix}",
                                    note=(f"Account …{p['account'][-4:]} — pages {pg[0]}-{pg[-1]} of the package ({len(parts)} accounts). "
                                          + (d.get("note") or "")).strip()))
                continue
        out.append(d)
    inv["docs"] = out


def _client_label(form, paths) -> str:
    """Taxpayer's last name + last 4 of the SSN from the 2024 return (page 1); else the client folder's name."""
    if form.get("pyret"):
        try:
            tp = (read_people(form["pyret"]) or [{}])[0]
            last = re.sub(r"[^A-Za-z' -]", "", tp.get("last") or "").strip().title()
            ssn = re.sub(r"\D", "", tp.get("ssn") or "")
            if last:
                return f"{last} {ssn[-4:]}".strip() if len(ssn) == 9 else last
        except Exception:  # noqa: BLE001
            pass
    return wip_mod.client_name(form, paths)


def _load_ut(r, path):
    r["ut_path"], r["ut_scr"], r["ut_error"] = path, None, None
    try:
        r["ut_scr"] = read_ut_screens(path)
        if not (r["ut_scr"]["entries"] or r["ut_scr"].get("rents") or r["ut_scr"].get("memo") or r["ut_scr"].get("payments")
                or r["ut_scr"].get("cscreens")):
            r["ut_error"] = f"No income entries found in \"{Path(path).name}\" — is it the input screens print?"
    except Exception as e:  # noqa: BLE001
        r["ut_error"] = f"Couldn't read the input screens: {type(e).__name__}: {e}"


def _looks_like_1040(path) -> bool:
    """The prior-year / current-year return: a Form 1040 package, not a 1099 or other document."""
    try:
        from core.pdfutil import open_pdf, page_text
        doc, _ = open_pdf(path)
        with doc:
            n = len(doc)
            txt = " ".join(page_text(doc, i) for i in range(min(n, 15)))
    except Exception:  # noqa: BLE001
        return False
    return n >= 2 and "1040" in txt and bool(re.search(r"Individual Income Tax Return|Two Year Comparison|Form 1040 \(20\d\d\)", txt))


def read_amounts(inv: dict) -> None:
    """Reads the 2025 amounts from every document the program can read; the rest goes to the AI."""
    for d in inv["docs"]:
        if d["route"] not in ("program", "excluded"):
            continue
        if d["route"] == "excluded":
            continue
        if d["family"] == "koinly" and "8949" in d.get("doc_type", "") and any(
                x["family"] == "koinly" and "Schedule D" in x.get("doc_type", "") for x in inv["docs"]):
            d.update(read="read", parsed=dict(status="read", amounts={}, notes=[], checks=[]),
                     note=(d["note"] + " Detail of the Koinly Schedule D — totals taken from the Schedule D.").strip())
            continue
        _step(f"   {d['file']}")
        p = parse_document(d)
        d["parsed"] = p
        if p is None:
            d.update(read="none", route="ai", note=(d["note"] + " No program reader for this form yet — AI review.").strip())
        elif isinstance(p, list):
            bad = [k["name"] for k in p if k["status"] != "read"]
            d["read"] = "partial" if bad else ("read" if p else "none")
            d["note"] = (d["note"] + f" {len(p)} K-1s read" + (f"; check: {', '.join(bad[:5])}" if bad else "")).strip()
            if not p:
                d["route"] = "ai"
        else:
            d["read"] = p["status"]
            if p.get("inv_note"):                               # 1095-A / 1098-T: a note only, not in the income summary
                d["note"] = (p["inv_note"] + (" · " + d["note"] if d["note"] else "")).strip()
            if p["status"] == "none":
                d.update(route="ai", note=(d["note"] + " Not read: " + "; ".join(p.get("checks") or ["no amounts found"]) + " — AI review.").strip())
            elif p["status"] == "partial":
                d["note"] = (d["note"] + " Partly read — check: " + "; ".join(p["checks"])).strip()
    # Koinly Schedule D: the 8949 tells which box of each pair (1099-B A-F / 1099-DA G-L)
    k8949 = next((d for d in inv["docs"] if d["family"] == "koinly" and "8949" in d.get("doc_type", "")), None)
    grp = None
    if k8949:
        try:
            grp = koinly_8949_group(k8949["path"])
        except Exception:  # noqa: BLE001
            grp = None
    for d in inv["docs"]:
        p = d.get("parsed")
        if d["family"] == "koinly" and isinstance(p, dict) and p.get("parts") and grp:
            pick = 1 if grp == "da" else 0
            p["parts"] = {k: [(re.sub(r"\(([A-L])/([A-L])\)", lambda m: f"({m.group(1 + pick)})", lb), v) for lb, v in pl]
                          for k, pl in p["parts"].items()}
    for d in inv["docs"]:
        # documents that now go to the AI: long ones send only their summary pages
        if (d["route"] in ("ai", "context") or d.get("read") == "partial") and not d.get("ai_page_list") and d["ext"] == ".pdf":
            sp = summary_pages_for(d["path"], d.get("pages") or 0)
            if sp:
                d.update(ai_page_list=sp, ai_pages=", ".join(map(str, sp)) + f" of {d['pages']}")
            elif d.get("pages") and not d.get("ai_pages"):
                d["ai_pages"] = f"all ({d['pages']})"
    inv["counts"] = {k: sum(1 for d in inv["docs"] if d["route"] == k) for k in ROUTE_LBL}


def default_to_ai(r) -> dict:
    """Goes to AI (ticked by default): not read / partly read / context documents and the prior-year return.
    Not ticked: documents the program read, excluded / skipped files, the Karbon organizer (its summary goes instead)."""
    out = {r["form"]["pyret"]: True} if r["form"].get("pyret") else {}
    for d in r["inv"]["docs"]:
        tick = (d["route"] in ("ai", "context") or d.get("read") == "partial") and d["family"] not in ("karbon", "pyreturn")
        out[d["path"]] = bool(tick)
    if r["form"].get("karbon"):
        out[r["form"]["karbon"]] = False
    return out


def _run(token):
    r = RUNS.get(token)
    if not r:
        abort(404, "This run expired (the program was restarted). Go back and click Run check again.")
    return r


@app.route("/summary/<token>")
def summary(token):
    r = _run(token)
    r.setdefault("comments", {})
    py_year = r["py"].get("year")
    inc, ded = _summaries(r)
    return render_template("summary.html", r=r, token=token, ROUTE_LBL=ROUTE_LBL, inc=inc, ded=ded, MAPL=PL_MAP_LINES,
                           invrows=inventory_rows(r), INV_SECS=INV_SECS,
                           SCHC=list(SCHC_LINES.items()), schc_json=json.dumps(r["schc"]),
                           SCHE=list(SCHE_LINES.items()), sche_json=json.dumps(r.get("sche") or []))


@app.route("/edits/<token>", methods=["POST"])
def save_edits(token):
    """2025 amounts typed over on the income summary: {row id: {cy, fit}}."""
    r = _run(token)
    r["edits"] = request.get_json(force=True, silent=True) or {}
    return jsonify(ok=True)


@app.route("/pl/<token>", methods=["POST"])
def load_pl(token):
    """Reads a P&L (CSV / Excel / PDF) for the Schedule C box: accounts, suggested lines, total check."""
    _run(token)
    path = (request.get_json(force=True, silent=True) or {}).get("path", "")
    if not path or not Path(path).is_file():
        return jsonify(file=Path(path).name if path else "", rows=[], error="File not found.")
    return jsonify(read_pl(path))


@app.route("/schc/<token>/<int:i>/<which>.csv")
def schc_csv(token, i, which):
    from flask import Response
    r = _run(token)
    bz = (r.get("schc") or [])
    if i >= len(bz):
        abort(404)
    b = bz[i]
    rows = ((b.get("pl") or {}).get("rows")) or []
    for x in rows:
        x["amount"] = float(x.get("amount") or 0)
    lines = {}
    for x in rows:
        inc_side = x["section"] in ("income", "other_income")
        sign = 1 if inc_side == (x["line"] in ("1", "6")) else -1
        lines[x["line"]] = lines.get(x["line"], 0) + (x["amount"] if x["line"] in ("nd", "x") else sign * x["amount"])
    name = re.sub(r'[\\/:*?"<>|]+', " ", b.get("name") or f"Business {i + 1}").strip()
    if which == "workpaper":
        data, fn = workpaper_csv(b, lines, b.get("final") or {}), f"{name} - Schedule C workpaper.csv"
    elif which == "other_expenses":
        data, fn = other_expenses_csv(rows), f"{name} - Schedule C other expenses.csv"
    elif which == "book_tax":
        data, fn = book_tax_csv(rows), f"{name} - books vs Schedule C.csv"
    else:
        abort(404)
    return Response(data, mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@app.route("/added/<token>", methods=["POST"])
def save_added(token):
    """Lines added with + on the income summary: [{id, sec, doc, cy, fit, note}] (kept for this run)."""
    r = _run(token)
    r["added"] = [a for a in (request.get_json(force=True, silent=True) or []) if isinstance(a, dict) and a.get("id")]
    return jsonify(ok=True)


# ---------------------------------------------------------------- work in progress (autosave)
WIP_ROUTES = {"save_edits", "save_added", "save_ut", "save_toai", "save_marks", "save_comments", "save_schc", "save_sche",
              "save_inventory", "verify_checklist", "verify_run", "save_invnote"}


@app.after_request
def _autosave(resp):
    if request.method == "POST" and request.endpoint in WIP_ROUTES and resp.status_code == 200:
        r = RUNS.get((request.view_args or {}).get("token"))
        if r is not None:
            wip_mod.save(r)
    return resp


@app.route("/wip/find", methods=["POST"])
def wip_find():
    """Home page: a work-in-progress file next to the Karbon letter / prior-year return just picked."""
    p = ((request.get_json(force=True, silent=True) or {}).get("path") or "").strip().strip('"')
    hit = wip_mod.find(str(Path(p).parent)) if p else None
    return jsonify(hit or {})


@app.route("/wip/<token>/folder", methods=["POST"])
def wip_folder(token):
    """No Karbon letter / prior-year return: the preparer picks where the work in progress is saved."""
    r = _run(token)
    folder = _dialog("folder", "", "Save the work in progress to…")
    if folder is None:
        return jsonify(error="A file window is already open — finish it first.")
    if not folder:
        return jsonify(cancelled=True)
    r["wip_path"] = wip_mod.new_path(folder, r)
    saved = wip_mod.save(r)
    return jsonify(saved=saved, error=r.get("wip_error"))


# ---------------------------------------------------------------- document inventory
INV_SECS = CATS + DED_CATS            # "Added to": the income (and deduction) lines
def inventory_rows(r) -> list:
    """Document inventory (top of screen 1): read by the program first, then not read, each alphabetical.
    Read documents are listed only (their amounts are on the income summary); a not-read document can carry
    one amount + the income line it goes to. Free lines (+) come last."""
    st = r.setdefault("invstate", {"verified": {}, "amt": {}, "notes": {}, "free": []})
    rows = []
    for d in r["inv"]["docs"]:
        if d["family"] == "pyreturn":
            continue
        read = d.get("read") in ("read", "partial")
        note = d.get("note") or ""
        if d.get("ai_page_list") and r.get("to_ai", {}).get(d["path"]):
            note = (note + " · " if note else "") + "AI pages: " + d["ai_pages"]
        a = st["amt"].get(d["path"]) or {}
        rows.append(dict(key=d["path"], file=d["file"], path=d["path"], issuer=d.get("issuer") or "", year=d.get("year") or "",
                         year_flag=d.get("year_flag"), read=d.get("read") or "none", is_read=read, password=d.get("password"),
                         feeds=("comments only" if isinstance(d.get("parsed"), dict) and d["parsed"].get("memo_only") else _feeds_label(d)) if read else "",
                         cy=a.get("cy"), sec=a.get("sec", ""),
                         note=st["notes"].get(d["path"], note), verified=bool(st["verified"].get(d["path"])),
                         ai=bool(r.get("to_ai", {}).get(d["path"])), free=False))
    rows.sort(key=lambda x: x["file"].lower())                     # by file name (A-Z)
    for f in st["free"]:
        rows.append(dict(key=f["id"], file=f.get("name", ""), issuer=f.get("issuer", ""), year="", read="", is_read=False,
                         feeds="", cy=f.get("cy"), sec=f.get("sec", ""), note=f.get("note", ""),
                         verified=bool(f.get("verified")), ai=False, free=True))
    return rows


def _feeds_label(d) -> str:
    """Income lines a read document landed on (from what the parser found)."""
    p = d.get("parsed")
    amts = {}
    for x in (p if isinstance(p, list) else [p] if isinstance(p, dict) else []):
        amts.update({k: v for k, v in (x.get("amounts") or {}).items() if v})
    keys = [k for k, _, _ in INV_SECS if k in amts]
    lbl = dict((k, l) for k, l, _ in INV_SECS)
    return ", ".join(lbl[k].replace("Total ", "") for k in keys)


def inventory_export(r) -> list:
    """Inventory rows for the Excel Documents sheet."""
    lbl = {k: l.replace("Total ", "") for k, l, _ in INV_SECS}
    rl = {"read": "Read", "partial": "Partly read", "none": "Not read"}
    return [dict(d, read_lbl=rl.get(d["read"], "") if not d["free"] else "Added line", sec_lbl=lbl.get(d.get("sec"), ""))
            for d in inventory_rows(r)]


def inventory_added(r) -> list:
    """Inventory amounts -> income summary lines (per preparer only; per document stays blank)."""
    st = r.get("invstate") or {}
    names = {d["path"]: d["file"] for d in r["inv"]["docs"]}
    out = []
    for path, a in (st.get("amt") or {}).items():
        if a.get("sec") and a.get("cy") is not None and path in names:
            out.append(dict(id="inv|" + path, sec=a["sec"], doc=names[path], file=names[path], cy=a["cy"], fit=None,
                            note=(st.get("notes") or {}).get(path, ""), inv=True))
    for f in st.get("free") or []:
        if f.get("sec") and f.get("cy") is not None:
            out.append(dict(id="inv|free|" + f["id"], sec=f["sec"], doc=f.get("name") or "Added line", cy=f["cy"], fit=None,
                            note=f.get("note", ""), inv=True))
    return out


@app.route("/invnote/<token>", methods=["POST"])
def save_invnote(token):
    """The comment typed on an inventory line of the income summary = that line's inventory note."""
    r = _run(token)
    j = request.get_json(force=True, silent=True) or {}
    rid, note = str(j.get("id") or ""), str(j.get("note") or "")
    st = r.setdefault("invstate", {"verified": {}, "amt": {}, "notes": {}, "free": []})
    if rid.startswith("inv|free|"):
        for f in st.get("free") or []:
            if f.get("id") == rid[9:]:
                f["note"] = note
    elif rid.startswith("inv|"):
        st.setdefault("notes", {})[rid[4:]] = note
    return jsonify(ok=True)


@app.route("/inventory/<token>", methods=["POST"])
def save_inventory(token):
    """Inventory state: {verified: {key: bool}, amt: {path: {cy, sec}}, notes: {path: text}, free: [{id, name, issuer, cy, sec, note, verified}]}."""
    r = _run(token)
    j = request.get_json(force=True, silent=True) or {}

    def num(v):
        try:
            return None if v in (None, "") else round(float(str(v).replace(",", "").replace("$", "")), 2)
        except ValueError:
            return None
    r["invstate"] = dict(
        verified={k: bool(v) for k, v in (j.get("verified") or {}).items()},
        amt={k: dict(cy=num(v.get("cy")), sec=v.get("sec") or "") for k, v in (j.get("amt") or {}).items() if isinstance(v, dict)},
        notes={k: str(v) for k, v in (j.get("notes") or {}).items()},
        free=[dict(id=str(f.get("id")), name=f.get("name", ""), issuer=f.get("issuer", ""), cy=num(f.get("cy")), sec=f.get("sec") or "",
                   note=f.get("note", ""), verified=bool(f.get("verified"))) for f in (j.get("free") or []) if isinstance(f, dict) and f.get("id")])
    return jsonify(ok=True)


@app.route("/ut/<token>", methods=["POST"])
def save_ut(token):
    """UT summary fields typed over: {field: value} (kept for this run)."""
    _run(token)["ut"] = request.get_json(force=True, silent=True) or {}
    return jsonify(ok=True)


@app.route("/toai/<token>", methods=["POST"])
def save_toai(token):
    """Goes-to-AI ticks from the Documents table: {path: true/false}."""
    r = _run(token)
    r["to_ai"].update(request.get_json(force=True, silent=True) or {})
    r["mask"] = None                     # the masking list follows the ticks again
    return jsonify(ok=True)


@app.route("/comments/<token>", methods=["POST"])
def save_comments(token):
    """Client comments (under the inventory) and the "received?" comments: {client, recv: {kind|name: text}, recv_note}."""
    r = _run(token)
    j = request.get_json(force=True, silent=True) or {}
    r["comments"] = dict(client=str(j.get("client") or ""), recv={k: str(v) for k, v in (j.get("recv") or {}).items() if str(v).strip()},
                         recv_ok={k: True for k, v in (j.get("recv_ok") or {}).items() if v}, recv_note=str(j.get("recv_note") or ""))
    return jsonify(ok=True)


@app.route("/marks/<token>", methods=["POST"])
def save_marks(token):
    """Ticks (✓) and typed comments on any line of any screen: {key: true/false} and {"n|" + key: text} - merged;
    false / empty removes the key."""
    r = _run(token)
    m = r.setdefault("marks", {})
    for k, v in (request.get_json(force=True, silent=True) or {}).items():
        if v in (False, None, "") or (isinstance(v, str) and not v.strip()):
            m.pop(k, None)
        else:
            m[k] = v
    return jsonify(ok=True)


@app.route("/income/<token>/excel")
def income_excel(token):
    from io import BytesIO
    from flask import send_file
    from core.excel import income_xlsx
    r = _run(token)
    py_year = r["py"].get("year")
    inc, ded = _summaries(r)
    name = r.get("client") or "Client"
    data = income_xlsx(inc, name, ded, inventory_export(r))
    return send_file(BytesIO(data), as_attachment=True, download_name=f"Income Summary {inc['cy_year'] or ''} - {name}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/schc/<token>", methods=["POST"])
def save_schc(token):
    r = _run(token)
    r["schc"] = request.get_json(force=True, silent=True) or []
    return jsonify(ok=True)


@app.route("/sche/<token>", methods=["POST"])
def save_sche(token):
    _run(token)["sche"] = request.get_json(force=True, silent=True) or []
    return jsonify(ok=True)


@app.route("/sche/template.xlsx")
def sche_template_dl():
    """The blank standard Schedule E sheet (one row per property)."""
    from io import BytesIO
    from flask import send_file
    import tempfile
    from core.sche_template import write_template
    p = Path(tempfile.mkdtemp()) / "Schedule E template.xlsx"
    write_template(p)
    return send_file(BytesIO(p.read_bytes()), as_attachment=True, download_name="Schedule E template.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/sche/<token>/import", methods=["POST"])
def sche_import(token):
    """Reads a filled Schedule E sheet (the standard template, .xlsx or .csv) -> properties for the Schedule E box."""
    from core.sche_template import read_template
    _run(token)
    path = ((request.get_json(force=True, silent=True) or {}).get("path") or "").strip().strip('"')
    if not path or not Path(path).is_file():
        return jsonify(error="File not found.")
    try:
        res = read_template(path)
    except Exception as e:  # noqa: BLE001
        return jsonify(error=f"Couldn't read {Path(path).name}: {type(e).__name__}: {e}")
    if not res["properties"]:
        return jsonify(error="; ".join(res["errors"]) or "No properties in the sheet.")
    return jsonify(file=Path(path).name, properties=res["properties"], errors=res["errors"])


@app.route("/sche/<token>/<int:i>/workpaper.csv")
def sche_csv(token, i):
    import csv
    from io import StringIO
    from flask import Response
    r = _run(token)
    props = r.get("sche") or []
    if i >= len(props):
        abort(404)
    p = props[i]
    t = p.get("totals") or {}
    buf = StringIO()
    w = csv.writer(buf)
    info = p.get("info") or {}
    w.writerow(["Schedule E workpaper", p.get("name") or f"Property {i + 1}"])
    w.writerow(["Type", info.get("type", ""), "Fair rental days", info.get("fair_days") or "", "Personal use days", info.get("personal_days") or ""])
    w.writerow([])
    w.writerow(["Line", "Description", "Last year", "This year"])

    def n(x):
        try:
            return f"{float(str(x).replace(',', '')):.2f}"
        except (TypeError, ValueError):
            return ""
    for k, lbl in SCHE_LINES.items():
        if k == "19" and info.get("other_desc"):
            lbl += " — " + info["other_desc"]
        cy = t.get(k) if k in ("20", "21") else (p.get("cy") or {}).get(k)
        w.writerow([k, lbl, n((p.get("py") or {}).get(k)), n(cy)])
    w.writerow(["", "To the income summary", "", n(t.get("net"))])
    name = re.sub(r'[\\/:*?"<>|]+', " ", p.get("name") or f"Property {i + 1}").strip()
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name} - Schedule E workpaper.csv"'})


# ---------------------------------------------------------------- 2. masking
@app.route("/mask/<token>")
def mask(token):
    r = _run(token)
    if not isinstance(r.get("people"), dict):
        # pre-fill only the obvious from the prior-year 1040: SSNs and city / ZIP
        try:
            pp = read_people(r["form"]["pyret"]) if r["form"].get("pyret") else []
        except Exception:  # noqa: BLE001
            pp = []
        r["people"] = dict(ids=[p["ssn"] for p in pp if p.get("ssn")], cityzip=[p["city"] for p in pp if p.get("city")])
    return render_template("mask.html", r=r, token=token, people=json.dumps(r["people"]),
                           step1=json.dumps(_mask_defaults(r)), maskable=sorted(MASKABLE), always=ALWAYS_MASK,
                           prev=json.dumps(r["mask"] or {}))


def _mask_defaults(r) -> list[str]:
    """Masking list default: the documents ticked "Goes to AI" (the prior-year return first)."""
    out = []
    ta = r.get("to_ai") or {}
    for p in [r["form"].get("pyret"), r["form"].get("karbon")] + list(r["docs"]):
        if p and ta.get(p) and p.lower() not in [x.lower() for x in out]:
            out.append(p)
    return out


@app.route("/mask/<token>/run", methods=["POST"])
def mask_run(token):
    r = _run(token)
    d = request.get_json(force=True, silent=True) or {}
    r["people"] = d.get("people") or {}
    files = [f for f in d.get("files") or [] if f]
    values = collect_values(r["people"])
    work = WORK / token
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    pages = {x["path"]: x["ai_page_list"] for x in r["inv"]["docs"] if x.get("ai_page_list")}
    res = mask_files(files, values, work, passwords=[p for p in (d.get("passwords") or "").split(",") if p.strip()], pages=pages)
    r["mask"] = dict(files=files, results=res, values={k: len(v) for k, v in values.items()})
    return jsonify(results=res, values=r["mask"]["values"])


@app.route("/mask/<token>/save", methods=["POST"])
def mask_save(token):
    r = _run(token)
    kind = (request.get_json(force=True, silent=True) or {}).get("kind")
    if not r.get("mask"):
        return jsonify(error="Mask the documents first."), 400
    start = str(HERE / "Claude_1040_skill") if kind == "redacted" and (HERE / "Claude_1040_skill").is_dir() else ""
    folder = _dialog("folder", start, "Save redacted documents + AI report to…" if kind == "redacted" else "Save a copy of the original documents to…")
    if folder is None:
        return jsonify(error="A file window is already open — finish it first.")
    if not folder:
        return jsonify(cancelled=True)
    if kind != "redacted":
        saved = save_copies(r["mask"]["files"], folder)
        return jsonify(folder=folder, saved=[Path(s).name for s in saved])
    pats = _text_patterns(collect_values(r.get("people") or {}))
    saved = save_redacted(r["mask"]["results"], folder, name_fn=lambda t: mask_text(t, pats)[0])
    # the AI report goes with the redacted documents - masked with the same values
    py_year = r["py"].get("year")
    inc, ded = _summaries(r)
    rep = build_report(r, inc, r.get("to_ai") or {}, r["mask"]["results"], ded)
    saved += write_report(folder, rep, lambda t: mask_text(t, pats)[0])
    return jsonify(folder=folder, saved=[Path(s).name for s in saved])


# ---------------------------------------------------------------- 2. verify the 2025 return
def _summaries(r):
    py_year = r["py"].get("year")
    cy_year = (py_year or 0) + 1 if py_year else None
    added = list(r.get("added") or []) + inventory_added(r)
    inc = build_income_summary(r["py_inc"], r["inv"]["docs"], r["schc"], py_year, cy_year, r.get("edits"), added, sche=r.get("sche"))
    ded = build_deduction_summary(r["py_inc"], r["inv"]["docs"], py_year, cy_year, r.get("edits"), added)
    return inc, ded


def _checklist(r):
    if r.get("checklist") is None:
        r["checklist"] = [dict(text=t, done=False, stays=True, master=True, note="") for t in master_load()]
    return r["checklist"]


@app.route("/verify/<token>")
def verify(token):
    r = _run(token)
    r.setdefault("comments", {})
    checks, err, ut = None, r.get("cy_error"), None
    inc, ded = _summaries(r)
    if r.get("cy_ret"):
        try:
            checks = run_checks(r["cy_ret"], inc, ded, r["inv"]["docs"], r["py"], r.get("sche"))
        except Exception as e:  # noqa: BLE001
            err = f"Couldn't check the return: {type(e).__name__}: {e}"
    if r.get("ut_scr"):
        ut = doc_verify(inc, r["inv"]["docs"], r["ut_scr"], r.get("sche"), r.get("schc"))
    return render_template("verify.html", r=r, token=token, checks=checks, error=err, ut=ut, ut_error=r.get("ut_error"),
                           cy_path=r.get("cy_path", ""), ut_path=r.get("ut_path") or "", inc=inc,
                           checklist=json.dumps(_checklist(r)))


@app.route("/verify/<token>/run", methods=["POST"])
def verify_run(token):
    """The 2025 return and / or the UT input screens. With the input screens -> the three-way check;
    without them -> the return-based check."""
    r = _run(token)
    j = request.get_json(force=True, silent=True) or {}
    path = (j.get("path") or "").strip().strip('"')
    utp = (j.get("ut") or "").strip().strip('"')
    r["cy_path"], r["cy_error"], r["cy_ret"] = path, None, None
    r["ut_path"], r["ut_error"], r["ut_scr"] = utp, None, None
    if not path and not utp:
        r["cy_error"] = "Choose the UltraTax input screens and / or the 2025 return (PDF)."
    for pth in (path, utp):
        if pth and Path(pth).is_file():
            res = safe_pdf.probe(pth, pages=0, timeout=90)
            if res.get("stuck"):
                r["cy_error"] = safe_pdf.stuck_message(pth, res)
                return jsonify(ok=False, error=r["cy_error"])
    if path:
        if not Path(path).is_file():
            r["cy_error"] = "The 2025 return file wasn't found."
        elif r["form"].get("pyret") and os.path.normcase(path) == os.path.normcase(r["form"]["pyret"]):
            r["cy_error"] = "That's the prior-year return — choose the 2025 return."
        elif not _looks_like_1040(path):
            r["cy_error"] = f"\"{Path(path).name}\" doesn't look like a tax return — choose the 2025 1040 (full print package)."
        else:
            try:
                r["cy_ret"] = read_cy_return(path)
            except Exception as e:  # noqa: BLE001
                r["cy_error"] = f"Couldn't read the return: {type(e).__name__}: {e}"
    if utp:
        if not Path(utp).is_file():
            r["ut_error"] = "The input screens file wasn't found."
        elif not looks_like_ut_screens(utp):
            r["ut_error"] = f"\"{Path(utp).name}\" doesn't look like the UltraTax input screens print."
        else:
            _load_ut(r, utp)
    return jsonify(ok=not (r["cy_error"] or r["ut_error"]), error=r["cy_error"] or r["ut_error"])


@app.route("/verify/<token>/checklist", methods=["POST"])
def verify_checklist(token):
    """Checklist lines: done / note / stays. Stays Y = on the master list for every client; N = this return only."""
    r = _run(token)
    items = [x for x in (request.get_json(force=True, silent=True) or []) if isinstance(x, dict) and str(x.get("text", "")).strip()]
    master = master_load()
    for x in items:
        t = x["text"].strip()
        if x.get("stays") and t not in master:
            master.append(t)
        if not x.get("stays") and x.get("master") and t in master:
            master.remove(t)
        x["master"] = bool(x.get("stays"))
    master_save(master)
    r["checklist"] = items
    return jsonify(ok=True, master=len(master))


@app.route("/verify/<token>/save", methods=["POST"])
def verify_save(token):
    r = _run(token)
    if not r.get("cy_ret") and not r.get("ut_scr"):
        return jsonify(error="Check the return first (input screens and / or the 2025 return).")
    start = str(Path(r["wip_path"]).parent) if r.get("wip_path") else (wip_mod.default_folder(r["form"]) or "")
    folder = _dialog("folder", start, "Save the review (Excel) to…")
    if folder is None:
        return jsonify(error="A file window is already open — finish it first.")
    if not folder:
        return jsonify(cancelled=True)
    inc, ded = _summaries(r)
    checks = run_checks(r["cy_ret"], inc, ded, r["inv"]["docs"], r["py"], r.get("sche")) if r.get("cy_ret") else None
    ut = doc_verify(inc, r["inv"]["docs"], r["ut_scr"], r.get("sche"), r.get("schc")) if r.get("ut_scr") else None
    client = r.get("client") or "Client"
    files = " + ".join(x for x in [(r.get("ut_scr") or {}).get("file"), (r.get("cy_ret") or {}).get("file")] if x)
    data = review_xlsx(client, files, checks, _checklist(r), inventory_export(r), ut, r.get("comments"), (r.get("py") or {}).get("expected"),
                       marks=r.get("marks") or {}, inc=inc, ded=ded)
    safe = re.sub(r'[\\/:*?"<>|]+', " ", client).strip()
    out = Path(folder) / ("Review " + str(inc.get("cy_year") or "") + " - " + safe + ".xlsx")
    try:
        out.write_bytes(data)
    except PermissionError:
        out = out.with_name(out.stem + f" {datetime.now():%H%M%S}.xlsx")
        out.write_bytes(data)
    return jsonify(saved=str(out))


@app.route("/ai/<token>")
def ai(token):
    _run(token)
    return render_template("placeholder.html", token=token, title="AI review",
                           text="Step 3 — the AI report and the skill hand-off come after the document parsers.")


def _no_quickedit():
    """Windows: clicking in the black window (QuickEdit "Select" mode) freezes the program until Esc is pressed.
    Turn QuickEdit off for this window so a click can't pause it."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-10)                         # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, (mode.value & ~0x0040) | 0x0080)   # QuickEdit off, extended flags on
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    _no_quickedit()
    shutil.rmtree(WORK, ignore_errors=True)
    url = f"http://127.0.0.1:{PORT}"
    print(f"1040 Ultimate running at {url}  (Ctrl+C to stop)")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
