// ✓ ticks and typed comments on any line (income summary, Schedule C / E, Verify return, forms filed ...).
// A ticked line turns light mint (class "done"): a row <tr class="mk" data-mk="key">, a chip .mkbox, else the row of the tick box
// (income summary, Schedule C) or, when the row holds several ticks (Schedule E: one per property), the tick's own cell.
// <input class="mkn" data-mk="key"> is a typed comment. Saved with the work in progress (marks) and listed in the Save review Excel.
// Needs: TOKEN.
(function () {
  const post = o => fetch(`/marks/${TOKEN}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(o)});
  function paint(el, key) {
    const mk = el.closest('tr.mk');
    if (mk && mk.dataset.mk === key) { mk.classList.toggle('done', el.checked); return; }
    const box = el.closest('.mkbox'); if (box) { box.classList.toggle('done', el.checked); return; }
    const tr = el.closest('tr'); if (!tr) return;
    const one = tr.querySelectorAll('input[type="checkbox"][data-mk]').length === 1;
    (one ? tr : el.closest('td') || tr).classList.toggle('done', el.checked);
  }
  document.addEventListener('change', e => {
    const el = e.target;
    if (el.type !== 'checkbox') return;
    const key = el.dataset.mk || (el.closest('tr.mk') && !el.classList.length ? el.closest('tr.mk').dataset.mk : null);
    if (!key) return;
    paint(el, key);
    if (window.MARKS) { if (el.checked) MARKS[key] = true; else delete MARKS[key]; }
    post({[key]: el.checked});
  });
  // ticks drawn by the page or later by a box's script (Schedule C / E, form tabs): paint the ones already ticked
  let queued = false;
  const paintAll = () => { queued = false;
    document.querySelectorAll('input[type="checkbox"][data-mk]:checked').forEach(el => paint(el, el.dataset.mk)); };
  const later = () => { if (!queued) { queued = true; setTimeout(paintAll, 0); } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', paintAll); else paintAll();
  new MutationObserver(later).observe(document.documentElement, {childList: true, subtree: true});
  const timers = {};
  document.addEventListener('input', e => {
    const el = e.target; if (!el.classList || !el.classList.contains('mkn')) return;
    clearTimeout(timers[el.dataset.mk]);
    timers[el.dataset.mk] = setTimeout(() => post({['n|' + el.dataset.mk]: el.value}), 500);
  });
})();
