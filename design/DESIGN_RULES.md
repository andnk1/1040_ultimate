# CFO Associates tools — design rules

One look for every internal app (1040 Preparation tool, K-1 Verification, PDF Mask, Sample training, 1099-DA Compare …).
Use `cfoa-tools.css` (next to this file) as the base stylesheet; app-specific CSS goes after it and must not change these rules.
Reference page: `C:\dev\1040_ultimate\_work\first_page_mockup.html`.

## Font
- System font: `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` (Segoe UI on Windows). No web fonts.
- Page title (h1): 2.2rem, weight 800, navy `#003366`, thin grey rule under it.
- Body / tables: 0.86rem, ink `#374151`. Table headers and section labels: 0.70–0.72rem, UPPERCASE, letter-spacing .04em, teal `#4e7874`.
- Numbers: right-aligned, tabular figures (`font-variant-numeric: tabular-nums`).

## Colors
| Use | Color |
|---|---|
| Navy — titles, card headers, active tab | `#003366` |
| Blue — links / info | `#3C69AB` |
| Teal — bottom-bar buttons, table header text, labels | `#4e7874` |
| Green — text on mint buttons, bottom-button hover | `#446B67` |
| Mint — buttons inside the boxes | `#7DD8C9` (hover `#9BE3D7`) |
| Verified row (ticked) | light mint `#E8F8F5` |
| Verified total row | `#D3F1EC` |
| Total row (not verified) | `#E3F1E8` |
| Grand total row | `#DADCE3`, navy text, 2px top line `#9AA3B2` |
| Section row inside a table | `#F7F7FB`, teal UPPERCASE text |
| Amount changed by the user | background `#FDF0F0`, text blue `#1F5FBF`, not bold |
| Warning (as in K-1 Verification) | text `#8B0000` on `#FDF0F0` + 4px left line `#8B0000` |
| Announcement / info box | background `#F1F5F4`, text `#294F4C`, 4px left line `#294F4C` |
| Card background | `#EFEFF7`, border `#9AA3B2` |
| Grey — inactive tabs, table lines | `#DFE1E9` |
| Ink — normal text | `#374151` |

Rules:
- **Green means verified** (and totals). Don't use green for anything else.
- **Red only for warnings / real data-entry differences.** Negative numbers are black.
- A changed amount and a warning share the light pink background; they're told apart by the text color
  (blue = changed by the user, dark red + left line = warning).

## Layout and components
- **Step tabs:** all the same width (210px), centered text. Active = navy with white text; others = grey `#DFE1E9`;
  not available yet = faded.
- **Cards (sections):** navy header bar, UPPERCASE white title, count on the right (e.g. "9 documents") — no explanations.
  Every section is collapsible (▶ arrow, starts closed, remembers open state) except the app's main summary.
- **Tables:** rounded corners (8px), white, thin grey lines.
- **Verify ticks (✓):** outside the table, on the grey card background, lined up with their row. Ticking turns the
  white part of the row light mint.
- **Buttons inside boxes:** mint `#7DD8C9`, text `#446B67`, bold, no border, all the same width (190px or the longest label).
- **Bottom-bar buttons:** teal `#4e7874`, white text, hover `#446B67`, all the same width (200px).
- **Announcement box** (top of the page: documents, work in progress, client comments): info colors above with the left line.
- **Warnings:** one line each, warning colors above with the left line.

## Text
- No explanatory or help text on screen ("how to use" notes, header sub-texts). Instructions go in a separate guide if needed.
- Keep: counts, status messages ("No K-1 documents were added"), warnings and errors.
- Wording: "per document" = as read by the program; "corrected amount" = what goes on the return. Never "per preparer".
- Amounts on screen in whole dollars.
