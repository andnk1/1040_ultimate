"""k1_codes.py - the one list of Schedule K-1 (Form 1065) boxes and codes: UltraTax + IRS, UltraTax wins (2026-11-05, item 3).

Replaces statement_codes.py. Used by the K-1 pages (statement-amount dropdowns, K-1 Prep descriptions and the "code not in UT"
problem) and by "Export for UT data entry" (the CSV's valid_in_ut column - UT Data Entry keeps no code list of its own).

The list lives here, in the code (Lady): change a row here, then refresh the reference copy with

    python -m core.k1v.k1_codes          (writes reference\\K-1 1065 statement codes.csv)

tests\\test_k1codes.py fails when that CSV is not the same as this list. Check the list after each UltraTax release.

One row = (box, code, UT description, IRS description, IRS status, in UT, note)
  code            "" = the box itself (boxes without codes, and the heading of a code box)
  UT description  only where UltraTax's dropdown wording is known and differs from the IRS wording ("" = same / not seen yet)
  IRS description IRS 2025 Partner's Instructions (list of codes)
  IRS status      "Active" | "Reserved"
  in UT           "Y" seen in UltraTax's dropdown | "?" assumed, not checked in UltraTax yet (counts as valid)
                  | "N" not in UltraTax (enter by hand) | "" a box without codes
"""
from __future__ import annotations

import csv
from pathlib import Path

TAX_YEAR = 2025
REFERENCE_CSV = Path(__file__).resolve().parents[2] / "reference" / "K-1 1065 statement codes.csv"
CSV_HEAD = ["Box", "Code", "UT description", "IRS description (2025)", "IRS status", "In UT", "Note"]
IN_UT_TEXT = {"Y": "Yes (seen in UT)", "?": "Assumed (not checked in UT)", "N": "No", "": "—"}

CODES = [
    ('1', '', '', 'Ordinary business income (loss)', 'Active', '', ''),
    ('2', '', '', 'Net rental real estate income (loss)', 'Active', '', ''),
    ('3', '', '', 'Other net rental income (loss)', 'Active', '', ''),
    ('4a', '', '', 'Guaranteed payments for services', 'Active', '', ''),
    ('4b', '', '', 'Guaranteed payments for capital', 'Active', '', ''),
    ('4c', '', '', 'Total guaranteed payments', 'Active', '', ''),
    ('5', '', '', 'Interest income', 'Active', '', ''),
    ('6a', '', '', 'Ordinary dividends', 'Active', '', ''),
    ('6b', '', '', 'Qualified dividends', 'Active', '', ''),
    ('6c', '', '', 'Dividend equivalents', 'Active', '', ''),
    ('7', '', '', 'Royalties', 'Active', '', ''),
    ('8', '', '', 'Net short-term capital gain (loss)', 'Active', '', ''),
    ('9a', '', '', 'Net long-term capital gain (loss)', 'Active', '', ''),
    ('9b', '', '', 'Collectibles (28%) gain (loss)', 'Active', '', ''),
    ('9c', '', '', 'Unrecaptured section 1250 gain', 'Active', '', ''),
    ('10', '', '', 'Net section 1231 gain (loss)', 'Active', '', ''),
    ('11', '', '', 'Other income (loss) — by code', 'Active', '', ''),
    ('11', 'A', '', 'Other portfolio income (loss)', 'Active', '?', ''),
    ('11', 'B', '', 'Involuntary conversions', 'Active', '?', ''),
    ('11', 'C', '', 'Section 1256 contracts and straddles', 'Active', '?', ''),
    ('11', 'D', '', 'Mining exploration costs recapture', 'Active', '?', ''),
    ('11', 'E', '', 'Cancellation of debt', 'Active', '?', ''),
    ('11', 'F', '', 'Section 743(b) positive income adjustments', 'Active', '?', ''),
    ('11', 'G', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('11', 'H', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('11', 'I', '', 'Gain from disposition of oil, gas, geothermal property', 'Active', '?', ''),
    ('11', 'J', '', 'Recoveries of tax benefit items', 'Active', '?', ''),
    ('11', 'K', '', 'Gambling gains and losses', 'Active', '?', ''),
    ('11', 'L', '', 'Distribution under section 751(b)', 'Active', '?', ''),
    ('11', 'M', '', 'Gain eligible for section 1045 rollover (replacement purchased)', 'Active', '?', ''),
    ('11', 'N', '', 'Gain eligible for section 1045 rollover (replacement not purchased)', 'Active', '?', ''),
    ('11', 'O', '', 'Sale or exchange of QSB stock with section 1202 exclusion', 'Active', '?', ''),
    ('11', 'P', '', 'Farm recapture property and section 1252 items', 'Active', 'Y', ''),
    ('11', 'Q', '', 'Fannie Mae/Freddie Mac qualified preferred stock gain/loss', 'Active', 'Y', ''),
    ('11', 'R', '', 'Specially allocated ordinary gain (loss)', 'Active', 'Y', ''),
    ('11', 'S', '', 'Non-portfolio capital gain (loss)', 'Active', 'Y', ''),
    ('11', 'T', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('11', 'U', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('11', 'V', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('11', 'W', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('11', 'X', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('11', 'ZZ', '', 'Other', 'Active', 'Y', ''),
    ('12', '', '', 'Section 179 deduction', 'Active', '', ''),
    ('13', '', '', 'Other deductions — by code', 'Active', '', ''),
    ('13', 'A', '', 'Cash contributions (60%)', 'Active', 'Y', ''),
    ('13', 'B', '', 'Cash contributions (30%)', 'Active', 'Y', ''),
    ('13', 'C', '', 'Noncash contributions (50%)', 'Active', 'Y', ''),
    ('13', 'D', '', 'Noncash contributions (30%)', 'Active', 'Y', ''),
    ('13', 'E', '', 'Capital gain property to 50% organization (30%)', 'Active', 'Y', ''),
    ('13', 'F', '', 'Capital gain property (20%)', 'Active', 'Y', ''),
    ('13', 'G', '', 'Contributions (100%)', 'Active', 'Y', ''),
    ('13', 'H', '', 'Investment interest expense', 'Active', 'Y', ''),
    ('13', 'I', '', 'Deductions—royalty income', 'Active', 'Y', ''),
    ('13', 'J', '', 'Section 59(e)(2) expenditures', 'Active', 'Y', ''),
    ('13', 'K', '', 'Excess business interest expense', 'Active', 'Y', ''),
    ('13', 'L', '', 'Deductions—portfolio income (other)', 'Active', 'Y', ''),
    ('13', 'M', '', 'Amounts paid for medical insurance', 'Active', 'Y', ''),
    ('13', 'N', '', 'Educational assistance benefits', 'Active', 'Y', ''),
    ('13', 'O', '', 'Dependent care benefits', 'Active', 'Y', ''),
    ('13', 'P', '', 'Preproductive period expenses', 'Active', 'Y', ''),
    ('13', 'Q', '', 'Reserved for future use', 'Reserved', 'Y', 'DIFFERENCE: reserved by the IRS, but listed in UT'),
    ('13', 'R', '', 'Pensions and IRAs', 'Active', 'Y', ''),
    ('13', 'S', '', 'Reforestation expense deduction', 'Active', 'Y', ''),
    ('13', 'T', '', 'Reserved for future use', 'Reserved', 'Y', 'DIFFERENCE: reserved by the IRS, but listed in UT'),
    ('13', 'U', 'Reserved', 'Reserved for future use', 'Reserved', 'N', 'Reserved in UT'),
    ('13', 'V', '', 'Section 743(b) negative income adjustments', 'Active', 'Y', ''),
    ('13', 'W', '', 'Soil and water conservation', 'Active', 'Y', ''),
    ('13', 'X', '', 'Qualified film, television, theatrical, sound recording production', 'Active', 'Y', ''),
    ('13', 'Y', '', 'Expenditures for removal of barriers', 'Active', 'Y', ''),
    ('13', 'Z', '', 'Itemized deductions', 'Active', 'Y', ''),
    ('13', 'AA', '', 'Contributions to capital construction fund', 'Active', 'Y', ''),
    ('13', 'AB', '', 'Penalty on early withdrawal of savings', 'Active', 'Y', ''),
    ('13', 'AC', '', 'Interest expense allocated to debt-financed distributions', 'Active', 'Y', ''),
    ('13', 'AD', '', 'Interest expense on working interest in oil or gas', 'Active', 'Y', ''),
    ('13', 'AE', '', 'Deductions—portfolio income', 'Active', 'Y', ''),
    ('13', 'AF', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('13', 'AG', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('13', 'AH', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('13', 'AI', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('13', 'AJ', '', 'Reserved for future use', 'Reserved', 'N', ''),
    ('13', 'ZZ', '', 'Other', 'Active', 'Y', ''),
    ('14', '', '', 'Self-employment earnings (loss) — by code', 'Active', '', ''),
    ('14', 'A', '', 'Net earnings (loss) from self-employment', 'Active', 'Y', ''),
    ('14', 'B', '', 'Gross farming or fishing income', 'Active', 'Y', ''),
    ('14', 'C', 'Gross non-farm income', 'Gross nonfarm income', 'Active', 'Y', ''),
    ('15', '', '', 'Credits — by code', 'Active', '', ''),
    ('15', 'A', 'Zero-emission nuclear power production', 'Zero-emission nuclear power production credit', 'Active', 'Y', ''),
    ('15', 'B', 'Production from advanced nuclear power facilities credit', 'Advanced nuclear power facilities production credit', 'Active', 'Y', ''),
    ('15', 'C', 'Low-income housing credit (sec. 42(j)(5)) from post-2007 buildings', 'Low-income housing credit (section 42(j)(5))', 'Active', 'Y', ''),
    ('15', 'D', 'Low-income housing credit (other) from post-2007 buildings', 'Low-income housing credit (other)', 'Active', 'Y', ''),
    ('15', 'E', '', 'Qualified rehabilitation expenditures (rental real estate)', 'Active', 'Y', ''),
    ('15', 'F', '', 'Other rental real estate credits', 'Active', '?', ''),
    ('15', 'G', '', 'Other rental credits', 'Active', '?', ''),
    ('15', 'H', '', 'Undistributed capital gains credit', 'Active', '?', ''),
    ('15', 'I', '', 'Biofuel producer credit', 'Active', '?', ''),
    ('15', 'J', '', 'Work opportunity credit', 'Active', '?', ''),
    ('15', 'K', '', 'Disabled access credit', 'Active', '?', ''),
    ('15', 'L', '', 'Empowerment zone employment credit', 'Active', '?', ''),
    ('15', 'M', '', 'Credit for increasing research activities', 'Active', '?', ''),
    ('15', 'N', '', 'Credit for employer social security and Medicare taxes', 'Active', '?', ''),
    ('15', 'O', '', 'Backup withholding', 'Active', '?', ''),
    ('15', 'P', '', 'Unused investment credit (cooperatives) — advanced coal / gasification project', 'Active', '?', ''),
    ('15', 'Q', '', 'Unused investment credit (cooperatives) — advanced energy project', 'Active', '?', ''),
    ('15', 'R', '', 'Unused investment credit (cooperatives) — advanced manufacturing investment', 'Active', '?', ''),
    ('15', 'S', '', 'Unused investment credit (cooperatives) — clean electricity investment', 'Active', '?', ''),
    ('15', 'T', '', 'Unused investment credit (cooperatives) — energy credit', 'Active', '?', ''),
    ('15', 'U', '', 'Unused investment credit (cooperatives) — rehabilitation credit', 'Active', '?', ''),
    ('15', 'V', '', 'Advanced manufacturing production credit', 'Active', '?', ''),
    ('15', 'W', '', 'Clean electricity production credit', 'Active', '?', ''),
    ('15', 'X', '', 'Clean fuel production credit', 'Active', '?', ''),
    ('15', 'Y', '', 'Clean hydrogen production credit', 'Active', '?', ''),
    ('15', 'Z', '', 'Orphan drug credit', 'Active', '?', ''),
    ('15', 'AA', '', 'Enhanced oil recovery credit', 'Active', '?', ''),
    ('15', 'AB', '', 'Renewable electricity production credit', 'Active', '?', ''),
    ('15', 'AC', '', 'Biodiesel, renewable diesel, or sustainable aviation fuels credit', 'Active', '?', ''),
    ('15', 'AD', '', 'New markets credit', 'Active', '?', ''),
    ('15', 'AE', '', 'Small employer pension plan startup costs and contributions credit', 'Active', '?', ''),
    ('15', 'AF', '', 'Small employer auto-enrollment credit', 'Active', '?', ''),
    ('15', 'AG', '', 'Small employer military spouse participation credit', 'Active', '?', ''),
    ('15', 'AH', 'Credit for employer-provided childcare facilities and services', 'Employer-provided childcare facilities and services credit', 'Active', 'Y', ''),
    ('15', 'AI', '', 'Low sulfur diesel fuel production credit', 'Active', 'Y', ''),
    ('15', 'AJ', '', 'Qualified railroad track maintenance credit', 'Active', 'Y', ''),
    ('15', 'AK', 'Credit for oil and gas production from marginal wells', 'Oil and gas production from marginal wells credit', 'Active', 'Y', ''),
    ('15', 'AL', '', 'Distilled spirits credit', 'Active', 'Y', ''),
    ('15', 'AM', '', 'Energy efficient home credit', 'Active', 'Y', ''),
    ('15', 'AN', '', 'Reserved for future use (IRS heading only, no description)', 'Reserved', '?', 'CHECK: reserved by the IRS, assumed in the UT list'),
    ('15', 'AO', '', 'Alternative fuel vehicle refueling property credit', 'Active', '?', ''),
    ('15', 'AP', '', 'Clean renewable energy bond credit', 'Active', '?', ''),
    ('15', 'AQ', '', 'New clean renewable energy bond credit', 'Active', '?', ''),
    ('15', 'AR', '', 'Qualified energy conservation bond credit', 'Active', '?', ''),
    ('15', 'AS', '', 'Qualified zone academy bond credit', 'Active', '?', ''),
    ('15', 'AT', '', 'Qualified school construction bond credit', 'Active', '?', ''),
    ('15', 'AU', '', 'Build America bond credit', 'Active', '?', ''),
    ('15', 'AV', '', 'Employer differential wage payments credit', 'Active', '?', ''),
    ('15', 'AW', '', 'Carbon oxide sequestration credit', 'Active', '?', ''),
    ('15', 'AX', '', 'Carbon oxide sequestration credit recapture', 'Active', '?', ''),
    ('15', 'AY', '', 'New clean vehicle credit', 'Active', 'Y', ''),
    ('15', 'AZ', 'Qualified commercial clean vehicle credit', 'Qualified commercial clean vehicles credit', 'Active', 'Y', ''),
    ('15', 'BA', 'Credit for small employer health insurance premiums', 'Small employer health insurance premiums credit', 'Active', 'Y', ''),
    ('15', 'BB', '', 'Employer credit for paid family and medical leave', 'Active', 'Y', ''),
    ('15', 'BC', '', 'Eligible credits from transferor(s) under section 6418', 'Active', 'Y', ''),
    ('15', 'BD', '', 'Reserved for future use (IRS heading only, no description)', 'Reserved', 'N', ''),
    ('15', 'BE', '', 'Reserved for future use (IRS heading only, no description)', 'Reserved', 'N', ''),
    ('15', 'BF', '', 'Reserved for future use (IRS heading only, no description)', 'Reserved', 'N', ''),
    ('15', 'BG', '', 'Reserved for future use (IRS heading only, no description)', 'Reserved', 'N', ''),
    ('15', 'ZZ', '', 'Other credits', 'Active', 'Y', ''),
    ('16', '', '', 'Schedule K-3 is attached (checkbox)', 'Active', '', ''),
    ('17', '', '', 'Alternative minimum tax (AMT) items — by code', 'Active', '', ''),
    ('17', 'A', '', 'Post-1986 depreciation adjustment', 'Active', 'Y', ''),
    ('17', 'B', '', 'Adjusted gain or loss', 'Active', 'Y', ''),
    ('17', 'C', '', 'Depletion (other than oil & gas)', 'Active', 'Y', ''),
    ('17', 'D', 'Oil, gas, & geothermal - gross income', 'Oil, gas, & geothermal properties — gross income', 'Active', 'Y', ''),
    ('17', 'E', 'Oil, gas, & geothermal - deductions', 'Oil, gas, & geothermal properties — deductions', 'Active', 'Y', ''),
    ('17', 'F', '', 'Other AMT items', 'Active', 'Y', ''),
    ('18', '', '', 'Tax-exempt income and nondeductible expenses — by code', 'Active', '', ''),
    ('18', 'A', '', 'Tax-exempt interest income', 'Active', 'Y', ''),
    ('18', 'B', '', 'Other tax-exempt income', 'Active', 'Y', ''),
    ('18', 'C', '', 'Nondeductible expenses', 'Active', 'Y', ''),
    ('19', '', '', 'Distributions — by code', 'Active', '', ''),
    ('19', 'A', 'Cash and marketable securities', 'Cash and marketable securities (other than for services)', 'Active', 'Y', ''),
    ('19', 'B', '', 'Distribution subject to section 737', 'Active', 'Y', ''),
    ('19', 'C', '', 'Other property', 'Active', 'Y', ''),
    ('19', 'D', 'Deemed dist of money - decrease in ptr share liabilities', 'Deemed distributions of money — decrease in share of liabilities', 'Active', 'Y', ''),
    ('19', 'E', 'Reserved', 'Reserved for future use (IRS heading only, no description)', 'Reserved', 'N', 'Reserved in UT'),
    ('19', 'F', 'Dist of cash or marketable securities for performing services', 'Cash and marketable securities for performing services', 'Active', 'Y', ''),
    ('19', 'G', 'Dist of prop other than cash or marketable securities for services', 'Property distributed for performing services', 'Active', 'Y', ''),
    ('20', '', '', 'Other information — by code', 'Active', '', ''),
    ('20', 'A', '', 'Investment income', 'Active', '?', ''),
    ('20', 'B', '', 'Investment expenses', 'Active', '?', ''),
    ('20', 'C', '', 'Fuel tax credit information', 'Active', '?', ''),
    ('20', 'D', '', 'Qualified rehabilitation expenditures (other than rental real estate)', 'Active', '?', ''),
    ('20', 'E', '', 'Basis of energy property', 'Active', '?', ''),
    ('20', 'F', '', 'Recapture of low-income housing credit (section 42(j)(5))', 'Active', '?', ''),
    ('20', 'G', '', 'Recapture of low-income housing credit (other)', 'Active', '?', ''),
    ('20', 'H', '', 'Recapture of investment credit', 'Active', '?', ''),
    ('20', 'I', '', 'Recapture of other credits', 'Active', '?', ''),
    ('20', 'J', '', 'Look-back interest—completed long-term contracts', 'Active', '?', ''),
    ('20', 'K', '', 'Look-back interest—income forecast method', 'Active', '?', ''),
    ('20', 'L', '', 'Dispositions of property with section 179 deductions', 'Active', '?', ''),
    ('20', 'M', '', 'Recapture of section 179 deduction', 'Active', '?', ''),
    ('20', 'N', '', 'Business interest expense', 'Active', '?', ''),
    ('20', 'O', '', 'Section 453(l)(3) information', 'Active', '?', ''),
    ('20', 'P', '', 'Section 453A(c) information', 'Active', '?', ''),
    ('20', 'Q', '', 'Section 1260(b) information', 'Active', '?', ''),
    ('20', 'R', '', 'Interest allocable to production expenditures', 'Active', '?', ''),
    ('20', 'S', '', 'Capital construction fund nonqualified withdrawals', 'Active', '?', ''),
    ('20', 'T', '', 'Depletion information—oil and gas', 'Active', '?', ''),
    ('20', 'U', '', 'Section 743(b) basis adjustment', 'Active', '?', ''),
    ('20', 'V', '', 'Unrelated business taxable income', 'Active', '?', ''),
    ('20', 'W', '', 'Precontribution gain (loss)', 'Active', '?', ''),
    ('20', 'X', '', 'Payment obligations including guarantees and deficit obligations', 'Active', '?', ''),
    ('20', 'Y', '', 'Net investment income', 'Active', '?', ''),
    ('20', 'Z', '', 'Section 199A information', 'Active', '?', ''),
    ('20', 'AA', '', 'Section 704(c) information', 'Active', '?', ''),
    ('20', 'AB', '', 'Section 751 gain (loss)', 'Active', '?', ''),
    ('20', 'AC', '', 'Section 1(h)(5) collectibles gain', 'Active', '?', ''),
    ('20', 'AD', '', 'Section 1(h)(6) unrecaptured section 1250 gain', 'Active', '?', ''),
    ('20', 'AE', '', 'Excess taxable income', 'Active', '?', ''),
    ('20', 'AF', '', 'Excess business interest income', 'Active', '?', ''),
    ('20', 'AG', '', 'Gross receipts for section 448(c)', 'Active', '?', ''),
    ('20', 'AH', '', 'Noncash charitable contributions', 'Active', '?', ''),
    ('20', 'AI', '', 'Interest and tax on deferred compensation to partners', 'Active', '?', ''),
    ('20', 'AJ', '', 'Excess business loss limitation', 'Active', '?', ''),
    ('20', 'AK', '', 'Gain from mark-to-market election', 'Active', '?', ''),
    ('20', 'AL', '', 'Section 721(c) partnership', 'Active', '?', ''),
    ('20', 'AM', '', 'Section 1061 information', 'Active', '?', ''),
    ('20', 'AN', '', 'Farming and fishing business', 'Active', '?', ''),
    ('20', 'AO', '', 'PTP information', 'Active', '?', ''),
    ('20', 'AP', '', 'Inversion gain', 'Active', '?', ''),
    ('20', 'AQ', '', 'Conservation reserve program payments', 'Active', '?', ''),
    ('20', 'AR', '', 'IRA disclosure', 'Active', '?', ''),
    ('20', 'AS', '', 'Qualifying advanced coal project property', 'Active', '?', ''),
    ('20', 'AT', '', 'Qualifying advanced energy project property', 'Active', '?', ''),
    ('20', 'AU', '', 'Advanced manufacturing investment property', 'Active', '?', ''),
    ('20', 'AV', '', 'Clean electricity investment property', 'Active', 'Y', ''),
    ('20', 'AW', '', 'Reportable transactions', 'Active', 'Y', ''),
    ('20', 'AX', '', 'Corporate alternative minimum tax', 'Active', 'Y', ''),
    ('20', 'AY', '', 'Foreign partners, Form 8990, Schedule A', 'Active', 'Y', ''),
    ('20', 'AZ', '', 'Reimbursement of preformation expenditures', 'Active', 'Y', ''),
    ('20', 'BA', '', 'Reserved for future use (IRS heading only, no description)', 'Reserved', 'N', ''),
    ('20', 'BB', '', 'Reserved for future use (IRS heading only, no description)', 'Reserved', 'N', ''),
    ('20', 'BC', '', 'Reserved for future use (IRS heading only, no description)', 'Reserved', 'N', ''),
    ('20', 'BD', '', 'Reserved for future use (IRS heading only, no description)', 'Reserved', 'N', ''),
    ('20', 'ZZ', '', 'Other', 'Active', 'Y', ''),
    ('21', '', '', 'Foreign taxes paid or accrued', 'Active', '', ''),
    ('22', '', '', 'More than one activity for at-risk purposes (checkbox)', 'Active', '', ''),
    ('23', '', '', 'More than one activity for passive activity purposes (checkbox)', 'Active', '', ''),
]

_BY = {(b, c): (ut, irs, status, inut, note) for b, c, ut, irs, status, inut, note in CODES}
BOXES = list(dict.fromkeys(b for b, *_ in CODES))                     # every box, in form order
CODE_BOXES = list(dict.fromkeys(b for b, c, *_ in CODES if c))        # the boxes that take a code: 11, 13, 14, 15, 17 ... 20


def known(box: str, code: str | None = "") -> bool:
    return (str(box), code or "") in _BY


def desc(box: str, code: str | None = "") -> str:
    """UltraTax's description when known, else the IRS one; "" for a box / code that is not on the list."""
    r = _BY.get((str(box), code or ""))
    return (r[0] or r[1]) if r else ""


def box_name(box: str) -> str:
    return desc(box, "").replace(" — by code", "")


def in_ut(box: str, code: str | None = "") -> str:
    """"Y" | "?" | "N" as on the list; "N" for a code that is not on the list; "" for a box without codes."""
    box, code = str(box), code or ""
    if box not in CODE_BOXES:
        return ""
    r = _BY.get((box, code))
    return r[3] if r and code else "N"


def valid_in_ut(box: str, code: str | None = "") -> str:
    """The export's valid_in_ut column: Y / N, blank for a box without codes. Not-yet-checked codes count as valid."""
    f = in_ut(box, code)
    return "" if f == "" else ("N" if f == "N" else "Y")


def dropdown() -> list:
    """[box, code, description] for the statement-amount dropdowns: every code UltraTax takes."""
    return [[b, c, ut or irs] for b, c, ut, irs, status, inut, note in CODES if c and inut != "N"]


def codes_by_box() -> dict:
    """{box: [[code, description], ...]} for the K-1 Prep code dropdowns: every code of the list except the reserved ones."""
    out: dict = {}
    for b, c, ut, irs, status, inut, note in CODES:
        if c and status != "Reserved":
            out.setdefault(b, []).append([c, ut or irs])
    return out


def csv_rows() -> list:
    return [CSV_HEAD] + [[b, c, ut, irs, status, IN_UT_TEXT[inut], note] for b, c, ut, irs, status, inut, note in CODES]


def write_csv(path=None) -> Path:
    """The reference copy (Excel opens it: UTF-8 with BOM)."""
    p = Path(path or REFERENCE_CSV)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(csv_rows())
    return p


if __name__ == "__main__":
    print("written:", write_csv())
