"""
k1_rules.py - Schedule K-1 (Form 1065) -> UltraTax 1040 rules.

Each rule has:
  label  : display name
  where  : UltraTax location - ONLY when there is a special UT spot (blank = standard K1 entry)
  note   : what to pay attention to
  why    : why it matters
  f1040  : where it lands on the 1040 (only when the checklist/preparer names it)
  passive: True if the box is part of the passive activity for the 8582

Sources: 1065_K1_UltraTax_1040_Checklist.csv and preparer-supplied mappings.
Keys: box number, or box + code (e.g. "13AE"). "13*" = fallback for any other code in box 13.
Edit this file to add or change rules - the page picks them up on the next run.
"""

F7217 = "Beginning in tax year 2024, partners who received property distributions from the partnership must file with their annual tax return a separate Form 7217, Partner’s Report of Property Distributed by a Partnership, for each date during the tax year on which they actually (and not constructively) received properties subject to section 732."

RULES = {
    # ---------------------------------------------------------------- Part II
    "G": {"label": "G — Partner type", "where": "K1 → Information About Partner",
          "why_by_value": {
              "General": "General partner or LLC member-manager: business earnings generally subject to self-employment tax (Schedule SE). Review Box 14A.",
              "Limited": "Limited partner or other LLC member: a qualifying limited partner's profit share generally avoids SE tax. Guaranteed payments for services are still subject to SE tax. The LLC checkbox alone doesn't establish the exemption."}},
    "H1": {"label": "H1 — Domestic / foreign partner", "where": "K1 → Information About Partner",
           "why_by_value": {
               "Domestic": "Generally a U.S. citizen or resident alien for tax purposes. Generally files Form 1040 and reports worldwide income.",
               "Foreign": "Generally a nonresident alien. Generally involves Form 1040-NR, with possible partnership withholding reported on Form 8805."}},
    "J": {"label": "J — Share of profit, loss, and capital", "where": "K1 → Information About Partner"},
    "K1": {"label": "K1 — Partner's share of liabilities", "where": "PBasis1 → Increase in Partner basis",
           "why_by_value": {
               "Nonrecourse": "No partner is personally liable; the lender generally relies on collateral. Counts toward tax basis: Yes. Counts toward at-risk: Generally no.",
               "Qualified nonrecourse financing": "Nonrecourse real-estate financing meeting special requirements, often a qualifying bank mortgage. Tax basis: Yes. At-risk: Yes, if requirements are met.",
               "Recourse": "A partner bears personal responsibility for repayment. Tax basis: Yes. At-risk: Generally yes, subject to exceptions."}},
    "M": {"label": "M — Contributed property with built-in gain (loss)", "where": "",
          "note": "A “Yes” in Item M does not, by itself, require a taxable dollar entry in UT. It flags the attached statement for review.",
          "why": "Asks whether the partner contributed property whose market value differed from its tax basis. Example: property worth $100,000 with $60,000 basis has a $40,000 built-in gain. A “Yes” flags special rules for allocating future income/loss and certain distributions. Review and retain the attached contribution statement; the built-in gain/loss itself isn't automatically current taxable income."},
    "N": {"label": "N — Net unrecognized §704(c) gain (loss)", "where": "Do not enter in UT — info only",
          "note": "Unrealized increase/decrease affects the GAAP capital account only - it does not increase tax basis.",
          "why": "Helps the partnership allocate tax gain and deductions when property is sold or depreciated; can arise from contributed property or a partnership revaluation. Informational — don't enter these balances or their change as taxable income. No direct adjustment to partnership basis from Item N alone; retain in workpapers."},

    "L": {"label": "L — Partner's capital account analysis",
          "where": "Capital contributed - PBasis1\nWithdrawals - Do not enter, check box 19"},
    "PART": {"label": "Participation", "where": "K1-2 Activity Info",
             "note": "1. Other Passive  ·  2. Passive rental real estate with active participation  ·  3. No limitation  ·  4. Active real estate professional",
             "why": "Rental real estate / active participation - Partner makes management decisions and generally owns at least 10%. Limited partners generally don't qualify. The special rental-loss allowance has income limits.\nNo limitation - Partner materially participates (more than 500 hours annually)\nReal estate professional - Partner meets both the more-than-750-hours and more-than-half-of-working-time tests, plus materially participates in the rental activity."},
    "TY": {"label": "Tax year (beginning – ending)", "where": ""},
    "J_dec": {"label": "J — Check if decrease is due to Sale / Exchange of partnership interest", "where": "",
              "note": "Red flag when checked — review."},
    "K2": {"label": "K2 — Liabilities include amounts from lower-tier partnerships", "where": "",
           "note": "This partnership also owns interests in other partnerships, and some of the debt reported in item K1 comes from those underlying partnerships. The K2 checkbox itself does not trigger an additional form or establish that the client personally guarantees the debt."},
    "K3": {"label": "K3 — Liability subject to guarantees or other payment obligations", "where": "",
           "note": "K3 is checked — liability subject to guarantees or other payment obligations by the partner. Review."},

    # ---------------------------------------------------------------- Part III
    "1": {"label": "Box 1 — Ordinary business income (loss)", "passive": True,
          "why": "Reports business income/loss.", "note": "Confirm material participation and apply loss limitations."},
    "2": {"label": "Box 2 — Net rental real estate income (loss)", "passive": True,
          "why": "Reports rental real estate activity.", "note": "Usually passive; review applicable exceptions."},
    "3": {"label": "Box 3 — Other net rental income (loss)", "passive": True,
          "why": "Reports rentals other than real estate.", "note": "Keep separate from box 2."},
    "4a": {"label": "Box 4a — Guaranteed payments for services",
           "why": "Guaranteed payments are taxable income; services and capital payments can have different self-employment treatment.",
           "note": "Enter the appropriate components. 4c totals 4a + 4b; do not count all three as separate income. Review SE-tax treatment."},
    "4b": {"label": "Box 4b — Guaranteed payments for capital",
           "why": "Guaranteed payments are taxable income; services and capital payments can have different self-employment treatment.",
           "note": "Enter the appropriate components. 4c totals 4a + 4b; do not count all three as separate income. Review SE-tax treatment."},
    "4c": {"label": "Box 4c — Total guaranteed payments",
           "why": "Total of 4a + 4b.",
           "note": "Do not count 4a, 4b and 4c as separate income. Review SE-tax treatment."},
    "5": {"label": "Box 5 — Interest income",
          "why": "Reports taxable interest.", "note": "Generally portfolio income rather than ordinary business income."},
    "6a": {"label": "Box 6a — Ordinary dividends",
           "why": "Reports total ordinary dividends, including the qualified portion.", "note": ""},
    "6b": {"label": "Box 6b — Qualified dividends",
           "why": "Identifies the part of 6a eligible for qualified-dividend rates.",
           "note": "Enter in the qualified-dividend field. Do not add it to 6a as additional ordinary dividends."},
    "6c": {"label": "Box 6c — Dividend equivalents",
           "why": "Generally reports ordinary dividend income.", "note": "Review statement; usually not qualified dividends."},
    "7": {"label": "Box 7 — Royalties",
          "why": "Reports royalty income.", "note": "Review related deductions and activity classification."},
    "8": {"label": "Box 8 — Net short-term capital gain (loss)",
          "why": "", "note": "Enter as short-term capital gain/loss; generally flows directly to Schedule D.", "f1040": "Schedule D"},
    "9a": {"label": "Box 9a — Net long-term capital gain (loss)",
           "why": "", "note": "Enter as long-term capital gain/loss."},
    "9b": {"label": "Box 9b — Collectibles (28%) gain (loss)",
           "why": "Identifies a special-rate component of the reported capital gain/loss.",
           "note": "Enter in its designated field. Do not add it again to 9a. Check the resulting capital-gain rate calculation."},
    "9c": {"label": "Box 9c — Unrecaptured §1250 gain",
           "why": "Identifies gain potentially subject to the special maximum 25% rate.",
           "note": "Enter separately for the rate calculation. It is not additional gain to add to 9a or 10."},
    "10": {"label": "Box 10 — Net section 1231 gain (loss)", "passive": True,
           "why": "Business-property gain/loss requires §1231 treatment rather than automatic capital-gain classification.",
           "note": "Review the prior five years’ nonrecaptured §1231 losses. They can cause current gain to be treated as ordinary income."},
    "11C": {"label": "Box 11 C — Section 1256 contracts and straddles", "where": "K1-2", "f1040": "Form 6781 → Schedule D",
            "note": "Form 6781 — 40% short-term / 60% long-term capital gain (loss).",
            "why": "Section 1256 contracts are marked to market at year-end; the gain or loss is treated as 60% long-term and 40% short-term regardless of how long they were held."},
    "11*": {"label": "Box 11 — Other income (loss)", "general": True,
            "why": "The code determines treatment; this box does not represent one uniform income category.",
            "note": "Read the statement and select the matching entry. Examples include §1256 contracts and cancellation of debt requiring separate forms or exclusion review."},
    "12": {"label": "Box 12 — Section 179 deduction",
           "why": "The partnership passes through a deduction, but partner-level limits still apply.",
           "note": "Enter the amount and prior carryforward. Verify the allowed deduction and carryforward after income and other limitations."},
    "13A": {"label": "Box 13 A — Charitable contributions (cash, 60%)", "group": "charity"},
    "13B": {"label": "Box 13 B — Charitable contributions (cash, 30%)", "group": "charity"},
    "13C": {"label": "Box 13 C — Noncash contributions (50%)", "group": "charity"},
    "13D": {"label": "Box 13 D — Noncash contributions (30%)", "group": "charity"},
    "13E": {"label": "Box 13 E — Capital gain property to a 50% org (30%)", "group": "charity"},
    "13F": {"label": "Box 13 F — Capital gain property (20%)", "group": "charity"},
    "13G": {"label": "Box 13 G — Contributions (100%)", "group": "charity"},
    "13H": {"label": "Box 13 H — Investment interest expense", "f1040": "Form 4952",
            "why": "This is the actual investment-interest expense evaluated on Form 4952.",
            "note": "Enter in the investment-interest field and include prior carryforward. The deduction generally cannot exceed net investment income."},
    "13K": {"label": "Box 13 K — Excess business interest expense", "where": "K1-6 → Business interest section", "f1040": "Form 8990",
            "why": "EBIE generally remains suspended until qualifying income from the same partnership allows its use.",
            "note": "Track prior carryforwards. Receiving EBIE can require Form 8990 even for an otherwise exempt individual."},
    "13M": {"label": "Box 13 M — Medical insurance",
            "why": "May support the self-employed health insurance deduction when eligibility requirements are met.",
            "note": "Check business-established coverage, earnings limits, and employer-plan eligibility. Do not deduct the same premiums again on Schedule A."},
    "13R": {"label": "Box 13 R — Retirement contributions",
            "why": "May support a partner’s retirement-plan deduction rather than an ordinary partnership expense.",
            "note": "Confirm plan type and eligible earnings. Coordinate all contribution entries so the same contribution is deducted only once."},
    "13V": {"label": "Box 13 V — §743(b) negative adjustment",
            "why": "Reports a partner-specific income adjustment associated with the partnership interest.",
            "note": "Use the statement’s activity allocation. Reconcile with other entries so the adjustment is applied once."},
    "13AE": {"label": "Box 13 AE — Portfolio deductions", "ut_warning": "Has to be entered manually to decrease basis.",
             "where": "K1-3 → “Portfolio deductions – subject to 2% of AGI limitation” (directly below 13L) — state only\nPBasis1 → Other decreases in Basis",
             "note": "Portfolio or production-of-income expenses under IRC § 212 are separately stated partnership items, but miscellaneous itemized deductions subject to the 2%-of-AGI limitation are disallowed for federal individual income tax purposes after 2017.",
             "why": "Portfolio expenses, such as investment-management fees. Not deductible on the individual's federal 1040 for {year}.",
             "f1040": "Not on federal 1040 — state only"},
    "13ZZ": {"label": "Box 13 ZZ — Other deductions", "where": "K1-3",
             "note": "The statement identifies the expense and determines the form — 13ZZ doesn't automatically go to Schedule A. Generally reduces outside basis even if the client takes the standard deduction; some items have special rules, so identify the expense first.\nUltraTax seems to incorrectly deduct it as a K-1 loss on Schedule E.",
             "why": "Expenses passed through by the partnership that are reported separately on the individual return rather than deducted against partnership business income. Eligibility and deduction limits are determined on the 1040; they generally give a tax benefit only if the client itemizes.",
             "f1040": "Schedule E (UltraTax deducts it as a K-1 loss)"},
    "13*": {"label": "Box 13 — Other deductions", "general": True,
            "why": "Some codes require special treatment, elections, or deduction eligibility review.",
            "note": "Read the statement before entering. A reported expense does not automatically qualify as a current individual deduction."},
    "14A": {"label": "Box 14 A — Self-employment earnings (loss)", "f1040": "Schedule SE",
            "why": "Supplies earnings for the SE-tax calculation; the underlying income is reported elsewhere.",
            "note": "Enter in the SE-earnings field. Do not add it again as income. Review partner status and payment character."},
    "14B": {"label": "Box 14 B — Gross farming or fishing income",
            "why": "Supports optional SE methods and certain farming/fishing determinations.",
            "note": "Enter when relevant to those calculations. These are not additional amounts of taxable income."},
    "14C": {"label": "Box 14 C — Gross nonfarm income",
            "why": "Supports optional SE methods.",
            "note": "Enter when relevant to those calculations. These are not additional amounts of taxable income."},
    "15O": {"label": "Box 15 O — Backup withholding", "f1040": "Tax payments (withholding)",
            "why": "Represents federal income tax already withheld.",
            "note": "Enter as withholding, not as a business credit. Verify that it reaches the tax-payment section of the return."},
    "15*": {"label": "Box 15 — Credits", "general": True, "f1040": "Form 3800 where applicable",
            "why": "Each credit follows its own rules and may be limited or carried forward.",
            "note": "Enter by code. Review passive-credit limitations and Form 3800 calculations where applicable."},
    "16": {"label": "Box 16 — Schedule K-3 attached",
           "why": "K-3 can supply foreign-source income and information needed for international calculations.",
           "note": "Review K-3. Enter applicable detail, including source and income category. Do not treat foreign-source amounts as extra income when already reported on the K-1."},
    "17A": {"label": "Box 17 A — Post-1986 depreciation adjustment", "where": "K1-5 → Post-1986 depreciation adjustment",
            "why": "Supplies adjustments for the alternative minimum tax calculation.",
            "note": "Enter in the AMT fields. Do not increase regular taxable income again merely because an AMT amount is reported."},
    "17*": {"label": "Box 17 — AMT items", "general": True,
            "why": "Supplies adjustments for the alternative minimum tax calculation.",
            "note": "Enter in the AMT fields. Do not increase regular taxable income again merely because an AMT amount is reported."},
    "18A": {"label": "Box 18 A — Tax-exempt interest",
            "why": "Reports exempt interest and generally increases partnership basis.",
            "note": "Enter in the tax-exempt interest field. It belongs on the return even though it is not federally taxable interest."},
    "18B": {"label": "Box 18 B — Other tax-exempt income",
            "why": "Generally affects basis without creating taxable income.",
            "note": "Enter as other tax-exempt income. Review the statement for additional consequences specific to the item."},
    "18C": {"label": "Box 18 C — Nondeductible expenses", "where": "K1-5", "ut_warning": "UT will decrease basis.",
            "why": "Generally reduces basis even though no tax deduction is allowed.",
            "note": "Enter in the nondeductible-expense field. Omitting it can overstate basis and allow excessive future losses."},
    "19A": {"label": "Box 19 A — Cash and marketable securities", "where": "K1-5",
            "note": "Cash and marketable securities. It doesn’t include deemed distributions (Code D).",
            "why": "Distributions generally reduce basis; cash exceeding basis can trigger gain."},
    "19B": {"label": "Box 19 B — Distribution subject to section 737",
            "note": "You contributed section 704(c) built-in gain property to the partnership and the partnership during the tax year distributed property; you may be required to recognize gain under section 737.",
            "flag": F7217, "f1040": "Form 7217",
            "why": "Distributions generally reduce basis; some trigger gain or property reporting."},
    "19C": {"label": "Box 19 C — Other property",
            "note": "", "flag": F7217, "f1040": "Form 7217",
            "why": "Distributions generally reduce basis; some trigger gain or property reporting."},
    "19F": {"label": "Box 19 F — Cash / marketable securities for performing services",
            "note": "Code F is used to report any distribution of cash or marketable securities treated as money made to you for performing services.",
            "why": "Distributions generally reduce basis; some trigger gain or property reporting."},
    "19G": {"label": "Box 19 G — Property distributed for performing services",
            "note": "Code G is used to report any property that was distributed to you for performing services. In addition, the partnership should report the adjusted basis and FMV of each property distributed to you in a statement attached to your Schedule K-1.",
            "flag": F7217, "f1040": "Form 7217",
            "why": "Distributions generally reduce basis; some trigger gain or property reporting."},
    "19D": {"label": "Box 19 D — Deemed distributions (decrease in share of liabilities)",
            "where": "Do not enter — must match the liability change entered in PBasis1", "ut_warning": "Do not enter — must match the liability change entered in PBasis1.",
            "why": "Represents the decrease in the partner's share of liabilities, already captured through PBasis1.",
            "note": "Should not be entered; confirm it matches the K1 liability change."},
    "19*": {"label": "Box 19 — Distributions", "general": True, "f1040": "Form 7217 (property distributions)",
            "why": "Distributions generally reduce basis; some trigger gain or property reporting.",
            "note": "Enter by type. Review cash exceeding basis and property distributions requiring Form 7217; UT uses PBasis1 information to determine excess-distribution gain treatment."},
    "20A": {"label": "Box 20 A — Investment income", "where": "K1-6 → Investment income", "f1040": "Form 4952",
            "where_note": "Do not add 20A as additional taxable income — the income is already reported in the other K-1 boxes.",
            "why": "These amounts support Form 4952, which limits the investment-interest deduction.",
            "note": "Information used for Form 4952, which limits the investment interest expense deduction. It generally includes Box 5 interest plus other qualifying investment income."},
    "20B": {"label": "Box 20 B — Investment expenses", "f1040": "Form 4952",
            "where_note": "Do not enter — already included in Box 13 AE (Portfolio deductions).",
            "why": "Supports Form 4952’s net-investment-income calculation, not additional income or deductions.",
            "note": "Enter applicable code B support, but do not claim an automatic second deduction."},
    "20N": {"label": "Box 20 N — Business interest expense", "where": "K1-6",
            "why": "Identifies business interest already deducted elsewhere on the K-1; it is not another deductible expense.",
            "note": "Business interest expenses, added back to ordinary income for QBI calculations."},
    "20Z": {"label": "Box 20 Z — §199A information", "where": "K1QBI",
            "why": "Supports the QBI deduction using activity-specific QBI, wages, UBIA, and other statement details.",
            "note": "Do not assume QBI equals box 1, and do not add wages or UBIA to income."},
    "20AE": {"label": "Box 20 AE — Excess taxable income", "where": "K1-6",
             "why": "Supports §163(j) calculations and can release prior EBIE from the same partnership.",
             "note": "Enter with the related carryforward. These amounts are not extra income."},
    "20AF": {"label": "Box 20 AF — Excess business interest income", "where": "K1-6",
             "why": "Supports §163(j) calculations and can release prior EBIE from the same partnership.",
             "note": "Enter with the related carryforward. These amounts are not extra income."},
    "20AG": {"label": "Box 20 AG — Gross receipts", "where": "Do not enter in UT — no field for it (info only)",
             "why": "Supports gross-receipts tests used for certain small-business exceptions.",
             "note": "Taxpayer share of partnership gross receipts for the §448(c) gross-receipts test, primarily relevant to the business-interest limitation under §163(j)/Form 8990"},
    "20AJ": {"label": "Box 20 AJ — Excess business loss information", "f1040": "Form 461",
             "why": "Helps identify business amounts for the excess-business-loss calculation on Form 461.",
             "note": "Compare with UT’s existing activity classification and adjust if necessary. Do not enter the statement totals again as income and expense."},
    "20AB": {"label": "Box 20 AB — §751 gain on sale of interest", "f1040": "Form 4797",
             "why": "Identifies the ordinary-income component of a partnership-interest disposition.",
             "note": "Coordinate Form 4797 with the capital portion of the sale. Do not report the ordinary component again as capital gain."},
    "20*": {"label": "Box 20 — Other information", "general": True,
            "why": "Can contain recapture, NIIT, disclosure, or other information requiring separate treatment.",
            "note": "Review every statement. Some items require entries or attachments; others explain amounts already reported."},
    "21": {"label": "Box 21 — Foreign taxes paid or accrued", "where": "K1-4 Foreign — will take to Form 1116", "f1040": "Form 1116",
           "why": "Can support a foreign tax credit or an elected deduction, subject to the relevant rules.",
           "note": "Coordinate with K-3 and the paid/accrued method. Do not claim both a credit and deduction for the same tax."},
    "22": {"label": "Box 22 — More than one activity (at-risk)",
           "why": "Indicates separate at-risk activities within one partnership.",
           "note": "Use the activity breakdown to create appropriate separate inputs. Do not assume one K-1 means one combined limitation calculation."},
    "23": {"label": "Box 23 — More than one activity (passive)",
           "why": "Indicates separate passive activities within one partnership.",
           "note": "Use the activity breakdown to create appropriate separate inputs. Do not assume one K-1 means one combined limitation calculation."},
}

_CHARITY = {
    "why": "Contribution type and percentage category affect the allowable deduction and carryforward.",
    "note": "Preserve the categories. Review noncash documentation and Form 8283 requirements; an entered contribution is not necessarily fully deductible.",
    "f1040": "Schedule A (Form 8283 for noncash)",
}
for _k, _r in RULES.items():
    if _r.get("group") == "charity":
        for _f, _v in _CHARITY.items():
            _r.setdefault(_f, _v)
    _r.setdefault("where", "")
    _r.setdefault("note", "")
    _r.setdefault("why", "")
    _r.setdefault("f1040", "")
    _r.setdefault("ut_warning", "")
    _r.setdefault("flag", "")
    _r.setdefault("where_note", "")

# Boxes 1-11 are entered on UT screen K1-2 (Lady), unless a rule names a special spot
_K12 = {"1", "2", "3", "4a", "4b", "4c", "5", "6a", "6b", "6c", "7", "8", "9a", "9b", "9c", "10", "11*"}
for _k in _K12:
    if _k in RULES and not RULES[_k]["where"]:
        RULES[_k]["where"] = "K1-2"

# display order for totals
ORDER = ["1", "2", "3", "4a", "4b", "4c", "5", "6a", "6b", "6c", "7", "8", "9a", "9b", "9c", "10", "11",
         "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23"]


def rule_for(box: str, code: str | None):
    """Exact rule, else the box's general rule (e.g. '13*'), else None."""
    key = box + (code or "")
    if key in RULES:
        return key, RULES[key]
    if box + "*" in RULES:
        return box + "*", RULES[box + "*"]
    return None, None
