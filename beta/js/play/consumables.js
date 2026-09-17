import { ap, state, els, CLIENT_ID } from './state.js';
import { consumableBalance, consumableReceivedCounts, consumableSpentCounts } from './logic.js';
import * as storage from '../shared/storage.js';
import { sanitizeCounts, writeManualConsumptions } from '../shared/server_state.js';

// =============================================================
// Manual consumption persistence + cross-client sync
// =============================================================
// Local changes write device storage, the server key (replace) and the
// TaskipelagoSync Bounce (kept for v1.0.x clients, UNIFY 3.1). Values that come
// in from the server or a Bounce only update the device copy, so they never echo
// back as another Set (legacy client.py:1471-1493).
function manualConsumptionsKey() {
  return `taskipelago_manual_v1::${state.serverAddr.toLowerCase()}::${state.slotName}::${state.seedName}`;
}

function applyManualConsumptions(incoming) {
  state.manualConsumptions = sanitizeCounts(incoming);
  storage.set(manualConsumptionsKey(), state.manualConsumptions);
  renderConsumables();
}

/** Retrieved (fromGet) or SetReply value of taskipelago_manual. */
export function applyServerManualConsumptions(value, fromGet) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    applyManualConsumptions(value);
  } else if (fromGet && value == null && Object.keys(state.manualConsumptions).length) {
    // Server key empty: push the device copy (includes migrated legacy state, UNIFY 3.3).
    writeManualConsumptions(state.manualConsumptions);
  }
}

export function loadManualConsumptions() {
  state.manualConsumptions = sanitizeCounts(storage.get(manualConsumptionsKey()));
}

function saveLocalManualChange() {
  storage.set(manualConsumptionsKey(), state.manualConsumptions);
  if (state.connState === 'connected') {
    writeManualConsumptions(state.manualConsumptions);
    sendManualSync();
  }
}

function sendManualSync() {
  ap.sendBounce(['TaskipelagoSync'], {
    type: 'taskipelago_manual_sync',
    client_id: CLIENT_ID,
    seed: state.seedName,
    slot_name: state.slotName,
    manual_consumptions: { ...state.manualConsumptions },
  });
}

export function handleManualSyncBounce(tags, data) {
  if (tags.includes('TaskipelagoSync') &&
      data.type === 'taskipelago_manual_sync' &&
      data.client_id !== CLIENT_ID &&
      data.seed === state.seedName &&
      data.slot_name === state.slotName &&
      data.manual_consumptions && typeof data.manual_consumptions === 'object') {
    applyManualConsumptions(data.manual_consumptions);
  }
}

function consumableNamesUsedInTasks() {
  const used = new Set();
  for (const branches of state.taskCostAmounts) {
    if (!branches) continue;
    for (const branch of branches) {
      for (const [name] of branch) used.add(name);
    }
  }
  return used;
}

// =============================================================
// Rendering: consumables
// =============================================================
export function renderConsumables() {
  const hasCost = state.taskCostAmounts.some(b => b && b.length);
  if (!hasCost || state.connState !== 'connected') {
    els.consumablesList.innerHTML = '<div style="padding:8px;color:var(--muted);font-size:12px">No consumable items in this session.</div>';
    return;
  }

  const bal   = consumableBalance();
  const recv  = consumableReceivedCounts();
  const spent = consumableSpentCounts();
  const names = [...new Set([...Object.keys(recv), ...Object.keys(spent)])].sort();

  if (!names.length) {
    els.consumablesList.innerHTML = '<div style="padding:8px;color:var(--muted);font-size:12px">No consumable items received yet.</div>';
    return;
  }

  const usedInTasks = consumableNamesUsedInTasks();
  const frag = document.createDocumentFragment();
  for (const name of names) {
    const b = bal[name]  || 0;
    const r = recv[name] || 0;
    const s = spent[name]|| 0;
    const m = state.manualConsumptions[name] || 0;
    const row = document.createElement('div');
    row.className = 'consumable-entry' + (b < 0 ? ' consumable-warning' : '');

    const label = document.createElement('span');
    label.textContent = `${name}:  ${b} remaining  (${r} received, ${s + m} spent)`;
    row.appendChild(label);

    if (!usedInTasks.has(name)) {
      const btnMinus = document.createElement('button');
      btnMinus.className = 'consumable-manual-btn';
      btnMinus.textContent = '-1';
      btnMinus.disabled = b < 1;
      btnMinus.addEventListener('click', () => {
        state.manualConsumptions[name] = (state.manualConsumptions[name] || 0) + 1;
        saveLocalManualChange();
        renderConsumables();
      });

      const btnPlus = document.createElement('button');
      btnPlus.className = 'consumable-manual-btn';
      btnPlus.textContent = '+1';
      btnPlus.disabled = m < 1;
      btnPlus.addEventListener('click', () => {
        const next = Math.max(0, (state.manualConsumptions[name] || 0) - 1);
        if (next) state.manualConsumptions[name] = next;
        else delete state.manualConsumptions[name];
        saveLocalManualChange();
        renderConsumables();
      });

      row.appendChild(btnMinus);
      row.appendChild(btnPlus);
    }

    frag.appendChild(row);
  }
  els.consumablesList.innerHTML = '';
  els.consumablesList.appendChild(frag);
}
