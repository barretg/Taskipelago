import { ap, state, els, CLIENT_ID } from './state.js';
import { consumableBalance, consumableReceivedCounts, consumableSpentCounts } from './logic.js';
import * as storage from '../shared/storage.js';

// =============================================================
// Manual consumption persistence + cross-client sync
// =============================================================
function manualConsumptionsKey() {
  const server = (els.serverInput.value || '').trim().toLowerCase();
  const slot   = (els.slotInput.value  || '').trim();
  const seed   = state.seedName || '';
  return `taskipelago_manual_v1::${server}::${slot}::${seed}`;
}

export function manualConsumptionsServerKey() {
  const slot = (els.slotInput.value || '').trim();
  const seed = state.seedName || '';
  return `taskipelago_manual::${slot}::${seed}`;
}

export function applyManualConsumptions(incoming) {
  if (!incoming || typeof incoming !== 'object') return;
  state.manualConsumptions = incoming;
  saveManualConsumptions();
  renderConsumables();
}

export function loadManualConsumptions() {
  const parsed = storage.get(manualConsumptionsKey());
  state.manualConsumptions = parsed && typeof parsed === 'object' ? parsed : {};
}

function saveManualConsumptions() {
  storage.set(manualConsumptionsKey(), state.manualConsumptions);
  if (state.connState === 'connected') {
    ap.sendSet(manualConsumptionsServerKey(), { ...state.manualConsumptions }, {});
  }
}

function sendManualSync() {
  ap.sendBounce(['TaskipelagoSync'], {
    type: 'taskipelago_manual_sync',
    client_id: CLIENT_ID,
    seed: state.seedName,
    slot_name: (els.slotInput.value || '').trim(),
    manual_consumptions: { ...state.manualConsumptions },
  });
}

export function handleManualSyncBounce(tags, data) {
  if (tags.includes('TaskipelagoSync') &&
      data.type === 'taskipelago_manual_sync' &&
      data.client_id !== CLIENT_ID &&
      data.seed === state.seedName &&
      data.slot_name === (els.slotInput.value || '').trim()) {
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
        saveManualConsumptions();
        sendManualSync();
        renderConsumables();
      });

      const btnPlus = document.createElement('button');
      btnPlus.className = 'consumable-manual-btn';
      btnPlus.textContent = '+1';
      btnPlus.disabled = m < 1;
      btnPlus.addEventListener('click', () => {
        state.manualConsumptions[name] = Math.max(0, (state.manualConsumptions[name] || 0) - 1);
        saveManualConsumptions();
        sendManualSync();
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
