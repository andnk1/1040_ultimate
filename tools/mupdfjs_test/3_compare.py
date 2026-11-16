"""Step 3 - compare what the two engines saw, page by page.
Run:  python 3_compare.py
Prints SAME / DIFFERENT per PDF and the first differences, and writes compare_report.txt.
SAME on every file = the readers will give the same answers in the browser.
"""
import difflib, json
from pathlib import Path

here = Path(__file__).parent
a = json.loads((here / "pymupdf.json").read_text(encoding="utf-8"))
b = json.loads((here / "mupdfjs.json").read_text(encoding="utf-8"))
TOL = 0.6                                                  # points; word positions closer than this count as equal
rep = [f"Today:   {a['engine']}", f"Browser: {b['engine']}", ""]
n_same = n_diff = 0


def same_word(x, y):
    return x[4] == y[4] and all(abs(x[i] - y[i]) <= TOL for i in range(4))


for f, fa in a["files"].items():
    fb = b["files"].get(f, {"error": "missing"})
    if "error" in fa or "error" in fb:
        rep.append(f"SKIPPED    {f}: today={fa.get('error', 'ok')} / browser={fb.get('error', 'ok')}")
        continue
    notes = []
    if len(fa["pages"]) != len(fb["pages"]):
        notes.append(f"  page count {len(fa['pages'])} vs {len(fb['pages'])}")
    for i, (pa, pb) in enumerate(zip(fa["pages"], fb["pages"]), 1):
        if pa["text"] != pb["text"]:
            d = [l for l in difflib.unified_diff(pa["text"].splitlines(), pb["text"].splitlines(), "today", "browser", n=0, lineterm="")
                 if l[:1] in "+-" and not l.startswith(("+++", "---"))][:6]
            notes.append(f"  page {i} TEXT differs:\n      " + "\n      ".join(map(repr, d)))
        wa, wb = pa["words"], pb["words"]
        bad = [k for k in range(min(len(wa), len(wb))) if not same_word(wa[k], wb[k])]
        if len(wa) != len(wb) or bad:
            k = bad[0] if bad else min(len(wa), len(wb))
            notes.append(f"  page {i} WORDS differ: {len(wa)} vs {len(wb)} words; first at #{k}: "
                         f"{wa[k] if k < len(wa) else '-'}  vs  {wb[k] if k < len(wb) else '-'}")
    if notes:
        n_diff += 1
        rep.append(f"DIFFERENT  {f}")
        rep += notes[:8] + (["  ..."] if len(notes) > 8 else [])
    else:
        n_same += 1
        rep.append(f"SAME       {f}")
rep += ["", f"RESULT: {n_same} same, {n_diff} different"]
(here / "compare_report.txt").write_text("\n".join(rep), encoding="utf-8")
print("\n".join(rep))
