// Schedule C box: one business at a time (picker), optional P&L mapping on the left, Schedule C on the right.
// Every amount is soft: the P&L amount (meals 50%) and the Schedule C line (sum of the mapped accounts) can be typed over;
// typed amounts show in green, clearing a box goes back to the calculated amount.
// Needs (from summary.html): LINES, MAPL, TOKEN, BIZ, fmt, num, recalc.
const LBL = Object.fromEntries(LINES);
const CALC = new Set(['3', '5', '7', '28', '29', '31']);
const EXP = ['8','9','10','11','12','13','14','15','16a','16b','17','18','19','20a','20b','21','22','23','24a','24b','25','26','27a','27b'];
const INCOME_LINES = new Set(['1', '6']);
const SECT = {income: 'Income', cogs: 'Cost of goods sold', expense: 'Expenses', other_income: 'Other income', other_expense: 'Other expenses'};
let CUR = 0;
if (!BIZ.length) BIZ.push({name: '', py: null, cy: {}});
BIZ.forEach(b => { b.cy = b.cy || {}; });

const typed = (b, k) => b.cy[k] !== undefined && String(b.cy[k]).trim() !== '';
const defAmt = r => r.line === '24b' ? Math.round(r.books * 50) / 100 : r.books;
// a P&L row's contribution to a Schedule C line (an expense mapped to an income line counts negative, and the reverse)
const contrib = r => {
  if (r.line === 'nd' || r.line === 'x') return 0;
  const incSide = r.section === 'income' || r.section === 'other_income';
  return (incSide === INCOME_LINES.has(r.line) ? 1 : -1) * num(r.amount);
};
function mapped(b) {
  const m = {};
  ((b.pl && b.pl.rows) || []).forEach(r => { m[r.line] = (m[r.line] || 0) + contrib(r); });
  return m;
}
function eff(b, k, m) {
  if (typed(b, k)) return num(b.cy[k]);
  m = m || mapped(b);
  return m[k] !== undefined ? m[k] : null;
}
function calc(b) {
  const m = mapped(b), v = k => eff(b, k, m) || 0, o = {};
  o['3'] = v('1') - v('2');
  o['5'] = o['3'] - v('4');
  o['7'] = o['5'] + v('6');
  o['28'] = EXP.reduce((s, k) => s + v(k), 0);
  o['29'] = o['7'] - o['28'];
  const ho = v('30');
  // home office: not used when the business has a loss; never more than the tentative profit
  o.hoUsed = o['29'] > 0 ? Math.min(ho, o['29']) : 0;
  o.hoNote = !ho ? '' : (o['29'] <= 0 ? 'Business has a loss — home office not used for verification.'
            : (ho > o['29'] ? 'Limited to the tentative profit (line 29).' : ''));
  o['31'] = o['29'] - o.hoUsed;
  if (typed(b, 'tot')) {                       // total only: the bottom line typed, no line detail
    o['31'] = num(b.cy['tot']); o.totalOnly = true;
  }
  return o;
}
const has = b => Object.values(b.cy || {}).some(v => String(v).trim() !== '') || !!(b.pl && b.pl.rows && b.pl.rows.length);
function totRow(b) {                       // "Enter total": only the bottom line (net profit / loss)
  const t = typed(b, 'tot');
  return `<tr class="totonly"><td class="b">Total</td><td>Enter total only <span class="note">— net profit / (loss) when there's no line detail;
    it replaces line 31. Not checked against the UT input screens (a note is added)</span></td><td></td>
    <td class="n"><input class="amt scin ${t ? 'edited' : ''}" data-k="tot" value="${t ? fmt(num(b.cy['tot'])) : ''}" data-m=""></td></tr>`;
}
function finals(b) {                       // every Schedule C line as it stands (for the downloads)
  const m = mapped(b), o = calc(b), f = {};
  LINES.forEach(([k]) => { f[k] = CALC.has(k) ? o[k] : (eff(b, k, m) || 0); });
  f['30'] = o.hoUsed;
  return f;
}

// ---------------------------------------------------------------- drawing
function scRow(b, k, o, m) {
  const py = b.py && b.py[k] !== undefined ? b.py[k] : null;
  let label = LBL[k];
  if (k === '24b') label = 'Deductible meals <span class="note">— deductible part only (usually 1/2)</span>';
  if (k === '30') label = 'Expenses for business use of your home <span class="note">— used only when the business has a profit</span>';
  let cy;
  if (CALC.has(k)) cy = `<td class="n calc" id="c_${k}">${has(b) ? fmt(o[k]) : ''}</td>`;
  else {
    const t = typed(b, k), mv = m[k];
    const val = t ? fmt(num(b.cy[k])) : (mv !== undefined ? fmt(mv) : '');
    cy = `<td class="n"><input class="amt scin ${t ? 'edited' : (mv !== undefined ? 'soft' : '')}" data-k="${k}" value="${val}"
          data-m="${mv !== undefined ? mv.toFixed(2) : ''}" placeholder="${py !== null ? fmt(py) : ''}"></td>`;
  }
  const extra = k === '30' ? `<div class="ho-off" id="hoNote">${o.hoNote}</div>` : '';
  return `<tr${CALC.has(k) ? ' class="tot"' : ''}><td class="b">${k}</td><td>${label}${extra}</td><td class="n note">${py !== null ? fmt(py) : ''}</td>${cy}</tr>`;
}
function tickRow(b) {                      // reviewed ✓ (kept with the work in progress, listed in the Save review Excel)
  const k = ('schc|' + (b.name || (b.pl && b.pl.company) || 'Business ' + (CUR + 1))).replace(/"/g, '&quot;');
  return `<tr class="tickrow"><td></td><td class="note">Reviewed ✓</td><td></td>
    <td class="n"><input type="checkbox" data-mk="${k}" ${(window.MARKS || {})[k] ? 'checked' : ''} title="Reviewed"></td></tr>`;
}
function scTable(b) {
  const o = calc(b), m = mapped(b), part = t => `<tr class="sec"><td colspan="4">${t}</td></tr>`;
  const rows = part('Part I · Income') + ['1','2','3','4','5','6','7'].map(k => scRow(b, k, o, m)).join('')
    + part('Part II · Expenses') + EXP.map(k => scRow(b, k, o, m)).join('') + ['28','29','30','31'].map(k => scRow(b, k, o, m)).join('')
    + totRow(b) + tickRow(b);
  const nd = ((b.pl && b.pl.rows) || []).filter(r => r.line === 'nd' || r.line === 'x');
  const ndNote = nd.length ? `<p class="note">Not on Schedule C: ${nd.map(r => `${r.account} ${fmt(num(r.amount))} (${r.line === 'nd' ? 'N/D' : 'personal'})`).join('; ')}</p>` : '';
  return `<table class="v sct"><tr><th>Line</th><th>Description</th><th class="n">Last year</th><th class="n">This year</th></tr>${rows}</table>${ndNote}`;
}
function plTable(b) {
  const pl = b.pl, opts = MAPL.map(([k, l]) => `<option value="${k}">${l}</option>`).join('');
  let last = null, body = '';
  pl.rows.forEach((r, j) => {
    if (r.section !== last) { body += `<tr class="sec"><td colspan="4">${SECT[r.section] || r.section}</td></tr>`; last = r.section; }
    body += `<tr class="${r.line === 'nd' || r.line === 'x' ? 'off' : ''}"><td>${r.account}</td><td class="n">${fmt(r.books)}</td>
      <td><select class="plsel" data-j="${j}">${opts.replace(`value="${r.line}"`, `value="${r.line}" selected`)}</select></td>
      <td class="n"><input class="amt plin ${r.typed ? 'edited' : 'soft'}" data-j="${j}" value="${fmt(num(r.amount))}"></td></tr>`;
  });
  const diff = (pl.net_income || 0) - (pl.computed || 0);
  return `<div class="plhead"><b>${pl.file}</b>${pl.company ? ' · ' + pl.company : ''}</div>
    <table class="v plt"><tr><th>P&L account</th><th class="n">Books</th><th>Schedule C line</th><th class="n">Amount</th></tr>${body}
    <tr class="tot"><td>Net income per P&L</td><td class="n">${pl.net_income !== null && pl.net_income !== undefined ? fmt(pl.net_income) : '—'}</td><td>Accounts read ${fmt(pl.computed)}</td>
      <td class="n ${Math.abs(diff) > 0.01 ? 'flag' : ''}">${Math.abs(diff) > 0.01 ? 'diff ' + fmt(diff) : '✓ ties'}</td></tr></table>`;
}
function render() {
  if (CUR >= BIZ.length) CUR = BIZ.length - 1;
  const b = BIZ[CUR];
  document.getElementById('bizPick').innerHTML = BIZ.map((x, i) =>
    `<button type="button" class="tabbtn ${i === CUR ? 'on' : ''}" onclick="pick(${i})">${x.name || (x.pl && x.pl.company) || 'Business ' + (i + 1)}${x.calculated ? ' ✓' : ''}</button>`).join('')
    + `<button type="button" class="tabbtn add" onclick="addBiz()">+ Add business</button>`;
  const nameBox = b.py ? `<span class="bfixed">${b.name || ''}</span>`
    : `<input class="bname" value="${(b.name || '').replace(/"/g, '&quot;')}" placeholder="Business name (new this year)">`;
  const err = b.pl && b.pl.error ? `<div class="error">${b.pl.error}</div>` : '';
  document.getElementById('schcBox').innerHTML = `
    <div class="bar" style="margin:0 0 10px">${nameBox}
      <button type="button" class="alt small pickbtn" onclick="addPL()">Add P&amp;L…</button>
      ${b.pl ? `<button type="button" class="light small" onclick="dropPL()">Remove P&amp;L</button>
        <span class="dl">Download: <a href="/schc/${TOKEN}/${CUR}/workpaper.csv" onclick="return dl(this)">workpaper</a> ·
        <a href="/schc/${TOKEN}/${CUR}/other_expenses.csv" onclick="return dl(this)">other expenses (Part V)</a> ·
        <a href="/schc/${TOKEN}/${CUR}/book_tax.csv" onclick="return dl(this)">books vs Schedule C</a></span>` : ''}
      ${b.py ? `<button type="button" class="light small" onclick="usePY()">Use PY amounts</button>` : ''}
      <button type="button" class="light small" onclick="clearBiz()">Clear typed amounts</button>
      ${!b.py && BIZ.length > 1 ? `<button type="button" class="light small" onclick="delBiz()">Remove business</button>` : ''}
      <span id="plMsg" class="note"></span></div>${err}
    <div class="${b.pl ? 'plgrid' : ''}">${b.pl ? `<div class="plcol">${plTable(b)}</div>` : ''}<div class="sccol">${scTable(b)}</div></div>`;
}
function refresh() {                       // totals and soft (mapped) amounts, without redrawing the boxes
  const b = BIZ[CUR], o = calc(b), m = mapped(b), on = has(b);
  CALC.forEach(k => { const el = document.getElementById('c_' + k); if (el) el.textContent = on ? fmt(o[k]) : ''; });
  document.querySelectorAll('#schcBox input.scin').forEach(el => {
    const k = el.dataset.k, mv = m[k];
    el.dataset.m = mv !== undefined ? mv.toFixed(2) : '';
    if (!typed(b, k) && document.activeElement !== el) { el.value = mv !== undefined ? fmt(mv) : ''; el.className = 'amt scin ' + (mv !== undefined ? 'soft' : ''); }
  });
  const ho = document.getElementById('hoNote'); if (ho) ho.textContent = o.hoNote;
}

// ---------------------------------------------------------------- actions
function pick(i) { CUR = i; render(); }
function addBiz() { BIZ.push({name: '', py: null, cy: {}}); CUR = BIZ.length - 1; render(); save(); document.getElementById('schc').open = true; }
function delBiz() { BIZ.splice(CUR, 1); CUR = Math.max(0, CUR - 1); render(); save(); }
function usePY() { const b = BIZ[CUR]; Object.keys(b.py || {}).forEach(k => { if (!CALC.has(k)) b.cy[k] = b.py[k]; }); render(); save(); }
function clearBiz() { BIZ[CUR].cy = {}; (BIZ[CUR].pl && BIZ[CUR].pl.rows || []).forEach(r => { r.typed = false; r.amount = defAmt(r); }); render(); save(); }
function dropPL() { delete BIZ[CUR].pl; render(); save(); }
async function addPL() {
  const msg = document.getElementById('plMsg'); msg.textContent = 'Choose the P&L (CSV, Excel or PDF)…';
  const j = await browse('pl');
  const path = (j.paths || [])[0];
  if (!path) { msg.textContent = ''; return; }
  msg.textContent = 'Reading…';
  const pl = await (await fetch(`/pl/${TOKEN}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({path})})).json();
  const b = BIZ[CUR];
  b.pl = pl;
  if (!b.py && !b.name && pl.company) b.name = pl.company;
  render(); saveNow();
}
function dl(a) { saveNow(); setTimeout(() => { window.location = a.href; }, 350); return false; }
function calculateSchC() {
  let any = false;
  BIZ.forEach((b, i) => {
    const on = has(b), v = on ? calc(b)['31'] : null;
    b.calculated = on;
    if (on) any = true;
    document.querySelectorAll(`[data-schc="${i}"] input`).forEach(el => { el.value = on ? fmt(v) : ''; el.dataset.read = on ? v.toFixed(2) : ''; el.dataset.v = el.dataset.read; el.dataset.shown = el.value; });
    const nm = document.querySelector(`[data-schcname="${i}"]`); if (nm) nm.textContent = b.name || (b.pl && b.pl.company) || 'Business';
  });
  recalc(true);
  document.getElementById('calcMsg').textContent = any ? 'Moved to the income summary ✓' : 'Nothing entered yet.';
  render();
  if (BIZ.some((b, i) => b.calculated && !document.querySelector(`[data-schc="${i}"]`))) {
    clearTimeout(t); post().then(() => location.reload()); return;
  }
  saveNow();
}

let t;
const post = () => fetch(`/schc/${TOKEN}`, {method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify(BIZ.map(b => ({...b, name: b.name || (b.pl && b.pl.company) || '', totals: calc(b), final: finals(b),
                                       total_only: typed(b, 'tot')})))});
function save() {
  clearTimeout(t); t = setTimeout(post, 400);
  const m = document.getElementById('calcMsg'); if (m && BIZ.some(b => b.calculated)) m.textContent = 'Changed — click Calculate to update the income summary.';
}
function saveNow() { clearTimeout(t); return post(); }

const box = document.getElementById('schcBox');
box.addEventListener('input', e => {
  const el = e.target, b = BIZ[CUR];
  if (el.classList.contains('bname')) { b.name = el.value; save(); return; }
  if (el.classList.contains('scin')) {
    const v = el.value.trim(), m = el.dataset.m;
    if (v === '' || (m !== '' && Math.abs(num(v) - parseFloat(m)) < 0.005)) delete b.cy[el.dataset.k]; else b.cy[el.dataset.k] = v;
    el.classList.toggle('edited', typed(b, el.dataset.k)); el.classList.toggle('soft', !typed(b, el.dataset.k) && m !== '');
  } else if (el.classList.contains('plin')) {
    const r = b.pl.rows[+el.dataset.j], v = el.value.trim();
    if (v === '' || Math.abs(num(v) - defAmt(r)) < 0.005) { r.typed = false; r.amount = defAmt(r); }
    else { r.typed = true; r.amount = num(v); }
    el.classList.toggle('edited', r.typed); el.classList.toggle('soft', !r.typed);
  } else return;
  refresh(); save();
});
box.addEventListener('focusout', e => {
  const el = e.target, b = BIZ[CUR];
  if (el.classList.contains('plin') && el.value.trim() === '') { el.value = fmt(b.pl.rows[+el.dataset.j].amount); }
  if (el.classList.contains('scin') && el.value.trim() === '') refresh();
});
box.addEventListener('change', e => {
  const el = e.target; if (!el.classList.contains('plsel')) return;
  const r = BIZ[CUR].pl.rows[+el.dataset.j];
  r.line = el.value;
  if (!r.typed) r.amount = defAmt(r);
  el.closest('tr').classList.toggle('off', r.line === 'nd' || r.line === 'x');
  const inp = el.closest('tr').querySelector('input.plin'); if (inp && !r.typed) inp.value = fmt(r.amount);
  render(); save();
});
render();
