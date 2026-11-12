# 1040 Ultimate + UT Data Entry — how the two apps fit (shared rules)

Master copy: `C:\dev\1040_ultimate\APPS_ARCHITECTURE.md`. An identical copy sits in `C:\dev\UT_Data_Entry`.
Change it only together with Lady, in both folders at once (the two files stay identical). Decided 2026-11-05;
the UltraTax entry rules (Bot / By hand) moved to the 1040 on 2026-11-11.

## Roles
- **1040 Ultimate** (`C:\dev\1040_ultimate`) does all the reading, checking and preparing: reads the documents (Python readers,
  later the Claude API), lets the preparer verify them (form tabs, K-1 page, corrections), builds the income summary, checks what
  was entered in UltraTax against the documents (Verify return, K-1 entry check), **decides what goes into UltraTax by bot and
  what by hand** (the entry rules, `core/k1v/ut_entry.py`) and **exports the data-entry CSV**.
- **UT Data Entry** (`C:\dev\UT_Data_Entry`) only types: reads the CSV, types the `bot` rows into UltraTax **Source Data Entry
  (SDE)**, skips the `hand` rows, exports to the return, logs. It never decides again. Optional — worth it only for a client
  with many forms of one type (about 5–6 or more).

## Flow
```
Documents ─> 1040 Ultimate: read ─> verify (form tabs / K-1 page) ─┬─> Add to Income Summary (return prep)
                                                                     └─> Export for UT data entry (CSV)
CSV ─> UT Data Entry: dry run (report) ─> types into SDE ─> Export to UltraTax CS ─> preparer accepts (Data Sharing review)
UltraTax input screens print ─> 1040 Ultimate: K-1 entry check / Verify return
```

## Rules
1. **One source for each thing.** Reading, codes, explanations, amounts, Bot / By hand: the 1040. Typing into SDE: UT Data Entry.
   Never two copies of the same logic or list.
2. **Anything data entry needs from a document is added to the 1040** (e.g. K-1 box E, added to the 1040's K-1 reader).
   UT Data Entry never reads PDFs.
3. **The only link is the CSV.** UT Data Entry never imports 1040 code and never changes the 1040 folder. The 1040 never runs
   the bot. The 1040 decides Bot / By hand (the CSV's `entry`); the bot follows it: it types `bot` rows and skips `hand` rows.
4. **Three kinds of UltraTax knowledge:**
   - the **return's input screens** (K1-2 … K1-6, W2, B&D …) — what was entered, used to check → **1040**;
   - the **entry rules** — what SDE takes by bot and what goes in by hand (fields not in SDE, grey fields, checkboxes Tab
     can't reach, rows per code box) → **1040** (`core/k1v/ut_entry.py`, decided 2026-11-11);
   - the **SDE form's physical layout** — the Tab maps: where each field is, the Tab order, how to type a field → **UT Data
     Entry**. That is how to type, not a decision.
5. **Explanations live only in the 1040** (what a box / code means, tax treatment, where it goes on the return — K-1 page,
   `k1_rules`). UT Data Entry shows actions only, no explanations, no link back (the CSV is exported from the 1040 page, so it is
   already open).
6. **The bot never decides again.** It types every `entry` = `bot` row and skips every `hand` row (the 1040 lists those on its
   "To enter by hand in UltraTax" list). Its only check is a safety stop: when the CSV asks for a `bot` row its Tab map doesn't
   have (e.g. a 4th row for a box its map has 3 rows for), it stops and reports — it never guesses.
7. **One code list, UT wins**, kept in the 1040: every IRS code + any UT-only code; UT description where known, IRS description
   where they differ; "in UT" yes / no. The CSV carries `valid_in_ut`, so UT Data Entry needs no code list of its own.
8. **Problems and by-hand lines:**
   - the **1040 shows red** — what can be fixed on the document side: recipient doesn't match taxpayer / spouse, code not valid in
     UT, missing amount, a copy of the same form;
   - the **1040 shows orange** — what goes into UltraTax by hand (the entry rules): the reason on the line, and the "To enter by
     hand in UltraTax" list (on the page, as Excel and as PDF);
   - **UT Data Entry's dry run reports** the `hand` rows it will skip and any safety stop, before anything is typed.
9. **The 1040 exports only verified data** from its K-1 page / form tabs: the corrected amount when there is one, else per document.
   A copy of the same form is exported once.
10. **Client data stays local:** the CSV, logs and work files are git-ignored; tests use anonymized samples only.
11. **Decisions** go in each app's own `BUILD_NOTES.md`; a change that affects both apps is written in both.

## The CSV (the contract between the apps)
One row per line of one form. A column change is agreed with Lady and built in both apps together.

| Column | Example | Notes |
|---|---|---|
| `form` | 1065 | 1065 / 1120S / W2 / … |
| `doc_id` | 3f9a1c…#2 | one form: file fingerprint # page (the bot groups lines by it) |
| `payer_ein` | 92-3585592 | partnership / employer / payer EIN as printed |
| `payer_name` | RANCHERS GLOBAL LLC | |
| `recipient_id` | XXX-XX-2400 | partner / employee / recipient ID as printed (K-1 box E) |
| `box` | 20 | K-1 Part II item: `G` / `H1` / `J` / `K1_nonrecourse` / `K1_qualified` / `K1_recourse` / `L` / `M` / `N` (see below) |
| `code` | A | blank for boxes without codes |
| `amount` | 63.00 | as verified, with cents (UT Data Entry rounds); `X` = checkbox ticked; Part II item: the value as text |
| `valid_in_ut` | Y | from the 1040's code list; blank for boxes without codes |
| `entry` | bot | `bot` = the bot types it; `hand` = entered by hand in UltraTax, the bot skips it. Every line is exported either way. Blank when the 1040's `ut_entry` setting is off (2026-11-11) |
| `entry_reason` | Only 3 rows in Source Data Entry | why `hand`; blank for `bot` |
| `note` | see statement | free text, ignored by the bot |

**K-1 Part II items (2026-11-10).** A K-1 also exports its Part II items, one row each, before its box lines, value as
printed: `box` = the item, `code` and `valid_in_ut` blank, `amount` = text, `note` = what the item is. An item not read is
left out (N when every amount is zero). G, H1, J, L, M, N are `hand` (not in SDE). K1 is `bot` and goes as up to three
numeric rows (2026-11-11): `box` = `K1_nonrecourse` / `K1_qualified` / `K1_recourse` (UT Data Entry's Tab map field names),
`amount` = the ending amount with cents, like a box line; a row whose amount is 0 is left out (all three when every amount is 0).

| Item | `amount` example |
|---|---|
| `G` partner type | `Limited` / `General` |
| `H1` domestic / foreign | `Domestic` / `Foreign` |
| `J` profit / loss / capital % | `Profit 0.718528% -> 0.665511%; Loss 0.718528% -> 0.665511%; Capital 0.718528% -> 0.665511%` (beginning -> ending) |
| `K1_nonrecourse` / `K1_qualified` / `K1_recourse` liabilities, ending | `67.00` (one row each; 0 left out) |
| `L` capital account | `36588 -> 23164` (beginning -> ending) |
| `M` contributed property with a built-in gain (loss) | `Yes` / `No` |
| `N` net unrecognized section 704(c) gain (loss) | `0 -> 691058` (beginning -> ending) |

Box lines added from a K-1 statement have `note` = `from statement`; lines added by hand on K-1 Prep `added line`.
