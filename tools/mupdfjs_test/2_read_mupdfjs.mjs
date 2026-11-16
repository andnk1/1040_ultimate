// Step 2 - read the same PDFs with MuPDF.js (the browser version of the same engine) and save what it sees.
// Run:  node 2_read_mupdfjs.mjs "<same folder>"      (needs step 1 first: it reuses the passwords step 1 found)
// Builds plain text and words the way PyMuPDF does, so step 3 can compare them one to one.
import * as mupdf from "mupdf";
import fs from "fs";
import path from "path";

const folder = process.argv[2];
const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const py = JSON.parse(fs.readFileSync(path.join(here, "pymupdf.json"), "utf8"));
const r1 = v => Math.round(v * 10) / 10;
const out = { engine: `MuPDF.js ${JSON.parse(fs.readFileSync(path.join(here, "node_modules/mupdf/package.json"), "utf8")).version}`, files: {} };

for (const rel of Object.keys(py.files)) {
  try {
    const doc = mupdf.Document.openDocument(fs.readFileSync(path.join(folder, rel)), "application/pdf");
    const pw = py.files[rel].password;
    if (doc.needsPassword() && !(pw && doc.authenticatePassword(pw))) throw new Error("password");
    const pages = [];
    for (let i = 0; i < doc.countPages(); i++) {
      // same settings PyMuPDF uses by default (flags 195): keep ligatures and spaces, clip to the page,
      // and output the font's own code for characters that have no Unicode (instead of the "?" diamond)
      const page = doc.loadPage(i);
      // MuPDF.js gives positions on the page as displayed (turned when the page has a rotation);
      // PyMuPDF gives them on the page as stored (not turned) -> undo the page's turn, like PyMuPDF:
      // displayed -> PDF space (inverse of the page transform) -> stored page, top-left origin
      const [a, b, c, d, e, f] = page.getTransform ? page.getTransform() : [1, 0, 0, -1, 0, 0];
      const det = a * d - b * c;
      const toPdf = (x, y) => [(d * (x - e) - c * (y - f)) / det, (a * (y - f) - b * (x - e)) / det];
      const pb = page.getBounds();
      const k1 = toPdf(pb[0], pb[1]), k2 = toPdf(pb[2], pb[3]);
      const bx0 = Math.min(k1[0], k2[0]), by1 = Math.max(k1[1], k2[1]);
      const un = (x, y) => { const [u, v] = toPdf(x, y); return [u - bx0, by1 - v]; };
      const [px0, py0, px1, py1] = [0, 0, Math.abs(k2[0] - k1[0]), Math.abs(k2[1] - k1[1])];
      const st = page.toStructuredText("preserve-whitespace,preserve-ligatures,clip,use-cid-for-unknown-unicode");
      const lines = [];                       // each line: [{code, c, box}]
      let cur = null, wmode = 0;
      st.walk({
        beginLine(bbox, wm) { cur = []; wmode = wm; },
        onChar(c, origin, font, size, q) {    // box = smallest rectangle around the 4 corners (also for turned text)
          const pts = [un(q[0], q[1]), un(q[2], q[3]), un(q[4], q[5]), un(q[6], q[7])];
          const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
          const b = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
          if (wmode && b[3] < b[1] + size) b[1] = b[3] - size;
          cur.push({ c, code: c.codePointAt(0), b });
        },
        endLine() { lines.push(cur); },
      });
      // words exactly like PyMuPDF's extractWORDS (copied rule by rule, including its quirks):
      // split at codes <= 32, 160 and 0x202A-0x202E; skip characters outside the page; a word whose box has no
      // size is dropped, and its box carries over into the next word (PyMuPDF only resets the box after a word)
      const delim = k => k <= 32 || k === 160 || (k >= 0x202a && k <= 0x202e);
      const empty = r => r[0] >= r[2] || r[1] >= r[3];
      const valid = r => r[0] <= r[2] && r[1] <= r[3];
      const union = (p, q) => !valid(q) ? p : !valid(p) ? q.slice()
        : [Math.min(p[0], q[0]), Math.min(p[1], q[1]), Math.max(p[2], q[2]), Math.max(p[3], q[3])];
      const NONE = [Infinity, Infinity, -Infinity, -Infinity];
      const off = r => px0 >= r[2] || py0 >= r[3] || px1 <= r[0] || py1 <= r[1];
      let text = "", words = [], wb = NONE, t = "";
      const emit = () => { words.push([r1(wb[0]), r1(wb[1]), r1(wb[2]), r1(wb[3]), t]); wb = NONE; };
      for (const ln of lines) {
        text += ln.map(o => o.c).join("") + "\n";
        t = "";
        for (const o of ln) {
          if (off(o.b)) continue;
          if (!t && o.code === 0x200d) continue;
          if (delim(o.code)) {
            if (!t) continue;
            if (!empty(wb)) emit();
            t = "";
            continue;
          }
          t += o.c;
          wb = union(wb, o.b);
        }
        if (t && !empty(wb)) emit();
      }
      pages.push({ text, words });
    }
    out.files[rel] = { pages };
    console.log(`read  ${rel}  (${pages.length} pages)`);
  } catch (e) {
    out.files[rel] = { error: String(e.message || e) };
  }
}
fs.writeFileSync(path.join(here, "mupdfjs.json"), JSON.stringify(out));
console.log(`\nDone - ${Object.keys(out.files).length} PDFs -> mupdfjs.json   [${out.engine}]`);
