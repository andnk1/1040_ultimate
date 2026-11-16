"""The AI tab (step tab 3, name from ai_settings.json) - spec: design/ai_requests.md.

register(app, run, inventory_rows) adds the routes. Nothing is sent before the preparer clicks Send; a Send runs in a
background thread (a call can take minutes) and the page polls it. A failed call changes nothing: only a successful
reply is kept (r["ai"]["last"][request]).
"""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path

from flask import jsonify, render_template, request

from . import client, docs, settings

NOT_SENT = ""                  # the dropdown's "- not sent -"
JOBS: dict = {}                # job id -> {token, request, started, done, result}
_LOCK = threading.Lock()


def _state(r) -> dict:
    return r.setdefault("ai", {"choice": {}, "last": {}, "error": {}})


def _ai_pages(r) -> dict:
    """{path: [page numbers]} - long PDFs send only their AI pages (the inventory's list)."""
    return {x["path"]: x["ai_page_list"] for x in (r.get("inv") or {}).get("docs") or [] if x.get("ai_page_list")}


def ai_documents(r, inventory_rows) -> list[dict]:
    """The documents ticked AI on the inventory, in inventory order: {key, num, name, path, type, sent, problem, request}."""
    to_ai, st = r.get("to_ai") or {}, _state(r)
    pages = _ai_pages(r)
    out = []
    py = (r.get("form") or {}).get("pyret")
    if py and to_ai.get(py):
        out.append(dict(key="pyret", num="PY", name=Path(py).name, path=py, type="Prior Year return"))
    n = 0
    for d in inventory_rows(r):
        if d.get("free"):
            continue
        n += 1
        if to_ai.get(d["path"]):
            out.append(dict(key=d["key"], num=n, name=d["file"], path=d["path"], type=d.get("type") or ""))
    for d in out:
        d["pages"] = pages.get(d["path"])
        d.update(docs.plan(d["path"], d["pages"]))
        default = NOT_SENT if d["key"] == "pyret" else "schedule_e"
        d["request"] = st["choice"].get(d["key"], default)
    return out


def _template_props(r) -> list:
    from core.sche_template import template_rows
    return template_rows(r.get("sche") or [])


def groups(r, documents) -> list[dict]:
    """One box per request that has documents: {key, label, model, docs, problems, template: [short addresses] | None}."""
    cfg = settings.load()
    out = []
    for t in settings.request_types(cfg):
        ds = [d for d in documents if d["request"] == t["key"]]
        if not ds or t["coming"]:
            continue
        problems = []
        if not settings.instructions_path(t).is_file():
            problems.append(f"The request file ai_requests\\{t['file']} is missing.")
        if not t["model"]:
            problems.append(f"No model for this request in ai_settings.json (requests → {t['key']} → model).")
        problems += [f"Document {d['num']} ({d['name']}): {d['problem']}." for d in ds if d["problem"]]
        g = dict(key=t["key"], label=t["label"], model=t["model"], effort=t["effort"], docs=ds, problems=problems, template=None)
        if t["attach"] == "schedule_e_template":
            g["template"] = [x["short"] for x in _template_props(r)]
        out.append(g)
    return out


def build_content(r, documents, rq) -> list[dict]:
    """The user message: each document (label + content), the attachment, one closing line."""
    blocks = []
    for d in documents:
        blocks += docs.blocks_for(d)
    if rq["attach"] == "schedule_e_template":
        rows = _template_props(r)
        text = docs.schedule_e_template_text(rows)
        blocks.append({"type": "text", "text": "Schedule E template (attached by the app"
                       + ("" if rows else " - no properties on the return, so it is blank") + ")\n\n" + text})
    blocks.append({"type": "text", "text": f"Request: {rq['label']}. Reply in the format given in your instructions."})
    return blocks


def _job(job_id, r, documents, rq):
    try:
        content = build_content(r, documents, rq)
        res = client.send(rq["key"], content, len(documents))
    except Exception as e:  # noqa: BLE001 - reading a document failed: report it, change nothing
        res = dict(ok=False, error_type="document", error=f"Couldn't prepare the documents: {type(e).__name__}: {e}", text="")
    st = _state(r)
    if res.get("ok"):
        st["last"][rq["key"]] = dict(res, documents=[dict(num=d["num"], name=d["name"]) for d in documents])
        st["error"].pop(rq["key"], None)
    else:
        st["error"][rq["key"]] = res
    with _LOCK:
        JOBS[job_id].update(done=True, result=dict(ok=res.get("ok"), error=res.get("error"), error_type=res.get("error_type")))


def register(app, run, inventory_rows):
    app.jinja_env.globals["AI_TAB_NAME"] = settings.tab_name()

    @app.route("/ai/<token>")
    def ai_requests(token):
        r = run(token)
        app.jinja_env.globals["AI_TAB_NAME"] = settings.tab_name()
        documents = ai_documents(r, inventory_rows)
        st = _state(r)
        running = {j["request"]: jid for jid, j in JOBS.items() if j["token"] == token and not j["done"]}
        return render_template("ai_requests.html", token=token, tab=settings.tab_name(), docs=documents,
                               types=settings.request_types(), groups=groups(r, documents), last=st["last"], errors=st["error"],
                               running=running, has_key=bool(settings.api_key()), no_key_msg=settings.NO_KEY_MSG)

    @app.route("/ai/<token>/choice", methods=["POST"])
    def ai_choice(token):
        r = run(token)
        j = request.get_json(force=True, silent=True) or {}
        valid = {t["key"] for t in settings.request_types() if not t["coming"]} | {NOT_SENT}
        if str(j.get("request", "")) in valid:
            _state(r)["choice"][str(j.get("key"))] = str(j.get("request", ""))
        return jsonify(ok=True)

    @app.route("/ai/<token>/send", methods=["POST"])
    def ai_send(token):
        r = run(token)
        key = str((request.get_json(force=True, silent=True) or {}).get("request") or "")
        rq = settings.request_type(key)
        if not rq or rq["coming"]:
            return jsonify(error="Unknown request.")
        if not settings.api_key():
            return jsonify(error=settings.NO_KEY_MSG)
        documents = [d for d in ai_documents(r, inventory_rows) if d["request"] == key]
        g = next((x for x in groups(r, documents) if x["key"] == key), None)
        if not documents or not g:
            return jsonify(error="No documents for this request.")
        if g["problems"]:
            return jsonify(error=" ".join(g["problems"]))
        with _LOCK:
            jid = next((i for i, j in JOBS.items() if j["token"] == token and j["request"] == key and not j["done"]), None)
            if not jid:
                jid = uuid.uuid4().hex[:10]
                JOBS[jid] = dict(token=token, request=key, started=time.time(), done=False, result=None)
                threading.Thread(target=_job, args=(jid, r, documents, rq), daemon=True).start()
        return jsonify(job=jid)

    @app.route("/ai/<token>/job/<jid>")
    def ai_job(token, jid):
        run(token)
        j = JOBS.get(jid)
        if not j or j["token"] != token:
            return jsonify(error="This call is no longer known (the program was restarted)."), 404
        return jsonify(done=j["done"], seconds=round(time.time() - j["started"]), result=j["result"])
