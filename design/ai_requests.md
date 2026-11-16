# AI requests — screen spec (Claude API)

The first screen that calls the Claude API. The preparer ticks documents on the Document inventory, opens them on the AI
tab, picks a request per document and clicks **Send**. Nothing is sent before **Send**.
Brief: "Request for Claude Code – AI requests (first request: Create Schedule E)", 2026-11-12. Built in three steps;
this spec covers all three, the status line says what is built.

**Status:** Step 1 (connection, raw reply) built 2026-11-12. Step 2 (review grid) and Step 3 (Accept) not built yet.

## Where things live
| What | Where |
|---|---|
| The one function that calls the API | `core/ai/client.py` → `send()` (every request type uses it) |
| Request types (instructions + reply format) | `ai_requests\<name>.md` — `schedule_e.md` copied in unchanged |
| Settings (model per request, reply size, timeout, tab name, prices) | `ai_settings.json` (repo root, plain JSON, goes to GitHub — no secrets) |
| API key | `.env` in the repo root: `ANTHROPIC_API_KEY=...` (git-ignored; `.env.example` shows the format) |
| Documents → what is sent (text / PDF) | `core/ai/docs.py` |
| Cost log | `AI_logs\cost_log.csv` (never wiped, goes to GitHub, no client data) |
| Full request + raw reply (debugging) | `_work\ai\` (wiped at every start) |
| Screen | `templates/ai_requests.html` (route `/ai/<token>`, step tab 3) |

## Document inventory
- The existing **AI** column marks documents for AI (unchanged).
- Under the AI column, in the inventory's last row: a mint button **Send to AI tab**. It opens the AI tab with the ticked
  documents. It sends nothing.

## AI tab (step tab 3)
Step tab 3 (Lady, 2026-11-12 — the brief said tab 4; tab 4 "AI Return Review" stays the later return review).
Tab name comes from `ai_settings.json` → `tab_name` (today "AI Doc Review"); the step tab and the page title both use it.
Same look as the Document inventory: one card, navy header, table `v`, mint buttons inside the card.

### Card 1 — Documents for AI
Header: "Documents for AI" · "N documents ticked on the inventory".
Table (the ticked documents, in inventory order):

| # | File name | Type | Copy sent | Request |
|---|---|---|---|---|

- **#** = the document's number in the inventory (1, 2, 3 … in the inventory's order; the prior-year return is "PY").
  The AI sees the same number and file name, so it can name its sources.
- **Copy sent** — what goes to the API: *original*, or *pages 1, 2, 5* for a long PDF (its AI pages); red when the
  file can't be sent (missing, format).
- **Request** dropdown per document: *— not sent —*, *Create Schedule E*, *Parse income information (coming)* (disabled),
  *Type a request (coming)* (disabled). Default: *Create Schedule E*; the prior-year return defaults to *— not sent —*.
  The choice is kept for the run.
- No documents ticked → one line: "No documents are ticked for AI. Tick AI on the Document inventory, then Send to AI tab."

### Card 2 — one box per request that has documents
All documents with the same request go **together in one call**. For each such request, a box:
- Line 1: **Create Schedule E** · 3 documents · model `claude-opus-5-5`.
- Schedule E only: "Schedule E template: N properties from the return – attached automatically" + the short addresses
  as chips. With no properties: "Schedule E template: no properties on the return – every property will come back as
  new" (the blank template is sent).
- **Send** (mint). While the call runs: the button is disabled and reads "Working…", a note shows the elapsed seconds.
- Blocked (Send disabled, reason in red): no API key ("No API key. Put it in `.env` in the app folder: …"), the request
  file is missing, a document can't be sent (missing, format).
- Error after Send (red warning box): no key, no internet, timeout, reply cut off (reply size limit), the AI declined,
  API error with its message, reply is not valid JSON (Step 1 shows the raw text anyway). A failed call changes nothing.

### Card 3 — Reply (Step 1)
- Header: "Reply — Create Schedule E" · time · input / output tokens · estimated cost.
- The raw reply text in a scrolling monospace box (as received).
- Step 2 replaces this card with the review grid; the raw text stays available under a closed "Raw reply" arrow.

## No masking (Lady, 2026-11-12)
The firm's API agreement allows client data, so documents go **as they are** — no masking, no Mask page needed.
- **PDF**: the original file. A long document (over 10 pages) sends only its AI pages (the inventory's page list), cut
  in memory. A password-protected PDF is opened with the usual passwords and sent without the password.
- **Excel / Word / text**: converted to text from the original file (calculated values, not formulas).
- File names and the Schedule E template are sent as they are.
- The Mask page itself is unchanged (it still makes redacted copies for other uses).

## What is sent
- System prompt: the request file (`ai_requests\schedule_e.md`) as is.
- User message, in order: for each document a label line `Document 3 — Rent 2025.xlsx (Excel)` then its content
  (PDF as a PDF document block; Excel every sheet with its name as a heading, rows tab-separated; Word paragraphs and
  tables; text as is), then the attachment (Schedule E: `Schedule E template (attached by the app)` + the template as
  text, built in memory by the same code as **Export Template**), then one closing line asking for the reply.
- Formats not sent: images, .doc, .xls, .msg (shown in red on the row; convert to PDF / xlsx / docx).

## Step 2 — review grid (not built)
Parse + validate the JSON in Python: every template property exactly once; Schedule E # / Property # unique; amounts
numbers or empty; lines 18 / 22 cleared + flagged if filled; each line's property total vs `client_totals` (difference
shown); `matched` rows keep the template's addresses. Grid: one row per property, template columns, status
(matched / new / no data); each amount = AI amount + editable Corrected amount (wins); flags list, excluded items,
tie-out, the AI's summary; flagged cells marked like the app's items to check.

## Step 3 — Accept (not built)
**Accept** writes the filled Schedule E template (Excel, Schedule E + Flags sheets, `core/sche_template.write_template`)
with corrected amounts where given; empty stays empty (never 0). Then offers to load it through the existing Import
Schedule E (amounts arrive as per document). Corrections log line per corrected amount (date, request type, line, kind).
Nothing reaches the Schedule E screen or the income summary before Accept.
