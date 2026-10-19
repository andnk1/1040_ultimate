// One file window at a time: every Browse / Add button (class "pickbtn") is greyed out while a window is open,
// and the answer goes back only to the button that asked for it.
let PICKING = false;
async function browse(kind, start) {
  if (PICKING) return {paths: [], path: ''};
  PICKING = true;
  const btns = document.querySelectorAll('button.pickbtn');
  btns.forEach(b => b.disabled = true);
  const msg = document.getElementById('pickMsg');
  if (msg) msg.textContent = 'File window open — check the taskbar if you don\'t see it.';
  try {
    const r = await fetch('/browse?kind=' + kind + (start ? '&start=' + encodeURIComponent(start) : ''));
    const j = await r.json();
    if (msg) msg.textContent = j.busy ? 'A file window is already open — finish it first.' : '';
    return j.busy ? {paths: [], path: ''} : j;
  } catch (e) { if (msg) msg.textContent = ''; return {paths: [], path: ''}; }
  finally { PICKING = false; btns.forEach(b => b.disabled = false); }
}
