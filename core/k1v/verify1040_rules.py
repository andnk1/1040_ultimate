"""
verify1040_rules.py - K-1 item -> where it should show up in the UltraTax 1040 (DRAFT - Lady to review).

kind:
  "verify" - compared with the K-1 Reconciliation Worksheet row(s) in `rows` (UltraTax row labels).
             K-1 items that point to the same row are added together before comparing (e.g. 4a + 4b).
             sign "abs" = compare absolute values (deductions show as negatives in UltraTax).
  "fyi"    - not reflected on the federal 1040 (or not reviewed yet). Shown grey with the reason.
  "manual" - reflected on the 1040, but combined with other items, so it can't be tied per partnership yet.
  cant     - text: when nothing is found in the return, show orange "Can't verify" with this text (instead of red).
  qbi      - QBI worksheet row ("Screen K1QBI Amount") to compare with; falls back to `rows` when there is no QBI worksheet.
  by_s11   - 11S only: rows per the Short-term / Long-term box ticked on the K-1 Interpreter.
`form` = where it is / should be on the return.
Keys: box + code, as read by k1_parser ("1", "9a", "13AE"). "13*" = any other code in box 13.
"""

MAP = {
    # ---- Schedule E page 2 (passive / nonpassive), Form 8582 when passive
    # boxes 1 and 2: checked against the QBI worksheet ("Screen K1QBI Amount"); Sch E worksheet = fallback + limitations
    "1":   dict(kind="verify", rows=["ordinary business income"], qbi="ordinary business inc", form="Schedule E p2, line 28 (Form 8582 if passive)"),
    "2":   dict(kind="verify", rows=["net rental real estate income"], qbi="net rental real estate inc", form="Schedule E p2, line 28 / Form 8582"),
    "3":   dict(kind="verify", rows=["other net rental income"], form="Schedule E p2, line 28 / Form 8582"),
    "4a":  dict(kind="verify", rows=["guaranteed payments"], form="Schedule E p2, line 28"),
    "4b":  dict(kind="verify", rows=["guaranteed payments"], form="Schedule E p2, line 28"),
    "4c":  dict(kind="fyi", why="Total of 4a + 4b — checked through 4a / 4b."),
    "4":   dict(kind="verify", rows=["guaranteed payments"], form="Schedule E p2, line 28"),
    "12":  dict(kind="verify", rows=["section 179 expense"], sign="abs", form="Form 4562 line 6 → Schedule E p2"),
    "13ZZ": dict(kind="verify", rows=["other deductions"], sign="abs", form="Schedule E p2 (UltraTax deducts it as a K-1 loss)"),
    "7":   dict(kind="verify", rows=["royalties"], form="Schedule E p1, line 4"),

    # ---- Schedule B / 1040 page 1
    "5":   dict(kind="verify", rows=["interest income"], form="Schedule B, line 1"),
    "6a":  dict(kind="verify", rows=["dividend income"], form="Schedule B, line 5"),
    "6b":  dict(kind="verify", rows=["qualified dividends"], form="Form 1040, line 3a"),
    "6c":  dict(kind="manual", form="Dividend equivalents — per statement"),

    # ---- Schedule D / 8949 / 4797 / 6781
    "8":   dict(kind="verify", rows=["short term capital gain"], form="Schedule D, line 5"),
    "9a":  dict(kind="verify", rows=["long term capital gain"], form="Schedule D, line 12"),
    "9b":  dict(kind="verify", rows=["28% capital gain"], form="28% Rate Gain Worksheet"),
    "9c":  dict(kind="manual", form="Unrecaptured Sec. 1250 Gain Worksheet"),
    "10":  dict(kind="verify", rows=["4797 part i"], form="Form 4797, Part I"),
    "11C": dict(kind="verify", rows=["1256 contracts and straddles"], form="Form 6781"),

    # ---- Schedule 1 / Form 4952 / Schedule A
    "11A": dict(kind="verify", rows=["other portfolio income"], form="Schedule 1, line 8z"),
    "11ZZ": dict(kind="verify", rows=["other income loss", "other inc loss schedule e"], form="Schedule 1, line 8z or Schedule E (per statement)"),
    "11F": dict(kind="verify", rows=["cancellation of debt"], form="Schedule 1, line 8c"),
    "13H": dict(kind="verify", rows=["investment interest expense"], sign="abs", form="Form 4952 → Schedule A, line 9",
                cant="UltraTax doesn't seem to have a direct input for this number; it can't be verified."),
    # 11S: added to box 8 (short-term) or 9a (long-term) per the box ticked on the K-1 Interpreter (line flag s11)
    "11S": dict(kind="verify", rows=[], by_s11={"ST": ["short term capital gain"], "LT": ["long term capital gain"]},
                form="Schedule D (with box 8 / 9a)"),
    "13L": dict(kind="verify", rows=["portfolio deductions other"], sign="abs", form="Schedule A, line 16"),
    "13A": dict(kind="verify", rows=["cash contributions"], sign="abs", form="Schedule A, line 11"),
    "13B": dict(kind="verify", rows=["cash contributions 30%"], sign="abs", form="Schedule A, line 11"),
    "13C": dict(kind="verify", rows=["noncash contributions 50%"], sign="abs", form="Schedule A, line 12"),
    "13D": dict(kind="verify", rows=["noncash contributions 30%"], sign="abs", form="Schedule A, line 12"),
    "13E": dict(kind="verify", rows=["cap gain prop 50% org"], sign="abs", form="Schedule A, line 12"),
    "13F": dict(kind="verify", rows=["cap gain prop 20%"], sign="abs", form="Schedule A, line 12"),

    # ---- Schedule SE
    "14A": dict(kind="verify", rows=["net earnings from self employ"], form="Schedule SE"),
    "14C": dict(kind="verify", rows=["gross nonfarm income"], form="Schedule SE"),

    # ---- AMT (Form 6251) - read from AMT version page 1
    "17A": dict(kind="verify", rows=["depreciation adjustment post"], amt=True, form="Form 6251, line 2l",
                cant="Can't find it in the return (Form 6251)."),

    # ---- Basis items that UltraTax carries on the worksheet (not on a 1040 line)
    "18A": dict(kind="verify", rows=["other tax exempt income"], form="UT K-1 worksheet — Other tax-exempt income (basis; 1040 line 2a if interest)"),
    "18B": dict(kind="verify", rows=["other tax exempt income"], form="UT K-1 worksheet — Other tax-exempt income (basis)"),
    "18C": dict(kind="verify", rows=["nondeductible expenses"], form="UT K-1 worksheet — Nondeductible expenses (basis)"),
    "19A": dict(kind="verify", rows=["cash market security distrib"], form="UT K-1 worksheet — Cash & marketable securities distributions (basis)"),
    "19B": dict(kind="verify", rows=["property distributions"], form="UT K-1 worksheet — Property distributions (basis) + Form 7217"),
    "19C": dict(kind="verify", rows=["property distributions"], form="UT K-1 worksheet — Property distributions (basis) + Form 7217"),

    # ---- not on the federal 1040 / not reviewed yet
    "13AE": dict(kind="fyi", why="State only — not deductible on the federal 1040. (Basis decrease is on the Partner's Basis Worksheet — not reviewed yet.)"),
    "16":  dict(kind="fyi", why="K-3 attached — review the K-3."),
    "19D": dict(kind="fyi", why="Do not enter — deemed distribution; ties to the K1 liability change."),
    "20B": dict(kind="fyi", rows=["investment expenses"], why="Do not enter — already included in Box 13 AE (Portfolio deductions).",
                if_entered="Entered in UT (Form 4952), but it shouldn't be — already included in Box 13 AE (Portfolio deductions)."),
    "20A": dict(kind="fyi", why="UltraTax computes investment income from Box 5 / 6 — not entered separately."),
    "20N": dict(kind="fyi", why="Business interest expenses, added back to ordinary income for QBI calculations — not an additional deduction."),
    "20AG": dict(kind="fyi", why="Gross receipts (§448(c) test) — information only."),
    "20Z": dict(kind="fyi", why="QBI — QBI worksheet not verified yet."),
    "20V": dict(kind="fyi", why="QBI / unrelated business taxable income — not verified yet."),
    "20AA": dict(kind="fyi", why="§704(c) information — information only."),
    "22":  dict(kind="fyi", why="More than one activity (at-risk) — information only."),
    "23":  dict(kind="fyi", why="More than one activity (passive) — information only."),
    "21":  dict(kind="manual", form="Form 1116 — foreign taxes are combined by category; check Form 1116 / Schedule 3 manually."),
}

# fallbacks by box when the code has no specific entry
BOX = {
    "11": dict(kind="manual", form="Per statement — Schedule 1 or Schedule E"),
    "13": dict(kind="manual", form="Per statement — Schedule A / Schedule E / Form 4952"),
    "15": dict(kind="manual", form="Credits — Form 3800 / specific credit form"),
    "17": dict(kind="manual", form="Form 6251 (AMT)"),
    "18": dict(kind="manual", form="Basis only"),
    "19": dict(kind="manual", form="Basis only"),
    "20": dict(kind="fyi", why="Other information — not verified yet."),
}


def rule_for(key: str, box: str) -> dict:
    return MAP.get(key) or BOX.get(box) or dict(kind="manual", form="No mapping yet")
