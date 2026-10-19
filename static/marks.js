// ✓ ticks and typed comments on any line (income summary, Schedule C / E, Verify return, forms filed ...).
// A row <tr class="mk" data-mk="key"> with a checkbox ticks green; <input class="mkn" data-mk="key"> is a typed comment.
// Saved with the work in progress (marks) and listed in the Save review Excel. Needs: TOKEN.
(function () {
  const post = o => fetch(`/marks/${TOKEN}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(o)});
  document.addEventListener('change', e => {
    const el = e.target;
    if (el.type !== 'checkbox') return;
    const key = el.dataset.mk || (el.closest('tr.mk') && !el.classList.length ? el.closest('tr.mk').dataset.mk : null);
    if (!key) return;
    const tr = el.closest('tr.mk'); if (tr && tr.dataset.mk === key) tr.classList.toggle('done', el.checked);
    const box = el.closest('.mkbox'); if (box) box.classList.toggle('done', el.checked);
    if (window.MARKS) { if (el.checked) MARKS[key] = true; else delete MARKS[key]; }
    post({[key]: el.checked});
  });
  const timers = {};
  document.addEventListener('input', e => {
    const el = e.target; if (!el.classList || !el.classList.contains('mkn')) return;
    clearTimeout(timers[el.dataset.mk]);
    timers[el.dataset.mk] = setTimeout(() => post({['n|' + el.dataset.mk]: el.value}), 500);
  });
})();
