# 1040 Ultimate

Internal return-review tool. Runs on this computer only (http://127.0.0.1:5067) — nothing is uploaded.
Contains client data: internal use only. Federal only.

## Settings (not in GitHub)
`local_settings.json` next to `app.py` holds the office values: `always_mask` (numbers masked on every document) and
`start_folders` (where the file dialogs open)
and `ut_entry` (`false` hides Bot / By hand on K-1 UT; default on). It is listed in `.gitignore`; copy `local_settings.example.json` to create it.
Client folders (`Return_Info`, `Claude_1040_skill`, `_work`) and every PDF / Excel / CSV / Word / image file are ignored too.

## Install on another computer (Windows)
Nothing in the code is tied to one computer — paths are relative to the app folder and the office values live in
`local_settings.json` (not in GitHub).
1. Install **Python 3.10 or newer** from python.org (64-bit). Tick **"Add python.exe to PATH"**; keep **tcl/tk** ticked
   (the Browse… windows use it). If the company blocks `.py` files, ask IT for an exception for the app folder.
2. Get the code: GitHub → the repository → **Code → Download ZIP** (or clone it), e.g. into `C:\dev\1040_ultimate`.
3. Copy `local_settings.example.json` to **`local_settings.json`** and fill in:
   - `always_mask`: the numbers masked on every document (the firm EIN …);
   - `start_folders`: where the Browse… windows open first (e.g. the Google Drive client folders:
     `"G:\\Shared drives\\Clients"` — double backslashes in JSON).
4. Double-click **`run.bat`**. The first run installs the Python packages (needs internet once); the browser opens at
   http://127.0.0.1:5067. Keep the black window open while working — closing it stops the app.
5. Optional:
   - port 5067 taken → set the environment variable `U1040_PORT` (e.g. 5070) before `run.bat`;
   - the master checklist (`checklist_master.json`) is created on first use — copy it from another computer to share the
     same list;
   - work in progress (`1040 Ultimate WIP … .json`) is saved next to the client's files, so it follows the client folder
     on Google Drive and opens on any computer (file paths are re-linked to the same folder).
Nothing is sent anywhere: the app runs only on this computer (127.0.0.1).

## Run (Windows)
Double-click **run.bat** (installs flask, pdfplumber, pymupdf, openpyxl the first time and opens the browser).

## Two modes
| Mode | Inputs | Status |
|---|---|---|
| **1040 Preparation tool** (summary) | prior-year return + documents folder | Step 1 built |
| **Verify return** | the same + current-year return | later |

## Folders
- `Return_Info\<Client_Year>\` — the client's documents for the year (the prior-year return can sit here too).
- `Claude_1040_skill\<Client_Year>\` — what the AI gets: the AI report + masked pages only (step 5-6).

## Screens
1. **Summary** — pick the prior-year return and the documents (Add documents… / Add a folder…; untick to skip), click **Run check**.
   - **Income summary** in the office template layout: Document/s | PY | CY Federal | ST#1-3 | Notes.
     PY totals come from the prior-year return (1040, Schedule D lines 7 / 15, Schedule E lines 26 / 32, Schedule C line 31;
     UltraTax Two Year Comparison fills gaps). CY amounts come from the documents in the next step; Schedule C fills in from the Schedule C box. **Other income** (Schedule 1 lines 8v / 8z, 1099-MISC, 1099-G) sits under Schedule C with the note "Entered as Other income". ST#1 repeats the federal amount; ST#2 / ST#3 stay empty.
   - **Prior Year Return** box: Carryovers from Prior Year · On last year's return — not received (only the ones still missing; ✓ verified + a comment per payer, and a note) · Forms filed last year
   - Document inventory (top) — see below
   - Schedule C (click to open) — PY soft-entered; 24b = deductible meals only; line 30 home office used only with a profit, capped at line 29.
2. **Mask info for AI agent** — pick documents one by one (PDF, Word, Excel, text, pictures …), check the person tabs
   (pre-filled from the prior-year 1040: names, SSNs, address, dependents), **Mask documents**, then:
   - **Save redacted documents…** → choose a folder → `redacted_<name>` for every document that was masked
   - **Save unredacted documents (copy)…** → choose a folder → plain copy of every document, names unchanged
   The results list shows what was masked, what needs a check (pages without text, values still found) and what was NOT masked (format) — those are never saved as redacted.
3. **AI review** — later.

## What the program reads (2025 column)
| Document | Read | Goes to |
|---|---|---|
| W-2 | box 1 / box 2 only from labels with the IRS box names (table or list layout); a summary page without box names is not read; copies B/2/C counted once; several W-2s in one file added; box 12 DD noted. Every other box (a–f, 3–14, state 15–17 and local 18–20 rows, as printed) is read for the W-2 form view (table layouts, e.g. ADP / IRS); an ADP "box 12 or 14 overflow" page joins the W-2 before it. A W-2 printed as a picture (no text) is not read | W-2 |
| 1099 composite / 1099-INT / DIV / B / MISC / OID — Schwab, Fidelity / National Financial, M1, Robinhood, Apex-style | INT 1+3, OID; DIV 1a (1b noted), 2a → LT; 1099-B Total short-/long-term gain (or the reported / not-reported rows); §1256 aggregate split 60/40; MISC 3 + 8 → Other income, MISC 2 → Rental & royalties | Interest, Dividends, LT, ST, Other, Rental |
| Schedule D (Form 1040) on its own — a crypto report (Koinly or any other program), recognized from the form | read like a 1099-B: one row per Form 8949 box from lines 1a / 1b, 2, 3 (ST) and 8a / 8b, 9, 10 (LT) — proceeds, cost, adjustments, gain in the comment; lines 4–6, 11–14 and the totals 7 / 15 are left out (other documents carry them) | ST, LT |
| Schedule 1 (Form 1040) on its own | only line 8v (digital assets received as ordinary income) and line 8z (other income, the type listed in the comment) — one row each | Other income |
| K-1 (1065) | in the K-1 section only (K-1 box → **Open K-1 Verification**, a new tab): 5 interest, 6a dividends, 8 ST, 9a+10 LT, 2+3+7 rental, 1+GP+11 ordinary. Nothing reaches the income summary until **Add to Income Summary** on the K-1 page (adding again replaces it; **Remove** in the K-1 box takes the lines off). The K-1 page's work is kept in `1040 Ultimate K-1 WIP … .json` next to the WIP file. A copy of the same K-1 (same partnership EIN, same box E, same year, same amounts) counts once; with different amounts it asks Count / Don't count. **K-1 UT** (third button on the K-1 page; spec `design\k1_prep.md`): K-1s in file-name order, box E matched to taxpayer / spouse (last 4), Part II items, a corrected amount per box, lines added under a "see statement" line or with "+ Add line" (shown on the Interpreter too), red problems, **Bot / By hand** per line (orange reason; rules in `core\k1v\ut_entry.py`), the **To enter by hand in UltraTax** list (also as Excel / PDF), and **Export for UT data entry** — the CSV the separate UT Data Entry app types into UltraTax (`bot` rows only) | per K-1 rows |
| 1099-MISC (IRS layout, e.g. Coinbase) | amounts by position in the box: 1 rents + 2 royalties → Rental, 3 + 8 → Other, 4 withholding | Rental, Other |
| 1099-NEC (IRS layout) | 1a / 1 → Schedule C (memo); 1b cash tips, 1d overtime, 3 golden parachute → Other with the box named; 4 withholding | Sch C, Other |
| 1099-INT (any layout, e.g. bank substitute forms) | label and amount on the same row: 1 (+3) interest, 2 penalty, 4 withholding, 6 foreign tax, 8 tax-exempt, bond premium → notes | Interest |
| 1099-R (IRS layout — 2025 "7 Distribution code(s)" + "IRA/SEP/SIMPLE" or older 7a / 7b — or broker text) | 2a taxable → IRA (IRA/SEP/SIMPLE checked) or Pension. The comment always says whether IRA/SEP/SIMPLE is checked and every box 7 code with its meaning (i1099r: 1-9, A-H, J-N, P-U, W, Y); 2b checks noted; non-taxable part in the note; copies on one page counted once; 4 withholding | IRA / Pension |
| 1099-SA (HSA / Archer MSA / MA MSA) | not income — a note on the inventory ("comments only"): box 1 gross distribution, box 2, code 1-6 with its meaning, box 4, account type; checked against the UT HSA / 8889 screen and Form 8889 on the return | — |
| List layout (W-2, 1099-R, 1099-SA) | the IRS boxes one per line ("1 Gross distribution ...... 450.49"): read when the box number and the IRS box name match; W-2 box 12 lines too | — |
| Box-list summary pages (e.g. Morgan Stanley stock plan: "1a. TOTAL ORDINARY DIVIDENDS ... $x", 1099-DIV and 1099-B side by side) | each row's box number + amount, the form taken from the heading above the column; used when the regular composite reader doesn't read the file. A 1099-B summary with sales but no short / long-term split is flagged | Dividends / gains |
| 1098-E | box 1 student loan interest (box 2 noted) | Deduction summary |
| 1098 (mortgage) — lender print or IRS blank | box 1 → Mortgage interest; comment: box 2, box 10 (as printed, e.g. Real estate taxes), boxes 4 / 5 / 6 when not 0, box 8 property (or box 7 checked); copies counted once | Deduction summary |
| 1099-R, SSA-1099 | 2a taxable (IRA box → IRA, else pension) · box 5 net benefits | IRA / Pension · Social Security |
Checks: 1b ≤ 1a; 1099-B gain = proceeds − cost + wash sale; a form section printed but not read → "Partly read". Anything not read → red row, AI review.
Tax-exempt interest, nondividend distributions, foreign tax, qualified dividends go in the Notes column (memo).
1099-NEC / 1099-K rows under Schedule C are memo only (already inside Schedule C gross receipts), listed under the business
they belong to (name printed on the form; one business = that one) with "check for duplicates, may be included on Schedule C for …".
A file with one 1099 form type in its title (IRS blank or a bank's substitute form) is labelled with that form, not "Composite";
the payer comes from "Payer's name:" when the issuer isn't on the list.
Capital gains: one row per Form 8949 box (A-L) when the 1099 prints it (Schwab categories, "basis reported / not reported" rows,
Robinhood A-L rows, IB "Applicable check box"); capital gain distributions (Sch D 13) and §1256 (6781) get their own rows.
Schedule D: box pair by line (1a / 1b A/G, 2 B/H, 3 C/I, 8a / 8b D/J, 9 E/K, 10 F/L) — a Form 8949 among the documents decides 1099-B vs 1099-DA by its X.
**File names decide nothing** (they're typed by hand) — the type, issuer and "received this year?" all come from the document's text. Two exceptions: "K-1" in the name sends a file to the K-1 reader (after the text check), and the Karbon organizer.

## Document inventory (top of screen 1)
Columns: Verified | File name | Issuer (from the text: a known broker / payroll name on the first two pages, the "Payer's name:" line, or the W-2 employer / 1098 lender the reader found) | Type (W-2, 1099-R, 1099 Composite (DIV, B) …; a wrong tax year in red) | Program read |
Amount | Added to | Note | AI. Sorted by file name, numbers in number order (2 before 10), numbered names first.
The section starts closed (arrow), like every section with an arrow.
- **Read** documents are listed only; their amounts are already on the income summary ("Added to" shows the lines they feed).
- **Not read** documents take one amount + the income line it goes to (**Added to**). That makes a line on the income summary
  (file name, the amount in **per document**; you can still type a corrected amount there) and replaces the "NOT READ" row for that file.
  More amounts from the same document: add them on the income summary with **+**.
- The small **+** at the bottom of the inventory adds a free line (description, issuer, amount, line, note).
- **Return Comments** (the box under the step tabs): general notes about the return — kept in the work in progress, shown on
  screen 2, in the review Excel (Checklist sheet) and the AI report.
- **✓ Verified**: the row turns light mint; the ticks go into the Excel files (Documents sheet). Screen 2 doesn't flag unticked documents.
- **AI**: the document goes to the AI (masked) — the masking list on screen 3 follows these ticks. For long documents the AI pages
  are listed in the note.


## Form tabs (inside the Document inventory)
Tabs under the Document inventory header, all the same size: **Summary** (the table above), **W2**, then 1098-M, 1098-T, 1099-B,
1099-Comp, 1099-DA, 1099-DIV, 1099-G, 1099-INT, 1099-NEC, 1099-R (alphabetical; other form types get a tab when the client has one).
"(2)" after a name = how many; no number when none. **W2** and **1098-M** work — the others say "Form view coming soon".
- **W2**: always 6 columns + Total on the screen (W-2s 7–12 on W2_2 …); each column headed by the employee name (box e) · the
  employer's first word (box c); hover shows the full employer name and the EIN. A name the program didn't read shows a message and
  the file name.
- Boxes 1–20 (box 12 / 14 / state / local lines when they have an amount; **+** adds one; state and locality on hover), a Total
  column for all the client's W-2s, a ✓ on every line. Type over a box to correct it (light pink, blue); ↺ goes back to the value read.
  Box 1 / 2 / 12 changes go to the income summary and Verify after **Refresh the income summary**; an amount typed on the income
  summary still wins.
- Excess Social Security check per employee name (2+ W-2s).
- **1098-M**: the same layout for the mortgage 1098s — header = borrower · first word of the lender (hover: lender, account, file);
  boxes 1–9 and one line per box 10 description. Changes go to the deduction summary after **Refresh the deduction summary**.

## Income and Deduction Summary — Prior Year · per document · corrected amount
One box (always open): the income table, then the deduction table. Every other section has an arrow and starts closed.
- **Prior Year** = from last year's return (comparison). **per document** = what came in (fixed): what the program read, the form
  tabs, the Schedule C / E box (after Calculate), the K-1 section, the amount typed on the document inventory. **corrected amount**
  = what goes on the return: starts as a copy, yours to change (tax interpretation) — it wins. Not-read rows, lines added with +
  and add-backs have a corrected amount only.
- When per document changes after you corrected a line (Schedule C recalculated, a form tab fix, a new inventory amount …), the
  line says "document amount changed since your correction — re-confirm"; **Re-confirm** keeps your correction.
- **Fed. w/h**: one column — the program's amount in grey (soft), type over it to change it (green). No withholding = blank.
- White lines; category totals bold with a thicker line under them (no colour, no side bar), same in the Excel file. Numbers you type or change are blue (not bold). The number columns have equal widths.
- Nothing is red: negative numbers are plain black everywhere (screens and Excel); the add-back / "minus losses carried over" rows are blue.
- Whole dollars on screen (nearest dollar); the exact amount is kept until you change the box, and Excel keeps the cents.
- A corrected amount you changed from the document has a light pink background and blue text (not bold).
- ✓ on every line and total (also deduction lines, Schedule C / E, forms filed last year; not the UT summary) — a ticked line turns
  light mint (a total a shade darker), kept with the work in progress; ticked lines are listed on the "Reviewed (✓)" sheet of the Save review Excel.
- Lines from the document inventory: amount and name are changed on the inventory; the comment can be typed here too (it is
  the inventory note — both places update).
- Every row has a comment box. The corrected amount is official data: the totals, the UT summary, screen 2, the Excel file and the
  AI report use it; the Excel file and the AI report also show per document.
- **+** next to a category total adds a line (kept for the run; lost when the program restarts).

## Screens
1 · Summary → 2 · Verify return → 3 · AI Doc Review → 4 · AI Return Review → 5 · AI Advisory (the three AI pages say what they will do — nothing behind them yet; the Mask page is no longer a step tab). Ticks (✓) sit just left of each table; buttons in the boxes are mint with green bold text, the bottom bar teal (white text). Design rules: `design/DESIGN_RULES.md`.

## 2 · Verify return
Two ways — pick the files on this screen (the input screens can also be picked on screen 1):
**With the UltraTax input screens (PDF print of the input screens)** — two parts, line by line (never totals or net amounts —
UT calculates those):
1. **Document verification** — every box the program read from a document, and every line typed on screen 1, against its UT
   entry: W-2 box 1 / box 2 (W2 screen, one per unit); 1099-INT / DIV / B (B&D screen and its statement page: interest,
   ordinary / qualified dividends, capital gain distributions, foreign tax, Form 8949 proceeds / cost / adjustment / gain by
   term); Schedule E lines vs the Rent screens; Schedule C lines vs the C screen (label-based — confirm on a real print; a
   business with the total only is a note, not checked); 1095-A / 1098-T; inventory and added lines.
   Within ±$1 ties (UT rounds; people round either way). One document amount entered in UT in pieces, or one UT entry for
   several document lines (§1256 60% / 40%), ties when the pieces add up.
   Red = data-entry difference only (not entered, different, entered on another line, other 8949 box).
   Yellow = you changed the document amount (flagged when screen 1 has no comment of yours).
2. **UltraTax entries with no document** — UT entries (and Rent / C screen lines) with nothing on screen 1 behind them.
- Every line has a ✓ and a comment box — kept with the work in progress and written to the Save review Excel.
- Payments found on the input screens (estimates, state payments) are listed for review.
- The 2025 return is optional here; with it, forms filed and payers 2024 vs 2025 are shown too.
**Without the input screens** — pick the finished 2025 return (full UltraTax print package). All by program:
- Income by category: every screen-1 total (corrected amount) vs the return line (1z, 2b, 3b, 4b, 5b,
  6b, Sch D 7 / 15, Sch 1, Sch E, 25d withholding, Sch 1 line 21 student loan interest, Sch A line 8a mortgage interest); total income line 9.
- Capital gains by Schedule D line (1b / 2 / 3 / 4 / 8b / 9 / 10 / 11 / 13) — the screen-1 rows by Form 8949 box vs the return.
- Form 8949 boxes: the box checked on each 8949 page vs the box of each 1099 / Koinly row (Koinly B/H etc. resolved from the return).
- Forms filed, payers / K-1 entities and filing status: 2024 return vs 2025 return.
- Each document amount found on the return (page numbers).
Checklist: starts from the master list (`checklist_master.json`, created on first use: the 8 reviewer items + "Check carryovers").
**+** adds a line; **Stays Y** puts it on the master list for every client, **N** keeps it on this return only (Y→N on a master
line removes it from the master list). **Save review (Excel)…** writes the checks + the checklist (ticks and notes) to a folder you
choose (default: the prior-year return's folder), with the UT check sheet and the Documents sheet (verified ticks).

## Deduction summary (under the income summary)
Same layout as the income summary (editable, + to add lines). 1098-E → Student loan interest (Prior Year: Schedule 1 line 21);
1098 → Mortgage interest (Prior Year: Schedule A line 8a).
Not in the UT summary. Goes into the Excel file and the AI report.

## Schedule E sheet (standard template)
One row per property, always the same columns (Schedule E #, Owner T/S/J, Property #, short / full address, type, days, QJV,
lines 3-18, 19 Other - total, 22, Source, Flags / notes) + a Flags sheet. **Blank template** in the Schedule E box downloads it;
the *schedule-e-workpaper* skill fills it from whatever the client sends. **Import Schedule E sheet…** loads it: properties are
matched to last year's by address, grouped by "Schedule E #" (the tab — 6 properties per tab) and owner (older sheets with "19 Other" still import), notes / source shown per property.
Verify return checks each property line by line: against the UT Rent screens (input screens) and / or Schedule E page 1 (2025 return).

## Tax year
Only from "Tax Year 2025" / "calendar year 2025" on the document; otherwise the Year column stays blank (never flagged).

## Document inventory order
By file name, numbers in number order ("2." before "10."), then A-Z; the prior-year return first, free lines last.

## Schedule C: total only
The last line of the Schedule C form, **Enter total only**, takes just the net profit / (loss) when there's no line detail; it
replaces line 31. That amount isn't checked against the UT input screens — the income summary and screen 2 say so in a note.

## Brokerage packages with several accounts
A consolidated package (e.g. Ameriprise) with 2+ account numbers is split by account and each account is read on its own
("… — acct …7367"); the note shows the package pages of each account.

## Schedule E box (under Schedule C)
6 properties per tab (Schedule E 1 = properties 1–6, Schedule E 2 = 7–12 …, **+ Add property**), one column each.
Each column: short address on the Income line, type, fair rental / personal use days, lines 3–22 (19 = Other — total only),
**PY income or (loss)** under line 21 (last year's line 21, or 22 when limited — read only) and a ✓ (reviewed) at the bottom.
Last year's amounts come from the 2024 Schedule E page 1, column by column (A / B / C, continuation pages too), shown in grey.
Lines 20 and 21 calculate; line 22 = the loss allowed after Form 8582 (enter it when the loss is limited — the property's result
is then line 22). No P&L import. **Calculate** moves each property's result to Rental & Royalties on the income summary
(1099-MISC / composite rents there become memo lines: "may be included on Schedule E"). Workpaper CSV per property.
With the UT input screens, each property is checked line by line against its UT **Rent** screen (matched by address; whole dollars; depreciation = asset module).

## 1095-A and 1098-T
Read by the program but not income: the amounts go in the document's note on the inventory ("Added to: comments only").
1095-A: line 33 column C (advance premium tax credit). 1098-T: box 1, box 5 (and 4 / 6, checks 7 / 8 / 9; a note when box 5 is
more than box 1). Screen 2 checks them on their own: with the UT input screens against the 1095-A / 8962 and 8863 / 1098-T
screens; with the 2025 return, that Form 8962 / 8863 is there and shows the amount.

## Opening PDFs
Every PDF is opened once in a separate process first (time limit): a file that makes the PDF reader hang is named (file + page)
instead of freezing the program. A hanging document is left out and listed on the summary ("Not read"). The black window
(`run.bat`) prints each step of Run check; http://127.0.0.1:5067/debug/stacks shows where the program is if it looks stuck.

## Work in progress (.json)
Everything on screen 1 is optional: prior-year return, client summary (PDF / Word), work in progress, documents (the Karbon organizer goes in with them). The UT input screens are picked on Verify return.
- Saved automatically as `1040 Ultimate WIP <year> - <last name> <last 4 of SSN>.json` (from the 2024 return page 1; without
  it — or with the SSN masked — the client folder's name). The Excel files use the same client name in the Karbon letter's folder (else the prior-year
  return's folder; with neither, the summary asks you to choose a folder). The first save of a session keeps the previous file
  as `.bak`.
- Picking the prior-year return or the client summary on screen 1 finds it and asks: **Continue where you left off / Start fresh**.
  Or browse to it in the "Work in progress" field.
- Holds your work, not the documents: amounts, comments, ticks, inventory, Schedule C / E, UT summary, checklist, carryover /
  Karbon ticks, the file paths (documents, 2025 return, UT screens). The documents are read again when you continue.
- Work on a document (ticks, corrected amounts, comments, inventory, form-tab corrections) follows the file's fingerprint, not
  its name: renaming or moving a file keeps it. A file re-saved (same text) keeps it with "matched by name — check"; a replaced
  document (same name, other content) starts clean with "This document was replaced …" on its inventory line until it is ticked
  Verified. Older WIP files are converted on load.
- A different client's WIP with another prior-year return is refused. Files that moved are looked for (same name) under the
  WIP folder and listed on the summary.
- Without a prior-year return the tax year comes from the documents (or the UT screens); the 2024 column, carryovers,
  "received?" and forms filed stay empty, and the masking tabs start empty.

## Schedule C box
One business at a time (picker; + Add business). **Add P&L…** reads a QuickBooks-style P&L (CSV, Excel or PDF): every account
gets a suggested Schedule C line (rules adapted from 1120 Mapping; meals 50%); change it in the dropdown and the Schedule C
fills in. Check: accounts read must equal the report's Net Income — otherwise an error with both numbers. Lines after
"Net Income" (preparer notes) are ignored. Every amount is soft: blue = from the P&L, grey = last year, green = typed (clear
to go back). Downloads per business: workpaper, other expenses (Part V, line 27b), books vs Schedule C.
**Calculate** moves line 31 of every business into the income summary.

## UT summary (right of the income summary)
The UltraTax "Watch" lines (no AMT, no bank lines), filled from the income summary as you type. Every field can be typed over
(green); clear it to recalculate. Filing status from the PY return (can be changed). 2025 brackets / standard deduction
(15,750 / 31,500 / 23,625), qualified dividend + capital gain rates, QBI 20% (no wage limits), SE tax, NIIT 3.8%.
Capital Gain/Loss = ST + LT (no loss limit); Schedule E = Rental + K-1s; Total Income adds IRA, pensions, 85% of SS, other.
Not in the Excel file.
Schedule C: enter the amounts in the Schedule C box at the top and click **Calculate** — line 31 moves into the summary.
Federal withholding: 2025 = W-2 box 2, 1099 box 4 (every form section), 1099-R box 4, SSA-1099 box 6; 2024 = Form 1040 line 25d.

## Carryovers box (first box under the income summary)
1. **Return Carryover Summary** (UltraTax, if printed): every line — Activity/Form, Unit, activity, description, amount.
   AMT lines are skipped unless the AMT amount differs from the regular amount above it.
2. **Read from the forms** — `CARRYOVER_RULES` in `core/carryovers.py` (add rules as you meet them):
   Capital Loss Carryover Worksheet line 8 (ST) and line 15 (LT) · Form 8582 Part VII (c) Unallowed loss · Form 172 line 10 (NOL).
3. **"Check for the …"** — `WARN_FORMS`: when one of these forms is in the prior-year return (the form itself, by its footer
   "Form NNNN (YYYY)", not a page that only mentions it): 461, 6198, 4952, 8990, 8829, 8995/8995-A, 8801, 3800, 8582-CR, 8839,
   5695, 8396, 8859, 8834, 7203, 4562, 8283, 2555.
"Forms filed last year" uses the same footer rule now (pages that only mention a form no longer count).

## Karbon organizer
Add the Karbon "Client Request Summary" PDF with the documents — it is recognized (same layout every time); there is no separate picker.
`core/karbon.py` reads every question and the client's answer; the **Karbon Summary** box (after "not received" / "Forms filed last year") lists each question whose
answer isn't "No" (unanswered questions are left out). The organizer goes to the AI as context.

- Questions answered just "No" (also Nope / None / N/A) and unanswered questions are left out.

## Client summary
Optional "Summary (PDF or Word)" picker on the first screen. `core/clientsum.py` turns every bullet point / numbered point / line
(paragraph) into an item of the **Client Summary** box (after the Karbon Summary), each with a tick box; "Title: text" items show the title
in bold; number-only lines (source markers) and headings are dropped. The items also go to the AI report (`client_summary`).

## Hand-off to the AI skill
- Documents table, column **AI**: ticked = goes to the AI (masked). Default: not read / partly read / context documents and the
  prior-year return; unticked: documents the program read, excluded / skipped files, the Karbon organizer (its parsed summary goes instead).
  The masking list follows these ticks.
- **Pages for AI**: long documents (over 10 pages) send only their summary / form pages — the redacted copy contains only those pages.
- **Save redacted documents + AI report…** writes `redacted_<name>` files (client names masked in the file names too) and
  `ai_report.json` (for the skill) + `ai_report.md` (to read): income summary per document with status (read / edited / partial / not read),
  withholding, Schedule C, carryovers (+ ticks), Karbon answers (+ ticks), the documents list with what goes to the AI and why,
  and instructions for the skill. Every text in the report is masked with the same values as the documents.

## Masking rules
- Screen 2 starts with **What to mask** — 7 lines: Names · SSN & EIN · Account numbers · E-mail addresses · Street address ·
  City & ZIP · Other info (phones etc.). 6 boxes per line (one item each); **Add more ▸** opens a box for more, separated by commas.
- **Names:** type only the part that must be hidden — usually the last name. First names stay visible.
- Pre-filled from the prior-year 1040: SSNs (taxpayer, spouse and every dependent — soft look in the Dependents block) and city / ZIP.
- Always masked on every document: the numbers in `local_settings.json` (`always_mask`).
- The masking list starts with the prior-year return, the Karbon organizer, then the step 1 documents.
- Masked automatically (only the obvious): SSNs printed as 123-45-6789, e-mail addresses (xxx@xxx.xxx, sub-domains too),
  the ZIP after a state (+ the street line above it, only when it looks like a street address).
- Everything typed is masked wherever it appears; SSNs keep their last 4 digits everywhere. EINs (XX-XXXXXXX) are recognised in the SSN & EIN line.
- Never masked: payer / employer names and amounts.
- The masking list of documents starts with the step 1 documents (grey, "from step 1") — remove what the AI doesn't need.
- PDF: true redaction (text kept). Word .docx / Excel .xlsx / .txt .csv .eml: text replaced with X. Pictures, .doc, .msg: not masked, flagged.
- **Save redacted documents…** → `redacted_<name>` (masked ones only) · **Save unredacted documents (copy)…** → plain copies.

## Build steps
1. **Inventory + prior-year review** ← this version
2. Prior-year reading (expected documents) — included in this version
3. Document parsers: K-1 1065 (from K-1_interpretation), W-2, standard 1099s, composite 1099s (Schwab, Fidelity, M1, Robinhood, IB), Koinly, 1099-DA
4. On-screen income summary (office template layout) + Excel download
5. Masking tab (one tab per person, first names stay visible)
6. AI report + one combined masked PDF (summary pages only)

## What step 1 shows
- **Prior-year summary** — UltraTax *Two Year Comparison* (both years, filing status, dependents). Other software: Form 1040 pages 1-2.
  Lines that moved more than 10% are red.
- **On last year's return — received this year?** Payers / employers / K-1 entities from the prior-year return
  (UltraTax wages report, broker worksheet, Federal Statements, K-1 Reconciliation Worksheets; Schedule B and Schedule E p2 for any software),
  matched to the documents by name.
- **Forms filed last year · carryovers** — UltraTax *Return Carryover Summary*.
- **Documents folder** — every file, its type, issuer, tax year, text layer, and who reads it:

| Read by | Meaning |
|---|---|
| Program | a tax form this program reads (parsers come in step 3) |
| AI | a tax document the program can't read yet; AI pages lists the pages it gets |
| Context (AI) | letters, notes, e-mails, other returns — the AI reads them for facts |
| Excluded | left out on purpose (1099-DA when a crypto report — Schedule D / 8949 — is present) |
| Skipped | duplicates, the prior-year return itself, unsupported files (a "draft" / "estimate" file name no longer skips) |

Rules: a crypto report (Schedule D / Schedule 1 / Form 8949 on their own, Koinly or other) takes precedence over any 1099-DA (the 1099-DA is ignored with a note to verify it's in the report);
documents over 10 pages send only their summary pages to the AI; a tax year other than PY+1 is flagged red.

- **Schedule C** (click to open) — one panel per business on last year's return, last year's amounts soft-entered in grey.
  Lines 3, 5, 7, 28, 29, 31 calculate. Line 24b: enter the deductible part only (usually 1/2 of meals).
  Line 30 home office: used only when the business has a profit, and never more than line 29.

## Files
| File | What |
|---|---|
| `app.py` | Web app |
| `core/inventory.py` | Folder scan, document types, routing rules — edit `ROUTE` / `ISSUERS` here |
| `core/py_return.py` | Prior-year return: summary, forms, expected documents, carryovers, Schedule C |
| `core/income.py` | Income summary rows (office template), per document / corrected amount |
| `core/utscreens.py` | UltraTax input screens reader (W2, B&D statements, Rent, C) + document verification |
| `core/wip.py` | Work in progress file (find / load / autosave / .bak) |
| `core/k1v/k1_codes.py` | The one K-1 (1065) box / code list, UltraTax + IRS (UT wins); `python -m core.k1v.k1_codes` refreshes the reference CSV |
| `core/k1v/prep.py` | K-1 UT page: box E match, box corrections, K-1 copies, the UT data entry CSV |
| `core/k1v/ut_entry.py` | UltraTax entry rules (Bot / By hand, rows per code box) and the by-hand list as Excel / PDF |
| `core/sche_template.py` | The standard Schedule E sheet: write (blank / filled) and read for the import |
| `core/safe_pdf.py` | Opens each PDF in a separate process with a time limit (a hanging file can't freeze the program) |
| `static/sche.js` | Schedule E box |
| `core/verify.py` | 2025 return reader, return-based checks, review Excel |
| `core/people.py` | Masking tabs pre-filled from the prior-year 1040 |
| `core/masking.py`, `core/redact_pdf.py` | Masking (PDF / Word / Excel / text) and saving |
| `core/pdfutil.py` | PDF open (passwords from the file name, same as k1_summary.py) |
| `templates/`, `static/style.css` | Pages (same look as the K-1 tools) |
