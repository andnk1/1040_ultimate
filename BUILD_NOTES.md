# 1040 Ultimate — build notes (read this first)

Hand-off for a new Claude session: the working rules, what's decided but not built, the open questions and the pending list.
Finished, settled work is in **BUILD_HISTORY.md** (moved there unchanged, in date order — the "history:" names below are its
section titles); a screen with a spec is in `design\` (e.g. `design\k1_prep.md`). Last updated 2026-11-10.

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

## Settled rules a change must keep (details in the history)
- Nothing is decided by the file name, except K-1 and Karbon — history: "File names decide nothing" (2026-11-01).
- Per document = what came in, from every source; corrected amount = the preparer's override and wins; a changed per
  document flags the correction — history: "Per document = every source" (2026-11-03).
- Saved work is keyed by the file's fingerprint, never its name — history: "Saved work keyed by the file's fingerprint" (2026-11-03).
- K-1 amounts reach the income summary only through "Add to Income Summary" — history: "K-1s: one route" (2026-11-04).
- Look: `design\DESIGN_RULES.md` (changed = light pink / blue, verified = light mint, red only for warnings) — history:
  "Design — …" and "Verified = light mint" (2026-11-01).
- Run `tests\run_tests.bat` before reporting a reader / summary / Verify change as done — history: "Automated tests" (2026-11-03).
- A test server never writes a work in progress (`wip_mod.save` a no-op) — history: "Verified = light mint" (2026-11-01).
- From a cloud session: each changed file to a new output path per commit — history: "K-1 section" (2026-10-21).
- The 1040 knows nothing about Source Data Entry; the only link to UT_Data_Entry is the CSV — `APPS_ARCHITECTURE.md`.

## Decided, not built (full text in the history)
- **AI (Claude API):** "Parse with AI" on ticked documents, one call per document, nothing counts until confirmed, two models,
  saved by fingerprint, guidance not training, scans as images (no OCR) — history: "AI (Claude API)" (2026-11-02).
  Learning plan: https://claude.ai/artifact/UF1Bn9myJWtaZPaJq6XyYF
- **Fillable PDFs flattened** before the readers and the AI (small step, can come first) — same section.
- **Masking and the Print return app = separate apps;** the masking code to take out of the 1040 is listed there —
  history: "Masking and printing = separate apps" (2026-11-02).
- **Form view for the other forms:** 1099 composite next (sub-tabs, B-Summary totals only), then the single forms —
  history: "Form view — next forms" (2026-10-31).
- **Generic export CSV for every form + an export button per form tab** — history: "K-1 Prep and UT data entry" (2026-11-05);
  pending item 2 of the 2026-11-05 list.

## Open questions
- AI: mask documents before sending? Depends on the retention agreement — history: "AI (Claude API)".
- One start file for all the apps, or each started on its own? — history: "Masking and printing = separate apps".
- 1099 composite joint accounts: how UltraTax carries them (decide when the composite is built) — history: "Form view — next forms".
- The Sample K-1s read with no EIN and no partnership name — pending item 7 of the 2026-11-05 list.
- 1120-S K-1s: box E untested (no sample) — history: "K-1 reader: box E".

## Pending list (each list in full: history, "Pending list")
List of 2026-11-02:
- 4. `AI_logs/` folder (corrections + cost log, goes to GitHub, no client data) — build with the AI.
- 6. 1120-S K-1s through the same route as 1065 (`handoff.FORMS`).

List of 2026-11-05:
- 2. Generic export CSV + export button per form tab (W2, 1098-M first).
- 4. One UT check for K-1s: Verify return skips the K-1 lines and shows the K-1 entry check's result.
- 5. Clean-up: move what `screen_verify` borrows (`norm`, `MAP`) into it; delete the old `verify1040_*` files.
- 7. Sample K-1s: no EIN / name read — look at the reader with Lady (correct the note and the test keys if needed).

Decided not to build: a document-type dropdown — history: "Decided not to build" (2026-11-02).

## Known gaps
- Schedule C vs the UT "C" screen: label-based, untested (no C screen print yet).
- B&D statement reader built from one print (column positions from the header rows); other layouts may need tuning.
- UT HSA / 8889 screen match for the 1099-SA: untested (no print with that screen).
- 1098: Prior Year from Schedule A line 8a untested (no return with a Schedule A); not checked against a UT input screen yet.
- List-layout W-2 / 1099-R tested on mock files only.
- A 2024 return once stopped both this app and PDF_Mask (a PDF that crashes the reader) — cause unknown (crash protection was never built).
  If it happens: note the last line in the black window and open http://127.0.0.1:5067/debug/stacks before closing.
