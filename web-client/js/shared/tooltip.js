// Hover/focus/tap tooltips with the legacy client's help text (UNIFY 5.3).
// One floating element is shared; any node with data-tip shows it.

let tipEl = null;
let owner = null;
let hideTimer = 0;
// Grace period for moving the pointer from the marker into a long, scrollable tip.
const HIDE_DELAY_MS = 200;

function ensureTip() {
  if (!tipEl) {
    tipEl = document.createElement('div');
    tipEl.className = 'tooltip hidden';
    tipEl.setAttribute('role', 'tooltip');
    // Keep focus on the marker so clicking the tip's scrollbar does not close it.
    tipEl.addEventListener('mousedown', e => e.preventDefault());
    document.body.appendChild(tipEl);
  }
  return tipEl;
}

function show(target) {
  cancelHide();
  const tip = ensureTip();
  tip.scrollTop = 0;
  owner = target;
  tip.textContent = target.dataset.tip;
  tip.classList.remove('hidden');
  const r = target.getBoundingClientRect();
  const margin = 8;
  const w = tip.offsetWidth;
  const h = tip.offsetHeight;
  let left = Math.min(r.left, innerWidth - w - margin);
  let top = r.bottom + 6;
  if (top + h > innerHeight - margin) top = Math.max(margin, r.top - h - 6);
  left = Math.max(margin, left);
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
}

function cancelHide() {
  clearTimeout(hideTimer);
  hideTimer = 0;
}

function scheduleHide() {
  if (!hideTimer) hideTimer = setTimeout(hide, HIDE_DELAY_MS);
}

function hide() {
  cancelHide();
  owner = null;
  tipEl?.classList.add('hidden');
}

/** A "?" marker carrying tip text. */
export function tipMarker(text) {
  const q = document.createElement('span');
  q.className = 'tip-marker';
  q.textContent = '?';
  q.tabIndex = 0;
  q.dataset.tip = text;
  q.setAttribute('aria-label', text);
  return q;
}

/** Label text followed by a "?" marker. */
export function tipHeader(label, text, tag = 'span') {
  const wrap = document.createElement(tag);
  wrap.className = 'tip-header';
  wrap.append(document.createTextNode(label + ' '), tipMarker(text));
  return wrap;
}

export function initTooltips() {
  const find = e => e.target.closest?.('[data-tip]');
  const inTip = e => tipEl && tipEl.contains(e.target);
  document.addEventListener('mouseover', e => {
    if (inTip(e)) { cancelHide(); return; }
    const t = find(e);
    if (t && t !== owner) show(t);
    else if (t) cancelHide();
    else if (owner) scheduleHide();
  });
  // Wheel over the marker scrolls a tip that overflows.
  document.addEventListener('wheel', e => {
    if (!owner || !tipEl || find(e) !== owner) return;
    if (tipEl.scrollHeight <= tipEl.clientHeight) return;
    e.preventDefault();
    tipEl.scrollTop += e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
  }, { passive: false });
  document.addEventListener('focusin', e => {
    const t = find(e);
    if (t) show(t);
  });
  document.addEventListener('focusout', hide);
  document.addEventListener('click', e => {
    if (inTip(e)) return;
    const t = find(e);
    if (t && t !== owner) show(t);
    else if (!t) hide();
  });
  addEventListener('scroll', e => { if (e.target !== tipEl) hide(); }, true);
}
