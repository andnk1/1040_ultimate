"""send() - the ONE place in the app that calls the Claude API. Every request type goes through it.

A request type is a file, not code: ai_requests/<name>.md holds the instructions and the reply format (the system prompt);
its model, effort, reply size and timeout are in ai_settings.json. Adding a request type never changes this function.

The caller gives the user-message content (document blocks + labels, built by docs.py). send() returns a plain dict and
never raises: {ok, error_type, error, text, model, input_tokens, output_tokens, cost, stop_reason, seconds}.
Every call (success or not) adds one line to the cost log; the full request and the raw reply go to _work/ai (debugging).
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime

from . import logs, settings

# error types (also the "result" column of the cost log)
ERRORS = {
    "no_key": "No API key.",
    "no_sdk": "The Claude API library isn't installed - restart run.bat (it installs it).",
    "no_request_file": "The request file is missing.",
    "bad_key": "The API key was refused (check the key in .env).",
    "no_access": "This API key isn't allowed to use this model or feature.",
    "model_not_found": "The model in ai_settings.json wasn't found - check its name.",
    "rate_limit": "Too many requests or tokens right now (rate limit) - wait a minute and try again.",
    "overloaded": "The API is busy or had a server error - try again in a few minutes.",
    "too_large": "The request is too large (too many pages / documents in one call) - send fewer documents.",
    "bad_request": "The API refused the request.",
    "api_error": "The API returned an error.",
    "no_internet": "Couldn't reach the API - check the internet connection.",
    "timeout": "No complete reply within the time limit (timeout_seconds in ai_settings.json).",
    "cut_off": "The reply was cut off at the maximum reply size (max_tokens in ai_settings.json) - nothing was used.",
    "declined": "The AI declined this request.",
    "not_json": "The reply is not valid JSON - nothing was used.",
    "empty": "The reply was empty.",
}


class _Overtime(Exception):
    pass


def parse_json(text: str):
    """The reply as JSON (an object), or None. A ```json fence around it is tolerated."""
    t = (text or "").strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", t, re.S)
    if m:
        t = m.group(1)
    try:
        v = json.loads(t)
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def _debug_save(stamp: str, key: str, params: dict, text: str, meta: dict) -> None:
    """_work/ai/<time>_<request>_request.json (PDF data left out) + _reply.txt. Wiped at every start."""
    try:
        settings.WORK_DIR.mkdir(parents=True, exist_ok=True)

        def strip(b):
            if isinstance(b, dict) and isinstance(b.get("source"), dict) and b["source"].get("type") == "base64":
                return dict(b, source=dict(b["source"], data=f"<{len(b['source'].get('data') or '')} base64 characters>"))
            return b
        p = dict(params, messages=[dict(m, content=[strip(b) for b in m["content"]]) for m in params.get("messages", [])])
        (settings.WORK_DIR / f"{stamp}_{key}_request.json").write_text(json.dumps(p, indent=1, ensure_ascii=False), encoding="utf-8")
        (settings.WORK_DIR / f"{stamp}_{key}_reply.txt").write_text(
            json.dumps(meta, ensure_ascii=False) + "\n\n" + (text or ""), encoding="utf-8")
    except OSError:
        pass


def send(request_key: str, content: list[dict], n_documents: int) -> dict:
    """Sends one request: system = the request file, user = content. Returns the result dict (see the module doc)."""
    cfg = settings.load()
    rq = settings.request_type(request_key, cfg) or {}
    model = rq.get("model") or ""
    res = dict(ok=False, error_type="", error="", text="", model=model, request=request_key, input_tokens=0, output_tokens=0,
               cost=None, stop_reason="", seconds=0.0, at=datetime.now().strftime("%Y-%m-%d %H:%M"))

    def fail(kind, detail=""):
        res.update(error_type=kind, error=ERRORS.get(kind, kind) + (f" ({detail})" if detail else ""))
        logs.cost_line(request_key, model, n_documents, res["input_tokens"], res["output_tokens"], res["cost"], kind)
        return res

    path = settings.instructions_path(rq) if rq else None
    if not rq or rq.get("coming") or not path.is_file():
        return fail("no_request_file", f"ai_requests\\{rq.get('file') or request_key + '.md'}")
    key = settings.api_key()
    if not key:
        res.update(error_type="no_key", error=settings.NO_KEY_MSG)
        logs.cost_line(request_key, model, n_documents, 0, 0, None, "no_key")
        return res
    try:
        import anthropic
    except ImportError:
        return fail("no_sdk")

    params = dict(model=model, max_tokens=rq["max_tokens"], system=path.read_text(encoding="utf-8"),
                  messages=[{"role": "user", "content": content}])
    if rq.get("effort"):
        params["output_config"] = {"effort": rq["effort"]}
    stamp = datetime.now().strftime("%H%M%S_%f")[:-3]
    t0 = time.monotonic()
    deadline = t0 + rq["timeout_seconds"]
    client = anthropic.Anthropic(api_key=key, timeout=rq["timeout_seconds"], max_retries=int(cfg.get("max_retries", 2)))
    msg = None
    try:
        # streaming: a long reply never hits an HTTP time limit; the loop enforces the total time limit
        with client.messages.stream(**params) as stream:
            for _ in stream:
                if time.monotonic() > deadline:
                    raise _Overtime()
            msg = stream.get_final_message()
    except (_Overtime, anthropic.APITimeoutError):
        kind, detail = "timeout", f"{rq['timeout_seconds']:.0f} seconds"
    except anthropic.AuthenticationError:
        kind, detail = "bad_key", ""
    except anthropic.PermissionDeniedError as e:
        kind, detail = "no_access", e.message
    except anthropic.NotFoundError:
        kind, detail = "model_not_found", model
    except anthropic.RateLimitError:
        kind, detail = "rate_limit", ""
    except anthropic.BadRequestError as e:
        kind, detail = ("too_large" if "too large" in str(e.message).lower() or "too long" in str(e.message).lower()
                        else "bad_request"), e.message
    except anthropic.APIStatusError as e:
        kind, detail = ("too_large", "") if e.status_code == 413 else ("overloaded", f"HTTP {e.status_code}") \
            if e.status_code >= 500 else ("api_error", f"HTTP {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        kind, detail = "no_internet", ""
    except Exception as e:  # noqa: BLE001 - never let a call stop the app
        kind, detail = "api_error", f"{type(e).__name__}: {e}"
    res["seconds"] = round(time.monotonic() - t0, 1)
    if msg is None:
        _debug_save(stamp, request_key, params, "", dict(error=kind, detail=detail))
        return fail(kind, detail)

    u = msg.usage
    res.update(input_tokens=(u.input_tokens or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0)
               + (getattr(u, "cache_creation_input_tokens", 0) or 0),
               output_tokens=u.output_tokens or 0, stop_reason=msg.stop_reason or "", model=msg.model or model)
    res["cost"] = logs.estimate_cost(model, res["input_tokens"], res["output_tokens"], cfg)
    res["text"] = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    _debug_save(stamp, request_key, params, res["text"], dict(stop_reason=res["stop_reason"], input_tokens=res["input_tokens"],
                                                               output_tokens=res["output_tokens"], seconds=res["seconds"]))
    if msg.stop_reason == "max_tokens":
        return fail("cut_off", f"{rq['max_tokens']:,} tokens")
    if msg.stop_reason == "refusal":
        det = getattr(msg, "stop_details", None)
        return fail("declined", getattr(det, "explanation", "") or getattr(det, "category", "") or "")
    if not res["text"].strip():
        return fail("empty")
    if parse_json(res["text"]) is None:
        return fail("not_json")
    res["ok"] = True
    logs.cost_line(request_key, model, n_documents, res["input_tokens"], res["output_tokens"], res["cost"], "ok")
    return res
