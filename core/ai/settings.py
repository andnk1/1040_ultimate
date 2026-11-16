"""AI settings: ai_settings.json (repo root, plain JSON, no secrets) and the API key from .env (git-ignored).

Read fresh on every use, so a change to ai_settings.json counts on the next screen / Send (restarting is not needed).
The key is never printed, logged or shown - only whether it is there.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS_FILE = ROOT / "ai_settings.json"
ENV_FILE = ROOT / ".env"
REQ_DIR = ROOT / "ai_requests"          # one <name>.md per request type: instructions + reply format
LOG_DIR = ROOT / "AI_logs"              # never wiped, goes to GitHub - no client data
WORK_DIR = ROOT / "_work" / "ai"        # full request + raw reply for debugging (wiped at every start)

DEFAULTS = {"tab_name": "AI Doc Review", "max_tokens": 32000, "timeout_seconds": 600,
            "max_retries": 2, "requests": {}, "prices": {}}


def load() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in data.items() if not k.startswith("_")})
    return out


def tab_name() -> str:
    return str(load().get("tab_name") or DEFAULTS["tab_name"])


def request_types(cfg: dict | None = None) -> list[dict]:
    """[{key, label, coming, model, effort, file, attach, max_tokens, timeout_seconds}] in the settings' order."""
    cfg = cfg or load()
    out = []
    for key, rq in (cfg.get("requests") or {}).items():
        rq = dict(rq or {})
        out.append(dict(key=key, label=rq.get("label") or key, coming=bool(rq.get("coming")), model=rq.get("model") or "",
                         effort=rq.get("effort") or "", file=rq.get("file") or f"{key}.md", attach=rq.get("attach") or "",
                         max_tokens=int(rq.get("max_tokens") or cfg.get("max_tokens") or DEFAULTS["max_tokens"]),
                         timeout_seconds=float(rq.get("timeout_seconds") or cfg.get("timeout_seconds") or DEFAULTS["timeout_seconds"])))
    return out


def request_type(key: str, cfg: dict | None = None) -> dict | None:
    return next((t for t in request_types(cfg) if t["key"] == key), None)


def instructions_path(rq: dict) -> Path:
    return REQ_DIR / rq["file"]


def api_key() -> str | None:
    """ANTHROPIC_API_KEY from .env in the app folder (else from the environment). None when missing / empty."""
    try:
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k.strip() == "ANTHROPIC_API_KEY":
                v = v.strip().strip('"').strip("'")
                if v:
                    return v
    except OSError:
        pass
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip() or None


NO_KEY_MSG = (f"No API key. Create the file .env in the app folder ({ROOT}) - copy .env.example - and put the key after "
              "ANTHROPIC_API_KEY= (no quotes, no spaces). Then click Send again.")
