"""web.py - the K-1 Verification pages inside 1040 Ultimate (Flask blueprint, URL prefix /k1v).

Copied and adapted from C:\\dev\\K-1_interpretation\\verify1040.py (that folder stays as the backup). Differences:
  * a blueprint, so 1040 Ultimate's own routes are untouched;
  * no K-1 Package Preparation (the K-1 PDFs are read directly - statement pages stay available);
  * no 8582 Reconciliation yet;
  * the home page has two tabs: K-1 1065 and K-1 1120-S.

    /k1v/                   home: upload the K-1 PDFs (+ the UltraTax Input Screens PDF), then open:
    /k1v/k1/<token>         K-1 Interpreter (UltraTax entry guide, statement amounts, totals, Income Summary)
    /k1v/verify/<token>     K-1 entry check: every K-1 item vs what was typed in UltraTax
Nothing is stored: PDFs are read from temp files deleted right away; results live in memory while the program runs.
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
from . import handoff
from .k1_summary import build_summary, write_xlsx
from .screen_parser import parse_screens
from .screen_verify import verify_screens
from .statement_codes import CODES
from .verify1040_excel import write_verification_xlsx

BASE = "/k1v"
bp = Blueprint("k1v", __name__, url_prefix=BASE)
RUNS: dict = {}          # token -> {"k1s", "k1name", "scr", "scrname", "result", "manual", "flags", "n1065", "n1120"}


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
            out.append(d)
    return out, problems, counts


def make_run(files, scr_path=None, scr_name=None):
    """Used by the 1040 verification: the K-1 files added there go through the same engine as this page.
    Returns (token or None, problems, counts). The K-1 lines are handed to the income summary right away."""
    k1s, problems, counts = read_k1_files(files)
    if not k1s:
        return None, problems, counts
    run = {"k1name": " + ".join(n for _, n in files), "result": None, "manual": {}, "flags": {}, "scr": None, "scrname": None,
           "k1s": k1s, "problems": problems, "owner": None,
           "n1065": sum(1 for k in k1s if k.get("form") == "1065"), "n1120": sum(1 for k in k1s if k.get("form") == "1120-S")}
    token = uuid.uuid4().hex[:12]
    RUNS[token] = run
    if scr_path:
        attach_screens(token, scr_path, scr_name)
    k65 = [k for k in k1s if k.get("form") == "1065"]
    if k65:
        handoff.put(handoff.build_payload(token, run["k1name"], k65, {}, build_summary(k65)))
    return token, problems, counts


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
        run["result"] = verify_screens(merge_manual(run["k1s"], run.get("manual"), run.get("flags")), scr)
    except Exception as e:  # noqa: BLE001
        return f"Couldn't read the input screens for the K-1 check: {type(e).__name__}: {e}"
    return ""


def set_owner(token, owner) -> None:
    run = RUNS.get(token)
    if run:
        run["owner"] = owner
        handoff.set_owner(token, owner)


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
            if not key or not re.fullmatch(r"\d+(\.\d+)?", t or "x"):
                continue
            v = -float(t) if neg else float(t)
            if v:
                add.append((key, v))
        if not add:
            out.append(k)
            continue
        k = copy.deepcopy(k)
        boxes = {re.match(r"\d+", key).group(0) for key, _ in add}
        k["lines"] = [l for l in k["lines"] if not (l["box"] in boxes and l.get("amt") is None and l.get("stmt") and not l.get("check"))]
        for key, v in add:
            box = re.match(r"\d+", key).group(0)
            k["lines"].append(dict(box=box, code=key[len(box):] or None, amt=v, stmt=True, check=False,
                                   raw="added from statement", key=key, manual=True))
        ob = lambda b: ORDER.index(b) if b in ORDER else 999
        k["lines"] = [l for _, l in sorted(enumerate(k["lines"]), key=lambda t: (ob(t[1]["box"]), t[0]))]
        out.append(k)
    return out


def _report_ctx(run=None, error=None, filename=None, token=None):
    dicts = run["k1s"] if run else []
    return _ctx(k1s=dicts, rules=RULES, order=ORDER, summary=build_summary(dicts),
                filename=filename or (run["k1name"] if run else None), error=error, static=False,
                codes=CODES, token=token)


def _run(token):
    run = RUNS.get(token)
    if not run:
        abort(404, "This run expired (the program was restarted). Go back and click Read again.")
    return run


# ------------------------------------------------------------------ pages
@bp.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        return render_template("k1v/home.html", **_ctx(run=None, token=None, error=None, tab=request.args.get("tab")))
    # the upload card on the K-1 Interpreter page posts a single "pdf" -> just the interpreter
    if "pdf" in request.files and "k1pdf" not in request.files:
        f = request.files["pdf"]
        try:
            k1s = [k.to_dict() for k in _read_upload(f, parse_pdf)]
        except Exception as e:  # noqa: BLE001
            return render_template("k1v/report.html", **_report_ctx(error=(f"{f.filename} is password-protected — use the K-1 Verification page and type the password there."
                                                                       if _is_password_error(e) else f"Couldn't read the PDF: {e}"), filename=f.filename))
        return render_template("k1v/report.html", **_report_ctx({"k1s": k1s, "k1name": f.filename}))
    fks = [f for f in request.files.getlist("k1pdf") if f and f.filename]
    fs = request.files.get("scrpdf")
    if not fks or not all(f.filename.lower().endswith(".pdf") for f in fks):
        return render_template("k1v/home.html", **_ctx(run=None, token=None, error="Please choose the K-1 PDF(s)."))
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
            run["k1s"].append(d)
        problems += pr
    run["problems"] = problems
    if not run["k1s"]:
        msg = "; ".join(problems) if problems else "No Schedule K-1 pages found in the K-1 PDF(s)."
        return render_template("k1v/home.html", **_ctx(run=None, token=None, error=msg))
    run["n1065"] = sum(1 for k in run["k1s"] if k.get("form") == "1065")
    run["n1120"] = sum(1 for k in run["k1s"] if k.get("form") == "1120-S")
    if fs and fs.filename:
        try:
            run["scr"] = _read_upload(fs, parse_screens)
            run["scrname"] = fs.filename
        except Exception as e:  # noqa: BLE001
            return render_template("k1v/home.html", **_ctx(run=None, token=None, error=f"Couldn't read the Input Screens PDF: {e}"))
        if not run["scr"]["units"]:
            return render_template("k1v/home.html", **_ctx(run=None, token=None,
                                   error="No K-1 input screens (K1, K1-2 …) found in the Input Screens PDF — print UltraTax File > Print > Input screens."))
        run["result"] = verify_screens(run["k1s"], run["scr"])
    token = uuid.uuid4().hex[:12]
    RUNS[token] = run
    return render_template("k1v/home.html", **_ctx(run=run, token=token, error=None, tab=None))


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
    if run.get("scr") and changed:
        run["result"] = verify_screens(merge_manual(run["k1s"], new, flags), run["scr"])
    return jsonify(ok=True, changed=changed)


@bp.route("/summary", methods=["POST"])
def summary():
    """Income Summary for the totals tab, recalculated with the statement amounts."""
    d = request.get_json(force=True, silent=True) or {}
    return jsonify(build_summary(d.get("k1s") or []))


@bp.route("/upload/<token>", methods=["POST"])
def upload_to_1040(token):
    """'Upload to 1040': the Income Summary lines (with the corrections typed on the K-1 page) go to the 1040 verification;
    each K-1's name / EIN / amounts go on a back channel. Several uploads (batches of K-1s) add up."""
    d = request.get_json(force=True, silent=True) or {}
    k1s = [k for k in (d.get("k1s") or []) if k.get("form") == "1065"]
    if not k1s:
        return jsonify(ok=False, error="No 1065 K-1s to upload."), 400
    payload = handoff.build_payload(token, d.get("filename") or "K-1s", k1s, d.get("corr") or {}, build_summary(k1s),
                                    owner=(RUNS.get(token) or {}).get("owner"))
    handoff.put(payload)
    lines = sum(len(v) for v in payload["sections"].values())
    return jsonify(ok=True, k1s=payload["n"], lines=lines, k1s_total=handoff.info(payload.get("owner") or None)["k1s"])


@bp.route("/handoff/clear", methods=["POST"])
def handoff_clear():
    d = request.get_json(force=True, silent=True) or {}
    handoff.clear(owner=d.get("owner") or None)
    return jsonify(ok=True, **handoff.info(d.get("owner") or None))


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
    handoff.init(Path(app.root_path) / "_work")
    app.register_blueprint(bp)
