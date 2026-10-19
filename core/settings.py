"""settings.py - office-specific values kept OUT of the code (and out of GitHub).

local_settings.json (next to app.py, listed in .gitignore) holds them; local_settings.example.json shows the format.
Without the file the program still runs: no always-masked numbers, dialogs open in Return_Info.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
_FILE = HERE / "local_settings.json"


def _load() -> dict:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


S = _load()
ALWAYS_MASK: list[str] = [str(x) for x in S.get("always_mask", [])]               # masked on every document
START_FOLDERS: list[str] = [str(x) for x in S.get("start_folders", [])]           # where the file dialogs open
