# 1040 Ultimate — build notes (read this first)

Hand-off for a new Claude session. The README describes what the app does; this file holds the working rules,
the pending list, the open questions and the known gaps that only lived in the chat. Last updated 2026-11-02.

## Working rules (from Lady)
- **List first, build on "go".** When Lady lists changes ("no changes yet", "keep a tab", "we may have more"), only add
  them to the numbered pending list below and confirm. Build only when she says go / implement / apply.
- **Client data stays local.** Never use unmasked documents; she removes them. Work only with masked (redacted) files.
  The app itself reads unmasked forms (all fields visible, 2026-11-01): parsers are built for full documents, not masked ones;
  masking is only for what goes to the AI. Test with samples / public forms.
- **Masking:** always mask the firm EIN kept in `local_settings.json` (never put it in code or GitHub). First names stay
  visible; payer / employer names and amounts are never masked.
- **GitHub:** she removes PDFs herself before pushing; `.gitignore` excludes client data, WIP json, `.bak`, xlsx.
  Keep client names / numbers out of code, README and this file.
- **Don't modify** `redact_pdf.py` or `k1_summary.py` (PDF_Mask). A small addition to PDF_Mask's `web_app.py` is OK
  if needed (see item 46).
- **Schedule C box:** don't change the design (P&L mapping beside it); no more businesses per page.
- **Style on screen:** whole dollars; negatives black (no red anywhere for negatives); numbers typed by the preparer
  blue, not bold; changed amounts light pink (design rules, 2026-11-01); verified (ticked) light mint; red only for real data-entry differences.
- **Verification is line by line** — never by totals or net amounts (UT doesn't calculate those on the input screens).
  Two sections: (1) document verification, (2) UltraTax entries with no document. Tolerance ±$1 per line.
- **Readers read only labelled IRS boxes** (box number + IRS box name), in table or list layout. A summary page
  without the IRS box names is not read.
- Replies: short, plain language; one question at a time.
- **Decisions go in this file.** When a decision is made or a change is finished, add it here (short, plain language) before
  ending the session. `CLAUDE.md` loads this file and README at the start of every Claude Code session.
- **Where to work:** undecided design (new screen, workflow, "which option?") is talked through in Cowork (project "1040_ultimate"),
  sometimes with a clickable test page in `_work/`; clear changes and all building go straight to Claude Code.
- **`_work` is temporary:** the program deletes it at every start (by design). Nothing meant to be kept goes there — Lady moves
  what she needs out of it by hand.

## How to work on it from a cloud session
- App folder on her computer: `C:\dev\1040_ultimate` (run with `run.bat`, http://127.0.0.1:5067). PDF_Mask:
  `C:\dev\PDF_Mask` (web app on port 5069, `run_web.bat`).
- Edit a copy in the cloud workspace, then write it back to her computer and confirm the copy on her computer is
  identical (byte compare). If the computer is offline, send a zip.
- Test before deploying: Flask test client + Playwright (Chromium) screenshots; check there are no page errors.
  When killing a test server started from a script, use a separate command with a pattern like `pkill -f "[s]rv9.py"`
  (a pattern that matches the command itself kills the shell).
- Restart `run.bat` after Python changes; a browser refresh (Ctrl+F5) is enough for CSS / JS / template changes.

## Test files (masked) — attach them to a new session
- UT input screens print, 110 pages (W2, B&D with a 3-section statement page, 11 Rent screens):
  the masked UT print in `C:\dev\PDF_Mask\redacted` + the matching W-2 detail (EEW2Detail).
- Older client set (2024 / 2025 returns, Coinbase 1099-B / 1099-MISC, Koinly Schedule D / Schedule 1, UT screens
  print) — used as the regression run (income total must stay 431,704).
- Single forms attached in chat on 2026-10-16: ADP W-2 (3 copies side by side), Fidelity IRA 1099-R (2025 layout,
  code 2), Fidelity 1099-SA (list layout), Morgan Stanley stock plan 1099 summary (1099-DIV + 1099-B box list).
- Also used: a W-2 with a summary page, a second W-2 with a summary page, Schwab / National / Vanguard / Fidelity / M1 /
  Robinhood composites, a mock 1098-T / 1095-A, a 31-page K-1 face-page file.

## K-1 section (2026-10-21)
- One K-1 reader: `core/k1v` (k1_parser, k1_summary, screen parser, web blueprint `/k1v`). (The empty stubs `core/k1_parser.py` /
  `core/k1_summary.py` were deleted 2026-11-04.)
- K-1 PDFs added as documents go to that engine in `app.py` `_route_k1s` (route "k1v"). Since 2026-11-04 the K-1 page opens in its
  own tab and amounts reach the income summary only through "Add to Income Summary" — see "K-1s: one route".
- Working from a cloud session: write each changed file to a NEW output path for every commit (re-using a path wrote the old content once); re-stage and compare checksums after committing.

## First page / summary changes (2026-10-26)
- The Karbon "Client Request Summary" is added with the Documents (no separate field any more); `inventory.classify_text` recognizes it
  (family "karbon") and `app.run` reads the first one into the Karbon Summary box. An old WIP's `form.karbon` still works.
- Karbon Summary leaves out questions answered just "No" (`karbon.is_just_no`: No / Nope / None / N/A ..., also "No" on several lines),
  and drops the avatar letter in front of a question ("Y Did you ...").
- New first-page field "Summary (PDF or Word) — optional" (`form.clientsum`, `core/clientsum.py`): each bullet / line / paragraph
  becomes an item in a "Client Summary" box (ticks = marks `cl<i>`); number-only lines (source markers) and headings are dropped;
  "Title: text" shows the title in bold. Also in ai_report (`client_summary`).
- The UltraTax input screens are picked on Verify return only (field removed from the first page; an old WIP's path still loads).
- Summary page order: ... carryovers → not received / forms filed last year → Karbon Summary → Client Summary.
- Second round (2026-10-26): Karbon Summary and Client Summary are collapsible (`<details open>`); Client Summary header is one "Items"
  column (Item / Detail split kept per row when there's a ":"); Carryovers: "Added by the preparer" table with + (`r.carry_added`,
  route `/carryadd`, WIP key, ticks `ca|<id>`, in ai_report); income / deduction tables use fixed column widths (document 25%, amounts 102px)
  so Comments get the room; the Karbon document shows "Read" in the inventory when its questions were read; a deduction summary with one
  kind of deduction shows its total as "Total Deductions" (no second grand-total row).

## Document inventory / summary page (2026-10-31)
- Inventory sorted by file name with numbers in number order (`app._natural`: "2." before "10.", numbered names before the others).
- Year column replaced by **Type** (`doc_type`; a composite lists the forms that hold amounts: INT / DIV / B / MISC). A wrong tax year
  still shows in red next to the type. The Excel Documents sheet has Type instead of Year.
- Every section with an arrow (Document inventory, Schedule C / E, K-1s, Karbon Summary, Client Summary) starts closed. The ones that were
  open stay open after a reload (typing an amount, Calculate, Refresh …) (`sessionStorage` "openBoxes:<path>").

## Design — main page and every 1040 page (2026-11-01, built)
- Pages: the main page, Verify return, Mask for AI and the first page. The K-1 Interpreter pages (`core/k1v`) are left as they are (Lady).
- Top: no line under the title; step tabs all one width (230px); "3 · Mask for AI" (was "(if needed)"); the comments box sits under
  the tabs (same `#clientCmt` textarea and saving) — see the second round below.
- Help texts removed everywhere: notes under boxes, header sub-texts, sentence placeholders, page subtitles, the masking banner.
  Kept: counts, status messages, red flags, Comment / Note contents, one-word placeholders ("Comment", "Note", "amount") (Lady).
- "per preparer" is "corrected amount" on screen, in the Excel files (income summary, review) and in the AI report text
  (the JSON key names did not change).
- Sections: every box has an arrow and starts closed (remembers open after a reload) except **Income and Deduction Summary** — one box,
  income table, then the deduction table, then Recalculate; the UT summary beside it stays open (Lady).
- **Prior Year Return** box (replaces "Carryovers from 2024" + "not received" + "Forms filed"): Carryovers from Prior Year → On last
  year's return — not received → Forms filed last year (`.pysec` headings).
- K-1 box: the "Remove the K-1s from the income summary" button and its script are gone (the `/k1v/handoff/clear` route stays —
  it's the K-1 code's). Links kept: K-1 entry check · Open in a new tab · Separate K-1 page.
- Schedule C: Add P&L / Use PY amounts / Clear Amounts are box buttons; "Remove business" is gone — Clear Amounts clears the amounts
  and removes the tab when the business is then empty (no name, no P&L, not on last year's return; the last one stays).
- Schedule E: "Export Template" and "Import Schedule E" are buttons in the Calculate row (not in the property tabs).
- Tables (`table.v`, the W2 tab): rounded corners (8px). Tick columns (first `td.ck`, the income summary's `span.rowck`, the W2 tab's
  first column) sit just left of the table on the card background, lined up with their row — CSS only (`position:absolute` from the
  row), on every 1040 page.
- Buttons inside the boxes: #7DD8C9, one width per page = the longest label (`static/ui.js`, measured from the text, re-run when a
  box draws new buttons). Not resized: `.small` buttons (Browse…, ✕, banner buttons like "Refresh the income summary"), + and tabs.
- Bottom bar buttons: #4e7874, white text. Main page: "Print Page", "Income and Deduction Summary (Excel)", "Verify Data Entry →";
  "Print income summary" (and `printIncome`, the `print-inc` CSS) removed. Verify: "Mask for AI →".

## Design — second round (2026-11-01, built)
- Top of the main page: the box under the step tabs shows only what's wrong (documents not found, work in progress not being saved +
  Choose a folder…, moved files, not read); "Documents: n selected" / "Work in progress: … saved automatically" are gone (Lady).
  Under it, the comments box alone: **Return Comments** (was Client comments) — also on Verify return, the review Excel and the
  AI report text (the JSON key `client_comments` didn't change).
- Years taken out of the labels: columns are **Prior Year** · **per document** · **corrected amount** (screen and Income Summary Excel);
  "2024 vs 2025" → "Prior Year vs Current Year"; the inventory's prior-year row type = "Prior Year return"; UT summary "estimate";
  Verify's file label "Current-year return". The AI report keeps the years (the skill needs them).
- Income and Deduction Summary: "Income" and "Deductions" titles above the tables (bold, #003366, `.tbltitle`). The deduction table
  has an empty column where the income table has Fed. w/h, so Comments lines up (the header no longer runs into "corrected amount").
- Client Summary items: regular weight (the title column was bold).
- Schedule C: Calculate is in the top button row (with Add P&L / Use PY amounts / Clear Amounts). Schedule E: Calculate · Export
  Template · Import Schedule E in a row under the property tabs, above the table.
- Schedule E: the Line column stays narrow (40px) and the table takes only the width it needs, so Description sits next to Line.
- W2 tab: the ✓ is a span placed from the row (`span.fvck`), not a cell — in the fixed-layout table the cell kept an empty column
  (the grey gap). Box 40px, Description 380px.

## Form view — W-2 (2026-10-31; tabs of the Document inventory since 2026-11-01)
- The forms are tabs inside **Document inventory** (no separate section, page or links): **Summary** (the inventory table, client
  comments) first, then **W2**, then 1098-M, 1098-T, 1099-B, 1099-Comp, 1099-DA, 1099-DIV, 1099-G, 1099-INT, 1099-NEC, 1099-R
  (alphabetical, always shown). Other types (1099-K, MISC, OID, SA, SSA-1099, 1098-E, 1095-A, 5498) get a tab only when the client
  has one. All tabs the same size (Schedule C business-tab style); label + "(n)" = how many (W2: W-2 forms on that tab; others:
  documents of that type), no number when none. W2 and 1098-M work; the others say "Form view coming soon".
  1098-M = the mortgage 1098; "1099-T" in Lady's list read as 1098-T.
- Files: `core/formview.py` (`DEFS`, box 12 codes `W2_12`, `TABS` / `TABS_IF`, effective values), `static/forms.js` (one renderer
  for any definition; later forms = a new entry in `DEFS`), data from `app.form_view_data` (passed to the page as `FV`).
- W2: always 6 columns + Total, fitting the screen (fixed layout, no sideways scroll), even with fewer W-2s (empty columns);
  W-2s 7–12 on W2_2 … in the inventory's order. The Total column = every W-2 of the client ("all N W-2s" when the tab shows fewer).
- Column header = employee name (box e) · first word of the employer name (box c, a leading "The" skipped). Hover: full employer
  name, EIN, file name. Box e or c not read → the file name + "Employee name not found on the W-2" / "Employer name not found on
  the W-2" (fix = teach the reader). No T / S / J, no owner matching (Lady, 2026-11-01). No tinted columns.
- Rows: boxes 1–11 and 13 always (box 9 left out: not used on the form); no rows for a–f and 15 (Lady, 2026-11-01). Box 12: one row
  per code ("D Elective deferrals…"), only codes with an amount; none → one "Box 12 — no codes" line. Box 14 the same per label.
  State 16 / 17 and local 18 / 19 with the generic box name only (no "NY —"); the state / locality shows on hover. + on the last
  row of box 12 / 14 / state / local adds one. No title rows.
- Corrections are kept apart: `r["formview"]["w2"]["<doc path>#<form index>"][row key]` (route `/formview/<token>/w2`, WIP key
  `formview`); parsed values are never changed. Effective = correction, else parsed. Ticks per tab = marks `fv|<tab>|<row key>`
  (`fv|w2|…` for W2, `fv|w2_2|…` for W2_2; the header box ticks every line); "x of y lines verified" under the table.
- A change to box 1, 2 or 12 shows the banner "W-2 amounts changed … Refresh the income summary" (button reloads the page; the
  inventory stays open on its tab). Downstream: `formview.effective_docs(r)` is used by `_summaries` (income summary per document +
  withholding, Income Summary Excel), `run_checks` and `doc_verify` (Verify return, Save review Excel) and the AI report. An amount
  typed over on the income summary still wins (Lady, 2026-10-31); the W2 tab says so in a banner.
- Excess Social Security check: W-2s grouped by the employee name read from box e (2+ W-2s with the same name); a W-2 with no name is
  left out and listed in a banner. Wage base table `WAGE_BASE` (2024 168,600 · 2025 176,100 · 2026 184,500), tax year = prior-year
  return + 1.
- Parser gaps left: the list layout reads 1–6, 12, 16, 17 only; box 12 in the list layout when a file holds more than one W-2; a W-2
  printed as a picture (no text layer, e.g. ADP's RUN sample) can't be read — no OCR.
- Main page (2026-11-01): title "1040 Preparation tool" (was "Create summary"); the "Prior-year return: …" line under the step tabs is gone.
- Sample files with fake names: `C:\dev\Z_Sample_training\Output` (2 W-2s, 1099-R, K-1, two 1099s).

## W-2 — the IRS blank as payroll services print it (2026-11-01, built)
- Taught on the sample "LEDGER" W-2 (Justworks, 2 copies side by side, 2 rows per page): boxes a–f printed **without their letter**
  ("Employer's name, address, and ZIP code") are labels now — `_w2_labels` adds them only when no lettered label for that box is on
  the page (ADP / IRS-lettered layouts read as before).
- Side-by-side copies: a copy starts at its leftmost box label (the IRS blank prints a–f and 7–11 left of box 1) — before, the left
  copy reached into the right copy's labels and got its employer name cut short.
- Box 12: "12a" sits a little left of the "1" label — it's read with its copy (a "12a" within 40pt left of the next copy's "1" is
  that copy's). The word "Code" printed one letter per line is not a code "C" — this also fixes a W-2 that showed box 12 "C" for DD.
- Checked: both sample W-2s, the IRS-layout W-2s (two) and the detail-sheet W-2 — boxes 1–6, withholding unchanged; box 12 code
  corrected on one (C → DD).

## W-2 — every box (2026-11-01, built)
- `parse_w2` (table layouts: ADP "W-2 and Earnings Summary", the IRS layout, payroll prints) reads every box: a SSN, b EIN,
  c employer name + address ("BATCH #" line left out), d control number, e/f employee name + address, 7, 8, 10, 11, 13 checkboxes,
  14 label + amount, 15 state code + state ID, 16 / 17 per state, 18 / 19 / 20 per locality. Box 20, the state ID and box 14 are
  shown as printed (e.g. "NEW YORK CIT", "130871985 9", "401A-TAX"); box 14 has no income note (Lady).
- How: `_w2_labels` finds every box label (box letter / number + IRS name, `W2_MORE`); `_w2_more` reads each box's cell = below
  the label down to the next label in its column, right edge = the next label beside it (box 14 also right of the label: ADP prints
  "35000.00 401A-TAX" on the label row). A box ends at a gap of 5+ label heights (text printed under the form). Text boxes leave
  amounts out. Box 13 = the X's position under Stat emp / Ret. plan / 3rd party sick pay. States / localities: one row per line
  with an amount (the i-th line of 15, 16, 17 together); a locality with no amounts is dropped.
- Copies of the same W-2 (same boxes 1 / 2 / 3 / 5) count once; boxes a copy missed are filled from the other copies.
- ADP "ADDITIONAL W-2 FOR BOX 12 OR 14 OVERFLOW" page (no box 1–6 amounts): its box 12 / 14 lines go to the W-2 before it with the
  same EIN + SSN (else the last one) — box 12 DD on that page was lost before.
- Fixed on the way: an empty box no longer takes the amount of the box below it (e.g. box 5 read as 0 on the detail-sheet W-2 —
  now blank); an amount exactly halfway between two box labels is no longer dropped (one ADP copy lost box 1). `16` / `17` = the sum
  of the state rows.
- Row keys: a–f = `ssn` / `ein` / `er` / `er_addr` / `ctl` / `ee` / `ee_addr` (read and kept; used for the column header, no rows);
  state `st:<state>:15|16|17` (15 = state ID, no row), local `lc:<locality>:18|19`.
- Checked: the ADP print, the IRS-layout W-2s (two), the ledger W-2, the detail-sheet W-2 (EEW2Detail) — box 1 / 2 amounts,
  withholding and notes unchanged (only the overflow DD note is new).

## 1098 (mortgage) — reader, deduction line, 1098-M tab (2026-11-01, built)
- `parse_1098` (`core/parsers.py`) reads the lender's print (taught on the sample Wells Fargo 1098) and the IRS blank (tested on the
  IRS f1098 filled with test numbers): boxes 1–11 by label (box number + IRS name), each box's cell = below its label down to the
  next label, right edge = the next label beside it or a box on the right that reaches down past it (IRS box 8 beside 9 / 10); a cell
  stops at the form's footer line. Box 7 = a check mark between "7" and its text. Box 10: the lender's own name ("Real estate taxes")
  or, on the IRS blank ("Other"), the text typed in the box ("Property tax"). Also lender name, borrower name, account number.
  Copies A / B / C with the same boxes 1–3 + account count once.
- Box 1 → Deduction summary, new line **Total Mortgage Interest** (under Student Loan Interest; with two kinds the table has the
  Total Deductions line again). Prior Year = Schedule A line 8a of the prior-year return (untested: no return with a Schedule A yet).
  Verify return (2025 return) checks it against Schedule A line 8a.
- Comment (Lady): box 2, box 10; also boxes 4 / 5 / 6 when not 0, box 8 (property address — a rental or second home shows here) or
  "Box 7: property = borrower's address". Several 1098s in one file: added, each comment starts with the lender.
- **1098-M tab** (Lady: boxes 1–10): same as the W2 tab — 6 columns + Total, header = borrower · first word of the lender (hover:
  lender, account, file), rows 1–9 + one row per box 10 description (+ adds one). Box 3 / 8 / 9 are text, 7 a tick box.
  Corrections `r["formview"]["1098"]`; a change to box 1, 2, 4–8 or 10 shows "Refresh the deduction summary"; an amount typed on the
  deduction summary still wins (banner).
- Code: `formview.FORMS` (per form: parsed → row keys, back, the document's result again) — `effective_docs` and the tabs work for
  any built form; `DEFS[form]` holds the header names, what feeds the summary and the banner words. `forms.js` reads them from the
  definition (no W-2-only code left except the excess Social Security check).

## Form view — next forms (planned 2026-10-31, not built)
- Same W2-style tab for every form type in the Document inventory (tabs already there), one column per form, Total column, a ✓ on
  every line (one tick covers every document in the tab). No T / S / J tag for now (Lady, 2026-11-01): the form's own names identify it.
  Layout reference: `_work/form_view_mockup.html` (layout only — its colors are not the app's;
  use `static/style.css`).
- Order: W-2 (done) → **1099 composite** → the other single forms (1099-INT, DIV, NEC, MISC, R, G, SSA-1099, 1098, 1098-T/E, 1095-A,
  1099-DA, K-1 summary), each mostly a new entry in `DEFS`.
- 1099 composite: sub-tabs inside the tab, only for the forms present (INT, DIV, MISC, OID, B-Summary). **B-Summary = totals only** by
  8949 box (A / B short-term basis reported / not reported, D / E long-term), each with proceeds, cost, wash sale disallowed and a
  calculated net gain / (loss), plus federal withholding. No transaction detail in the form view (that review belongs in a table /
  1099DA Compare). Joint accounts: decide how UltraTax carries them when the composite is built.

## File names decide nothing; Schedule D / Schedule 1; design rules (2026-11-01, built)
- Rule (Lady): **nothing is decided by the file name, except K-1 and Karbon** (names are typed by hand; mistakes happen).
  `inventory.classify_text` uses the text only (the Karbon name check stays; `app._route_k1s` still sends "K-1" in the name to the K-1
  reader, after the text check). "Draft" / "estimate" in a name no longer skips. A CSV is a normal spreadsheet for the AI (the program
  reads no CSV in the documents; "Koinly" in a CSV name meant nothing). Before, Schedule 1 (renamed) read as a K-1 (1041) and
  Schedule D as a 1099 Composite.
- Crypto reports = the IRS forms on their own, recognized by the title at the top of page 1 (Koinly or any other program; family
  still "koinly"; "Koinly - " in the type only when Koinly is in the text): Form 8949, Schedule D (≤3 pages), Schedule 1 (≤3 pages).
  Checked before the K-1 / 1099 rules. They count as the crypto report → a 1099-DA is ignored.
- Schedule D (`parsers._sched_d`, Lady: same rules as 1099-B): one row per Form 8949 box from lines 1a / 1b (A/G), 2 (B/H),
  3 (C/I), 8a / 8b (D/J), 9 (E/K), 10 (F/L); columns (d) (e) (g) (h) by their headers; comment per row = proceeds · cost ·
  adjustments · gain; check proceeds − cost + adjustments = (h) ±$1. Lines 4–6, 11–14 and totals 7 / 15 left out.
- Schedule 1 (`parsers._sched_1`, Lady): only lines 8v and 8z, one Other income row each (8z comment = the type listed).
  Rows come from `parsed["parts"]["other"]`; per-row comments from `parsed["part_notes"]` (also used by Schedule D).
- Issuer (kept, Lady): the known name found first on the first two pages (`ISSUERS`, whole words), else "Payer's name:", else the W-2
  employer (box c) / 1098 lender the reader found (`app.read_amounts`). "On last year's return — received?" matches last year's payer
  in the document text (`head_text`, first two pages; the payer's first word must be there), not the file name.
- Design rules (`design/DESIGN_RULES.md`): changed by the preparer = light pink `#FDF0F0`, blue `#1F5FBF`, not bold (was yellow) —
  income / deduction corrected amount, W2 / 1098-M tabs, Verify return rows, Income Summary Excel. Buttons in the boxes: green
  `#446B67` bold text; bottom bar hover `#446B67`. Step tabs stay 230px (the rules file says 210px — Lady's earlier choice kept).
- First page: "Clear list" removed; "Add all files in a folder…" → "Add a folder…"; after the K-1 Verification button: "For more
  than 4 K-1s, it is advisable to run K-1 Verification separately." (the Mask page keeps its own buttons).

## Verified = light mint; UT summary without ticks (2026-11-01, built)
- Every tick box turns its line light mint `#E8F8F5` (a ticked total `#D3F1EC`), on every page: inventory, Income and Deduction
  Summary, Prior Year Return (carryovers, not received, forms filed chips), Karbon / Client Summary, Schedule C / E, W2 / 1098-M tabs,
  Verify return. `static/marks.js` puts "done" on the tick's row (`tr.mk`, else the row of the tick box), or on its cell when the row
  holds several ticks (Schedule E: one per property); it also paints ticks already saved, after the page loads and after a box
  redraws (MutationObserver + setTimeout — requestAnimationFrame doesn't run in a hidden tab).
- The Income and Deduction Summary lines didn't turn green any more: their rows had no "done" class and the white row style won.
- UT summary: tick boxes removed (Lady); old `ut|…` ticks in a work in progress are left out of the "Reviewed (✓)" Excel sheet.
- Testing: the test server must not write a work in progress (`wip_mod.save` replaced by a no-op) — a test run with the client's
  prior-year return wrote over the folder's WIP once (restored from the `.bak`).

## AI (Claude API) — decided 2026-11-02, not built
Learning plan (Lady's doc): https://claude.ai/artifact/UF1Bn9myJWtaZPaJq6XyYF — files, commands, glossary.
- Python reading stays the default; the AI runs only on documents ticked AI, when the preparer clicks "Parse with AI".
- **One call per document:** Claude identifies the document (form, issuer) and returns its values + a suggested destination
  in the same answer (one JSON shape for every document; no separate "is this a standard form?" call).
- Screen: a form the form view knows (W-2, composite …) → form view, values flagged AI. Other forms (1099-G …) and
  non-standard documents (e-mails, contracts) → a card on the AI review page (tab 4): type, issuer, summary, quote, amounts
  (soft), Goes to dropdown (income categories + Deduction + Federal withholding + blank), + line, actions (e.g. Form 8824).
- **Nothing counts until the preparer confirms** the card (or verifies the form-view lines); until then "suggested".
- **Two models:** Standard model for Parse with AI; "Verify with stronger model" on the AI page (every AI-read row): both
  answers kept, differences highlighted, preparer picks, agreeing values "✓ both models"; confirmed work never undone.
- Settings page: Standard + Verify model dropdowns filled from the API (`client.models.list()`), fixed dated model names,
  warning when a saved model is retired; key status (last 4 only), Test connection, AI cost so far.
- **Pages:** up to 25 pages → the whole PDF. Over 25 with a text layer → the extracted text or the pages typed in the page box;
  over 25 scanned → typed pages or "Send all" (estimated cost first). Over the API's limit → refused. The keyword rule
  (`_summary_pages`) only pre-fills the page box.
- **Saved answers:** in the WIP (key `ai`) under file fingerprint (`_file_hash`) + model; new calls only for a new / changed
  file, "Re-read with AI", "Verify with stronger model".
- Key only in the back end (`local_settings.json` `anthropic_api_key`, or env `ANTHROPIC_API_KEY`); Console spend limit.
- **Improving = guidance, not training:** rules in `core/ai_guidance/*.md` (general.md always + topic files). Every preparer
  change to an AI answer → `AI_logs/ai_corrections.csv`; Lady reviews it regularly, repeated mistakes become rules, tested on
  sample documents before going live; guidance in git. Cost log `AI_logs/ai_usage.csv`. (Not `_work`: it is wiped at every start.)
- Not yet: teaching Python new forms from AI results. Open: masking before sending (depends on the retention agreement).
- Scans: sent as page images, **no OCR** before the AI (OCR misreads digits and scrambles box layouts; small saving under
  the 25-page cap). OCR only as a helper to find pages for the page box on long scans.
- **Fillable PDFs: flatten** with PyMuPDF (form-field values printed onto the page) before the Python readers and before the
  AI — accuracy, not cost. (Small step; can be built before the AI work.)

## Masking and printing = separate apps; 1040 = the return only (2026-11-02, decided, not built)
- Masking is only for documents sent to other AI models. With the Claude API set up correctly (retention terms confirmed in
  writing), documents go to the API unmasked: no masking step in the 1040.
- Masking (PDF_Mask) and the coming Print return app are **separate apps in their own folders**, with no link to the 1040's
  data: the user picks the documents again there and saves the results on the computer. The 1040 only shows them as a link /
  tab on a shared front page (opens the other app in a new browser tab; a note when that app isn't running).
- 1040 step tabs become: 1 · Summary → 2 · Verify return → 3 · AI review.
- To take out of the 1040 when built: `core/masking.py`, `core/redact_pdf.py` (it lives in PDF_Mask), `templates/mask.html`, the
  `/mask` routes, the "3 · Mask for AI" tabs / buttons (summary.html, verify.html), `_work/<token>` masked copies, the AI tick →
  masking list link (`save_toai` resetting `r["mask"]`, `_mask_defaults`). `ai_report.py` (skill hand-off) depends on the mask
  results — retire it or keep it as a plain export when the API AI is built. **Keep `core/people.py`**: `_client_label` uses it
  for the WIP file name.
- The "AI" tick on the inventory = parse with the Claude API only (nothing to do with masking).
- Shared look: every app uses the same `design/cfoa-tools.css` + DESIGN_RULES.md (one copy, not edited separately per app).
- Open: one start file that launches all the apps, or each app started on its own.

## Step tabs: Mask for AI gone, three AI pages (2026-11-02, built)
- Step tabs on every 1040 page: **1 · Summary → 2 · Verify return → 3 · AI Doc Review → 4 · AI Return Review → 5 · AI Advisory**
  (Lady wrote 4 / 5 / 6 counting the Mask tab). One shared macro `templates/_steps.html` (`steps(token, on)`) on the main page,
  Verify return, the Mask page and the AI pages; the three AI tabs are faded ("not available yet") except on their own page.
- "3 · Mask for AI" tab removed (Lady). The Mask page (`/mask/<token>`) and its code stay until the masking removal; nothing links
  to it now. Verify's bottom button: "AI Doc Review →".
- AI pages = `templates/ai_page.html` + `app.AI_PAGES` (Lady's text: What it does / How to use it (coming later)); routes `/ai/<token>`
  (AI Doc Review, was the "AI review" placeholder), `/ai-return/<token>`, `/ai-advisory/<token>`. `templates/placeholder.html` deleted.

## Automated tests (2026-11-03, built — pending item 8)
- Folder `tests\` (local only: the whole folder is in `.gitignore`; back it up on Google Drive). One folder per fake client in
  `tests\samples\<case>\`; the first case is `Sample` (the old `tests\Sample`, moved).
- `tests\harness.py` runs a case through the 1040's own code (Flask test client → `/run`, no browser), with the WIP save turned off
  and `_work` / the K-1 hand-off in a temporary folder (a test never touches a client's files or the running app).
- `answer_key.xlsx` per case: sheets **Documents** (type, issuer, tax year, read status, forms read, then every box: W-2 / 1098 by
  the form-tab row keys, K-1s by line from the K-1 section, other forms by the reader's own fields), **Summary** (income / deduction
  lines, per document + Fed. w/h), **UT check** (result per Verify line: ok / different / not entered / entered on another line /
  entered in pieces / one UT entry for several lines / 8949 box; then the UT entries with no document and their amount), **Files**
  (the role of each file: Document / Prior-year return / UT input screens / Current-year return / Leave out — guessed the first
  time, Lady can change it). Columns File · Form # · What · Expected · Checked. Blank box = `blank`, never 0.
- `tests\make_key.bat` (`make_key.py`): a case with no key → a draft key from what the program reads now. A case with a key → rows only
  for files that have none yet; a file taken out of the folder loses its rows unless one of them is checked. No row already in a key
  is ever changed. To start a draft over: delete `answer_key.xlsx` (only if nothing is checked).
- `tests\run_tests.bat` (pytest; installs pytest the first time): one test per case and sheet; a failure lists every row that differs
  ([changed] / [not read now] / [new] / [no key]); at the end, how many rows of each key are checked. Claude Code runs it before
  reporting a reader / summary / Verify change as done.
- Not covered yet: the current-year return checks (Verify without the UT screens), Schedule C / E box amounts (the cases have no
  P&L / Schedule E sheet), the Karbon / client summary contents. The UT print is matched by the most entries: the app's own
  `looks_like_ut_screens` also says yes to one of the sample K-1s (left as it is, noted here).
- Lines from the K-1 section are attributed to the K-1 file they came from. Since the one K-1 route (2026-11-04) the harness does
  "Add to Income Summary" itself (no corrections), so the Summary / UT sheets kept their K-1 rows (the key didn't change).
- `tests\fixtures\sample_wip_v1.json` = a frozen version-1 WIP of the Sample case (copied from its `.bak`) for `test_docid.py` —
  the Sample folder's own WIP was saved again as version 2 on 2026-11-03 (by a real run with "Start fresh", it seems: no ticks).

## Saved work keyed by the file's fingerprint (2026-11-03, built — pending item 7)
- Every document gets an id when the documents are scanned: `d["did"]` = the first 16 characters of the SHA-1 of the file's bytes
  (`inventory.scan_files`; a duplicate gets `~2`, one account of a split brokerage package `~<last 4>`). Also `d["tfp"]` = a
  fingerprint of the text of the first pages (`inventory.text_fp`). Code and rules: `core/docid.py`.
- Keys: income / deduction line = `<category>|<id>` (+ `|<8949 box / Schedule 1 line>` when one document gives several rows) — edits,
  ticks `inc|…`, comments, Verify `v|<line>|main|fit|<box>`; inventory amounts `inv|<id>`; inventory verified / amounts / notes by
  id; form tabs `<id>#<form index>`; Verify 1095-A / 1098-T / 1099-SA `memo|<id>|…`, return checks `rp|<line id>`, `rm|<id>|…`.
  K-1 section lines and Schedule C / E rows are not documents (K-1 lines: pending item 5). The AI ticks stay by path while the
  program runs and are saved by id. Form-tab ticks (`fv|<tab>|<row>`) are per tab, not per document — unchanged.
- WIP file version 2: a table `fps` (id → file name + text fingerprint) and `docnotes`. On load (`docid.upgrade`, before the saved
  work goes on the fresh read):
  - **same document re-saved** (new bytes, same file name, same text): the work moves to the new id, the line says "matched by name —
    check" and its Verified tick is taken off;
  - **replaced document** (same file name, different text): the work is not carried over (it stays in the file, unseen), the line says
    "This document was replaced — your previous ticks and comments were on the old version";
  - the note shows on the inventory line (and a count in the top box) until the document is ticked Verified.
  - The brief said "re-saved → match by name"; telling re-saved from replaced (both have a new fingerprint) needed the text check —
    Claude's addition, said before building.
- Older WIP files (version 1: keys from file names / paths) are converted once on load, matching by file name; a line whose issuer
  changed is matched by category + file (+ the 8949 box / line at the end of its name).
- The review Excel's "Reviewed (✓)" sheet shows file names instead of ids.
- Tests: `tests\test_docid.py` (old WIP converted, renamed file, re-saved file, replaced file — on copies of Sample documents).

## Per document = every source; stale correction flag (2026-11-03, built — pending items 1–3)
- **Per document** = what came in, fixed: the program's read, the form tabs (W-2 / 1098 corrections), the Schedule C box (line 31
  after Calculate), the Schedule E box (each property's result after Calculate), the K-1 section, and the amount typed on the
  document inventory (a not-read document or an inventory + line). **Corrected amount** = per document unless the preparer types
  over it — the correction wins (light pink when it differs). Lines added with + on the income summary stay corrected amount only.
- `income.build_income_summary`: `prog` no longer excludes Schedule C rows; Schedule E rows have their own marker `sche=i` (the
  `schc=-1-i` trick is gone — the template, Verify and the test harness check `sche` first). Inventory lines are no longer "added"
  rows: `inv=True`, status "inventory", drawn like a document line (per document + a corrected amount box; the comment is still the
  inventory note; no withholding box). Verify lists them as "inventory amount".
- **Calculate** (Schedule C / E) saves the box and reloads the page (scroll kept), so both columns come from the program. Before,
  Calculate wrote over the corrected amount; now a correction typed there stays.
- **Stale correction flag:** every saved correction keeps the per-document amount it was typed over (`edits[id]["base"]`,
  `["base_fit"]`, set by the server in `/edits` — `income.stamp_edits`). A correction that didn't change keeps its base; a new or
  changed one takes the current per document. When per document changes later (form tab fix, Schedule C / E recalculated,
  inventory amount changed, K-1 re-added, AI re-read later), the line says "document amount changed since your correction —
  re-confirm" with a **Re-confirm** button (`/edits/<token>/confirm`: the base becomes the current per document). Also in the Income
  Summary Excel note. Corrections saved before this change have no base — not flagged until they are typed again.
- The change note on a corrected line says "changed from X (per document)" (was "as read by the program").
- Tests: `tests\test_perdoc.py`.

## K-1s: one route (2026-11-04, built — pending item 5; 1120-S joins later, item 6)
- **Nothing reaches the income summary until "Add to Income Summary"** on the K-1 page. Gone: the automatic hand-off at Run check
  (`make_run` no longer calls the hand-off), the `parsers.parse_k1` fallback (K-1 PDFs are read only by `core/k1v`), the
  duplicate-by-name logic in `income.build_income_summary`, the in-memory / `_work/k1v_handoff.json` store and its claiming
  (`handoff.payloads`, the `_k1v_ctx` context processor), the `/k1v/upload` and `/k1v/handoff/clear` routes, the empty stubs
  `core/k1_parser.py` / `core/k1_summary.py`, the K-1 iframe on the main page.
- **One K-1 run per 1040 run, owned from the start.** At Run check the K-1 PDFs among the documents (+ the ones added on the K-1 page
  before, from the K-1 work file) are read into a K-1 run whose owner is the 1040 run. The K-1 box's **Open K-1 Verification** =
  `/k1v/?for=<1040 run>` (new tab): that run's K-1 PDFs (by path) and **Add K-1 PDFs…** (the 1040's file window; all files read
  again), then K-1 Interpreter / K-1 entry check. A client with no K-1 documents gets an empty run there (made on first open).
  The UT input screens picked on Verify go to the K-1 entry check (as before).
- **"Add to Income Summary"** (replaces "Upload to 1040", shown only on a run opened from the 1040): one package
  (`core/k1v/handoff.build_package`) — per K-1 line: the amount read (with statement amounts) → **per document**, the correction on
  the totals tab → **corrected amount**; adjustment lines typed on the K-1 page → corrected amount only. Adding again replaces the
  package. Saved in the 1040 WIP (key `k1`). Income summary K-1 lines are keyed **`k1|<EIN>|<line>`** (no EIN → the name, else the
  file's fingerprint + the page in the file — never the file name; line = the K-1 section's row id without its page, e.g. `int`,
  `ord|E`, `lt1256`; the sample K-1s have no EIN / name read, so they use the fingerprint), so ticks, corrected amounts typed on the
  1040 and comments stay when the client is opened again; the stale-correction flag covers a line whose amount changed when re-added.
- **The K-1 page's own work is saved:** what the page kept only in the browser (statement amounts, 11 S / 11 ZZ ticks, Verified
  ticks, comments, UT numbers, totals-tab corrections) is posted to `/k1v/state/<run>` and written by the 1040 to
  **`1040 Ultimate K-1 WIP <year> - <client>.json`** next to the WIP file (`wip.save_k1` / `load_k1`; with the K-1 PDFs added on the
  page). When the client is opened again the page starts from it (the server copy wins over the browser's).
- **Main page K-1 box:** status — "K-1 documents found — not added yet" (also in the top box) / "12 K-1s added 14:05" / "changed since
  added — add again" (the K-1s read or the page's work differ from what was added: `handoff.signature`) — Open K-1 Verification,
  K-1 entry check (when read), Remove (takes the K-1 lines off the income summary; the K-1 page's work stays).
- The separate `/k1v/` page (no `for`) stays a stand-alone reader (upload) with no Add.
- 1120-S: `handoff.FORMS = ("1065",)` — the package, keys and rules are form-neutral; item 6 adds "1120-S" there plus its lines.
- Tests: `tests\test_k1route.py`. The test harness does the Add itself (no corrections), so the answer key's Summary / UT sheets
  still cover the K-1 lines.

## Pending list
Cleared on 2026-10-21 (Lady): the old items 32-49 and the open questions were dropped. Start a new list from zero when needed.
(Item 1, ADP W-2 every box: built 2026-11-01 — see "W-2 — every box".)

Items 1–7 of 2026-11-01 built — see "File names decide nothing" below.

Items 1–3 of the second 2026-11-01 list built — see "Verified = light mint" above.

**List of 2026-11-02 (items 1–3, 7, 8 built 2026-11-03; 5 built 2026-11-04; 4 (with the AI) and 6 not built):**
1. **Per document = every source; corrected amount = the preparer's override (Lady). Built 2026-11-03 (items 1–3) — see "Per document
   = every source" above.** Amounts from the form view, Schedule C box,
   Schedule E box, K-1s and (when built) confirmed AI reads all sit in **per document** as fixed values; the preparer can change any of
   them in **corrected amount**, which wins (light pink when it differs). Today: form view (W-2 / 1098) and K-1s already work this way;
   **Schedule C and Schedule E rows have a corrected amount only** (`income.build_income_summary`: `prog` is false when `schc` is set;
   Schedule E rows reuse `schc=-1-i`) — change them to fill per document. While there, give Schedule E rows their own marker instead of
   the `schc=-1-i` trick. Check Verify return / the review Excel / Income Summary Excel / AI report still show both columns right.
2. **Stale correction flag.** When a corrected amount is saved, keep the per-document value it was typed over (`edits[id]["base"]`).
   If per document later changes (form view fix, Schedule C / E recalculated, K-1 re-uploaded, AI re-read), the line shows
   "document amount changed since your correction — re-confirm" instead of keeping the old number silently.
3. **Inventory amount = per document (Lady, 2026-11-02).** The amount typed on the inventory for a not-read document (and a free
   + line) goes into **per document** (today: corrected amount only, `inventory_added` rows are `added=True`, so `prog` is false).
   The preparer can still override it in corrected amount; the stale-correction flag (item 2) covers it when the inventory amount
   changes later. Lines added with + on the income summary itself stay corrected amount only.
4. **AI logs folder (build with the AI).** New folder `AI_logs/` next to `app.py`, never wiped: `ai_corrections.csv` (every preparer
   change to an AI answer) and `ai_usage.csv` (cost log). Created on first use. **Goes to GitHub — not in `.gitignore` (Lady).**
   So the logs hold no client data: no client / employee names, file names, SSNs, EINs, account numbers or addresses — only date,
   form type, payer / issuer (never masked), box / line, AI value, corrected value, model, guidance file, and for the cost log the
   tokens and cost. `_work` stays as it is — deleted at every start.
5. **K-1s: one route — open from the 1040, nothing counts until "Add to Income Summary" (Lady, 2026-11-02). Built 2026-11-04 — see
   "K-1s: one route" above.** The K-1 code stays
   inside the 1040 program (`core/k1v`, opened in its own browser tab); it is always started from the 1040, even for a client with
   only K-1s. Today K-1 amounts reach the income summary three ways (auto hand-off when K-1 PDFs are among the documents —
   `k1v.web.make_run` calls `handoff.put` right away; "Upload to 1040" from the embedded K-1 page; "Upload to 1040" from the
   separate `/k1v/` page, claimed by whichever 1040 page renders next) plus the `parsers.parse_k1` fallback, with duplicates removed
   by name. New:
   - **Main page K-1 box:** a status line + **Open K-1 Verification** (new tab) + Remove. Status: "K-1 documents found — not added
     yet" (also in the top box that lists what's wrong) / "12 K-1s added 14:05" / "changed since added — add again". The iframe goes.
   - **The link carries the 1040 run token** (`/k1v/?for=<token>`): the K-1 run has its owner from the start — no claiming
     (`handoff.payloads` claim logic and the `_k1v_ctx` context processor claim go; that processor also ran on the K-1 pages with the
     K-1 token, a likely bug).
   - **Opens with the K-1 PDFs found among the 1040 documents listed** (paths, no re-upload); more can be added (10 or 100 the
     same way). UT input screens picked on Verify are passed for the K-1 entry check.
   - **The 1040 reads no K-1 amounts itself:** remove the auto `handoff.put` in `make_run`, the `parsers.parse_k1` fallback (k1p in
     `parse_document`), the duplicate-by-name logic in `income.build_income_summary`, and the empty stubs `core/k1_parser.py` /
     `core/k1_summary.py`. K-1 files show "K-1 section" in the inventory.
   - **"Add to Income Summary"** (replaces "Upload to 1040") sends one package: per K-1 (name, EIN, page) its lines by section, the
     amount read → **per document**, the K-1 page correction → **corrected amount** (item 1 rule). Adding again replaces that run's
     package; the stale-correction flag (item 2) covers lines whose amount changed.
   - **Saved in the 1040 WIP** (new key, e.g. `k1`), not only in memory + `_work/k1v_handoff.json` (wiped at start — today a
     restart loses uploads and K-1 page corrections). Income summary K-1 lines keyed by **EIN + line** (today `k1v:<random token>`,
     so ticks / corrected amounts / comments on K-1 lines are lost on reopen).
   - **The K-1 page's own work** (statement amounts, flags, corrections) saved too — a K-1 WIP file in the client folder next to the
     1040 WIP — so 100 K-1s don't have to be redone after a restart.
   - The separate `/k1v/` page (no 1040 run): may stay as a stand-alone reader with **no** Add / Upload to 1040.
6. **1120-S K-1s: same path as 1065 (Lady, 2026-11-04) — build later, after item 5.** Today they are read and checked on the K-1
   page but never reach the income summary (`handoff.build_payload` and `parse_k1` keep 1065 only). Decided: 1120-S K-1s go through
   the same route as 1065s — the same "Add to Income Summary" package, per document / corrected amount rules, stale flag, EIN + line
   keys. Item 5 is built for 1065 now, in a way that 1120-S can join later without a second route.
7. **Saved work keyed by the file's fingerprint, not its name (Lady, 2026-11-02). Built 2026-11-03 — see "Saved work keyed by the
   file's fingerprint" above.** Today a line's key is built from the file name
   and the description (issuer + file name), e.g. income summary `w2|<file>|<issuer — file>`, inventory / form view / marks by path or
   file name, Verify by file name. Renaming a file or teaching a reader a better issuer changes the key, and the saved ticks, corrected
   amounts and comments silently stop showing. New: key = **fingerprint** (`inventory._file_hash`, SHA-1 of the file's contents —
   same file = same code whatever its name or folder) **+ form number in the file + box / line**, e.g. `3f9a1c…#0#b1`. Applies to
   every place that saves work per document: income / deduction summary edits and notes, ticks (marks), inventory state, form view
   corrections, Verify lines, AI answers (already planned by fingerprint), K-1 lines (EIN + line, item 5).
   - The app keeps a table fingerprint → current file name / path for the run (built when the documents are scanned).
   - **Old WIPs:** on load, convert the old keys to the new ones once (match by file name / path), so existing work isn't lost.
   - **Replaced document** (client sends a corrected form = new fingerprint): the work is not carried over; the line says
     "This document was replaced — your previous ticks and comments were on the old version".
   - **Same document re-saved** (e.g. Acrobat Save changes the bytes): fall back to matching by file name, with "matched by name —
     check".
8. **Automated tests — `C:\dev\1040_ultimate\tests` (Lady, 2026-11-02). Built 2026-11-03 — see "Automated tests" above.**
   - **Samples:** `tests\samples\<case>\` — one folder per fake client (copied from the Sample training app's Output; only fake
     names / SSNs / EINs / addresses): the documents, a prior-year return, the UT input screens print and (optional) the
     current-year return. One sample per layout a reader has special code for (W-2: ADP, IRS blank, ledger, detail sheet, list,
     ADP overflow; composites: Schwab, Fidelity / National, Vanguard, M1, Robinhood, IB, Ameriprise multi-account, Morgan Stanley box
     list; Coinbase 1099-MISC, NEC, INT substitute, 1099-R 2025 + old layout, 1099-SA, SSA-1099, 1098 lender + IRS blank, 1098-E / T,
     1095-A, Koinly Sch D / Sch 1 / 8949, Karbon, client summary) — start with the common ones. Awkward files too: password PDF, scan
     with no text, a PDF that hangs.
   - **Answer key:** `answer_key.xlsx` per case, columns File · Form # · What · Expected · Checked (initials). Sheet 1 = per
     document: type, issuer, tax year, read status, number of forms, then **every box the reader reads** (amounts and text, one row
     per box 12 / 14 code and per state / locality); exact to the cent; an empty box = `blank`, not 0; no comments / notes. Sheet 2 =
     the income / deduction summary lines (per document). Sheet 3 = the UT check: expected result per Verify line (ok / different /
     not entered / entered on another line / entered in pieces / 8949 box) — the UT print gets **deliberate mistakes** keyed in.
   - **Making the key:** a script writes a draft key from what the app reads now (every box, not only the income summary — the income
     summary holds only box 1 / 2-level amounts); Lady checks it against the PDFs, corrects, initials → frozen.
     The script (`tests\make_key.py` + a .bat) is not part of the 1040 screens and not a separate app: it uses the 1040's own readers,
     no browser. Run it whenever a new sample is added; it writes keys only for samples / files that have none yet and **never
     overwrites a checked key**.
   - **Running:** `run_tests.bat` (pytest): pass / fail per document and box, and lists every row that differs. **Claude Code runs it
     before reporting a reader / summary / Verify change as done**; a difference is either a fix (Lady updates the key) or a breakage.
   - **Habit:** every time a reader learns a new layout, that sample + its key go into `tests\samples`.
   - **GitHub:** local only for now (PDF / xlsx are git-ignored); back up on Google Drive. Samples to GitHub only later, if every file
     came from the Sample training app.

(Items 9–10 built 2026-11-02 — see "Step tabs: Mask for AI gone, three AI pages" above.)

## Decided not to build
- **Document type picked by the user (dropdown) — not built (Lady, 2026-11-02).** The type stays found from the text. A wrong type is
  fixed by teaching the classifier (`inventory.classify_text`); unknown / unreadable documents go to the AI. Revisit only if wrong
  types turn out to be frequent in a real season.

## Known gaps
- Schedule C vs the UT "C" screen: label-based, untested (no C screen print yet).
- B&D statement reader built from one print (column positions from the header rows); other layouts may need tuning.
- UT HSA / 8889 screen match for the 1099-SA: untested (no print with that screen).
- 1098: Prior Year from Schedule A line 8a untested (no return with a Schedule A); not checked against a UT input screen yet.
- List-layout W-2 / 1099-R tested on mock files only.
- A 2024 return once stopped both this app and PDF_Mask (a PDF that crashes the reader) — cause unknown (crash protection was never built).
  If it happens: note the last line in the black window and open http://127.0.0.1:5067/debug/stacks before closing.
