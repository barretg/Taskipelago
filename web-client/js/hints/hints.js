// v1.1 F1: Hints tab. Mirrors the Archipelago CommonClient / kvui hint table:
// _read_hints_<team>_<slot> via Get + SetNotify, sortable columns, and an
// UpdateHint status dropdown on hints for items we receive that are not found.
import { ap, state } from '../play/state.js';
import { $, h } from '../shared/dom.js';
import { dpItemName, dpLocationName, hasDataPackage } from '../play/datapackage.js';

export const HintStatus = { UNSPECIFIED: 0, NO_PRIORITY: 10, AVOID: 20, PRIORITY: 30, FOUND: 40 };

const STATUS_LABELS = {
  [HintStatus.UNSPECIFIED]: 'Unspecified',
  [HintStatus.NO_PRIORITY]: 'No Priority',
  [HintStatus.AVOID]: 'Avoid',
  [HintStatus.PRIORITY]: 'Priority',
  [HintStatus.FOUND]: 'Found',
};
const STATUS_CLASSES = {
  [HintStatus.UNSPECIFIED]: 'hint-status-unspecified',
  [HintStatus.NO_PRIORITY]: 'hint-status-no-priority',
  [HintStatus.AVOID]: 'hint-status-avoid',
  [HintStatus.PRIORITY]: 'hint-status-priority',
  [HintStatus.FOUND]: 'hint-status-found',
};
const EDITABLE_STATUSES = [HintStatus.NO_PRIORITY, HintStatus.PRIORITY, HintStatus.AVOID];

const COLUMNS = [
  ['receiving', 'Receiving Player'],
  ['item', 'Item'],
  ['finding', 'Finding Player'],
  ['location', 'Location'],
  ['entrance', 'Entrance'],
  ['status', 'Status'],
];

let hints = [];
let sort = null; // { key, desc } once a header was clicked; null = default order

export const hintsKey = () => `_read_hints_${ap.ourTeam ?? 0}_${ap.ourSlot ?? 0}`;

/** After Connected: read and subscribe to our hints. */
export function subscribeHints() {
  const key = hintsKey();
  ap.sendGet([key]);
  ap.sendSetNotify([key]);
}

const int = (v, fallback = 0) => (Number.isInteger(v) ? v : fallback);

/** Plain hint objects; tolerates an extra "class" field and missing optional fields. */
export function normalizeHints(value) {
  if (!Array.isArray(value)) return [];
  return value.filter(x => x && typeof x === 'object').map(x => ({
    receiving_player: int(x.receiving_player),
    finding_player: int(x.finding_player),
    location: int(x.location),
    item: int(x.item),
    found: !!x.found,
    entrance: typeof x.entrance === 'string' ? x.entrance : '',
    item_flags: int(x.item_flags),
    status: int(x.status, x.found ? HintStatus.FOUND : HintStatus.UNSPECIFIED),
  }));
}

/** Retrieved / SetReply value for hintsKey(). */
export function handleHintsValue(value) {
  hints = normalizeHints(value);
  renderHints();
}

export function clearHints() {
  hints = [];
  renderHints();
}

export const effectiveStatus = hint => (hint.found ? HintStatus.FOUND : hint.status);

// ---------------------------------------------------------------------------
// Names
// ---------------------------------------------------------------------------
function ownIndex(id, base, n) {
  if (typeof base !== 'number') return -1;
  const off = id - base;
  return off >= 0 && off < n ? off : -1;
}

export function hintItemName(hint) {
  if (hint.receiving_player === ap.ourSlot) {
    const idx = ownIndex(hint.item, state.baseItemId, state.items.length);
    if (idx >= 0 && state.items[idx]) return state.items[idx];
  }
  const game = ap.gameOfSlot(hint.receiving_player);
  return (game && dpItemName(hint.item, game)) || `#${hint.item}`;
}

export function hintLocationName(hint) {
  if (hint.finding_player === ap.ourSlot) {
    const n = state.tasks.length;
    const reward = ownIndex(hint.location, state.baseRewardId, n);
    if (reward >= 0) return state.tasks[reward];
    const complete = ownIndex(hint.location, state.baseCompleteId, n);
    if (complete >= 0) return `${state.tasks[complete]} (Complete)`;
  }
  const game = ap.gameOfSlot(hint.finding_player);
  return (game && dpLocationName(hint.location, game)) || `#${hint.location}`;
}

/** True while a shown name is still an #id waiting for its game's DataPackage. */
function waitingForDataPackage(row) {
  const pending = (text, id, slot) => {
    const game = ap.gameOfSlot(slot);
    return text === `#${id}` && !!game && !hasDataPackage(game);
  };
  return pending(row.item, row.hint.item, row.hint.receiving_player)
    || pending(row.location, row.hint.location, row.hint.finding_player);
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
function itemClass(flags) {
  if (flags & 0b001) return 'hint-item-progression';
  if (flags & 0b010) return 'hint-item-useful';
  if (flags & 0b100) return 'hint-item-trap';
  return 'hint-item-normal';
}

const playerClass = slot => (slot === ap.ourSlot ? 'hint-player-own' : 'hint-player-other');

function rowsWithNames() {
  return hints.map(hint => ({
    hint,
    receiving: ap.resolvePlayerName(hint.receiving_player) || '',
    item: hintItemName(hint),
    finding: ap.resolvePlayerName(hint.finding_player) || '',
    location: hintLocationName(hint),
    entrance: hint.entrance,
    status: effectiveStatus(hint),
  }));
}

function compare(a, b, key) {
  const x = a[key];
  const y = b[key];
  if (typeof x === 'number' && typeof y === 'number') return x - y;
  return String(x).localeCompare(String(y));
}

/** Default: status descending, then receiving player. A clicked header sorts by it; again reverses. */
export function sortRows(rows, order = sort) {
  const out = [...rows];
  if (!order) {
    out.sort((a, b) => (b.status - a.status) || compare(a, b, 'receiving'));
  } else {
    out.sort((a, b) => compare(a, b, order.key) * (order.desc ? -1 : 1));
  }
  return out;
}

function statusCell(row) {
  const { hint, status } = row;
  const label = STATUS_LABELS[status] ?? String(status);
  if (hint.receiving_player !== ap.ourSlot || hint.found) {
    return h('span', { className: STATUS_CLASSES[status] || '' }, label);
  }
  const options = EDITABLE_STATUSES.includes(status) ? EDITABLE_STATUSES : [status, ...EDITABLE_STATUSES];
  const select = h('select', {
    className: `hint-status-select ${STATUS_CLASSES[status] || ''}`, 'aria-label': 'Hint status',
    onchange: e => {
      // No optimistic write: the table updates when the server's SetReply arrives.
      ap.sendUpdateHint(hint.location, hint.finding_player, Number(e.target.value));
      e.target.value = String(status);
    },
  }, options.map(s => h('option', { value: String(s), disabled: s === HintStatus.UNSPECIFIED }, STATUS_LABELS[s] ?? String(s))));
  select.value = String(status);
  return select;
}

export function renderHints() {
  const root = $('hints-root');
  if (!root) return;
  if (!hints.length) {
    root.replaceChildren(h('div', { className: 'hints-empty muted-text' },
      state.connState === 'connected'
        ? 'No hints yet. Use !hint <item> in the Text Console.'
        : 'Connect to a server to see hints.'));
    return;
  }
  const header = h('tr', {}, COLUMNS.map(([key, label]) => {
    const active = sort && sort.key === key;
    return h('th', {
      scope: 'col', 'aria-sort': active ? (sort.desc ? 'descending' : 'ascending') : 'none',
    }, h('button', {
      type: 'button', className: 'hint-sort-btn',
      onclick: () => {
        sort = active ? { key, desc: !sort.desc } : { key, desc: false };
        renderHints();
      },
    }, label + (active ? (sort.desc ? ' v' : ' ^') : '')));
  }));
  const named = sortRows(rowsWithNames());
  const rows = named.map(row => h('tr', { className: row.hint.found ? 'hint-found' : '' },
    h('td', { className: playerClass(row.hint.receiving_player) }, row.receiving),
    h('td', { className: itemClass(row.hint.item_flags) }, row.item),
    h('td', { className: playerClass(row.hint.finding_player) }, row.finding),
    h('td', { className: 'hint-location' }, row.location),
    h('td', {}, row.entrance),
    h('td', {}, statusCell(row))));
  const table = h('div', { className: 'hints-scroll' },
    h('table', { className: 'hints-table' }, h('thead', {}, header), h('tbody', {}, rows)));
  // replaceChildren would render a null argument as the text "null".
  if (named.some(waitingForDataPackage)) {
    root.replaceChildren(table, h('div', { className: 'muted-text hints-note' }, 'Loading item and location names...'));
  } else {
    root.replaceChildren(table);
  }
}
