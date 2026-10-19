"""karbon.py - read a Karbon "Client Request Summary" (client organizer) PDF.

Layout (one block per question):
    <question text>
    Due <date>
    <help text>
    <activity log: "... changed the status/due date ...">
    <avatar letter>            <- only when the client answered
    <client name>
    <answer lines>
    <timestamp "Thursday, June 4, 2026 3:08:32 PM">
Returns every question with its answer; the summary shows only the answered ones whose answer isn't "No".
"""
from __future__ import annotations

import re

from .pdfutil import open_pdf, page_text

DAY = r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
TS = re.compile(rf"^{DAY},\s+\w+\s+\d{{1,2}},\s+\d{{4}}\s+\d{{1,2}}:\d{{2}}:\d{{2}}\s*(AM|PM)$")
DUE = re.compile(rf"^Due\s+{DAY},")
DUE_ANY = re.compile(rf"\bDue\s+{DAY},")
LOG = re.compile(r"changed the (status|due date)|^Automator\b|^Reminder sent|^Request (sent|re-?sent)|uploaded|^Attachment")
TS_TAIL = re.compile(rf"\s*{DAY},\s+\w+\s+\d{{1,2}},\s+\d{{4}}\s+\d{{1,2}}:\d{{2}}:\d{{2}}\s*(AM|PM)\s*$")
ACTOR = re.compile(r"^(.{2,60}?)\s+(changed|sent|uploaded|created|completed|reopened|assigned|added|removed)\b")
NO_ANSWERS = {"no", "no.", "nope", "n", "no thanks", "none", "no change", "no changes"}


def is_karbon(text: str) -> bool:
    return "Client Request Summary" in text and "Client Organizer" in text


def read_karbon(path) -> dict:
    doc, _ = open_pdf(path)
    with doc:
        text = "\n".join(page_text(doc, i) for i in range(len(doc)))
    head = text.split("Client Organizer", 1)[0]
    m = re.search(r"Tax:\s*(.+)", head)
    title = m.group(1).strip() if m else ""
    lines = []
    for l in text.splitlines():
        l = l.strip()
        m = DUE_ANY.search(l)
        if m and m.start() > 0:             # "Did your marital status change?   Due Wednesday, June 10, ..." on one line
            lines += [l[:m.start()].strip(), l[m.start():].strip()]
        else:
            lines.append(l)
    start = next((i + 1 for i, l in enumerate(lines) if l == "Custom Reminders"), None)
    if start is None:
        start = next((i + 1 for i, l in enumerate(lines) if l == "Client Organizer"), 0)
    qs, buf = [], []
    i = start
    while i < len(lines):
        l = lines[i]
        if DUE.match(l):
            q = dict(question=" ".join(x for x in buf if x and not LOG.search(x)).strip(), due=l[4:], help="",
                     answer=None, who="", when="")
            buf = []
            i += 1
            help_ = []
            while i < len(lines) and not LOG.search(lines[i]) and not DUE.match(lines[i]):
                if lines[i]:
                    help_.append(lines[i])
                i += 1
            while i < len(lines) and (LOG.search(lines[i]) or not lines[i]):
                i += 1
            # answer block: avatar letter, name, answer lines, timestamp
            j = i
            if j + 1 < len(lines) and re.fullmatch(r"[A-Z]{1,2}", lines[j]):
                k = j + 2
                ans = []
                while k < len(lines) and not TS.match(lines[k]) and not DUE.match(lines[k]):
                    ans.append(lines[k])
                    k += 1
                if k < len(lines) and TS.match(lines[k]):
                    q.update(answer="\n".join(a for a in ans if a).strip(), who=lines[j + 1], when=lines[k])
                    i = k + 1
            if q["answer"] is None and help_:
                # unanswered: the help text may actually be the start of the next question - keep it as help
                pass
            q["help"] = " ".join(help_)
            qs.append(q)
            continue
        if TS.match(l):
            buf = []
        elif l and not LOG.search(l):
            buf.append(l)
        i += 1
    # the client's answer is the pink bubble - wherever it sits between the log lines
    try:
        by_color = _answers_by_color(path, len(qs))
    except Exception:  # noqa: BLE001
        by_color = None
    if by_color is not None:
        for q, a in zip(qs, by_color):
            q["answer"] = clean_answer(a, q.get("who", ""))
        source = "pink answer bubbles"
    else:
        source = "text layout"
        for q in qs:
            q["answer"] = clean_answer(q["answer"], q.get("who", ""))
    return dict(title=title, questions=qs, source=source)


PINK = (0.988, 0.941, 0.957)          # the client's answer bubble


def _is_pink(c) -> bool:
    """Light pink fill (Karbon's answer bubble): red near full, green / blue a little lower - not grey, not white."""
    if not c or len(c) < 3:
        return False
    r, g, b = c[:3]
    return r > 0.95 and 0.85 < g < 0.975 and 0.85 < b < 0.99 and r - g > 0.02


def _bubbles_and_dues(doc):
    """Pink answer bubbles and 'Due ...' lines, in reading order: [(page, y, kind, text)]."""
    out = []
    for pi, page in enumerate(doc):
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = "".join(sp["text"] for sp in l["spans"]).strip()
                if DUE_ANY.search(t):
                    out.append((pi, l["bbox"][1], "due", t))
        for dr in page.get_drawings():
            if not _is_pink(dr.get("fill")):
                continue
            r = dr["rect"]
            parts = []
            for b in page.get_text("dict", clip=r)["blocks"]:
                for l in b.get("lines", []):
                    line = "".join(sp["text"] for sp in l["spans"]
                                   if not re.search(r"Medium|Bold|Semi|Heavy", sp.get("font", ""), re.I)   # name is in the heavier font
                                   and r.contains(((sp["bbox"][0] + sp["bbox"][2]) / 2, (sp["bbox"][1] + sp["bbox"][3]) / 2)))
                    if line.strip():
                        parts.append(line.strip())
            out.append((pi, r.y0, "answer", "\n".join(parts)))
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def _answers_by_color(path, n_questions: int):
    """Answer per question from the pink bubbles (None when the PDF has no pink bubbles at all)."""
    doc, _ = open_pdf(path)
    with doc:
        items = _bubbles_and_dues(doc)
    if not any(k == "answer" for _, _, k, _ in items):
        return None
    answers, qi = [None] * n_questions, -1
    for _, _, kind, text in items:
        if kind == "due":
            qi += 1
        elif 0 <= qi < n_questions and text:
            answers[qi] = (answers[qi] + "\n" + text) if answers[qi] else text
    return answers


def clean_answer(text: str | None, who: str = "") -> str | None:
    """Keeps only what the client wrote: drops Karbon's activity log ("X changed the status ... PM"),
    avatar letters, timestamps and the client's name in front of the answer."""
    if text is None:
        return None
    names = {who.strip()} if who and who.strip() else set()
    keep = []
    for l in text.splitlines():
        l = l.strip()
        if not l:
            continue
        if LOG.search(l) or re.search(r"\bchanged the\b", l):
            m = ACTOR.match(l)
            if m and m.group(1) not in ("Automator",):
                names.add(m.group(1).strip())
            continue
        if re.fullmatch(r"[A-Z]{1,2}", l) or TS.match(l):
            continue
        keep.append(TS_TAIL.sub("", l).strip())
    out = []
    for l in keep:
        for n in sorted(names, key=len, reverse=True):
            if n and l.lower().startswith(n.lower()):
                l = l[len(n):].lstrip(" :-,")
                break
        if l:
            out.append(l)
    return "\n".join(out)


def answered(k: dict) -> list[dict]:
    """Questions with an answer that isn't 'No'."""
    out = []
    for q in k.get("questions", []):
        a = (q.get("answer") or "").strip()
        if not a or a.lower().strip(" .!") in NO_ANSWERS:
            continue
        out.append(q)
    return out
