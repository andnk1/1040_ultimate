// Schedule E box - 6 properties per tab (Schedule E 1 = properties 1-6, Schedule E 2 = 7-12 ...), one column each.
// Each column: short address (on the "Income" line), type, fair rental / personal use days, lines 3-22, last year's
// income or (loss) (read only), and a ✓ at the bottom (reviewed - kept with the work in progress).
// Grey placeholder = last year's amount; typed amounts show in green. Lines 20 / 21 calculate.
// Line 22 (loss allowed after Form 8582) is entered; the property's result = line 21, or line 22 when entered for a loss.
// Needs (from summary.html): ELINES, TOKEN, PROPS, fmt, num, recalc.
(function () {
  const LBL = Object.fromEntries(ELINES);
  const EXP = ['5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19'];
  const CALC = new Set(['20', '21']);
  const TYPES = ['', 'Single Family Residence', 'Multi-Family Residence', 'Vacation/Short-Term Rental', 'Commercial', 'Land',
                 'Royalties', 'Self-Rental', 'Other'];
  const PER = 6;
  let SCH = 0, t;
  if (!PROPS.length) PROPS.push({name: '', py: null, cy: {}, info: {}});
  PROPS.forEach(p => { p.cy = p.cy || {}; p.info = p.info || {}; });
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const typed = (p, k) => p.cy[k] !== undefined && String(p.cy[k]).trim() !== '';
  const v = (p, k) => typed(p, k) ? num(p.cy[k]) : 0;
  const has = p => Object.values(p.cy || {}).some(x => String(x).trim() !== '');
  const nSch = () => Math.max(1, Math.ceil(PROPS.length / PER));
  function calc(p) {
    const o = {};
    o['20'] = EXP.reduce((s, k) => s + v(p, k), 0);
    o['21'] = v(p, '3') + v(p, '4') - o['20'];
    const l22 = typed(p, '22') ? -Math.abs(num(p.cy['22'])) : null;
    o['22'] = l22;
    o.net = o['21'] < 0 && l22 !== null ? l22 : o['21'];
    o.note = (o['21'] < 0 && l22 !== null
      ? `Loss ${fmt(o['21'])} limited to ${fmt(l22)} (Form 8582) — from the Schedule E box`
      : 'From the Schedule E box (Calculate)') + (p.notes ? ' — ' + p.notes : '');
    return o;
  }
  function cell(p, j, k, o) {
    if (!p) return '<td></td>';
    if (CALC.has(k)) return `<td class="n calc" id="e_${k}_${j}">${has(p) ? fmt(o[k]) : ''}</td>`;
    const py = p.py && p.py[k] !== undefined ? fmt(p.py[k]) : '';
    return `<td class="n"><input class="amt ein ${typed(p, k) ? 'edited' : ''}" data-j="${j}" data-k="${k}"
              value="${typed(p, k) ? fmt(num(p.cy[k])) : ''}" placeholder="${py}" title="${py ? 'Last year ' + py : ''}"></td>`;
  }
  function render() {
    if (SCH >= nSch()) SCH = nSch() - 1;
    const idx = Array.from({length: PER}, (_, c) => SCH * PER + c), ps = idx.map(j => PROPS[j] && !PROPS[j].placeholder ? PROPS[j] : (PROPS[j] ? null : undefined));
    const own = s => { const o = [...new Set(PROPS.slice(s * PER, s * PER + PER).filter(p => !p.placeholder).map(p => p.info.owner || 'T'))];
                       return PROPS.some(p => (p.info.owner || 'T') !== 'T') ? ` (${o.join('/') || 'T'})` : ''; };
    document.getElementById('propPick').innerHTML = Array.from({length: nSch()}, (_, s) =>
      `<button type="button" class="tabbtn ${s === SCH ? 'on' : ''}" data-s="${s}">Schedule E ${s + 1}${own(s)}${
        PROPS.slice(s * PER, s * PER + PER).some(p => p.calculated) ? ' ✓' : ''}</button>`).join('')
      + `<button type="button" class="tabbtn add" data-add="1">+ Add property</button>
         <button type="button" class="tabbtn add pickbtn" data-import="1">Import Schedule E sheet…</button>
         <a class="tabbtn add" href="/sche/template.xlsx">Blank template</a> <span id="impMsg" class="note"></span>`;
    const os = ps.map(p => p ? calc(p) : null);
    const head = `<tr><th>Line</th><th>Description</th>${idx.map((j, i) => `<th class="n">${ps[i] !== undefined ? 'Property ' + (j + 1) : ''}${ps[i] && ps[i].calculated ? ' ✓' : ''}</th>`).join('')}</tr>`;
    const info = `
      <tr class="sec"><td colspan="2">Income</td>${ps.map((p, i) => p
        ? `<td><input class="txt ename" data-j="${idx[i]}" value="${esc(p.name)}" placeholder="Address (short)" title="${esc(p.name)}"></td>` : '<td></td>').join('')}</tr>
      <tr><td></td><td class="note">Type</td>${ps.map((p, i) => p ? `<td><select class="etype" data-j="${idx[i]}">${
        TYPES.map(x => `<option ${x === (p.info.type || '') ? 'selected' : ''}>${x}</option>`).join('')}</select></td>` : '<td></td>').join('')}</tr>
      <tr><td></td><td class="note">Fair rental days / personal use days</td>${ps.map((p, i) => p
        ? `<td class="n"><input class="amt eday" data-j="${idx[i]}" data-f="fair_days" value="${p.info.fair_days ?? ''}" placeholder="fair">
           <input class="amt eday" data-j="${idx[i]}" data-f="personal_days" value="${p.info.personal_days ?? ''}" placeholder="personal"></td>` : '<td></td>').join('')}</tr>`;
    const row = k => {
      let label = LBL[k];
      if (k === '22') label = 'Loss allowed after limitation <span class="note">(Form 8582)</span>';
      if (k === '19') label = 'Other — total';
      return `<tr${CALC.has(k) ? ' class="tot"' : ''}><td class="b">${k}</td><td>${label}</td>${ps.map((p, i) => cell(p, idx[i], k, os[i])).join('')}</tr>`;
    };
    const part = s => `<tr class="sec"><td colspan="${PER + 2}">${s}</td></tr>`;
    // last year's income or (loss): line 21 (line 22 when the loss was limited) - read only
    const pyNet = p => { const y = p && p.py; if (!y) return null; const a = num(y['21']), b = y['22'] !== undefined && y['22'] !== null && y['22'] !== '' ? -Math.abs(num(y['22'])) : null;
                         return y['21'] === undefined && b === null ? null : (a < 0 && b !== null ? b : a); };
    const pyrow = `<tr class="pyrow"><td></td><td class="note">PY income or (loss) <span class="note">(last year's return)</span></td>${ps.map(p => {
        const v = pyNet(p); return `<td class="n note">${v === null ? '' : fmt(v)}</td>`; }).join('')}</tr>`;
    const mkey = (p, j) => 'sche|' + (p.name || 'Property ' + (j + 1));
    const ticks = `<tr class="tickrow"><td></td><td class="note">Reviewed ✓</td>${ps.map((p, i) => p ? `<td class="n"><input type="checkbox" data-mk="${esc(mkey(p, idx[i]))}"
        ${(window.MARKS || {})[mkey(p, idx[i])] ? 'checked' : ''} title="Reviewed"></td>` : '<td></td>').join('')}</tr>`;
    const foot = `<tr><td></td><td></td>${ps.map((p, i) => p ? `<td class="n note">
        <a href="/sche/${TOKEN}/${idx[i]}/workpaper.csv" data-act="dl">workpaper</a>
        ${p.py ? ` · <a href="#" data-act="usepy" data-j="${idx[i]}">use PY</a>` : ''}
        · <a href="#" data-act="clear" data-j="${idx[i]}">clear</a>
        ${!p.py && PROPS.length > 1 ? ` · <a href="#" data-act="del" data-j="${idx[i]}">remove</a>` : ''}</td>` : '<td></td>').join('')}</tr>`;
    const notes = ps.some(p => p && (p.notes || p.info.source)) ? `<tr><td></td><td class="note">Notes / source</td>${ps.map(p => p
        ? `<td class="note">${esc(p.notes || '')}${p.info.source ? `<div>${esc(p.info.source)}</div>` : ''}</td>` : '<td></td>').join('')}</tr>` : '';
    document.getElementById('scheBox').innerHTML = `<table class="v sct sce">${head}${info}${notes}
      ${['3', '4'].map(row).join('')}${part('Expenses')}${EXP.map(row).join('')}${['20', '21'].map(row).join('')}${pyrow}${row('22')}${ticks}${foot}</table>`;
  }
  function refresh(j) {
    const p = PROPS[j], o = calc(p);
    CALC.forEach(k => { const el = document.getElementById(`e_${k}_${j}`); if (el) el.textContent = has(p) ? fmt(o[k]) : ''; });
  }
  const post = () => fetch(`/sche/${TOKEN}`, {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(PROPS.map(p => ({...p, totals: calc(p)})))});
  function save() {
    clearTimeout(t); t = setTimeout(post, 400);
    const m = document.getElementById('calcMsgE'); if (m && PROPS.some(p => p.calculated)) m.textContent = 'Changed — click Calculate to update the income summary.';
  }
  const saveNow = () => { clearTimeout(t); return post(); };

  document.getElementById('propPick').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.import) { importSheet(); return; }
    if (b.dataset.add) { PROPS.push({name: '', py: null, cy: {}, info: {}}); SCH = nSch() - 1; save(); }
    else SCH = +b.dataset.s;
    render();
  });
  const box = document.getElementById('scheBox');
  box.addEventListener('click', e => {
    const a = e.target.closest('[data-act]'); if (!a) return;
    e.preventDefault();
    if (a.dataset.act === 'dl') { saveNow().then(() => { window.location = a.href; }); return; }
    const j = +a.dataset.j, p = PROPS[j];
    if (a.dataset.act === 'usepy') Object.keys(p.py || {}).forEach(k => { if (!CALC.has(k)) p.cy[k] = p.py[k]; });
    if (a.dataset.act === 'clear') p.cy = {};
    if (a.dataset.act === 'del') { PROPS.splice(j, 1); saveNow().then(() => location.reload()); return; }
    render(); save();
  });
  box.addEventListener('input', e => {
    const el = e.target, j = +el.dataset.j, p = PROPS[j];
    if (!p) return;
    if (el.classList.contains('ename')) p.name = el.value;
    else if (el.classList.contains('eday')) p.info[el.dataset.f] = el.value.trim() === '' ? null : num(el.value);
    else if (el.classList.contains('ein')) {
      if (el.value.trim() === '') delete p.cy[el.dataset.k]; else p.cy[el.dataset.k] = el.value;
      el.classList.toggle('edited', typed(p, el.dataset.k));
      refresh(j);
    } else return;
    save();
  });
  box.addEventListener('change', e => {
    if (e.target.classList.contains('etype')) { PROPS[+e.target.dataset.j].info.type = e.target.value; save(); }
    if (e.target.classList.contains('eowner')) { PROPS[+e.target.dataset.j].info.owner = e.target.value; save(); render(); }
  });

  // ---------- import the standard Schedule E sheet (one row per property; Schedule E # (tab, 6 per tab) / Owner group them)
  const key = n => String(n || '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\b(avenue|ave|street|st|drive|dr|road|rd|place|pl|north|n|south|s|east|e|west|w)\b/g, '').replace(/\s+/g, ' ').trim();
  async function importSheet() {
    const msg = document.getElementById('impMsg'); msg.textContent = 'Choose the Schedule E sheet (.xlsx / .csv)…';
    const j = await browse('sheet');
    const path = (j.paths || [])[0]; if (!path) { msg.textContent = ''; return; }
    const res = await (await fetch(`/sche/${TOKEN}/import`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({path})})).json();
    if (res.error) { msg.textContent = res.error; return; }
    const real = PROPS.filter(p => !p.placeholder), used = new Set(), groups = {};
    res.properties.forEach(ip => {
      const hit = real.find(p => !used.has(p) && p.name && key(p.name) === key(ip.name));
      const p = hit || {name: ip.name, py: null};
      if (hit) used.add(hit);
      Object.assign(p, {cy: Object.fromEntries(Object.entries(ip.cy).map(([k, v]) => [k, String(v)])), notes: ip.notes,
                        info: Object.assign({}, p.info || {}, ip.info), calculated: false});
      if (!hit || !p.name) p.name = ip.name;
      const g = (ip.owner || 'T') + '|' + ip.sch; (groups[g] = groups[g] || []).push(p);
    });
    const out = [], pad = () => { while (out.length % PER) out.push({name: '', py: null, cy: {}, info: {}, placeholder: true}); };
    Object.keys(groups).forEach(g => { pad(); groups[g].forEach(p => out.push(p)); });
    const rest = real.filter(p => !used.has(p) && !res.properties.some(ip => key(ip.name) === key(p.name)) && (p.py || Object.keys(p.cy || {}).length));
    if (rest.length) { pad(); rest.forEach(p => out.push(p)); }
    PROPS.splice(0, PROPS.length, ...out); SCH = 0;
    render(); saveNow();
    document.getElementById('impMsg').textContent = `${res.properties.length} properties imported from ${res.file}` + (res.errors.length ? ' — ' + res.errors.join('; ') : '')
      + (rest.length ? ` · ${rest.length} from last year not in the sheet (kept at the end)` : '') + ' — click Calculate.';
  }

  window.calculateSchE = function () {
    let any = false, missing = false;
    PROPS.forEach((p, j) => {
      const on = has(p), o = calc(p);
      p.calculated = on;
      if (on) any = true;
      const c = document.querySelector(`[data-sche="${j}"]`);
      if (on && !c) missing = true;
      if (c) c.querySelectorAll('input').forEach(el => { el.value = on ? fmt(o.net) : ''; el.dataset.read = on ? o.net.toFixed(2) : ''; el.dataset.v = el.dataset.read; el.dataset.shown = el.value; });
      const nm = document.querySelector(`[data-schename="${j}"]`); if (nm) nm.textContent = p.name || 'Property ' + (j + 1);
    });
    recalc(true);
    document.getElementById('calcMsgE').textContent = any ? 'Moved to the income summary ✓' : 'Nothing entered yet.';
    render();
    if (missing) { saveNow().then(() => location.reload()); return; }
    saveNow();
  };
  render();
})();
