"""web.py - the K-1 Verification pages inside 1040 Ultimate (Flask blueprint, URL prefix /k1v).

Copied and adapted from C:\\dev\\K-1_interpretation\\verify1040.py (that folder stays as the backup). Differences:
  * a blueprint, so 1040 Ultimate's own routes are untouched;
  * no K-1 Package Preparation (the K-1 PDFs are read directly - statement pages stay available);
  * no 8582 Reconciliation yet;
  * the home page has two tabs: K-1 1065 and K-1 1120-S.

    /k1v/?for=<1040 run>    the K-1 run of that 1040 run (always opened from the 1040): its K-1 PDFs (found among the 1040's
                            documents, + Add K-1 PDFs...), then open:
    /k1v/k1/<token>         K-1 Interpreter (UltraTax entry guide, statement amounts, totals, Income Summary,
                            Add to Income Summary)
    /k1v/verify/<token>     K-1 entry check: every K-1 item vs what was typed in UltraTax
    /k1v/prep/<token>       K-1 Prep (a run opened from the 1040): box E vs taxpayer / spouse, corrected amounts per box,
                            problems, "Export for UT data entry" (the CSV of APPS_ARCHITECTURE.md) - see prep.py
    /k1v/                   stand-alone reader (upload the PDFs; no 1040 run, nothing goes to an income summary)
A run opened from the 1040 has its owner (the 1040 run token) from the start. Nothing reaches the 1040 until "Add to Income
Summary" (handoff.build_package -> HOOKS["added"]). The K-1 page's own work (statement amounts, ticks, comments, corrections)
is posted here (/state) and saved by the 1040 in a K-1 work-in-progress file next to its own (HOOKS["state"]).
"""
from __future__ import annotations

import copy
import os
import re
import tempfile
import uuid
from io import BytesIO
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request, send_file

from .codes_1120s import BOXES_1120S
from .k1_parser import parse_pdf
from .k1_rules import ORDER, RULES
from . import handoff, k1_codes, prep
from .k1_summary import build_summary, write_xlsx
from .screen_parser import parse_screens
from .screen_verify import verify_screens
from .verify1040_excel import write_verification_xlsx

BASE = "/k1v"
bp = Blueprint("k1v", __name__, url_prefix=BASE)
RUNS: dict = {}          # token -> {"k1s", "k1name", "files", "owner", "state", "scr", "scrname", "result", "manual", "flags", "n1065", "n1120"}
# set by the 1040 app: added(owner, package), state(owner) (save the K-1 work file), ut_path(owner) -> UT input screens or ""
# people(owner) -> {"tp": taxpayer SSN, "sp": spouse SSN} from the prior-year return; label(owner) -> "2025 - Name 1234"
HOOKS: dict = {"added": None, "state": None, "ut_path": None, "people": None, "label": None}


def _ctx(**kw):
    return dict(k1v_base=BASE, codes_1120s=BOXES_1120S, **kw)


def _is_password_error(e) -> bool:
    c, n = e, 0
    while c is not None and n < 6:                       # pdfplumber wraps pdfminer's error
        if "Password" in type(c).__name__ or "password" in str(c).lower():
            return True
        c = c.__cause__ or c.__context__ or (c.args[0] if c.args and isinstance(c.args[0], BaseException) else None)
        n += 1
    return not str(e).strip() and "Pdfminer" in type(e).__name__    # pdfminer's own message is empty


def _name_password(filename: str) -> str:
    """The password is kept at the end of the file name: '... PW-8wRxFRRM.pdf', '... PW - 8wRxFRRM.pdf'."""
    m = re.search(r"\bPW[\s_]*[-:=]?[\s_]*([A-Za-z0-9!@#$%^&*._]+?)(?:\s*\(\d+\))?\.pdf$", filename or "", re.I)
    return m.group(1).strip("._") if m else ""


def read_k1_files(files, pw: str = ""):
    """files: [(path on disk, display name)] -> (K-1 dicts, problems, {display name: number of K-1s}).
    A password at the end of the name ('... PW-8wRxFRRM.pdf') is tried first. Pages of the 2nd file are 1001+, 3rd 2001+."""
    try:
        from core.pdfutil import password_candidates
    except Exception:  # noqa: BLE001
        password_candidates = lambda path, extra=None: []  # noqa: E731
    out, problems, counts = [], [], {}
    for n, (path, name) in enumerate(files):
        got, err = None, None
        for cand in dict.fromkeys([_name_password(name), pw, *password_candidates(Path(name)), ""]):
            try:
                got = parse_pdf(str(path), password=cand)
                break
            except Exception as e1:  # noqa: BLE001
                err = e1
                if not _is_password_error(e1):
                    break
        if got is None:
            if _is_password_error(err):
                problems.append(f"{name} is password-protected — the password at the end of the file name (PW-…) didn't open it")
            else:
                problems.append(f"{name} couldn't be read ({type(err).__name__}: {err})")
            continue
        counts[name] = [k.form for k in got]
        for k in got:
            d = k.to_dict()
            d["page"] += 1000 * n
            out.append(prep.assign_lids(d))
    return out, problems, counts


def _fill(run, files):
    """(Re-)reads the run's K-1 files: [(path, display name)]."""
    k1s, problems, counts = read_k1_files(files)
    run.update(files=list(files), k1s=k1s, problems=problems, k1name=" + ".join(n for _, n in files),
               n1065=sum(1 for k in k1s if k.get("form") == "1065"), n1120=sum(1 for k in k1s if k.get("form") == "1120-S"))
    return counts


def make_run(files, scr_path=None, scr_name=None, owner=None, state=None):
    """Used by the 1040: the K-1 files found among its documents go through the same engine as this page.
    Returns (token, problems, counts) - a run is made even when nothing was read (more K-1s can be added on the page).
    Nothing goes to the income summary here: that waits for "Add to Income Summary"."""
    run = {"result": None, "manual": {}, "flags": {}, "scr": None, "scrname": None, "owner": owner, "state": state}
    counts = _fill(run, files)
    token = uuid.uuid4().hex[:12]
    RUNS[token] = run
    if scr_path:
        attach_screens(token, scr_path, scr_name)
    return token, run["problems"], counts


def file_ids(run) -> list:
    """The fingerprint of each K-1 file of the run (same rule as the 1040's documents: the first 16 characters of the SHA-1)."""
    import hashlib
    out = []
    for p, _ in run.get("files") or []:
        try:
            h = hashlib.sha1(Path(p).read_bytes()).hexdigest()[:16]
        except OSError:
            h = ""
        out.append(h)
    return out


def run_for(owner):
    """The K-1 run of a 1040 run (token, run) - or (None, None)."""
    return next(((t, x) for t, x in RUNS.items() if owner and x.get("owner") == owner), (None, None))


def attach_screens(token, path, name=None) -> str:
    """The UltraTax Input Screens PDF -> the K-1 entry check of that run. Returns an error text ('' = ok)."""
    run = RUNS.get(token)
    if not run:
        return "run not found"
    try:
        scr = parse_screens(str(path))
        if not scr["units"]:
            return "No K-1 input screens (K1, K1-2 …) found in the input screens PDF."
        run["scr"], run["scrname"] = scr, name or Path(path).name
        run["result"] = verify_screens(prep.for_check(run), scr)
    except Exception as e:  # noqa: BLE001
        return f"Couldn't read the input screens for the K-1 check: {type(e).__name__}: {e}"
    return ""


def set_owner(token, owner) -> None:
    run = RUNS.get(token)
    if run:
        run["owner"] = owner


def _read_upload(f, reader, **kw):
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        f.save(tmp)
        return reader(tmp, **kw)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


# ------------------------------------------------------------------ statement amounts (same as verify1040.py)
def merge_manual(k1s, manual, flags=None):
    """Add the 'Statement amounts' typed on the K-1 Interpreter page to the K-1s, as if read from the PDF.
    The box's generic "See statement" line (no amount) is replaced. Mirrors mergeK1() in report.html.
    flags: {"page|n": "ST" | "LT"} - box 11 S ticked Short-term / Long-term (n-th 11S line on that K-1)."""
    return [_flag_11s(k, flags) for k in _merge_amounts(k1s, manual)]


def _flag_11s(k, flags):
    if not flags or not any(l["box"] == "11" and l.get("code") == "S" for l in k["lines"]):
        return k
    k, n = copy.deepcopy(k), 0
    for l in k["lines"]:
        if l["box"] == "11" and l.get("code") == "S":
            v = flags.get(f"{k['page']}|{n}")
            if v in ("ST", "LT"):
                l["s11"] = v
            n += 1
    return k


def _merge_amounts(k1s, manual):
    out = []
    for k in k1s:
        ent = (manual or {}).get(str(k["page"])) or []
        add = []
        for e in ent:
            try:
                key, a = e[0], str(e[1] or "")
            except (IndexError, TypeError):
                continue
            t = a.replace("$", "").replace(",", "").replace(" ", "")
            neg = (t.startswith("(") and t.endswith(")")) or t.startswith("-")
            t = t.strip("()-")
            if not key or not re.match(r"\d", key) or not re.fullmatch(r"\d+(\.\d+)?", t or "x"):
                continue
            v = -float(t) if neg else float(t)
            if v:
                add.append((key, v))
        if not add:
            out.append(k)
            continue
        k = copy.deepcopy(k)
        boxes = {prep.split_key(key)[0] for key, _ in add}
        k["lines"] = [l for l in k["lines"] if not (l["box"] in boxes and l.get("amt") is None and l.get("stmt") and not l.get("check"))]
        for key, v in add:
            box = prep.split_key(key)[0]
            k["lines"].append(dict(box=box, code=key[len(box):] or None, amt=v, stmt=True, check=False,
                                   raw="added from statement", key=key, manual=True))
        ob = lambda b: ORDER.index(b) if b in ORDER else 999
        k["lines"] = [l for _, l in sorted(enumerate(k["lines"]), key=lambda t: (ob(t[1]["box"]), t[0]))]
        out.append(k)
    return out


def _recheck(run) -> None:
    """The K-1 entry check again (after a change to what counts: K-1s added, a copy choice, a box correction)."""
    if run.get("scr"):
        run["result"] = verify_screens(prep.for_check(run), run["scr"])


def _summary(k1s, state):
    """The Income Summary of the K-1s that count + "box_corr": {rid: amount} - the lines a K-1 Prep box correction moves
    (the totals tab's Correction column starts from it)."""
    st = state or {}
    ks = prep.counted(k1s, st)
    s = build_summary(ks)
    s["box_corr"] = prep.summary_corr(ks, st.get("pcorr"), build_summary)[0]
    return s


def _report_ctx(run=None, error=None, filename=None, token=None):
    dicts = run["k1s"] if run else []
    state = (run or {}).get("state")
    return _ctx(k1s=dicts, rules=RULES, order=ORDER, summary=_summary(dicts, state),
                filename=filename or (run["k1name"] if run else None), error=error, static=False,
                codes=k1_codes.dropdown(), code_boxes=k1_codes.CODE_BOXES, token=token, owner=(run or {}).get("owner"),
                state=state, dups=prep.find_copies(dicts, (state or {}).get("dup")), plines=prep.plines_entries(state))


def _run(token):
    run = RUNS.get(token)
    if not run:
        abort(404, "This run expired (the program was restarted). Go back and click Read again.")
    return run


# ------------------------------------------------------------------ pages
@bp.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        owner = request.args.get("for")
        if owner:                                             # opened from the 1040: its K-1 run (made now if it has none yet)
            token, run = run_for(owner)
            if not run:
                ut = (HOOKS["ut_path"] or (lambda o: ""))(owner)
                token, _, _ = make_run([], ut or None, owner=owner)
                run = RUNS[token]
            return render_template("k1v/home.html", **_ctx(run=run, token=token, error=None, tab=request.args.get("tab"), owner=owner))
        return render_template("k1v/home.html", **_ctx(run=None, token=None, error=None, tab=request.args.get("tab"), owner=None))
    # the upload card on the K-1 Interpreter page posts a single "pdf" -> just the interpreter
    if "pdf" in request.files and "k1pdf" not in request.files:
        f = request.files["pdf"]
        try:
            k1s = [prep.assign_lids(k.to_dict()) for k in _read_upload(f, parse_pdf)]
        except Exception as e:  # noqa: BLE001
            return render_template("k1v/report.html", **_report_ctx(error=(f"{f.filename} is password-protected — use the K-1 Verification page and type the password there."
                                                                       if _is_password_error(e) else f"Couldn't read the PDF: {e}"), filename=f.filename))
        return render_template("k1v/report.html", **_report_ctx({"k1s": k1s, "k1name": f.filename}))
    fks = [f for f in request.files.getlist("k1pdf") if f and f.filename]
    fs = request.files.get("scrpdf")
    if not fks or not all(f.filename.lower().endswith(".pdf") for f in fks):
        return render_template("k1v/home.html", **_ctx(run=None, token=None, owner=None, error="Please choose the K-1 PDF(s)."))
    run = {"k1name": " + ".join(f.filename for f in fks), "result": None, "manual": {}, "flags": {}, "scr": None, "scrname": None}
    pw = (request.form.get("pdfpw") or "").strip()
    run["k1s"], problems = [], []
    for n, f in enumerate(fks):
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            f.save(tmp)
            ks, pr, _ = read_k1_files([(tmp, f.filename)], pw)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        for d in ks:
            d["page"] += 1000 * n
            for l in d["lines"]:                             # line ids follow the page number
                l.pop("lid", None)
            run["k1s"].append(prep.assign_lids(d))
        problems += pr
    run["problems"] = problems
    if not run["k1s"]:
        msg = "; ".join(problems) if problems else "No Schedule K-1 pages found in the K-1 PDF(s)."
        return render_template("k1v/home.html", **_ctx(run=None, token=None, owner=None, error=msg))
    run["n1065"] = sum(1 for k in run["k1s"] if k.get("form") == "1065")
    run["n1120"] = sum(1 for k in run["k1s"] if k.get("form") == "1120-S")
    if fs and fs.filename:
        try:
            run["scr"] = _read_upload(fs, parse_screens)
            run["scrname"] = fs.filename
        except Exception as e:  # noqa: BLE001
            return render_template("k1v/home.html", **_ctx(run=None, token=None, owner=None, error=f"Couldn't read the Input Screens PDF: {e}"))
        if not run["scr"]["units"]:
            return render_template("k1v/home.html", **_ctx(run=None, token=None, owner=None,
                                   error="No K-1 input screens (K1, K1-2 …) found in the Input Screens PDF — print UltraTax File > Print > Input screens."))
        run["result"] = verify_screens(prep.counted(run["k1s"], None), run["scr"])
    token = uuid.uuid4().hex[:12]
    RUNS[token] = run
    return render_template("k1v/home.html", **_ctx(run=run, token=token, error=None, tab=None, owner=None))


@bp.route("/k1/<token>")
def k1_view(token):
    return render_template("k1v/report.html", **_report_ctx(_run(token), token=token))


@bp.route("/verify/<token>")
def verify_view(token):
    run = _run(token)
    if not run["result"]:
        abort(400, "No Input Screens PDF was read — go back and add the UltraTax Input Screens PDF.")
    return render_template("k1v/verify.html", **_ctx(res=run["result"], k1name=run["k1name"], retname=run["scrname"], token=token,
                                                    manual=run.get("manual") or {}, flags=run.get("flags") or {}))


@bp.route("/manual/<token>", methods=["POST"])
def manual(token):
    """Statement amounts typed on the K-1 Interpreter page -> re-run the check with them."""
    run = _run(token)
    d = request.get_json(force=True, silent=True) or {}
    new, flags = d.get("manual") or {}, d.get("flags") or {}
    changed = new != (run.get("manual") or {}) or flags != (run.get("flags") or {})
    run["manual"], run["flags"] = new, flags
    if changed:
        _recheck(run)
    return jsonify(ok=True, changed=changed)


@bp.route("/summary", methods=["POST"])
def summary():
    """Income Summary for the totals tab, recalculated with the statement amounts (K-1 copies left out; "box_corr" = the
    lines moved by the box corrections typed on K-1 Prep)."""
    d = request.get_json(force=True, silent=True) or {}
    run = RUNS.get(d.get("token") or "")
    return jsonify(_summary(d.get("k1s") or [], (run or {}).get("state")))


@bp.route("/add/<token>", methods=["POST"])
def add_to_income_summary(token):
    """'Add to Income Summary': one package of the run's K-1 lines (amount read -> per document, the correction typed on the
    totals tab -> corrected amount) to the 1040 run that owns this K-1 run. Adding again replaces the package."""
    run = _run(token)
    if not run.get("owner") or not HOOKS["added"]:
        return jsonify(ok=False, error="Open the K-1 page from the 1040 (K-1 box, Open K-1 Verification) to add the K-1s."), 400
    d = request.get_json(force=True, silent=True) or {}
    if isinstance(d.get("state"), dict):
        run["state"] = prep.keep_prep_keys(run.get("state"), d["state"])
    st = run.get("state") or {}
    skip = {p for p, m in prep.find_copies(run["k1s"], st.get("dup")).items() if not m["counted"]}      # a copy counts once
    k1s = [k for k in (d.get("k1s") or []) if k.get("form") in handoff.FORMS and k.get("page") not in skip]
    if not k1s:
        return jsonify(ok=False, error="No Form 1065 K-1s to add."), 400
    box_corr, box_rows = prep.summary_corr(k1s, st.get("pcorr"), build_summary)
    pkg = handoff.build_package(k1s, st.get("corr") or {}, build_summary(k1s), [n for _, n in run["files"]],
                                handoff.signature(run["k1s"], run.get("state")), file_ids(run), box_corr, box_rows)
    if not HOOKS["added"](run["owner"], pkg):
        return jsonify(ok=False, error="The 1040 run is gone (the program was restarted) — open the client again."), 400
    if HOOKS["state"]:
        HOOKS["state"](run["owner"])
    return jsonify(ok=True, k1s=pkg["n"], lines=len(pkg["rows"]), at=pkg["added"])


@bp.route("/state/<token>", methods=["POST"])
def save_state(token):
    """The K-1 page's own work (what it keeps in the browser: statement amounts, 11 S / 11 ZZ ticks, Verified ticks, comments,
    UT numbers, corrections) - kept with the run and saved by the 1040 next to its work in progress."""
    run = _run(token)
    d = request.get_json(force=True, silent=True)
    if isinstance(d, dict):
        run["state"] = prep.keep_prep_keys(run.get("state"), d)      # what K-1 Prep saved is not the Interpreter's to change
        if run.get("owner") and HOOKS["state"]:
            HOOKS["state"](run["owner"])
    return jsonify(ok=True)


@bp.route("/files/<token>", methods=["POST"])
def add_files(token):
    """Add K-1 PDFs (paths picked in the file window) to a run opened from the 1040: every file is read again."""
    run = _run(token)
    paths = [p for p in (request.get_json(force=True, silent=True) or {}).get("paths") or [] if p and Path(p).is_file()]
    have = {os.path.normcase(p) for p, _ in run.get("files") or []}
    new = [(p, Path(p).name) for p in paths if p.lower().endswith(".pdf") and os.path.normcase(p) not in have]
    if new:
        _fill(run, (run.get("files") or []) + new)
        _recheck(run)
        if run.get("owner") and HOOKS["state"]:
            HOOKS["state"](run["owner"])
    return jsonify(ok=True, added=len(new), problems=run["problems"])


# ------------------------------------------------------------------ K-1 Prep (list of 2026-11-05, items 1 and 6)
def _prep_data(run):
    people = (HOOKS["people"] or (lambda o: {}))(run.get("owner")) if run.get("owner") else {}
    label = (HOOKS["label"] or (lambda o: ""))(run.get("owner")) if run.get("owner") else ""
    return prep.build(run, people, file_ids(run), client=re.sub(r"^\d{4}\s*-\s*", "", label))


@bp.route("/prep/<token>")
def prep_view(token):
    run = _run(token)
    if not run.get("owner"):
        abort(400, "Open the K-1 page from the 1040 (K-1 box, Open K-1 Verification) for K-1 Prep.")
    return render_template("k1v/prep.html", **_ctx(token=token, owner=run["owner"], data=_prep_data(run)))


@bp.route("/prep/<token>/save", methods=["POST"])
def prep_save(token):
    """A change on K-1 Prep (a corrected amount, a tick, count / don't count, the taxpayer / spouse SSN) - also used by the
    Interpreter for count / don't count. Saved in the K-1 work file; the entry check runs again."""
    run = _run(token)
    prep.save(run, request.get_json(force=True, silent=True) or {})
    _recheck(run)
    if run.get("owner") and HOOKS["state"]:
        HOOKS["state"](run["owner"])
    return jsonify(ok=True, data=_prep_data(run))


@bp.route("/prep/<token>/export")
def prep_export(token):
    """"Export for UT data entry": the CSV the separate UT Data Entry app reads (columns: APPS_ARCHITECTURE.md)."""
    run = _run(token)
    data = _prep_data(run)
    if not data["people"].get("tp"):
        abort(400, "Enter the taxpayer SSN (last 4) on K-1 Prep first - box E is matched to it.")
    if not prep.export_rows(data):
        abort(400, "Nothing to export - no K-1 is Ready.")
    label = (HOOKS["label"] or (lambda o: ""))(run.get("owner")) if run.get("owner") else ""
    name = ("UT data entry K-1 " + label).strip() + ".csv"
    return send_file(BytesIO(prep.export_csv(data)), as_attachment=True, download_name=name, mimetype="text/csv")


@bp.route("/verify/<token>/excel")
def verify_excel(token):
    run = _run(token)
    if not run["result"]:
        abort(400, "No Input Screens PDF was read — go back and add the UltraTax Input Screens PDF.")
    data = write_verification_xlsx(run["result"], run["k1name"], run["scrname"])
    name = Path(run["scrname"] or "UltraTax").stem + "_K1_verification.xlsx"
    return send_file(BytesIO(data), as_attachment=True, download_name=name,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/excel", methods=["POST"])
def excel():
    """Excel summary for the K-1 Interpreter page."""
    d = request.get_json(force=True, silent=True) or {}
    k1s = d.get("k1s") or []
    if not k1s:
        return jsonify(error="No K-1 data"), 400
    data = write_xlsx(k1s, ut=d.get("ut"), pcomments=d.get("pc"), items=d.get("items"), filename=d.get("filename", ""),
                      corr=d.get("corr"))
    name = (Path(d.get("filename") or "K-1").stem or "K-1") + "_Income_Summary.xlsx"
    return send_file(BytesIO(data), as_attachment=True, download_name=name,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def register(app) -> None:
    app.register_blueprint(bp)
