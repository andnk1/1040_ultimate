"""AI_logs - one CSV line per call (cost log). Goes to GitHub, so NO client data: no names, addresses, file names,
document text or reply text - only date, request type, model, counts, tokens, cost and the result."""
from __future__ import annotations

import csv
from datetime import datetime

from . import settings

COST_LOG = "cost_log.csv"
COST_COLS = ["date_time", "request_type", "model", "documents", "input_tokens", "output_tokens", "estimated_cost_usd", "result"]


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cfg: dict | None = None) -> float | None:
    """US$ from ai_settings.json prices ([input, output] per million tokens). None when the model has no price there."""
    p = ((cfg or settings.load()).get("prices") or {}).get(model)
    if not p or len(p) < 2:
        return None
    return round((input_tokens or 0) * float(p[0]) / 1e6 + (output_tokens or 0) * float(p[1]) / 1e6, 4)


def cost_line(request_type: str, model: str, documents: int, input_tokens: int, output_tokens: int, cost, result: str) -> None:
    """Appends one line (creates the file with its header the first time). A log problem never stops the call."""
    try:
        settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = settings.LOG_DIR / COST_LOG
        new = not path.is_file()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(COST_COLS)
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), request_type, model, documents, input_tokens or 0,
                        output_tokens or 0, "" if cost is None else f"{cost:.4f}", result])
    except OSError:
        pass
