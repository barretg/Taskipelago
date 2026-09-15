import { ap, state, els } from './state.js';
import { recalcPurchasesFromCompleted, maybeSendGoal } from './logic.js';
import { showItemNotification, handleDeathLinkBounce } from './notifications.js';
import {
  loadManualConsumptions, manualConsumptionsServerKey, applyManualConsumptions,
  handleManualSyncBounce,
} from './consumables.js';
import { updateConsoleConnected } from '../console/console.js';
import { renderAll } from './render.js';
import * as storage from '../shared/storage.js';
import { cfg } from '../shared/config.js';

// =============================================================
// Notify index persistence (device storage)
// =============================================================
function notifyKey() {
  const server = (els.serverInput.value || '').trim().toLowerCase();
  const slot   = (els.slotInput.value  || '').trim();
  const seed   = state.seedName || '';
  return `taskipelago_notify_v3::${server}::${slot}::${seed}`;
}

function loadNotifyIndex() {
  const v = storage.get(notifyKey());
  if (v !== null && v !== undefined) {
    const n = parseInt(v, 10);
    if (n >= 0) return n;
  }
  return null;
}

function saveNotifyIndex(idx, force = false) {
  const key = notifyKey();
  if (!force) {
    const cur = loadNotifyIndex();
    if (cur !== null && cur > idx) return;
  }
  storage.set(key, idx);
}

// Persist last server/slot
function saveLastConnection(server, slot) {
  storage.set('taskipelago_last_conn', { server, slot });
}
function loadLastConnection() {
  const v = storage.get('taskipelago_last_conn');
  return v && typeof v === 'object' ? v : {};
}

// =============================================================
// Slot data application
// =============================================================
function applySlotData(sd) {
  state.tasks               = sd.tasks || [];
  state.items               = sd.items || sd.rewards || [];
  state.taskPrereqs         = sd.task_prereqs || [];
  state.itemPrereqs         = sd.item_prereqs || sd.reward_prereqs || [];
  state.lockPrereqs         = !!sd.lock_prereqs;
  state.hideUnreachable     = sd.hide_unreachable_tasks !== false;
  state.goalExpression      = sd.goal_expression || '';
  state.goalRegionReqs      = sd.goal_region_reqs || [];
  state.baseRewardId        = sd.base_reward_location_id ?? null;
  state.baseCompleteId      = sd.base_complete_location_id ?? null;
  state.baseItemId          = sd.base_item_id ?? null;
  state.baseTokenId         = sd.base_token_id ?? null;
  state.deathLinkPool       = sd.death_link_pool || [];
  state.deathLinkWeights    = sd.death_link_weights || [];
  state.deathLinkAmnesty    = parseInt(sd.death_link_amnesty || 0);
  state.deathLinkEnabled    = !!sd.death_link_enabled;
  state.seedName            = sd.seed_name || '';
  state.sentItemNames       = sd.sent_item_names || [];
  state.sentPlayerNames     = sd.sent_player_names || [];
  state.taskRewardPreviews  = parseInt(sd.task_reward_previews || 0);
  state.progressiveGroups   = sd.progressive_groups || [];
  state.rewardProgressiveGroup = sd.item_progressive_group || sd.reward_progressive_group || [];
  state.taskProgressiveReqs = sd.task_progressive_reqs || [];
  state.taskCostAmounts     = sd.task_cost_amounts || [];
  state.itemConsumable      = sd.item_consumable || [];
  state.regions             = sd.regions || [];
  state.regionColors        = sd.region_colors || [];
  state.taskRegion          = sd.task_region || [];
  state.taskRegionReqs      = sd.task_region_reqs || [];
  state.taskDescriptions    = sd.task_description || [];
  state.bingoMode           = !!sd.bingo_mode;
  state.bingoDimX           = parseInt(sd.bingo_dimension_x || 5);
  state.bingoDimY           = parseInt(sd.bingo_dimension_y || 5);
  state.bingoal             = parseInt(sd.bingoal || 3);
  state.deathLinkAmnestyLeft = state.deathLinkAmnesty;
}

// =============================================================
// Connect / disconnect
// =============================================================
function startConnect() {
  const server = els.serverInput.value.trim();
  const slot   = els.slotInput.value.trim();
  const pass   = els.passInput.value.trim() || null;

  if (!server || !slot) {
    setStatus('Server and Slot Name are required.');
    return;
  }

  saveLastConnection(server, slot);
  state.connState = 'connecting';
  state.sentGoal  = false;
  state.notifyIndexLoaded = false;
  state.pendingNotifyIndex = null;

  setStatus(`Connecting to ${server} as ${slot}...`);
  els.connectBtn.textContent = 'Disconnect';

  ap.connect(server, slot, pass);
}

function startDisconnect() {
  state.connState = 'disconnected';
  setStatus('Disconnected.');
  els.connectBtn.textContent = 'Connect';
  els.deathLinkBtn.classList.add('hidden');
  clearPlayState();
  ap.disconnect();
  updateConsoleConnected(false);
  renderAll();
}

function clearPlayState() {
  // Slot data
  state.tasks = [];
  state.items = [];
  state.taskPrereqs = [];
  state.itemPrereqs = [];
  state.lockPrereqs = false;
  state.hideUnreachable = true;
  state.goalExpression = '';
  state.goalRegionReqs = [];
  state.baseCompleteId = state.baseRewardId = state.baseItemId = state.baseTokenId = null;
  state.deathLinkPool = [];
  state.deathLinkWeights = [];
  state.deathLinkAmnesty = 0;
  state.deathLinkEnabled = false;
  state.sentItemNames = [];
  state.sentPlayerNames = [];
  state.taskRewardPreviews = 0;
  state.progressiveGroups = [];
  state.rewardProgressiveGroup = [];
  state.taskProgressiveReqs = [];
  state.taskCostAmounts = [];
  state.itemConsumable = [];
  state.regions = [];
  state.regionColors = [];
  state.taskRegion = [];
  state.taskRegionReqs = [];
  state.taskDescriptions = [];
  state.bingoMode = false;
  state.bingoDimX = 5;
  state.bingoDimY = 5;
  state.bingoal = 3;
  // Runtime
  state.checkedLocations = new Set();
  state.pendingLocations = new Set();
  state.taskPurchases    = {};
  state.manualConsumptions = {};
  state.hintRequestedIndices = new Set();
  state.notifications    = [];
  state.sentGoal         = false;
  state.deathLinkAmnestyLeft = 0;
  state.lastItemIndex    = 0;
  state.notifyIndexLoaded = false;
  state.pendingNotifyIndex = null;
  // UI toggles
  state.localEnforce     = false;
  state.showLocked       = false;
  state.hideCompleted    = false;
  els.enforceCb.checked  = false;
  els.showLockedCb.checked = false;
  els.hideCompletedCb.checked = false;
  // AP client received items
  ap.itemsReceived = [];
}

function setStatus(msg) { els.connectStatus.textContent = msg; }

export function initConnection() {
  const last = loadLastConnection();
  if (last.server) els.serverInput.value = last.server;
  if (last.slot)   els.slotInput.value   = last.slot;

  els.connectBtn.addEventListener('click', () => {
    if (state.connState === 'disconnected') {
      startConnect();
    } else {
      startDisconnect();
    }
  });

  [els.serverInput, els.slotInput, els.passInput].forEach(inp => {
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter' && state.connState === 'disconnected') startConnect();
    });
  });

  els.deathLinkBtn.addEventListener('click', () => {
    if (state.connState !== 'connected') return;
    ap.sendBounce(['DeathLink'], {
      time: Date.now() / 1000,
      source: els.slotInput.value.trim() || 'Taskipelago',
    });
  });

  // ===========================================================
  // Archipelago callbacks
  // ===========================================================
  ap.onConnected = (slotData, checkedLocs) => {
    // Merge server-checked locations
    for (const c of checkedLocs) state.checkedLocations.add(c);

    applySlotData(slotData);
    loadManualConsumptions();        // seed from localStorage as initial value
    ap.sendGet([manualConsumptionsServerKey()]); // server value overrides via onRetrieved

    state.connState = 'connected';
    setStatus('Connected.');
    els.connectBtn.textContent = 'Disconnect';

    state.deathLinkAmnestyLeft = state.deathLinkAmnesty;

    if (state.deathLinkEnabled) {
      ap.sendConnectUpdate(['AP', 'TaskipelagoSync', 'DeathLink']);
      els.deathLinkBtn.classList.remove('hidden');
    }

    updateConsoleConnected(true);
    renderAll();
  };

  ap.onDisconnected = reason => {
    if (state.connState === 'connecting') {
      setStatus(`Could not connect: ${reason}`);
    } else if (state.connState === 'connected') {
      setStatus('Disconnected (server closed connection).');
    }
    state.connState = 'disconnected';
    els.connectBtn.textContent = 'Connect';
    els.deathLinkBtn.classList.add('hidden');
    clearPlayState();
    updateConsoleConnected(false);
    renderAll();
  };

  ap.onReceivedItems = (items, packetIndex) => {
    const packetEnd = packetIndex + items.length;

    if (!state.notifyIndexLoaded) {
      state.notifyIndexLoaded = true;
      const saved = loadNotifyIndex();
      if (saved !== null) {
        state.lastItemIndex = Math.max(0, saved);
      } else {
        state.lastItemIndex = packetEnd;
      }
      saveNotifyIndex(state.lastItemIndex);
    }

    // Server restart: packet ends before our cursor
    if (packetEnd < state.lastItemIndex) {
      state.lastItemIndex = packetIndex;
      saveNotifyIndex(state.lastItemIndex, true);
    }

    if (packetEnd <= state.lastItemIndex) {
      recalcPurchasesFromCompleted();
      renderAll();
      return;
    }

    const alreadyNotified = Math.max(0, state.lastItemIndex - packetIndex);
    const newItems = items.slice(alreadyNotified);
    state.lastItemIndex = packetEnd;
    saveNotifyIndex(state.lastItemIndex);

    for (const it of newItems) {
      showItemNotification(it);
    }

    recalcPurchasesFromCompleted();
    renderAll();
  };

  ap.onRoomUpdate = newChecked => {
    for (const c of newChecked) {
      state.checkedLocations.add(c);
      state.pendingLocations.delete(c);
    }
    recalcPurchasesFromCompleted();
    maybeSendGoal();
    renderAll();
  };

  ap.onRetrieved = (keys) => {
    const serverKey = manualConsumptionsServerKey();
    if (serverKey in keys && keys[serverKey] && typeof keys[serverKey] === 'object') {
      applyManualConsumptions(keys[serverKey]);
    }
  };

  ap.onBounced = (tags, data) => {
    handleManualSyncBounce(tags, data);
    handleDeathLinkBounce(tags, data);
  };

  // Launcher autoconnect (UNIFY 2.6): prefill and connect once on boot.
  const launch = cfg.launch;
  if (launch && typeof launch === 'object') {
    if (launch.server) els.serverInput.value = launch.server;
    if (launch.slot) els.slotInput.value = launch.slot;
    if (launch.password) els.passInput.value = launch.password;
    if (launch.autoconnect && launch.server && launch.slot) startConnect();
  }
}
