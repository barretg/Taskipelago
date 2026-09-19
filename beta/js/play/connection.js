import { ap, state, els } from './state.js';
import { recalcPurchasesFromCompleted, maybeSendGoal } from './logic.js';
import { showItemNotification, handleDeathLinkBounce } from './notifications.js';
import {
  loadManualConsumptions, applyServerManualConsumptions, handleManualSyncBounce,
} from './consumables.js';
import { requestDataPackages, handleDataPackage } from './datapackage.js';
import { loadDeviceDeathLinkQueue, applyServerDeathLinkQueue } from './deathlink_queue.js';
import { primeAudio } from './alerts.js';
import { subscribeHints, handleHintsValue, clearHints, hintsKey } from '../hints/hints.js';
import { updateConsoleConnected } from '../console/console.js';
import { renderAll } from './render.js';
import * as storage from '../shared/storage.js';
import { cfg } from '../shared/config.js';
import {
  serverKeys, subscribeServerState, sanitizePurchases, isOwnWrite,
  writeNotifyCursor, flushNotifyCursor, resetNotifyCursor,
} from '../shared/server_state.js';

// How long ReceivedItems notifications wait for the server notify cursor.
const NOTIFY_FALLBACK_MS = 3000;

// =============================================================
// Notify cursor (UNIFY 3.1): server key, device fallback (3.2)
// =============================================================
function deviceNotifyKey() {
  return `taskipelago_notify_v3::${state.serverAddr.toLowerCase()}::${state.slotName}::${state.seedName}`;
}

function loadDeviceNotifyIndex() {
  const v = storage.get(deviceNotifyKey());
  if (v !== null && v !== undefined) {
    const n = parseInt(v, 10);
    if (n >= 0) return n;
  }
  return null;
}

function saveNotifyIndex(idx, force = false) {
  const cur = loadDeviceNotifyIndex();
  if (force || cur === null || cur <= idx) storage.set(deviceNotifyKey(), idx);
  if (force) resetNotifyCursor(idx);
  else writeNotifyCursor(idx);
}

let notifyFallbackTimer = null;

function beginNotifySync() {
  clearTimeout(notifyFallbackTimer);
  state.notifyReady = false;
  state.notifyQueue = [];
  state.serverNotifyIndex = null;
  state.notifyIndexLoaded = false;
  notifyFallbackTimer = setTimeout(markNotifyReady, NOTIFY_FALLBACK_MS);
}

function markNotifyReady() {
  clearTimeout(notifyFallbackTimer);
  notifyFallbackTimer = null;
  if (state.notifyReady || state.connState !== 'connected') return;
  state.notifyReady = true;
  const queue = state.notifyQueue;
  state.notifyQueue = [];
  for (const { items, packetIndex } of queue) processNotify(items, packetIndex);
}

// Port of the legacy _last_item_index logic (legacy_client/client.py:1498).
function processNotify(items, packetIndex) {
  const packetEnd = packetIndex + items.length;

  if (!state.notifyIndexLoaded) {
    state.notifyIndexLoaded = true;
    // Baseline: the furthest known cursor (server, or device incl. migrated legacy
    // state); with neither, skip all history.
    const known = [state.serverNotifyIndex, loadDeviceNotifyIndex()].filter(v => v !== null);
    state.lastItemIndex = known.length ? Math.max(...known) : packetEnd;
    saveNotifyIndex(state.lastItemIndex);
  }

  // Server restart: packet ends before our cursor
  if (packetEnd < state.lastItemIndex) {
    state.lastItemIndex = packetIndex;
    saveNotifyIndex(state.lastItemIndex, true);
  }

  if (packetEnd <= state.lastItemIndex) return;

  const alreadyNotified = Math.max(0, state.lastItemIndex - packetIndex);
  const newItems = items.slice(alreadyNotified);
  state.lastItemIndex = packetEnd;
  saveNotifyIndex(state.lastItemIndex);

  for (const it of newItems) showItemNotification(it);
}

// =============================================================
// Purchases (UNIFY 3.1): server entries win, min-cost default for the rest
// =============================================================
function applyServerPurchases(value) {
  const incoming = sanitizePurchases(value);
  for (const [idx, deduction] of Object.entries(incoming)) state.taskPurchases[idx] = deduction;
  recalcPurchasesFromCompleted();
  renderAll();
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
  state.deathLinkLockTasks  = !!sd.death_link_lock_tasks;
  state.seedName            = sd.seed_name || (ap.roomInfo && ap.roomInfo.seed_name) || '';
  state.sentItemNames       = sd.sent_item_names || [];
  state.sentPlayerNames     = sd.sent_player_names || [];
  state.taskRewardPreviews  = parseInt(sd.task_reward_previews || 0);
  state.progressiveGroups   = sd.progressive_groups || [];
  state.progressiveGroupColors = Array.isArray(sd.progressive_group_colors) ? sd.progressive_group_colors : [];
  state.groupTypes          = Array.isArray(sd.group_types) ? sd.group_types : [];
  state.itemFillers         = Array.isArray(sd.item_fillers) ? sd.item_fillers : null;
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
export function startConnect() {
  const server = els.serverInput.value.trim();
  const slot   = els.slotInput.value.trim();
  const pass   = els.passInput.value.trim() || null;

  if (!server || !slot) {
    setStatus('Server and Slot Name are required.');
    return false;
  }

  saveLastConnection(server, slot);
  primeAudio(); // F2: Connect click (or launcher autoconnect) unlocks DeathLink sound
  state.connState = 'connecting';
  state.serverAddr = server;
  state.slotName = slot;
  state.sentGoal  = false;
  state.notifyIndexLoaded = false;

  setStatus(`Connecting to ${server} as ${slot}...`);
  els.connectBtn.textContent = 'Disconnect';

  ap.connect(server, slot, pass);
  return true;
}

export function startDisconnect() {
  flushNotifyCursor();
  state.connState = 'disconnected';
  setStatus('Disconnected.');
  els.connectBtn.textContent = 'Connect';
  els.deathLinkBtn.classList.add('hidden');
  clearPlayState();
  ap.disconnect();
  updateConsoleConnected(false);
  renderAll();
}

/** Console /connect: optional address (host:port or archipelago://slot:pw@host:port). */
export function connectTo(address = '') {
  let addr = address.trim();
  const m = /^archipelago:\/\/(?:([^:@/]*)(?::([^@/]*))?@)?([^/]+)\/?$/i.exec(addr);
  if (m) {
    if (m[1]) els.slotInput.value = decodeURIComponent(m[1]);
    if (m[2] !== undefined) els.passInput.value = decodeURIComponent(m[2]);
    addr = m[3];
  }
  if (addr) els.serverInput.value = addr;
  if (state.connState !== 'disconnected') startDisconnect();
  return startConnect();
}

export function hasServerAddress() {
  return !!els.serverInput.value.trim();
}

export function getConnectStatus() {
  return els.connectStatus.textContent;
}

function clearPlayState() {
  clearTimeout(notifyFallbackTimer);
  notifyFallbackTimer = null;
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
  state.deathLinkLockTasks = false;
  state.sentItemNames = [];
  state.sentPlayerNames = [];
  state.taskRewardPreviews = 0;
  state.progressiveGroups = [];
  state.progressiveGroupColors = [];
  state.groupTypes = [];
  state.itemFillers = null;
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
  state.deathLinkQueue   = {}; // F3: in-memory only; the device and server copies stay
  state.lastItemIndex    = 0;
  state.notifyIndexLoaded = false;
  state.notifyReady      = false;
  state.notifyQueue      = [];
  state.serverNotifyIndex = null;
  // Session-only toggle (enforce locally / hide completed persist, UNIFY 3.2)
  state.showLocked       = false;
  els.showLockedCb.checked = false;
  // AP client received items
  ap.itemsReceived = [];
  clearHints(); // F1: the DataPackage cache stays
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
      source: state.slotName || 'Taskipelago',
    });
  });

  // ===========================================================
  // Archipelago callbacks
  // ===========================================================
  ap.onConnected = (slotData, checkedLocs) => {
    // Merge server-checked locations
    for (const c of checkedLocs) state.checkedLocations.add(c);

    applySlotData(slotData);
    state.connState = 'connected';
    setStatus('Connected.');
    els.connectBtn.textContent = 'Disconnect';

    loadManualConsumptions();  // device copy first; the server value overrides via onRetrieved
    loadDeviceDeathLinkQueue(); // F3: device copy before the first render
    beginNotifySync();         // before the Get, so an immediate Retrieved is handled
    subscribeServerState();
    subscribeHints();
    requestDataPackages();

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
    // Notifications wait for the server notify cursor; the item list renders now.
    if (state.notifyReady) processNotify(items, packetIndex);
    else state.notifyQueue.push({ items, packetIndex });
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

  ap.onRetrieved = keys => {
    const k = serverKeys();
    if (hintsKey() in keys) handleHintsValue(keys[hintsKey()]);
    if (k.manual in keys) applyServerManualConsumptions(keys[k.manual], true);
    if (k.purchases in keys) applyServerPurchases(keys[k.purchases]);
    if (k.deathlink in keys) {
      applyServerDeathLinkQueue(keys[k.deathlink], true);
      renderAll();
    }
    if (k.notify in keys) {
      const v = keys[k.notify];
      state.serverNotifyIndex = Number.isInteger(v) && v >= 0 ? v : null;
      markNotifyReady();
      renderAll();
    }
  };

  ap.onSetReply = (key, value, msg) => {
    const k = serverKeys();
    if (key === hintsKey()) {
      handleHintsValue(value);
      return;
    }
    if (key === k.notify) {
      // Recorded only: another client showing an item does not hide it here.
      if (Number.isInteger(value) && value >= 0) state.serverNotifyIndex = value;
      return;
    }
    if (isOwnWrite(msg)) return;
    if (key === k.manual) applyServerManualConsumptions(value, false);
    else if (key === k.purchases) applyServerPurchases(value);
    else if (key === k.deathlink) {
      applyServerDeathLinkQueue(value, false);
      renderAll();
    }
  };

  ap.onDataPackage = games => {
    handleDataPackage(games);
    renderAll();
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
