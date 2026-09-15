import { ap, state, els } from './state.js';
import { progressiveGroupCounts, consumableItemNames, consumableReceivedCounts } from './logic.js';

export function renderItems() {
  const baseToken  = state.baseTokenId;
  const nTasks     = state.tasks.length;
  const base       = state.baseItemId;
  const frag       = document.createDocumentFragment();

  // --- Group summary section ---
  const progCounts  = progressiveGroupCounts();
  const consNames   = consumableItemNames();
  const consRecv    = consumableReceivedCounts();
  const hasGroups   = Object.keys(progCounts).length > 0 || consNames.length > 0;

  if (hasGroups) {
    for (const [name, { received, total }] of Object.entries(progCounts)) {
      const row = document.createElement('div');
      row.className = 'group-row';
      const lbl = document.createElement('span');
      lbl.textContent = name;
      const cnt = document.createElement('span');
      cnt.className = 'group-row-count';
      cnt.textContent = `${received} / ${total}`;
      row.appendChild(lbl);
      row.appendChild(cnt);
      frag.appendChild(row);
    }
    for (const name of consNames) {
      const row = document.createElement('div');
      row.className = 'group-row';
      const lbl = document.createElement('span');
      lbl.textContent = `${name}  (currency)`;
      const cnt = document.createElement('span');
      cnt.className = 'group-row-count';
      cnt.textContent = `${consRecv[name] || 0} received`;
      row.appendChild(lbl);
      row.appendChild(cnt);
      frag.appendChild(row);
    }
    const hr = document.createElement('hr');
    hr.className = 'group-summary-divider';
    frag.appendChild(hr);
  }

  // --- Item list ---
  let count = 0;
  for (const it of ap.itemsReceived) {
    if (!it || typeof it.item !== 'number') continue;

    // Skip completion tokens
    if (typeof baseToken === 'number' && nTasks > 0) {
      const off = it.item - baseToken;
      if (off >= 0 && off < nTasks) continue;
    }

    // Resolve name
    let name = `Item #${it.item}`;
    if (typeof base === 'number') {
      const idx = it.item - base;
      if (idx >= 0 && idx < state.items.length && state.items[idx]) {
        name = state.items[idx];
      }
    }

    const sender = it.player != null
      ? ap.resolvePlayerName(it.player)
      : null;

    const row = document.createElement('div');
    row.className = 'item-entry';
    row.textContent = name + (sender ? `  (from ${sender})` : '');
    frag.appendChild(row);
    count++;
  }

  els.itemsList.innerHTML = '';
  if (!hasGroups && !count) {
    els.itemsList.innerHTML = '<div style="padding:8px;color:var(--muted);font-size:12px">No items received yet.</div>';
  } else {
    els.itemsList.appendChild(frag);
  }
}
