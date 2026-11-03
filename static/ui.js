// Buttons inside the boxes (Calculate, Add P&L, Clear Amounts, Export Template ...): all the same width on a page = the width of the
// longest label. Small buttons (Browse…, ✕, banner buttons), + and tabs keep their own size. Re-run when a box draws new buttons.
(function () {
  const SEL = '.card .cardbody :is(button, a.btn):not(.small):not(.plus):not(.tabbtn):not(.fvreset)';
  const cv = document.createElement('canvas').getContext('2d');
  let busy = false;
  function size() {
    if (busy) return;
    busy = true;
    const bs = [...document.querySelectorAll(SEL)];
    let w = 0;
    bs.forEach(b => {                                      // measured from the text, so buttons in closed boxes count too
      const cs = getComputedStyle(b);
      cv.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
      const pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) + parseFloat(cs.borderLeftWidth) + parseFloat(cs.borderRightWidth);
      w = Math.max(w, Math.ceil(cv.measureText(b.textContent.trim()).width + pad + 2));
    });
    bs.forEach(b => { if (b.style.width !== w + 'px') b.style.width = w + 'px'; });
    busy = false;
  }
  let t;
  new MutationObserver(() => { clearTimeout(t); t = setTimeout(size, 30); }).observe(document.body, {childList: true, subtree: true});
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', size); else size();
})();
