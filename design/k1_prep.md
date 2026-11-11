# K-1 Prep — screen spec

Build this screen exactly as described here: **how it works and how it looks**. The mockup
`design\k1_prep_mockup.html` (v4) shows it with dummy data; where the mockup and this file differ, this file wins
(the mockup still has Source Data Entry parts that don't belong in the 1040 — see "Not on this screen").
Shared look: `design\DESIGN_RULES.md` + `design\cfoa-tools.css`. Shared rules between the apps: `APPS_ARCHITECTURE.md`.
Anything not answered here or in BUILD_NOTES.md / BUILD_HISTORY.md: ask Lady, don't guess.

## Purpose
Verify the K-1s line by line, complete what the K-1 face doesn't give (statement lines, extra lines), and export the
verified lines for UT Data Entry. Form 1065 only for now. Opened by the third button on the K-1 Verification page.

## Page layout (top to bottom)
1. **Title** "K-1 Prep", then a one-line status banner: client · number of K-1s · ready · to finish · problems.
2. **Client card:** taxpayer SSN and spouse SSN, **last 4 only**, pre-filled from the prior-year return, editable.
3. **K-1 list:** # · Partnership · EIN · Box E (as printed) · Partner (Taxpayer / Spouse / No match / Matches both) ·
   Lines · Status. The partnership name links to its K-1 card.
4. **One card per K-1**, always open (no arrows, no collapsing). Navy header: "K-1 #n · NAME  EIN …" on the left,
   "Box E … · Taxpayer · PDF page n" on the right.
5. **Bottom bar:** Save · Export for UT data entry.

Wide page, thin side margins: the tables use the screen width.

## The table on each K-1 card
One plain table — **no section rows** (no "Partner information" / "Income, deductions …" headings).
Columns: tick (outside the table) · Box · Code · Description · Per document · Corrected amount · Problem.

Row order:
1. **Part II items**, as printed: G (partner type), H1 (domestic / foreign), J (profit / loss / capital %, beginning →
   ending), K1 (liabilities, ending: nonrecourse / qualified nonrecourse / recourse), L (capital account), M, N.
   No corrected amount for these. No "by hand" or Source Data Entry wording.
2. **Part III lines** in box order. Lines printed as zero are not shown.
3. **"+ Add line"** button (last row of every K-1).

### Line with an amount
Box · Code · Description (code description from `k1_codes.py`, else the box name) · Per document · Corrected amount
(input; when changed: blue text on pink — the shared rule). A "*" or "see statement" next to an amount adds **no** tag.

### "See statement" line (the K-1 shows STMT / see statement and **no amount**, e.g. 20 Z STMT, 20 AJ * STMT, 17 * STMT)
- Description: the box name in normal text and font, then " - " and **"See statement"** in orange `#B45309`
  (only those two words are orange). Example: `AMT items - See statement`.
- Per document: `STMT`.
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

## Problems (red only — document side)
Dark red `#8B0000` on `#FDF0F0` with a 4px left line. One short line each:
- Box E matches neither taxpayer nor spouse / matches both / not read → the K-1 is not exported.
- Code not in UltraTax (still exported with `valid_in_ut` = N).
- Box needs a code · box not on the 1065 K-1 · missing amount.
- K-1 copies: "Check: same partnership and partner, different amounts" with Count / Don't count (as built).

## Ticks and status
- A tick turns the row light mint `#E8F8F5` (verified). Green means verified only.
- Status per K-1: Ready · Statement to finish · Problem · Taxpayer SSN needed · Copy — not counted · Not counted.

## Export for UT data entry
Ready K-1s only. Columns as in `APPS_ARCHITECTURE.md`. Includes: Part II items (G, H1, J, K1, L, M, N — one row each,
value as printed), every line, statement lines, free lines. Corrected amount wins over per document.

## Not on this screen (Source Data Entry knowledge — UT Data Entry's dry-run report shows it)
No Bot / By hand column · no orange "Not in Source Data Entry" / row-limit / checkbox notes · no "To enter by hand in
UltraTax" list · no row limits.
