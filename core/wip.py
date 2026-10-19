"""wip.py - the client's work in progress, saved as a JSON file in the client folder.

Saved next to the Karbon letter (else the prior-year return; else a folder the preparer picks), as
"1040 Ultimate WIP <year> - <client>.json". Autosaved on every change. The first save of a session keeps the
file as it was as "<name>.bak", so one bad session can't wipe earlier work.
Holds only the preparer's work + the file paths - the documents are read again when the client is opened.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

VERSION = 1
PATTERN = "1040 Ultimate WIP*.json"
# run keys that are the preparer's work
KEYS = ["edits", "added", "schc", "sche", "ut", "marks", "to_ai", "invstate", "comments", "checklist"]


def client_name(form: dict, docs: list | None = None) -> str:
    """The client folder's name (where the Karbon letter / prior-year return / documents sit)."""
    for p in [form.get("karbon"), form.get("pyret"), form.get("utscreens")] + list(docs or []):
        if p:
            return Path(p).parent.name or "Client"
    return "Client"


def default_folder(form: dict) -> str | None:
    for k in ("karbon", "pyret"):
        if form.get(k):
            return str(Path(form[k]).parent)
    return None


def find(folder: str | None) -> dict | None:
    """The newest WIP file in a folder: {path, saved, client, file}."""
    if not folder or not Path(folder).is_dir():
        return None
    hits = sorted(Path(folder).glob(PATTERN), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in hits:
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        return dict(path=str(p), file=p.name, saved=j.get("saved", ""), client=j.get("client", ""))
    return None


def load(path: str) -> dict:
    j = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(j, dict) or "form" not in j:
        raise ValueError("not a 1040 Ultimate work-in-progress file")
    return j


def relink(paths: list, folder: str) -> tuple[list, list]:
    """Documents that moved: look for the same file name under the WIP folder. Returns (paths, moved notes)."""
    missing = [p for p in paths if p and not Path(p).is_file()]
    if not missing or not folder or not Path(folder).is_dir():
        return paths, []
    names = {}
    for root, dirs, files in os.walk(folder):
        if root.count(os.sep) - folder.count(os.sep) > 3:
            dirs[:] = []
            continue
        for f in files:
            names.setdefault(f.lower(), os.path.join(root, f))
    out, notes = [], []
    for p in paths:
        if p and not Path(p).is_file() and Path(p).name.lower() in names:
            q = names[Path(p).name.lower()]
            notes.append(f"{Path(p).name}: moved — found in {Path(q).parent}")
            out.append(q)
        else:
            out.append(p)
    return out, notes


def snapshot(r: dict) -> dict:
    return dict(app="1040 Ultimate", version=VERSION, saved=datetime.now().strftime("%Y-%m-%d %H:%M"),
                client=r.get("client") or client_name(r["form"], r.get("docs")), cy_year=r.get("cy_year"),
                form=r["form"], docs=r.get("doc_list") or [{"path": p, "on": True} for p in r.get("docs") or []],
                cy_path=r.get("cy_path") or "", ut_path=r.get("ut_path") or "",
                **{k: r.get(k) for k in KEYS})


def save(r: dict) -> str | None:
    """Writes the WIP file (if it has a place). Returns the path or None."""
    path = r.get("wip_path")
    if not path:
        return None
    p = Path(path)
    if not r.get("wip_bak_done"):
        if p.is_file():
            try:
                shutil.copy2(p, p.with_suffix(".bak"))
            except OSError:
                pass
        r["wip_bak_done"] = True
    tmp = p.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(snapshot(r), indent=1, default=str), encoding="utf-8")
        os.replace(tmp, p)
    except OSError as e:
        r["wip_error"] = f"Couldn't save the work in progress: {e}"
        return None
    r["wip_error"], r["wip_saved"] = None, datetime.now().strftime("%H:%M")
    return str(p)


def new_path(folder: str, r: dict) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', " ", r.get("client") or "Client").strip()
    return str(Path(folder) / f"1040 Ultimate WIP {r.get('cy_year') or ''} - {name}.json".replace("  ", " "))
