# 1040 Ultimate — build notes (read this first)

Hand-off for a new Claude session. The README describes what the app does; this file holds the working rules,
the pending list, the open questions and the known gaps that only lived in the chat. Last updated 2026-10-19.

## Working rules (from Lady)
- **List first, build on "go".** When Lady lists changes ("no changes yet", "keep a tab", "we may have more"), only add
  them to the numbered pending list below and confirm. Build only when she says go / implement / apply.
- **Client data stays local.** Never use unmasked documents; she removes them. Work only with masked (redacted) files.
- **Masking:** always mask the firm EIN kept in `local_settings.json` (never put it in code or GitHub). First names stay
  visible; payer / employer names and amounts are never masked.
- **GitHub:** she removes PDFs herself before pushing; `.gitignore` excludes client data, WIP json, `.bak`, xlsx.
  Keep client names / numbers out of code, README and this file.
- **Don't modify** `redact_pdf.py` or `k1_summary.py` (PDF_Mask). A small addition to PDF_Mask's `web_app.py` is OK
  if needed (see item 46).
- **Schedule C box:** don't change the design (P&L mapping beside it); no more businesses per page.
- **Style on screen:** whole dollars; negatives black (no red anywhere for negatives); numbers typed by the preparer
  blue, not bold; changed amounts yellow; red only for real data-entry differences.
- **Verification is line by line** — never by totals or net amounts (UT doesn't calculate those on the input screens).
  Two sections: (1) document verification, (2) UltraTax entries with no document. Tolerance ±$1 per line.
- **Readers read only labelled IRS boxes** (box number + IRS box name), in table or list layout. A summary page
  without the IRS box names is not read.
- Replies: short, plain language; one question at a time.

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

## Pending list (not built yet)
32. Document verification — "UT screen" column shows only the page number ("p. 10"; "p. 13, 14" when entered in
    pieces); notes like "entered in 2 pieces" stay; header "UT page".
33. K-1 page detection: a page is a K-1 only with "Schedule K-1" + the form line (1065 / 1120-S / 1041) + the Part I
    heading ("Information About the Partnership / the Corporation / the Estate or Trust") — wherever it sits in the file.
34. Faster file check: probe all PDFs in one separate process instead of one per file.
35. K-1 summary import: a standard template (one row per K-1) for large / messy packages processed first; imported
    like the Schedule E sheet; K-1 PDFs then aren't in the document list.
36. "Skip K-1 verification" checkbox on Verify return (off by default): K-1 lines leave document verification; UT K-1
    screen entries go to a collapsed "skipped by preparer" note; noted in the review Excel. Needs a UT K-1 screens print.
37. Crash protection: read every PDF (prior-year return, documents, UT print) in a separate process; a reader crash
    gives a message with the file and page, and the app keeps running.
38. Automatic repair copy: when a file crashes the reader, try a cleaned copy before giving up.
39. PDF_Mask: the same crash protection in its own wrapper (not in `redact_pdf.py`).
40. "Partly read" documents: the comment lists what WAS read, with the amounts; the not-read part as a short flag.
41. Green when ticked, everywhere in the 1040 verification: income / deduction lines and totals, each Schedule C
    business, each Schedule E property (only that property's column), UT summary fields, forms filed. A yellow
    "changed" amount box stays yellow inside a green line.
42. Document inventory sort: names starting with a number sort by the number (1, 2, 10), then A–Z; others after.
43. Unticked documents on "Choose the files": not opened / not read (saves time), still listed on the inventory as
    "Not read" + "skipped by preparer"; amount + line can be typed there; not flagged as an error.
44. Plain "Not read" in comments (drop "(AI review)"); keep a short reason when known (password, missing page).
45. Remove the AI tick column from the document inventory.
46. AI page (screen 4): list every document (prior-year return too) with two ticks, Mask and AI. "Mask selected…"
    starts PDF_Mask if needed and opens it in a new window with the ticked files pre-loaded (needs a small route in
    PDF_Mask `web_app.py` that receives a file list — it already pre-loads files from its K-1 screen). AI tick: saved,
    nothing else yet.
47. Schedule C box: move "Last year" and "This year" left, close to the line descriptions.
48. Schedule C last line text: "Enter Total Only - Not checked against UT input".
49. Capital gains by Form 8949 box on the income summary: one row per box A-L (not only ST / LT), the box letter on
    every row even when the document doesn't print it. Derived when missing: 1099-B basis reported = A (ST) / D (LT),
    not reported (noncovered) = B / E; 1099-DA basis reported = G / J, not reported = H / K; no 1099-B / 1099-DA =
    C / F (other) or I / L (digital assets). Term not known = flagged. Same boxes used by the 8949 check on Verify return.

## Open questions for Lady
- Item 46: once Mask on the AI page opens PDF_Mask, remove 1040 Ultimate's own screen 3 ("Mask for AI") or keep it?
- Schedule E template: the Owner (T/S/J) column was removed from the screen; keep it in the Excel template (it
  groups properties on import) or remove it too?
- Form 8949 box check for single-letter boxes ("LT (D)") — offered; she said fine for now (not on the list).

## Known gaps
- Schedule C vs the UT "C" screen: label-based, untested (no C screen print yet).
- B&D statement reader built from one print (column positions from the header rows); other layouts may need tuning.
- UT HSA / 8889 screen match for the 1099-SA: untested (no print with that screen).
- No reader for the UT K-1 screens yet (needed for items 35 / 36 to check K-1 lines).
- List-layout W-2 / 1099-R tested on mock files only.
- W-2 box 5 read as 0 on one employer print (box 5 isn't used in any check).
- A 2024 return once stopped both this app and PDF_Mask (a PDF that crashes the reader) — cause unknown; items 37–39.
  If it happens: note the last line in the black window and open http://127.0.0.1:5067/debug/stacks before closing.
