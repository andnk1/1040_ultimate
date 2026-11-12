# K-1 UT — screen spec

(The screen was called "K-1 Prep" until 2026-11-11; the file, the code (`core/k1v/prep.py`) and the address `/prep/` keep the
old name.)

Build this screen exactly as described here: **how it works and how it looks**. The mockup
`design\k1_prep_mockup.html` (v4) shows it with dummy data; where the mockup and this file differ, this file wins.
Shared look: `design\DESIGN_RULES.md` + `design\cfoa-tools.css`. Shared rules between the apps: `APPS_ARCHITECTURE.md`.
Anything not answered here or in BUILD_NOTES.md / BUILD_HISTORY.md: ask Lady, don't guess.

## Purpose
Verify the K-1s line by line, complete what the K-1 face doesn't give (statement lines, extra lines), say what goes into
UltraTax by bot and what by hand, and export the verified lines for UT Data Entry. Form 1065 only for now. Opened by the
"K-1 UT" button on the K-1 Verification page.

## K-1 Verification page — buttons
"Add K-1 PDFs…", "K-1 Interpreter", "K-1 entry check" and "K-1 UT": mint `#7DD8C9`, text `#446B67`, bold, no border, all the
same width (the widest of them). A button that can't be used yet is faded. The tabs (K-1 1065 / K-1 1120-S) and "Read" keep
their look.

## Page layout (top to bottom)
1. **Title** "K-1 UT", then a one-line status banner: client · number of K-1s · ready · to finish · problems · items by hand.
2. **Client card:** taxpayer SSN and spouse SSN, **last 4 only**, pre-filled from the prior-year return, editable.
3. **K-1 list:** Document (PDF file name) · Partnership · EIN · Box E (as printed) · Partner (Taxpayer / Spouse / No match /
   Matches both) · Lines · Status. The partnership name links to its K-1 card.
   **Order:** by document — names that start with a number first, in number order (2 before 10), then A-Z; K-1s in the same
   PDF by page. The cards, the by-hand list and the exports follow the same order.
4. **One card per K-1**, always open (no arrows, no collapsing). Navy header: "K-1 #n · NAME  EIN …" on the left,
   "Box E … · Taxpayer · PDF page n" on the right (n = the K-1's place in the list).
5. **To enter by hand in UltraTax** card (see below).
6. **Bottom bar:** Save · Export for UT data entry · By-hand list (Excel) · By-hand list (PDF).

Wide page, thin side margins: the tables use the screen width.

## The table on each K-1 card
One plain table — **no section rows** (no "Partner information" / "Income, deductions …" headings).
Columns: tick (outside the table) · Box · Code · Description · Per document · Corrected amount · Entry · Note.

Row order:
1. **Part II items**, as printed: G (partner type), H1 (domestic / foreign), J (profit / loss / capital %, beginning →
   ending), K1 (liabilities, ending: nonrecourse / qualified nonrecourse / recourse), L (capital account), M, N.
   No corrected amount for these.
2. **Part III lines** in box order. Lines printed as zero are not shown.
3. **"+ Add line"** button (last row of every K-1).

### Line with an amount
Box · Code · Description (code description from `k1_codes.py`, else the box name) · Per document · Corrected amount
(input; when changed: blue text on pink — the shared rule). A "*" or "see statement" next to an amount adds **no** tag.

### "See statement" line (the K-1 shows STMT / see statement and **no amount**, e.g. 20 Z STMT, 20 AJ * STMT, 17 * STMT)
- Description: the box name in normal text and font, then " - " and **"See statement"** in orange `#B45309`
  (only those two words are orange). Example: `AMT items - See statement`.
- Per document: `STMT`. Entry: empty (its lines below have their own).
- A small mint **"+"** button next to the text: adds a line **directly under this row**:
  - Box: same box (same font, size, color and alignment as every other row).
  - Code: **dropdown** with that box's codes, each shown as "code - description" (from `k1_codes.py`). Pre-selected:
    the code printed on the K-1 (e.g. Z, AJ), if any.
  - Amount input, and **×** to remove the line.
- Problem until at least one line is added under it: **"Missing amount - see statement"** (red). It is cleared **only**
  by adding a line. Ticking the row does **not** clear it.

### "+ Add line" (end of every K-1)
Adds a free line: **Box** input · **Code** input (free text, no dropdown) · Description (fills itself from box + code) ·
Amount input · **×** to remove. Checked like every line: unknown box, code not valid for the box, box needs a code,
missing amount → red.

### Lines the user adds (statement lines and free lines)
Inputs in pale orange `#FEF3E2`, border `#F5C58A`, normal text `#374151`. Not pink: they are not errors.
They are stored **in the same place as the Interpreter's statement amounts**: typed once, shown on both pages
(tagged "From statement" on the Interpreter).

## Entry column — Bot / By hand (rules: `core/k1v/ut_entry.py`)
- **Bot** (teal, bold, uppercase) or **By hand** (orange `#B45309`, bold, uppercase) on every line and Part II item.
- A By hand row shows its reason in the Note cell as an orange note: text `#B45309` on `#FEF3E2`, 4px orange left line
  (`#B45309`). Orange = "UltraTax can't take it by bot", never an error.
- Rules for the 1065 K-1 (written in `ut_entry.py`; change them there):
  - Not in Source Data Entry: G, H1, J, L, M, N
  - Grey in Source Data Entry: 9c, 12
  - Checkbox – Tab can't reach it: 16, 22, 23
  - By hand: 13 AE
  - Code not in UltraTax (the code isn't in UltraTax's dropdown — the red problem stays too)
  - Rows per code box in Source Data Entry: 11:3, 13:3, 14:2, 15:2, 17:3, 18:3, 19:2, 20:8. The lines of a box that would go
    by bot are counted in the card's order; the ones beyond are By hand, "Only N rows in Source Data Entry". A line that is
    By hand for another reason uses no row.
  - Everything else is Bot (K1 liabilities too).
- A line with a red problem that keeps the K-1 out of the export (enter a box, unknown box / code, missing amount) has no
  Entry until it is fixed.
- Setting `"ut_entry": false` in `local_settings.json` hides the Entry column, the by-hand list and its two buttons (and the
  CSV's `entry` / `entry_reason` stay blank). Default: on.

## Problems (red only — document side)
Dark red `#8B0000` on `#FDF0F0` with a 4px left line, in the Note cell. One short line each:
- Box E matches neither taxpayer nor spouse / matches both / not read → the K-1 is not exported.
- Code not in UltraTax (still exported with `valid_in_ut` = N, entry = hand).
- Box needs a code · box not on the 1065 K-1 · missing amount.
- K-1 copies: "Check: same partnership and partner, different amounts" with Count / Don't count (as built).
A row with both a problem and a By hand reason shows the red line first, then the orange one (the same text only once).

## To enter by hand in UltraTax (card at the end)
Ready K-1s only (the ones exported). Columns: tick · K-1 (K-1 #n · partnership) · Box · Code · Amount · Why. Same order as the
page. The ticks are kept with the page's ticks (they mean "entered by hand").

## By-hand list (Excel) / (PDF)
The same items as the card. Columns: Document · Partnership · EIN · Box · Code · Description · Amount · Why · Done (empty).
Header: client, tax year, date, item count.
- Excel: amounts as numbers in whole dollars (Part II values as text), header row frozen.
- PDF: landscape, page numbers.
- File names: `UT by hand K-1 <year> - <client>.xlsx` / `.pdf`.

## Ticks and status
- A tick turns the row light mint `#E8F8F5` (verified). Green means verified only.
- Status per K-1: Ready · Statement to finish · Problem · Taxpayer SSN needed · Copy — not counted · Not counted.

## Export for UT data entry
Ready K-1s only. Columns as in `APPS_ARCHITECTURE.md`. Includes: Part II items (G, H1, J, L, M, N — one row each,
value as printed; K1 as up to three numeric rows `K1_nonrecourse` / `K1_qualified` / `K1_recourse`, ending amounts, a zero
left out), every line, statement lines, free lines — by-hand lines too, with `entry` = hand and `entry_reason`.
Corrected amount wins over per document.
