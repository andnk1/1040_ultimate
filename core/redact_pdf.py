#!/usr/bin/env python3
"""
redact_pdf.py — True PDF redaction (no rasterization)

COPY for 1040 Ultimate (adapted from C:\\dev\\PDF_Mask\\redact_pdf.py v1.10.0):
  - an SSN typed in a person tab is masked in any format, but the last 4 digits stay visible (as with auto-detection)
  - the line above a masked ZIP is masked only when it looks like a street address (payer names stay)
  - never prompts for a password (runs inside the web app)

SETUP:
    pip install pymupdf

AUTO-DETECTION (no user input needed):
    - SSN:  XXX-XX-#### format → masks XXX-XX, shows last 4
    - State abbreviation + 5-digit ZIP → masks ZIP, keeps state abbrev
    - NO other number patterns are auto-detected

USER-ENTERED (interactive prompt or flags):
    - SSN (any format)   → full mask
    - EIN as XX-XXXXXXX  → hunts for that exact 7-digit suffix only
                           (not random 7-digit sequences)
    - Names              → masked wherever found
    - Addresses          → masked wherever found
    - Phone numbers      → masked wherever found
    - Other free text    → masked wherever found

K-1 MASKING INPUT (optional):
    If Input\\k1_mask_input.json exists (written by k1_summary.py), its values are
    shown and — after you confirm — added to the values you type: K-1 EINs,
    partner/shareholder last names (first name kept), and the full addresses
    (street, "City, ST", ZIP) of the partner and the partnership / S corp.
    Its PDF passwords are used to open protected K-1s. Skip it with --no-k1.
    It is looked for next to the PDFs being masked, then in the Input folder next to
    this script — so  python redact_pdf.py "K-1 Forms"  uses Input\\k1_mask_input.json.

PASSWORD-PROTECTED PDFs (same rules as k1_summary.py), tried in order:
    1. password saved for that file in k1_mask_input.json
    2. text after "PW" in the file name ("... PW-2400.pdf" -> 2400)
    3. every other 4+ character letter/digit chunk of the file name
    4. --passwords a,b,c
    5. typed at a prompt (when run in a window); otherwise the file is skipped

USAGE:
    python redact_pdf.py "C:\\dev\\PDF_Mask\\Input"
    python redact_pdf.py "C:\\path\\to\\return.pdf"
    python redact_pdf.py   # defaults to Input subfolder next to script
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

__version__ = "1.10.0"

try:
    import pymupdf
except ImportError:
    print("PyMuPDF isn't installed. Run:  pip install pymupdf", file=sys.stderr)
    sys.exit(1)


# ── US STATE / TERRITORY ABBREVIATIONS ─────────────────────────────────────
US_STATE_ABBR = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY",
    "DC", "PR", "VI", "GU", "AS", "MP",
}
# Matches "FL 32084" or "NY 10001-1234" — state abbr + ZIP only
STATE_ZIP_RE = re.compile(
    r"\b(" + "|".join(sorted(US_STATE_ABBR)) + r")\s+(\d{5})(-\d{4})?\b"
)

# SSN auto-detection: must have XXX-XX-#### format with dashes/en-dash/em-dash
# Masks the first 5 digits (XXX-XX), leaves the last 4 visible.
SSN_AUTO_RE = re.compile(
    r"\b(\d{3}[-\u2013\u2014]\d{2})([-\u2013\u2014]\d{4})\b"
)
STREET_RE = re.compile(r"^\s*\d+[A-Za-z]?\s+\S|\bP\.?\s?O\.?\s*BOX\b|\b(ST|STREET|AVE|AVENUE|RD|ROAD|DR|DRIVE|LN|LANE|BLVD|"
                       r"BOULEVARD|WAY|CT|COURT|PL|PLACE|HWY|HIGHWAY|PKWY|PARKWAY|CIR|CIRCLE|TER|TRL|STE|SUITE|APT|UNIT|CALLE|URB)\b\.?", re.I)
# Space-separated form printed on some 1040s: "123 45 6789"
SSN_SPACE_RE = re.compile(r"(?<![\d,.$])(\d{3}\s\d{2})(\s\d{4})(?![\d,.])")
# Also catch already-partially-masked: ***-**-####
SSN_MASKED_RE = re.compile(r"\*{3}[-\u2013\u2014]\*{2}[-\u2013\u2014]\d{4}")


# ── LABEL-DRIVEN FIELDS ─────────────────────────────────────────────────────
LABEL_FIELDS = [
    {"key": "name", "re": re.compile(r"^(Taxpayer'?s?\s+name|name\s+of\s+taxpayer)\s*:?$", re.I)},
    {"key": "ssn",  "re": re.compile(
        r"^(Taxpayer'?s?\s+)?(Social\s+Security\s+(Number|No\.?)|SSN|SS\s*#)\s*#?\s*:?$", re.I
    )},
    {"key": "address", "re": re.compile(r"^State$", re.I),
     "value_re": re.compile(r"^[A-Za-z]{2}$")},
    {"key": "address", "re": re.compile(r"^ZIP\s*code$", re.I),
     "value_re": re.compile(r"^\d{5}(-\d{4})?$")},
    {"key": "address", "re": re.compile(r"^City,?\s*town,?\s*or\s*post\s*office\b", re.I)},
    {"key": "address", "re": re.compile(
        r"^Foreign\s+province\s*[/,]?\s*state\s*[/,]?\s*(or\s*)?county\b", re.I)},
    {"key": "address", "re": re.compile(r"^Foreign\s+postal\s+code$", re.I)},
]

CAT_KEYS = {"ssn", "name", "address", "employer", "phone", "email", "financial"}
DEFAULT_ON = {"ssn", "name", "address", "employer", "phone", "email"}

_EMPLOYER_SUFFIX_RE = re.compile(r"^(LLC|Inc\.?|Corp\.?|Ltd\.?|LLP|PLLC|PA|DBA)[.,;:]?$")


def _group_lines(words):
    lines = defaultdict(list)
    for w in words:
        x0, y0, x1, y1, text, block_no, line_no, word_no = w
        lines[(block_no, line_no)].append(w)
    for key in lines:
        lines[key].sort(key=lambda w: w[0])
    return lines


def _line_bounds(line_words):
    return (
        min(w[0] for w in line_words), min(w[1] for w in line_words),
        max(w[2] for w in line_words), max(w[3] for w in line_words),
    )


def _scan_employer(line_words):
    matches, consumed = [], set()
    for i, w in enumerate(line_words):
        if i in consumed or not _EMPLOYER_SUFFIX_RE.match(w[4]):
            continue
        start, j, count = i, i - 1, 0
        while j >= 0 and count < 4 and j not in consumed and line_words[j][4][:1].isupper():
            start = j; j -= 1; count += 1
        matches.append(line_words[start:i + 1])
        consumed.update(range(start, i + 1))
    return matches


def find_redaction_rects(page, active_cats, exclude_set=None):
    """
    Returns (results, label_diag).

    Auto-detects ONLY:
      - SSN in XXX-XX-#### format  → redacts XXX-XX portion, leaves last 4
      - State-abbr + ZIP           → redacts ZIP only, leaves state abbrev
      - Names/addresses via labels ("Taxpayer's name", "SSN" label → value below)
      - Employer names (corporate suffix anchor)
      - Phone / email (word-level pattern)

    Does NOT auto-detect:
      - Plain digit sequences of any length
      - EINs (user must enter; exact suffix is then hunted)
    """
    exclude_set = exclude_set or set()
    label_diag = {f["key"]: {"label_seen": False, "value_found": False} for f in LABEL_FIELDS}
    words = page.get_text("words")
    if not words:
        return [], label_diag

    results = []
    already = []

    def add(rect, key, text, is_label=False):
        norm = " ".join(text.split()).lower()
        if any(ex in norm or norm in ex for ex in exclude_set):
            return
        r = pymupdf.Rect(rect)
        for i, (er, ek, et, el) in enumerate(already):
            if ek == key and abs(er.x0 - r.x0) < 2 and abs(er.y0 - r.y0) < 2:
                if is_label and not el:
                    already[i] = (er, ek, et, True)
                    for j, (rr, rk, rt, rl) in enumerate(results):
                        if rr is er and rk == ek:
                            results[j] = (rr, rk, rt, True)
                            break
                return
        already.append((r, key, text, is_label))
        results.append((r, key, text, is_label))

    lines = _group_lines(words)

    for line_words in lines.values():
        line_str = " ".join(w[4] for w in line_words)
        cursor = 0
        offsets = []
        for w in line_words:
            offsets.append((cursor, cursor + len(w[4]), w))
            cursor += len(w[4]) + 1

        # ── SSN auto: XXX-XX-#### → redact only the XXX-XX prefix ────────────
        if "ssn" in active_cats:
            for m in SSN_AUTO_RE.finditer(line_str):
                # m.group(1) = "XXX-XX", m.group(2) = "-####"
                prefix_end = m.start() + len(m.group(1))
                spanned = [w for (s, e, w) in offsets
                           if not (e <= m.start() or s >= prefix_end)]
                if spanned:
                    x0 = min(w[0] for w in spanned)
                    y0 = min(w[1] for w in spanned)
                    x1 = max(w[2] for w in spanned)
                    y1 = max(w[3] for w in spanned)
                    add((x0 - 1, y0 - 1, x1 + 1, y1 + 1), "ssn", m.group(1))
            # already-masked form ***-**-####
            for m in SSN_MASKED_RE.finditer(line_str):
                spanned = [w for (s, e, w) in offsets
                           if not (e <= m.start() or s >= m.end())]
                if spanned:
                    x0 = min(w[0] for w in spanned)
                    y0 = min(w[1] for w in spanned)
                    x1 = max(w[2] for w in spanned)
                    y1 = max(w[3] for w in spanned)
                    add((x0 - 1, y0 - 1, x1 + 1, y1 + 1), "ssn", m.group(0))

        # ── State + ZIP: redact ZIP digits only, leave state abbrev ──────────
        if "address" in active_cats:
            for m in STATE_ZIP_RE.finditer(line_str):
                # m.group(1) = state, m.group(2) = 5-digit ZIP
                zip_start = m.start(2)
                zip_end   = m.end(0)   # includes optional -#### extension
                spanned = [w for (s, e, w) in offsets
                           if not (e <= zip_start or s >= zip_end)]
                if spanned:
                    x0 = min(w[0] for w in spanned)
                    y0 = min(w[1] for w in spanned)
                    x1 = max(w[2] for w in spanned)
                    y1 = max(w[3] for w in spanned)
                    zip_text = m.group(2) + (m.group(3) or "")
                    add((x0 - 1, y0 - 1, x1 + 1, y1 + 1), "address", zip_text)

                    # Also grab the line above (city/street of the address block)
                    best_gap, best_above = None, None
                    lx0, ly0, lx1, ly1 = _line_bounds(line_words)
                    for other in lines.values():
                        if other is line_words:
                            continue
                        ox0, oy0, ox1, oy1 = _line_bounds(other)
                        if oy1 <= ly0 + 2:
                            gap = ly0 - oy1
                            if best_gap is None or gap < best_gap:
                                best_gap, best_above = gap, other
                    if best_above is not None and best_gap <= 40:
                        ax0, ay0, ax1, ay1 = _line_bounds(best_above)
                        above_text = " ".join(w[4] for w in best_above)
                        # 1040 Ultimate: only when the line above looks like a street address - never a
                        # payer / employer name line (payer names must stay readable)
                        if STREET_RE.search(above_text):
                            add((ax0 - 1, ay0 - 1, ax1 + 1, ay1 + 1), "address", above_text)

        # ── Phone (word-level) ────────────────────────────────────────────────
        if "phone" in active_cats:
            phone_re = re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")
            for m in phone_re.finditer(line_str):
                spanned = [w for (s, e, w) in offsets
                           if not (e <= m.start() or s >= m.end())]
                if spanned:
                    x0 = min(w[0] for w in spanned)
                    y0 = min(w[1] for w in spanned)
                    x1 = max(w[2] for w in spanned)
                    y1 = max(w[3] for w in spanned)
                    add((x0 - 1, y0 - 1, x1 + 1, y1 + 1), "phone", m.group(0))

        # ── Email (word-level) ────────────────────────────────────────────────
        if "email" in active_cats:
            for w in line_words:
                t = w[4].strip()
                if re.match(r"^[\w.+\-]+@[\w\-]+(\.[\w\-]+)*\.[a-z]{2,}[.,;:)]?$", t, re.I):   # also sub-domains
                    add((w[0]-1, w[1]-1, w[2]+1, w[3]+1), "email", t)

        # ── Financial (opt-in only) ───────────────────────────────────────────
        if "financial" in active_cats:
            fin_re = re.compile(r"\$[\d,]+(\.\d{2})?|\b\d[\d,]*\.\d{2}\b")
            for m in fin_re.finditer(line_str):
                spanned = [w for (s, e, w) in offsets
                           if not (e <= m.start() or s >= m.end())]
                if spanned:
                    x0 = min(w[0] for w in spanned)
                    y0 = min(w[1] for w in spanned)
                    x1 = max(w[2] for w in spanned)
                    y1 = max(w[3] for w in spanned)
                    add((x0-1, y0-1, x1+1, y1+1), "financial", m.group(0))

        # ── Employer (corporate suffix anchor) ────────────────────────────────
        if "employer" in active_cats:
            for window in _scan_employer(line_words):
                x0 = min(w[0] for w in window); y0 = min(w[1] for w in window)
                x1 = max(w[2] for w in window); y1 = max(w[3] for w in window)
                add((x0-1, y0-1, x1+1, y1+1), "employer",
                    " ".join(w[4] for w in window))

        # ── Label-driven fields ───────────────────────────────────────────────
        for field in LABEL_FIELDS:
            if field["key"] not in active_cats:
                continue
            if not field["re"].search(line_str):
                continue
            label_diag[field["key"]]["label_seen"] = True
            lx0, ly0, lx1, ly1 = _line_bounds(line_words)

            same_line_val = [w for w in line_words if w[0] > lx1 - 2]
            below_candidates = []
            for other in lines.values():
                if other is line_words:
                    continue
                ox0, oy0, ox1, oy1 = _line_bounds(other)
                if oy0 > ly1 - 1 and oy0 < ly1 + (ly1 - ly0) * 3 and abs(ox0 - lx0) < 260:
                    below_candidates.append((oy0, other))

            value_words = []
            if below_candidates:
                below_candidates.sort(key=lambda t: t[0])
                closest_y = below_candidates[0][0]
                same_y = sorted(
                    (w for (y, ws) in below_candidates if abs(y - closest_y) < 3 for w in ws),
                    key=lambda w: w[0],
                )
                groups, current, prev_x1 = [], [], None
                for w in same_y:
                    if prev_x1 is not None and w[0] - prev_x1 > 20:
                        groups.append(current); current = []
                    current.append(w); prev_x1 = w[2]
                if current:
                    groups.append(current)
                if groups:
                    value_words = min(groups, key=lambda g: abs(min(w[0] for w in g) - lx0))
            elif same_line_val:
                value_words = same_line_val

            if not value_words:
                continue
            value_str = " ".join(w[4] for w in value_words)
            if any(f["re"].search(value_str) for f in LABEL_FIELDS):
                continue
            vr = field.get("value_re")
            if vr and not vr.fullmatch(value_str):
                continue

            vx0 = min(w[0] for w in value_words); vy0 = min(w[1] for w in value_words)
            vx1 = max(w[2] for w in value_words); vy1 = max(w[3] for w in value_words)
            add((vx0-1, vy0-1, vx1+1, vy1+1), field["key"], value_str, is_label=True)
            label_diag[field["key"]]["value_found"] = True

    return results, label_diag


# ── Hunt / literal search ────────────────────────────────────────────────────

def _build_hunt_pattern(key, value):
    """
    Build regex to hunt for a user-supplied value.
    - ssn: digit-by-digit with optional separator → matches any formatting
    - ein_suffix: exact 7-digit string only (no random match)
    - name/other: case-insensitive, flexible whitespace
    """
    if key == "ssn":
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 4:
            sep = r"[-\u2013\u2014.\s]?"
            return re.compile(r"\b" + sep.join(digits) + r"\b")
    if key == "ein_suffix":
        # Exact 7-digit suffix only — no separator allowed, word-bounded
        return re.compile(r"\b" + re.escape(value) + r"\b")
    tokens = [re.escape(t) for t in value.split()]
    return re.compile(r"\b" + r"\s+".join(tokens) + r"\b", re.IGNORECASE)


def find_literal_rects(page, needle, key="name"):
    """Find every occurrence of needle on the page and return bounding rects."""
    words = page.get_text("words")
    if not words or not needle or len(needle) < 3:
        return []
    lines = _group_lines(words)
    pattern = _build_hunt_pattern(key, needle)
    rects = []

    for line_words in lines.values():
        line_str = " ".join(w[4] for w in line_words)
        cursor = 0; offsets = []
        for w in line_words:
            offsets.append((cursor, cursor + len(w[4]), w))
            cursor += len(w[4]) + 1
        for m in pattern.finditer(line_str):
            end = m.end()
            if key == "ssn":
                # 1040 Ultimate: keep the last 4 digits visible - cut the box after the 5th digit
                digits = [i for i in range(m.start(), m.end()) if line_str[i].isdigit()]
                if len(digits) >= 9:
                    end = digits[4] + 1
            spanned = [(s, e, w) for (s, e, w) in offsets if not (e <= m.start() or s >= end)]
            if not spanned:
                continue
            x0 = min(w[0] for _, _, w in spanned); y0 = min(w[1] for _, _, w in spanned)
            y1 = max(w[3] for _, _, w in spanned)
            s_, e_, wl = spanned[-1]
            if end < e_:                         # cut inside the last word, proportionally to its characters
                x1 = wl[0] + (wl[2] - wl[0]) * (end - s_) / max(1, e_ - s_)
            else:
                x1 = max(w[2] for _, _, w in spanned)
            rects.append(pymupdf.Rect(x0-1, y0-1, x1+(0 if end < e_ else 1), y1+1))

    # Squashed fallback for character-spaced text (e.g. "S I D D H A R T H A")
    if key not in ("ssn", "ein_suffix"):
        sq = re.sub(r"\s+", "", needle).lower()
        if len(sq) >= 6:
            sq_chars = [(ch.lower(), w) for w in words for ch in w[4]]
            sq_line = "".join(c for c, _ in sq_chars)
            start = 0
            while True:
                idx = sq_line.find(sq, start)
                if idx < 0:
                    break
                spanned = {sq_chars[i][1] for i in range(idx, idx + len(sq))}
                y0 = min(w[1] for w in spanned); y1 = max(w[3] for w in spanned)
                if y1 - y0 <= 60:
                    x0 = min(w[0] for w in spanned); x1 = max(w[2] for w in spanned)
                    r = pymupdf.Rect(x0-1, y0-1, x1+1, y1+1)
                    if not any(abs(er.x0-r.x0) < 2 and abs(er.y0-r.y0) < 2 for er in rects):
                        rects.append(r)
                start = idx + len(sq)
    return rects


# ── Hidden metadata helpers (unchanged from v1.8.0) ─────────────────────────

_HIDDEN_TEXT_KEYS = ("Alt", "ActualText", "TU", "Contents", "Subj", "Title")  # Title = bookmarks
_HIDDEN_TEXT_KEY_RE = re.compile(
    r"/(" + "|".join(_HIDDEN_TEXT_KEYS) + r")\s*(\((?:\\.|[^()\\])*\)|<[0-9A-Fa-f\s]*>)"
)

def _decode_pdf_string_literal(raw):
    if raw.startswith("(") and raw.endswith(")"):
        return re.sub(r"\\([()\\])", r"\1", raw[1:-1])
    if raw.startswith("<") and raw.endswith(">"):
        h = re.sub(r"\s+", "", raw[1:-1])
        if len(h) % 2: h += "0"
        try:
            data = bytes.fromhex(h)
            if data[:2] == b"\xfe\xff":
                return data.decode("utf-16-be", errors="ignore")
            return data.decode("latin-1", errors="ignore")
        except ValueError:
            return ""
    return raw

def _value_in_text(text, key, value):
    if key in ("ssn", "ein", "ein_suffix"):
        digits = re.sub(r"\D", "", value)
        return len(digits) >= 4 and digits in re.sub(r"\D", "", text)
    needle = re.sub(r"\s+", "", value).lower()
    return len(needle) >= 4 and needle in re.sub(r"\s+", "", text).lower()

def _scan_hidden_metadata(doc, hunted_summary):
    hits = defaultdict(int)
    all_values = [(k, v) for k, info in hunted_summary.items() for v in info.get("values", [])]
    if not all_values:
        return {}
    info_text = " ".join(str(v) for v in (doc.metadata or {}).values() if v)
    xmp_text = ""
    try: xmp_text = doc.get_xml_metadata() or ""
    except Exception: pass
    for key, value in all_values:
        if info_text and _value_in_text(info_text, key, value): hits[(key, value)] += 1
        if xmp_text  and _value_in_text(xmp_text,  key, value): hits[(key, value)] += 1
    try: n = doc.xref_length()
    except Exception: n = 0
    for xref in range(1, n):
        try: obj_text = doc.xref_object(xref, compressed=False)
        except Exception: continue
        if not obj_text or ("(" not in obj_text and "<" not in obj_text): continue
        for _, decoded, _ in [(m.group(1), _decode_pdf_string_literal(m.group(2)), m.span(2))
                               for m in _HIDDEN_TEXT_KEY_RE.finditer(obj_text)]:
            if decoded:
                for key, value in all_values:
                    if _value_in_text(decoded, key, value): hits[(key, value)] += 1
    return dict(hits)

def _scrub_hidden_metadata(doc, hunted_summary):
    all_values = [(k, v) for k, info in hunted_summary.items() for v in info.get("values", [])]
    summary = {"info_fields": [], "xmp_cleared": False, "objects": 0}
    if not all_values: return summary
    meta = dict(doc.metadata or {}); changed = False
    for field in ("author", "title", "subject", "keywords"):
        val = meta.get(field) or ""
        if val and any(_value_in_text(val, k, v) for k, v in all_values):
            meta[field] = ""; summary["info_fields"].append(field); changed = True
    if changed:
        try: doc.set_metadata(meta)
        except Exception: pass
    try:
        xmp = doc.get_xml_metadata() or ""
        if xmp and any(_value_in_text(xmp, k, v) for k, v in all_values):
            doc.del_xml_metadata(); summary["xmp_cleared"] = True
    except Exception: pass
    try: n = doc.xref_length()
    except Exception: n = 0
    for xref in range(1, n):
        try: obj_text = doc.xref_object(xref, compressed=False)
        except Exception: continue
        if not obj_text or ("(" not in obj_text and "<" not in obj_text): continue
        pieces, last_end, touched = [], 0, False
        for m in _HIDDEN_TEXT_KEY_RE.finditer(obj_text):
            lit = m.group(2); decoded = _decode_pdf_string_literal(lit)
            if decoded and any(_value_in_text(decoded, k, v) for k, v in all_values):
                pieces.append(obj_text[last_end:m.start(2)])
                pieces.append("()" if lit.startswith("(") else "<>")
                last_end = m.end(2); touched = True
        if touched:
            pieces.append(obj_text[last_end:])
            try: doc.update_object(xref, "".join(pieces)); summary["objects"] += 1
            except Exception: pass
    return summary

def verify_output(output_path, hunted_summary):
    report = {}
    doc = pymupdf.open(str(output_path))
    try:
        hidden_hits = _scan_hidden_metadata(doc, hunted_summary)
        for key, info in hunted_summary.items():
            for value in info.get("values", []):
                pattern = _build_hunt_pattern(key, value)
                sq = re.sub(r"\s+", "", value).lower()
                pages_hit = []
                for page_num, page in enumerate(doc, start=1):
                    text = page.get_text()
                    norm = " ".join(text.split())
                    n = sum(1 for _ in pattern.finditer(norm))
                    if n == 0 and key not in ("ssn", "ein_suffix") and len(sq) >= 6:
                        n = re.sub(r"\s+", "", text).lower().count(sq)
                    try:
                        for wdg in page.widgets() or []:
                            fv = wdg.field_value if isinstance(wdg.field_value, str) else ""
                            if fv and pattern.search(" ".join(fv.split())):
                                n += 1
                    except Exception: pass
                    if n: pages_hit.append((page_num, n))
                hn = hidden_hits.get((key, value), 0)
                if hn: pages_hit.append((0, hn))
                if pages_hit: report[(key, value)] = pages_hit
    finally:
        doc.close()
    return report


# ── Core redaction ───────────────────────────────────────────────────────────

def _split_multi(value):
    return [p.strip() for p in value.split(",") if p.strip()] if value else []

def _dedupe(values):
    seen = {}
    for v in values:
        k = v.strip().lower()
        if k and k not in seen: seen[k] = v.strip()
    return list(seen.values())


K1_MASK_FILE = "k1_mask_input.json"


def _password_candidates(path, known=None):
    """Known password for this file first, then tokens from its name ("... PW-2400.pdf" -> "2400")."""
    cands = []
    if known and known.get(path.name):
        cands.append(known[path.name])
    cands += [m.group(1) for m in re.finditer(r"PW\s*[-_:]?\s*([A-Za-z0-9]+)", path.stem, re.I)]
    cands += re.findall(r"[A-Za-z0-9]{4,}", path.stem)[::-1]
    cands += list((known or {}).get("*", []))          # --passwords a,b,c
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


_QUOTE_OP_RE = re.compile(rb"(\((?:\\.|[^()\\])*\))\s*'")


def _normalize_quote_ops(doc):
    """Rewrite the text operator  (string) '  as  T* (string) Tj .
    MuPDF's content cleaning (used by apply_redactions) silently drops text drawn with
    the ' operator in some PDFs (e.g. flattened fill-in K-1 fields), which blanked whole
    name/address blocks instead of masking only the hunted words."""
    for x in range(1, doc.xref_length()):
        try:
            if not doc.xref_is_stream(x):
                continue
            if doc.xref_get_key(x, "Subtype")[1] == "/Image":
                continue
            data = doc.xref_stream(x)
        except Exception:
            continue
        if not data or b")'" not in data or b"BT" not in data:
            continue
        new = _QUOTE_OP_RE.sub(rb"T* \1 Tj", data)
        if new != data:
            try: doc.update_stream(x, new)
            except Exception: pass


def _open_pdf(input_path, passwords=None):
    doc = pymupdf.open(str(input_path))
    if doc.needs_pass:
        for pw in _password_candidates(Path(input_path), passwords):
            if doc.authenticate(pw):
                _normalize_quote_ops(doc)
                return doc
        if False:  # no prompts inside the web app
            pw = input(f'  Password for "{Path(input_path).name}" (Enter to skip): ').strip()
            if pw and doc.authenticate(pw):
                if passwords is not None:
                    passwords[Path(input_path).name] = pw   # don't ask twice for the same file
                _normalize_quote_ops(doc)
                return doc
        doc.close()
        raise PermissionError("password-protected — password not found "
                              "(name it '... PW-<password>.pdf', use --passwords, or run k1_summary.py first)")
    _normalize_quote_ops(doc)
    return doc


def load_k1_mask_file(folder):
    """Read k1_mask_input.json written by k1_summary.py. Returns dict or None."""
    import json
    p = Path(folder) / K1_MASK_FILE
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠ Could not read {p.name}: {e}", file=sys.stderr)
        return None
    data["_path"] = str(p)
    return data


def _show_list(label, values, limit=None):
    shown = values if limit is None else values[:limit]
    print(f"  {label:<18}({len(values)}) " + ", ".join(shown) +
          (f", … +{len(values) - len(shown)} more" if len(shown) < len(values) else ""))


def redact_pdf(input_path, output_path, active_cats, overrides=None, exclude_set=None, passwords=None):
    overrides = overrides or {}
    doc = _open_pdf(input_path, passwords)
    repair_warning = None
    try:
        cleaned = doc.tobytes(garbage=4, clean=True)
        cdoc = pymupdf.open(stream=cleaned, filetype="pdf")
        # The repair pass can silently drop text on some PDFs — keep it only if no words were lost
        lost = [i + 1 for i in range(len(doc))
                if len(cdoc[i].get_text("words")) < len(doc[i].get_text("words"))]
        if lost:
            cdoc.close()
            repair_warning = (f"repair pass would drop text on page(s) {', '.join(map(str, lost[:10]))}"
                              " — skipped it")
        else:
            doc.close()
            doc = cdoc
    except Exception as e:
        repair_warning = f"{type(e).__name__}: {e}"
        doc = _open_pdf(input_path, passwords)

    total = 0
    pages_no_text, pages_failed = [], []
    label_summary = {f["key"]: {"label_seen_on": [], "value_found_on": []} for f in LABEL_FIELDS}
    hunted_summary = {}
    scrub_summary = {"info_fields": [], "xmp_cleared": False, "objects": 0}

    try:
        page_rects = []
        discovered = defaultdict(list)

        # Pass 1: per-page auto-detection
        for page_num, page in enumerate(doc, start=1):
            if not page.get_text("words"):
                pages_no_text.append(page_num)
            rects, label_diag = find_redaction_rects(page, active_cats, exclude_set)
            page_rects.append(rects)
            for key, info in label_diag.items():
                if info["label_seen"]:  label_summary[key]["label_seen_on"].append(page_num)
                if info["value_found"]: label_summary[key]["value_found_on"].append(page_num)
            for rect, key, text, is_label in rects:
                if key in ("name", "ssn") and is_label:
                    discovered[key].extend(_split_multi(text))

        # Pass 2: global hunt for user-supplied and label-discovered values
        hunt_targets = []  # list of (key, value) pairs to hunt

        # Names discovered via label
        for v in _dedupe(discovered.get("name", []) + overrides.get("name", [])):
            hunt_targets.append(("name", v))

        # SSNs: user-entered → full mask; auto-detected (partial) already handled in pass 1
        for v in _dedupe(overrides.get("ssn", [])):
            hunt_targets.append(("ssn", v))

        # EINs: user enters XX-XXXXXXX → hunt ONLY the exact 7-digit suffix
        for v in _dedupe(overrides.get("ein", [])):
            m = re.match(r"^(\d{2})[-–—](\d{7})$", v.strip())
            if m:
                suffix = m.group(2)
                hunt_targets.append(("ein_suffix", suffix))
            else:
                # Non-standard format: hunt the whole thing as free text
                hunt_targets.append(("other", v))

        # Other free text
        for v in _dedupe(overrides.get("other", [])):
            hunt_targets.append(("other", v))

        # Longest phrases first, so "1213 CALLE LUCHETTI, APTO 5" wins over "1213 CALLE LUCHETTI"
        hunt_targets.sort(key=lambda kv: -len(kv[1]))
        for key, value in hunt_targets:
            hunted_summary.setdefault(key, {"values": [], "extra_hits": 0})
            if value not in hunted_summary[key]["values"]:
                hunted_summary[key]["values"].append(value)
            for page_num, page in enumerate(doc, start=1):
                existing = page_rects[page_num - 1]
                for r in find_literal_rects(page, value, key):
                    dup = any(ek == key and abs(er.x0-r.x0) < 2 and abs(er.y0-r.y0) < 2
                              for er, ek, et, el in existing)
                    if not dup:
                        existing.append((r, key, value, True))
                        hunted_summary[key]["extra_hits"] += 1

                # Form field values
                try: widgets = list(page.widgets() or [])
                except Exception: widgets = []
                pattern = _build_hunt_pattern(key, value)
                for wdg in widgets:
                    fv = wdg.field_value if isinstance(wdg.field_value, str) else ""
                    flat = " ".join(fv.split())
                    if not fv or not pattern.search(flat):
                        continue
                    # Replace only the matched text inside the field (keeps e.g. the
                    # first name or the fund name); fall back to removing the field.
                    new_val = pattern.sub(lambda m: "X" * min(len(m.group(0)), 8), flat)
                    hunted_summary[key]["extra_hits"] += 1
                    try:
                        wdg.field_value = new_val
                        wdg.update()
                    except Exception:
                        r = pymupdf.Rect(wdg.rect)
                        dup = any(ek == key and abs(er.x0-r.x0) < 2 and abs(er.y0-r.y0) < 2
                                  for er, ek, et, el in existing)
                        if not dup:
                            existing.append((r, key, f"[field] {fv[:40]}", True))
                        try: page.delete_widget(wdg)
                        except Exception:
                            try: wdg.field_value = ""; wdg.update()
                            except Exception: pass

        # Apply redactions
        for page_num, page in enumerate(doc, start=1):
            rects = page_rects[page_num - 1]
            if not rects: continue
            try:
                # Remove text using only the vertical core of each box, so tightly spaced
                # neighbouring lines (e.g. the name line above an address) are not
                # removed too; then paint the black box over the full word height.
                boxes = []
                for rect, key, text, is_label in rects:
                    r = pymupdf.Rect(rect)
                    h = r.height
                    core = pymupdf.Rect(r.x0, r.y0 + 0.3 * h, r.x1, r.y1 - 0.3 * h) if h > 4 else r
                    page.add_redact_annot(core, fill=False)
                    boxes.append(pymupdf.Rect(r.x0, r.y0 + 0.12 * h, r.x1, r.y1 - 0.12 * h) if h > 4 else r)
                page.apply_redactions(
                    images=pymupdf.PDF_REDACT_IMAGE_NONE,
                    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                    text=pymupdf.PDF_REDACT_TEXT_REMOVE,
                )
                for b in boxes:
                    page.draw_rect(b, color=None, fill=(0, 0, 0), overlay=True)
                total += len(rects)
            except Exception as e:
                pages_failed.append((page_num, f"{type(e).__name__}: {e}"))

        try: scrub_summary = _scrub_hidden_metadata(doc, hunted_summary)
        except Exception as e:
            scrub_summary = {"info_fields": [], "xmp_cleared": False, "objects": 0,
                             "error": f"{type(e).__name__}: {e}"}

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path), garbage=4, deflate=True)
    finally:
        doc.close()

    try: verification = verify_output(output_path, hunted_summary)
    except Exception as e: verification = {("error", str(e)): [(0, 0)]}

    return {
        "redactions": total, "pages_failed": pages_failed,
        "repair_warning": repair_warning, "pages_no_text": pages_no_text,
        "label_summary": label_summary, "hunted_summary": hunted_summary,
        "scrub_summary": scrub_summary, "verification": verification,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="True (non-rasterizing) PDF PII redaction.")
    ap.add_argument("--version", action="version", version=f"redact_pdf.py {__version__}")
    ap.add_argument("path", nargs="?", default=None,
                    help='PDF file or folder. Defaults to "Input" subfolder next to script.')
    ap.add_argument("--categories", help="Comma-separated category override.")
    ap.add_argument("--include-financial", action="store_true", help="Also redact dollar amounts.")
    ap.add_argument("--name",  help="Name(s) to mask. Comma-separated.")
    ap.add_argument("--ssn",   help="SSN(s) to mask (any format; fully masked).")
    ap.add_argument("--ein",   help="EIN(s) as XX-XXXXXXX. Masks exact 7-digit suffix only.")
    ap.add_argument("--other", help="Any other free text to mask. Comma-separated.")
    ap.add_argument("--auto",  action="store_true", help="Skip interactive prompt.")
    ap.add_argument("--exclude", help="Comma-separated phrases to never redact.")
    ap.add_argument("--passwords", default="", help="Comma-separated extra PDF passwords to try.")
    ap.add_argument("--no-k1", action="store_true",
                    help=f"Ignore {K1_MASK_FILE} in the input folder.")
    ap.add_argument("--out-dir", default="redacted",
                    help='Output folder (default "redacted", sibling of input).')
    args = ap.parse_args()

    if args.categories:
        active_cats = {c.strip() for c in args.categories.split(",") if c.strip()}
        unknown = active_cats - CAT_KEYS
        if unknown:
            print(f"Unknown categories: {', '.join(unknown)}", file=sys.stderr)
            sys.exit(1)
    else:
        active_cats = set(DEFAULT_ON)
        if args.include_financial:
            active_cats.add("financial")

    exclude_set = set()
    if args.exclude:
        exclude_set = {" ".join(p.strip().split()).lower()
                       for p in args.exclude.split(",") if len(p.strip()) >= 4}

    in_path = Path(args.path) if args.path else Path(__file__).resolve().parent / "Input"
    if not args.path:
        print(f"No path given — defaulting to {in_path}")
    if not in_path.exists():
        print(f"Path not found: {in_path}", file=sys.stderr); sys.exit(1)

    overrides = {}
    if args.name:  overrides["name"]  = _split_multi(args.name)
    if args.ssn:   overrides["ssn"]   = _split_multi(args.ssn)
    if args.ein:   overrides["ein"]   = _split_multi(args.ein)
    if args.other: overrides["other"] = _split_multi(args.other)

    # ── K-1 masking input (from k1_summary.py) ──────────────────────────────
    k1_overrides, k1_passwords = {}, {}
    extra_pw = [p.strip() for p in args.passwords.split(",") if p.strip()]
    k1 = None
    if not args.no_k1:
        # Look next to the PDFs first, then in the Input folder next to this script
        # (so "K-1 Forms" PDFs made by k1_summary.py pick up Input\k1_mask_input.json)
        here = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
        for folder in (in_path if in_path.is_dir() else in_path.parent, here / "Input"):
            k1 = load_k1_mask_file(folder)
            if k1:
                break
    if k1:
        print(f"\nK-1 masking input found: {k1['_path']}  (created {k1.get('created', '?')})")
        _show_list("EINs", k1.get("ein", []))
        _show_list("Names (masked)", k1.get("name", []))
        _show_list("First names kept", k1.get("keep_first_names", []))
        _show_list("Addresses", k1.get("address", []), limit=12)
        if k1.get("passwords"):
            print(f"  {'PDF passwords':<18}({len(k1['passwords'])}) for protected K-1 files")
        use = True
        if not args.auto:
            try:
                while True:
                    ans = input("Use these K-1 masking values? [Y]es / [n]o / [l]ist all addresses: ").strip().lower()
                    if ans == "l":
                        for a in k1.get("address", []):
                            print(f"      {a}")
                        continue
                    use = ans in ("", "y", "yes")
                    break
            except (EOFError, OSError):
                pass
        if use:
            # keep first names and entity names readable (auto-detection skips them)
            for keep in list(k1.get("keep_first_names", [])) + [d.get("entity", "") for d in k1.get("k1s", [])]:
                keep = " ".join(str(keep).split()).lower()
                if len(keep) >= 4:
                    exclude_set.add(keep)
            k1_overrides = {"ein": list(k1.get("ein", [])), "name": list(k1.get("name", [])),
                            "other": list(k1.get("address", []))}
            k1_passwords.update(k1.get("passwords", {}))
            print("  → K-1 values will be added to anything you enter below.")
        else:
            print("  → K-1 masking input ignored.")

    if not args.auto and not any(k in overrides for k in ("name","ssn","ein","other")):
        try:
            sys.stdout.flush()
            print("\nOptional — enter values to mask across every document.")
            print("Leave any blank to skip.\n")

            resp_ssn_ein = input(
                "SSN(s) / EIN(s) to redact?\n"
                "  SSN: any format → fully masked\n"
                "  EIN: enter as XX-XXXXXXX → only the 7-digit suffix is masked\n"
                "  (comma-separated for multiple; Enter to skip): "
            ).strip()

            resp_name = input(
                "Name(s) to redact? (comma-separated; Enter to skip): "
            ).strip()

            resp_address = input(
                "Address(es) to redact? (comma-separated; Enter to skip): "
            ).strip()

            resp_phone = input(
                "Phone number(s) to redact? (comma-separated; Enter to skip): "
            ).strip()

            resp_other = input(
                "Any other text to redact? (comma-separated; Enter to skip): "
            ).strip()

            if resp_name:    overrides["name"]  = _split_multi(resp_name)
            if resp_address: overrides.setdefault("other", []).extend(_split_multi(resp_address))
            if resp_phone:   overrides.setdefault("other", []).extend(_split_multi(resp_phone))
            if resp_other:   overrides.setdefault("other", []).extend(_split_multi(resp_other))

            if resp_ssn_ein:
                for val in _split_multi(resp_ssn_ein):
                    if re.match(r"^\d{2}[-–—]\d{7}$", val.strip()):
                        overrides.setdefault("ein", []).append(val.strip())
                    else:
                        overrides.setdefault("ssn", []).append(val.strip())

        except (EOFError, OSError):
            print("(No interactive input — auto-detecting only. Use --auto to silence this.)")

    for k, vs in k1_overrides.items():
        overrides.setdefault(k, []).extend(v for v in vs if v not in overrides.get(k, []))
    if extra_pw:
        k1_passwords["*"] = extra_pw

    pdfs = (sorted([p for p in in_path.iterdir() if p.suffix.lower() == ".pdf"], key=lambda p: p.name.lower())
            if in_path.is_dir() else [in_path])
    out_dir = in_path.parent / args.out_dir

    if not pdfs:
        print("No PDF files found.", file=sys.stderr); sys.exit(1)

    print(f"\nredact_pdf.py v{__version__}")
    print(f"Categories active : {', '.join(sorted(active_cats))}")
    print(f"Auto-detect rules : SSN (XXX-XX-#### → mask prefix), State+ZIP (mask ZIP only)")
    if overrides:
        for k, vs in overrides.items():
            shown = ", ".join(repr(v) for v in vs[:10])
            more = f", … +{len(vs) - 10} more" if len(vs) > 10 else ""
            print(f"  {k:12s}: {shown}{more}")
    if exclude_set:
        ex = sorted(exclude_set)
        print(f"Excluded phrases  : {', '.join(repr(p) for p in ex[:8])}"
              + (f", … +{len(ex) - 8} more" if len(ex) > 8 else ""))
    print(f"Output folder     : {out_dir}\n")

    ok = failed = 0
    for pdf_path in pdfs:
        out_path = out_dir / (pdf_path.stem + "-redacted.pdf")
        try:
            r = redact_pdf(pdf_path, out_path, active_cats,
                           overrides=overrides, exclude_set=exclude_set, passwords=k1_passwords)
            print(f"  ✓ {pdf_path.name} — {r['redactions']} item(s) redacted → {out_path.name}")

            if r.get("repair_warning"):
                print(f"      ⚠ Repair pass failed ({r['repair_warning']}); processed original.")
            if r["pages_no_text"]:
                print(f"      ⚠ Page(s) {', '.join(map(str,r['pages_no_text']))} have no text — needs OCR.")
            for pn, err in r.get("pages_failed", []):
                print(f"      ✗ Page {pn} FAILED ({err}) — PII NOT removed. Do not share.")

            scrub = r.get("scrub_summary") or {}
            if scrub.get("error"):
                print(f"      ⚠ Metadata scrub error: {scrub['error']}")
            elif any(scrub.get(k) for k in ("info_fields","xmp_cleared","objects")):
                bits = []
                if scrub.get("info_fields"): bits.append("doc props: " + ", ".join(scrub["info_fields"]))
                if scrub.get("xmp_cleared"): bits.append("XMP cleared")
                if scrub.get("objects"):     bits.append(f"{scrub['objects']} hidden-text objects blanked")
                print(f"      🧹 Metadata scrubbed — {'; '.join(bits)}.")

            hunt = r.get("hunted_summary", {})
            for key, info in hunt.items():
                if info.get("values"):
                    vals = info["values"]
                    shown = (", ".join(repr(v) for v in vals) if len(vals) <= 8
                             else f"{len(vals)} values")
                    print(f"      🔍 {key}: {shown} — {info['extra_hits']} extra occurrence(s) masked.")

            leftover = r.get("verification") or {}
            any_hunted = any(i.get("values") for i in hunt.values())
            if leftover:
                for (vk, val), pages in leftover.items():
                    if vk == "error":
                        print(f"      ⚠ Verify error: {val}")
                        continue
                    total_left = sum(n for _, n in pages)
                    where = []
                    pl = [p for p, _ in pages if p != 0]
                    if pl: where.append("page(s) " + ", ".join(map(str, pl)))
                    if any(p == 0 for p, _ in pages): where.append("embedded metadata")
                    print(f"      ✗ VERIFY FAILED: {repr(val)} still appears {total_left}× "
                          f"({'; '.join(where)}). Do NOT share.")
            elif any_hunted:
                print(f"      ✅ VERIFY: no hunted values remain in output.")
            ok += 1
        except Exception as e:
            print(f"  ✗ {pdf_path.name} — {type(e).__name__}: {e}", file=sys.stderr)
            failed += 1

    print(f"\nDone — {ok} redacted" + (f", {failed} failed" if failed else "") + ".")


if __name__ == "__main__":
    main()
