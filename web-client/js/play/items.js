import { ap, state, els } from './state.js';
import { progressiveGroupCounts, consumableItemNames, consumableReceivedCounts } from './logic.js';
import { dpItemName, ownGame } from './datapackage.js';
import { isFiller } from '../shared/filler.js';
import { h } from '../shared/dom.js';
import { getUiPref, setUiPref } from '../shared/ui_prefs.js';

// v1.1 F7 categories, in precedence order, and the AP NetworkItem flag bits.
export const ITEM_CATEGORIES = [
  ['consumable', 'Consumable'], ['filler', 'Filler'], ['progression', 'Progression'],
  ['useful', 'Useful'], ['trap', 'Trap'], ['junk', 'Junk'],
];
const FLAG_PROGRESSION = 0b001;
const FLAG_USEFUL = 0b010;
const FLAG_TRAP = 0b100;
const NO_GROUP = ''; // "(No group)" in the filter; group names cannot be empty

// ---------------------------------------------------------------------------
// Filter state (taskipelago_ui.itemFilters): only the unchecked sets are stored
// ---------------------------------------------------------------------------
function readFilters() {
  const f = getUiPref('itemFilters', null);
  const list = v => (Array.isArray(v) ? v.filter(x => typeof x === 'string') : []);
  return { hiddenCategories: list(f && f.hiddenCategories), hiddenGroups: list(f && f.hiddenGroups) };
}

function writeFilters(filters) {
  setUiPref('itemFilters', filters);
}

/** Group names the filter offers for the connected seed, "(No group)" last. */
function filterGroups() {
  return [...state.progressiveGroups, NO_GROUP];
}

/** Number of hidden categories and groups that exist in this seed (unknown names are ignored). */
export function hiddenFilterCount(filters = readFilters()) {
  const cats = new Set(ITEM_CATEGORIES.map(c => c[0]));
  const groups = new Set(filterGroups());
  return filters.hiddenCategories.filter(c => cats.has(c)).length
    + filters.hiddenGroups.filter(g => groups.has(g)).length;
}

// ---------------------------------------------------------------------------
// Item classification
// ---------------------------------------------------------------------------
export function itemCategory(idx, name, flags) {
  if (idx >= 0 && state.itemConsumable[idx]) return 'consumable';
  const filler = state.itemFillers && idx >= 0 && idx < state.itemFillers.length
    ? !!state.itemFillers[idx]
    : isFiller(name);
  if (filler) return 'filler';
  if (flags & FLAG_PROGRESSION) return 'progression';
  if (flags & FLAG_USEFUL) return 'useful';
  if (flags & FLAG_TRAP) return 'trap';
  return 'junk';
}

/** Item group type ('progressive', 'random-choice', 'aesthetic'); older seeds are progressive. */
export function groupType(group) {
  const i = state.progressiveGroups.indexOf(group);
  return (i >= 0 && state.groupTypes[i]) || 'progressive';
}

function groupColorMap() {
  const m = {};
  state.progressiveGroups.forEach((g, i) => { m[g] = state.progressiveGroupColors[i] || ''; });
  return m;
}

/** Received items (completion tokens excluded) with name, sender, group and category. */
function receivedEntries() {
  const baseToken = state.baseTokenId;
  const nTasks = state.tasks.length;
  const base = state.baseItemId;
  const out = [];
  for (const it of ap.itemsReceived) {
    if (!it || typeof it.item !== 'number') continue;
    if (typeof baseToken === 'number' && nTasks > 0) {
      const off = it.item - baseToken;
      if (off >= 0 && off < nTasks) continue;
    }
    // Resolve name: YAML item text, DataPackage, then the id
    let name = dpItemName(it.item, ownGame()) || `Item #${it.item}`;
    let idx = -1;
    if (typeof base === 'number') {
      const off = it.item - base;
      if (off >= 0 && off < state.items.length) {
        idx = off;
        if (state.items[off]) name = state.items[off];
      }
    }
    out.push({
      name,
      sender: it.player != null ? ap.resolvePlayerName(it.player) : null,
      group: (idx >= 0 && state.rewardProgressiveGroup[idx]) || NO_GROUP,
      category: itemCategory(idx, name, it.flags || 0),
    });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
const muted = text => h('div', { className: 'items-empty muted-text' }, text);

function itemRow(entry, color) {
  const row = h('div', { className: 'item-entry' }, entry.name + (entry.sender ? `  (from ${entry.sender})` : ''));
  if (color !== undefined) row.style.borderLeft = `4px solid ${color || 'var(--border)'}`;
  return row;
}

export function renderItems() {
  const frag = document.createDocumentFragment();
  const colors = groupColorMap();

  // --- Group summary section (never filtered) ---
  const progCounts = progressiveGroupCounts();
  const consNames = consumableItemNames();
  const consRecv = consumableReceivedCounts();
  const hasGroups = Object.keys(progCounts).length > 0 || consNames.length > 0;

  if (hasGroups) {
    for (const [name, { received, total }] of Object.entries(progCounts)) {
      frag.appendChild(h('div', { className: 'group-row' },
        h('span', { className: 'group-row-name' },
          h('span', { className: 'group-swatch', style: { background: colors[name] || 'var(--border)' } }),
          groupType(name) === 'progressive' ? name : `${name}  (${groupType(name)})`),
        h('span', { className: 'group-row-count' }, `${received} / ${total}`)));
    }
    for (const name of consNames) {
      frag.appendChild(h('div', { className: 'group-row' },
        h('span', {}, `${name}  (currency)`),
        h('span', { className: 'group-row-count' }, `${consRecv[name] || 0} received`)));
    }
    frag.appendChild(h('hr', { className: 'group-summary-divider' }));
  }

  // --- Item list (F7 filtered, F6 grouped) ---
  const filters = readFilters();
  const hiddenCats = new Set(filters.hiddenCategories);
  const hiddenGroups = new Set(filters.hiddenGroups);
  const entries = receivedEntries();
  const visible = entries.filter(e => !hiddenCats.has(e.category) && !hiddenGroups.has(e.group));
  const hiddenCount = entries.length - visible.length;

  if (state.progressiveGroups.length) {
    const counts = progCounts;
    for (const g of state.progressiveGroups) {
      const rows = visible.filter(e => e.group === g);
      if (!rows.length) continue;
      const c = counts[g] || { received: rows.length, total: rows.length };
      const header = h('div', { className: 'item-group-header' }, `${g}  ${c.received}/${c.total}`);
      if (colors[g]) header.style.color = colors[g];
      frag.appendChild(header);
      for (const e of rows) frag.appendChild(itemRow(e, colors[g]));
    }
    const other = visible.filter(e => e.group === NO_GROUP || !state.progressiveGroups.includes(e.group));
    if (other.length) {
      frag.appendChild(h('div', { className: 'item-group-header' }, 'Other'));
      for (const e of other) frag.appendChild(itemRow(e));
    }
  } else {
    for (const e of visible) frag.appendChild(itemRow(e));
  }

  if (!hasGroups && !entries.length) frag.appendChild(muted('No items received yet.'));
  if (state.connState === 'connected') {
    frag.appendChild(h('div', { className: 'items-hidden-footer muted-text' }, `+${hiddenCount} Hidden Items`));
  }

  els.itemsList.replaceChildren(frag);
  updateFilterButton(filters);
}

// ---------------------------------------------------------------------------
// Filter popover
// ---------------------------------------------------------------------------
function updateFilterButton(filters = readFilters()) {
  if (!els.itemsFilterBtn) return;
  const k = hiddenFilterCount(filters);
  els.itemsFilterBtn.textContent = k ? `Filter (${k})` : 'Filter';
}

let popover = null;

function closeFilterPopover() {
  if (!popover) return;
  popover.remove();
  popover = null;
  els.itemsFilterBtn.setAttribute('aria-expanded', 'false');
  document.removeEventListener('mousedown', onOutside, true);
  document.removeEventListener('keydown', onEscape, true);
}

function onOutside(e) {
  if (popover && !popover.contains(e.target) && e.target !== els.itemsFilterBtn) closeFilterPopover();
}

function onEscape(e) {
  if (e.key === 'Escape') {
    e.preventDefault();
    closeFilterPopover();
    els.itemsFilterBtn.focus();
  }
}

function buildPopover() {
  const filters = readFilters();
  const toggle = (listKey, value, shown) => {
    const next = readFilters();
    const set = new Set(next[listKey]);
    if (shown) set.delete(value);
    else set.add(value);
    next[listKey] = [...set];
    writeFilters(next);
    renderItems();
  };
  const box = (listKey, value, label) => h('label', { className: 'check-label' },
    h('input', {
      type: 'checkbox', checked: !filters[listKey].includes(value), dataset: { filter: `${listKey}:${value}` },
      onchange: e => toggle(listKey, value, e.target.checked),
    }), label);
  const setAll = shown => {
    writeFilters(shown ? { hiddenCategories: [], hiddenGroups: [] } : {
      hiddenCategories: ITEM_CATEGORIES.map(c => c[0]), hiddenGroups: filterGroups(),
    });
    renderItems();
    const fresh = buildPopover();
    popover.replaceWith(fresh);
    popover = fresh;
  };
  return h('div', { className: 'items-filter-popover', role: 'dialog', 'aria-label': 'Item filters' },
    h('div', { className: 'filter-group-title' }, 'Types'),
    h('div', { className: 'filter-options' }, ITEM_CATEGORIES.map(([key, label]) => box('hiddenCategories', key, label))),
    h('div', { className: 'filter-group-title' }, 'Item Groups'),
    h('div', { className: 'filter-options' },
      filterGroups().map(g => box('hiddenGroups', g, g === NO_GROUP ? '(No group)' : g))),
    h('div', { className: 'btn-row' },
      h('button', { type: 'button', onclick: () => setAll(true) }, 'Show all'),
      h('button', { type: 'button', onclick: () => setAll(false) }, 'Hide all')));
}

function openFilterPopover() {
  if (popover) {
    closeFilterPopover();
    return;
  }
  popover = buildPopover();
  els.itemsFilterBtn.parentElement.appendChild(popover);
  els.itemsFilterBtn.setAttribute('aria-expanded', 'true');
  document.addEventListener('mousedown', onOutside, true);
  document.addEventListener('keydown', onEscape, true);
}

export function initItems() {
  els.itemsFilterBtn?.addEventListener('click', openFilterPopover);
  updateFilterButton();
}
