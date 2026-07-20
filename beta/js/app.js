import { ArchipelagoClient } from './archipelago.js';

// =============================================================
// State
// =============================================================
const ap = new ArchipelagoClient();

const state = {
  connState: 'disconnected', // 'disconnected' | 'connecting' | 'connected'

  // Slot data
  tasks: [],
  items: [],
  taskPrereqs: [],
  itemPrereqs: [],
  lockPrereqs: false,
  hideUnreachable: true,
  goalExpression: '',
  goalRegionReqs: [],
  baseRewardId: null,
  baseCompleteId: null,
  baseItemId: null,
  baseTokenId: null,
  deathLinkPool: [],
  deathLinkWeights: [],
  deathLinkAmnesty: 0,
  deathLinkEnabled: false,
  sentItemNames: [],
  sentPlayerNames: [],
  taskRewardPreviews: 0,
  progressiveGroups: [],
  rewardProgressiveGroup: [],
  taskProgressiveReqs: [],
  taskCostAmounts: [],
  itemConsumable: [],
  regions: [],
  regionColors: [],
  taskRegion: [],
  taskRegionReqs: [],
  taskDescriptions: [],
  bingoMode: false,
  bingoDimX: 5,
  bingoDimY: 5,
  bingoal: 3,

  // Runtime
  checkedLocations: new Set(), // combined server + optimistic
  pendingLocations: new Set(), // optimistic (not yet confirmed by server)
  taskPurchases: {},           // taskIdx -> {name: amount}
  manualConsumptions: {},      // name -> count of manually consumed units
  hintRequestedIndices: new Set(), // task indices already hinted this session
  notifications: [],           // [{kind, title, body, createdAt}]
  sentGoal: false,
  deathLinkAmnestyLeft: 0,

  // Notify dedup (mirrors Python _last_item_index logic)
  lastItemIndex: 0,
  notifyIndexLoaded: false,
  pendingNotifyIndex: null, // loaded from localStorage before first ReceivedItems

  // UI toggles
  localEnforce: false,
  showLocked: false,
  hideCompleted: false,
};

const CLIENT_ID = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);

const MAX_NOTIFICATIONS = 200;

// =============================================================
// DOM references
// =============================================================
const $ = id => document.getElementById(id);

const els = {
  mainTabs:      document.querySelectorAll('#main-tabs .tab-btn'),
  tabPlay:       $('tab-play'),
  tabConsole:    $('tab-console'),

  serverInput:   $('server-input'),
  slotInput:     $('slot-input'),
  passInput:     $('pass-input'),
  connectBtn:    $('connect-btn'),
  deathLinkBtn:  $('deathlink-send-btn'),
  connectStatus: $('connect-status'),

  enforceHeader: $('enforce-header'),
  enforceCb:     $('enforce-cb'),
  showLockedHeader: $('show-locked-header'),
  showLockedWrapper: $('show-locked-wrapper'),
  showLockedCb:  $('show-locked-cb'),
  hideCompletedCb: $('hide-completed-cb'),

  tasksList:     $('tasks-list'),
  bingoSection:  $('bingo-section'),
  bingoCounter:  $('bingo-counter'),
  bingoGrid:     $('bingo-grid'),

  subTabs:       document.querySelectorAll('.sub-tabs .tab-btn'),
  notifList:     $('notif-list'),
  clearNotifsBtn:$('clear-notifs-btn'),
  itemsList:     $('items-list'),
  consumablesList: $('consumables-list'),

  consoleOutput: $('console-output'),
  consoleInput:  $('console-input'),
  consoleSendBtn:$('console-send-btn'),

  modalOverlay:  $('modal-overlay'),
  modalTitle:    $('modal-title'),
  modalDesc:     $('modal-desc'),
  modalBtns:     $('modal-btns'),
};

// =============================================================
// Utility – prereq expression evaluator
// (port of client.py _eval_prereq_expr)
// =============================================================
function evalPrereqExpr(text, leafFn, nameFn) {
  text = (text || '').trim();
  if (!text) return true;

  const tokens = [];
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (c === ' ' || c === '\t') { i++; continue; }
    if (/\d/.test(c)) {
      let j = i;
      while (j < text.length && /\d/.test(text[j])) j++;
      tokens.push(parseInt(text.slice(i, j), 10));
      i = j;
    } else if (text.slice(i, i + 2) === '&&') { tokens.push('&&'); i += 2; }
    else if (text.slice(i, i + 2) === '||') { tokens.push('||'); i += 2; }
    else if (c === '(' || c === ')' || c === ',') { tokens.push(c); i++; }
    else if (/[a-zA-Z_]/.test(c)) {
      let j = i;
      while (j < text.length) {
        const ch = text[j];
        if (ch === ' ' || ch === '\t' || ch === '(' || ch === ')' || ch === ',') break;
        if (text.slice(j, j + 2) === '&&' || text.slice(j, j + 2) === '||') break;
        j++;
      }
      tokens.push(text.slice(i, j)); // raw name token e.g. "Infamy*5"
      i = j;
    } else { i++; } // skip unknown chars
  }

  let pos = 0;
  const peek = () => (pos < tokens.length ? tokens[pos] : null);
  const consume = () => tokens[pos++];

  const parseOr = () => {
    const results = [parseAnd()];
    while (peek() === '||') { consume(); results.push(parseAnd()); }
    return results.some(Boolean);
  };
  const parseAnd = () => {
    const results = [parseAtom()];
    while (peek() === '&&' || peek() === ',') { consume(); results.push(parseAtom()); }
    return results.every(Boolean);
  };
  const parseAtom = () => {
    const tok = peek();
    if (tok === '(') { consume(); const v = parseOr(); consume(); return v; }
    if (typeof tok === 'number') { consume(); return leafFn(tok); }
    if (typeof tok === 'string' && tok !== '&&' && tok !== '||' && tok !== '(' && tok !== ')' && tok !== ',') {
      consume();
      if (nameFn) {
        const mStar = tok.match(/^(.+[a-zA-Z_])\*(\d+)$/);
        const mDash = tok.match(/^(.+[a-zA-Z_])-(\d+)$/);
        if (mStar) return nameFn(mStar[1], parseInt(mStar[2], 10));
        if (mDash) return nameFn(mDash[1], null);
        return nameFn(tok, null);
      }
      return true;
    }
    if (tok !== null) consume();
    return true;
  };

  try { return parseOr(); } catch (_) { return true; }
}

// =============================================================
// Utility – bingo line calculator
// (port of client.py _bingo_lines)
// =============================================================
function bingoLines(X, Y) {
  const lines = [];
  for (let r = 0; r < Y; r++) {
    const row = [];
    for (let c = 0; c < X; c++) row.push(r * X + c);
    lines.push(row);
  }
  for (let c = 0; c < X; c++) {
    const col = [];
    for (let r = 0; r < Y; r++) col.push(r * X + c);
    lines.push(col);
  }
  const d = Math.min(X, Y);
  for (let r0 = 0; r0 <= Y - d; r0++) {
    for (let c0 = 0; c0 <= X - d; c0++) {
      const diag = [];
      for (let k = 0; k < d; k++) diag.push((r0 + k) * X + (c0 + k));
      lines.push(diag);
    }
  }
  for (let r0 = 0; r0 <= Y - d; r0++) {
    for (let c0 = d - 1; c0 < X; c0++) {
      const diag = [];
      for (let k = 0; k < d; k++) diag.push((r0 + k) * X + (c0 - k));
      lines.push(diag);
    }
  }
  return lines;
}

// =============================================================
// Prereq satisfaction helpers
// =============================================================
function allChecked() {
  const s = new Set(ap.checkedLocations);
  for (const c of state.pendingLocations) s.add(c);
  return s;
}

function prereqsSatisfied(prereqText, checked) {
  if (!prereqText || state.baseCompleteId === null) return true;
  return evalPrereqExpr(prereqText, idx1 =>
    checked.has(state.baseCompleteId + idx1 - 1)
  );
}

function receivedItemIds() {
  const out = new Set();
  for (const it of ap.itemsReceived) {
    if (it && typeof it.item === 'number') out.add(it.item);
  }
  return out;
}

function itemPrereqsSatisfied(prereqText, progReqs) {
  if (!prereqText) return true;
  const have = receivedItemIds();
  const base = state.baseItemId;
  const progCount = {};
  for (const req of (progReqs || [])) {
    const g = req.group ?? req[0];
    const c = req.count ?? req[1] ?? 1;
    progCount[g] = c;
  }
  const nameFn = (group, count) => {
    const c = count !== null ? count : (progCount[group] ?? 1);
    return progressiveReqSatisfied(group, c);
  };
  return evalPrereqExpr(
    prereqText,
    idx1 => typeof base === 'number' && have.has(base + idx1 - 1),
    nameFn
  );
}

function progressiveReqSatisfied(group, required) {
  const progGroup = state.rewardProgressiveGroup;
  const base = state.baseItemId;
  if (typeof base !== 'number') return true;
  const have = receivedItemIds();
  let count = 0;
  for (let i = 0; i < progGroup.length; i++) {
    if (progGroup[i] === group && have.has(base + i)) count++;
  }
  return count >= required;
}

function regionReqSatisfied(rname, pct, checked) {
  const region_indices = state.taskRegion
    .map((r, i) => r === rname ? i : -1)
    .filter(i => i >= 0);
  if (!region_indices.length) return true;
  const required = Math.ceil(region_indices.length * pct / 100);
  const done = region_indices.filter(i =>
    checked.has(state.baseCompleteId + i)
  ).length;
  return done >= required;
}

function regionReqSatisfiedAbs(rname, requiredCount, checked) {
  const region_indices = state.taskRegion
    .map((r, i) => r === rname ? i : -1)
    .filter(i => i >= 0);
  const done = region_indices.filter(i =>
    checked.has(state.baseCompleteId + i)
  ).length;
  return done >= requiredCount;
}

// =============================================================
// Consumable helpers
// =============================================================
function consumableReceivedCounts() {
  const counts = {};
  const base = state.baseItemId;
  if (typeof base !== 'number') return counts;
  for (const it of ap.itemsReceived) {
    if (!it || typeof it.item !== 'number') continue;
    const idx = it.item - base;
    if (idx < 0 || idx >= state.items.length) continue;
    if (!state.itemConsumable[idx]) continue;
    const name = state.items[idx];
    counts[name] = (counts[name] || 0) + 1;
  }
  return counts;
}

function consumableSpentCounts() {
  const totals = {};
  for (const deduction of Object.values(state.taskPurchases)) {
    for (const [name, amt] of Object.entries(deduction)) {
      totals[name] = (totals[name] || 0) + amt;
    }
  }
  return totals;
}

function consumableBalance() {
  const recv = consumableReceivedCounts();
  const spent = consumableSpentCounts();
  const manual = state.manualConsumptions;
  const all = new Set([...Object.keys(recv), ...Object.keys(spent), ...Object.keys(manual)]);
  const bal = {};
  for (const n of all) bal[n] = (recv[n] || 0) - (spent[n] || 0) - (manual[n] || 0);
  return bal;
}

function consumableItemNames() {
  const names = [];
  const seen  = new Set();
  for (let i = 0; i < state.items.length; i++) {
    const name = state.items[i];
    if (state.itemConsumable[i] && name && !seen.has(name)) {
      names.push(name);
      seen.add(name);
    }
  }
  return names;
}

function progressiveGroupCounts() {
  const progGroup = state.rewardProgressiveGroup;
  const base = state.baseItemId;
  const have = receivedItemIds();
  const result = {};
  for (const g of state.progressiveGroups) {
    let total = 0, received = 0;
    for (let i = 0; i < progGroup.length; i++) {
      if (progGroup[i] === g) {
        total++;
        if (typeof base === 'number' && have.has(base + i)) received++;
      }
    }
    result[g] = { received, total };
  }
  return result;
}

function taskCostIsPaid(idx) {
  const branches = (state.taskCostAmounts[idx] || []);
  if (!branches.length) return true;
  return idx in state.taskPurchases;
}

function recalcPurchasesFromCompleted() {
  const checked = allChecked();
  if (state.baseCompleteId === null) return;
  for (let i = 0; i < state.taskCostAmounts.length; i++) {
    const branches = state.taskCostAmounts[i];
    if (!branches || !branches.length) continue;
    if (!checked.has(state.baseCompleteId + i)) continue;
    if (i in state.taskPurchases) continue;
    // assign minimum-cost branch as default
    const min = branches.reduce((a, b) =>
      b.reduce((s, [, amt]) => s + amt, 0) < a.reduce((s, [, amt]) => s + amt, 0) ? b : a
    );
    state.taskPurchases[i] = Object.fromEntries(min);
  }
}

// =============================================================
// Notify index persistence (localStorage)
// =============================================================
function notifyKey() {
  const server = (els.serverInput.value || '').trim().toLowerCase();
  const slot   = (els.slotInput.value  || '').trim();
  const seed   = state.seedName || '';
  return `taskipelago_notify_v3::${server}::${slot}::${seed}`;
}

function loadNotifyIndex() {
  try {
    const v = localStorage.getItem(notifyKey());
    if (v !== null) { const n = parseInt(v, 10); if (n >= 0) return n; }
  } catch (_) {}
  return null;
}

function saveNotifyIndex(idx, force = false) {
  try {
    const key = notifyKey();
    if (!force) {
      const cur = loadNotifyIndex();
      if (cur !== null && cur > idx) return;
    }
    localStorage.setItem(key, String(idx));
  } catch (_) {}
}

// Persist last server/slot
function saveLastConnection(server, slot) {
  try { localStorage.setItem('taskipelago_last_conn', JSON.stringify({ server, slot })); } catch (_) {}
}
function loadLastConnection() {
  try { return JSON.parse(localStorage.getItem('taskipelago_last_conn') || '{}'); } catch (_) { return {}; }
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
// Goal completion
// =============================================================
function maybeSendGoal() {
  if (state.sentGoal) return;
  if (!state.tasks.length || state.baseCompleteId === null) return;
  const checked = allChecked();
  let done;
  if (state.goalExpression) {
    done = evalPrereqExpr(state.goalExpression, idx1 =>
      checked.has(state.baseCompleteId + idx1 - 1)
    );
    for (const req of (state.goalRegionReqs || [])) {
      const r = req.region ?? req[0];
      const abs = req.abs_count ?? null;
      const pct = req.pct ?? req[1] ?? 100;
      done = done && (abs !== null
        ? regionReqSatisfiedAbs(r, abs, checked)
        : regionReqSatisfied(r, pct, checked));
    }
  } else {
    done = state.tasks.every((_, i) => checked.has(state.baseCompleteId + i));
  }
  if (!done) return;
  state.sentGoal = true;
  ap.sendStatusUpdate(30); // CLIENT_GOAL
}

// =============================================================
// Task completion
// =============================================================
function completeTask(taskIdx) {
  if (state.baseRewardId === null || state.baseCompleteId === null) return;
  const completeId = state.baseCompleteId + taskIdx;
  const rewardId   = state.baseRewardId   + taskIdx;
  const checked = allChecked();
  if (checked.has(completeId) || state.pendingLocations.has(completeId)) return;

  state.pendingLocations.add(completeId);
  renderTasks();

  // Sent notification
  const rewardName = state.sentItemNames[taskIdx] || '';
  const recipient  = state.sentPlayerNames[taskIdx] || '';
  if (rewardName && !isFiller(rewardName)) {
    enqueueNotification({
      kind: 'sent',
      title: 'Reward Sent!',
      body: `Task ${taskIdx + 1}: ${state.tasks[taskIdx] || ''}\n\n${rewardName}\n\n(sent to ${recipient || 'Unknown'})`,
    });
  }

  ap.sendLocationChecks([completeId, rewardId]);
}

// =============================================================
// Purchase / Make Change
// =============================================================
function attemptPurchase(taskIdx) {
  const branches = state.taskCostAmounts[taskIdx] || [];
  if (!branches.length) return;
  const bal = consumableBalance();

  const canAfford = branch => branch.every(([name, amt]) => (bal[name] || 0) >= amt);
  const affordable = branches.filter(canAfford);

  if (!affordable.length) {
    showModal(
      'Insufficient Funds',
      "You don't have enough consumable items to purchase this task.",
      ['OK'],
      () => {}
    );
    return;
  }

  const doWithBranch = branch => {
    state.taskPurchases[taskIdx] = Object.fromEntries(branch);
    renderTasks();
    renderConsumables();
  };

  if (affordable.length === 1 && branches.length === 1) {
    doWithBranch(affordable[0]);
    return;
  }

  const labels = affordable.map(b => b.map(([name, amt]) => `${amt} ${name}`).join(' && '));
  showModal('Choose Payment', 'Choose how to pay for this task:', labels, idx => {
    if (idx !== null) doWithBranch(affordable[idx]);
  });
}

function attemptMakeChange(taskIdx) {
  const branches = state.taskCostAmounts[taskIdx] || [];
  if (branches.length <= 1) return;
  const current = state.taskPurchases[taskIdx];
  if (!current) return;

  const baseBal = consumableBalance();
  const refundBal = { ...baseBal };
  for (const [name, amt] of Object.entries(current)) {
    refundBal[name] = (refundBal[name] || 0) + amt;
  }

  const currentDict = JSON.stringify(current);
  const alternatives = branches.filter(b => {
    if (JSON.stringify(Object.fromEntries(b)) === currentDict) return false;
    return b.every(([name, amt]) => (refundBal[name] || 0) >= amt);
  });

  if (!alternatives.length) {
    const currentLabel = Object.entries(current).map(([n, a]) => `${a} ${n}`).join(', ');
    showModal(
      'No Alternatives',
      `Currently paid: ${currentLabel}\n\nNo alternative payment can be afforded right now.`,
      ['OK'],
      () => {}
    );
    return;
  }

  const currentLabel = Object.entries(current).map(([n, a]) => `${a} ${n}`).join(', ');
  const labels = alternatives.map(b => b.map(([name, amt]) => `${amt} ${name}`).join(' && '));
  showModal('Make Change', `Currently paid: ${currentLabel}\n\nSwitch payment to:`, labels, idx => {
    if (idx !== null) {
      state.taskPurchases[taskIdx] = Object.fromEntries(alternatives[idx]);
      renderTasks();
      renderConsumables();
    }
  });
}

// =============================================================
// Filler detection
// =============================================================
const FILLER_SET = new Set([
  'Several pats on the back', 'A big thumbs up', 'Free dopamine',
  'One (1) sense of accomplishment', 'Mildly increased self-esteem',
  'A crisp high five', 'A firm handshake', 'A tiny mental victory parade',
  'Temporary immunity to self-criticism', 'An imaginary star sticker',
  'A nod of respect', 'nothing here, get pranked nerd',
]);
function isFiller(s) { return FILLER_SET.has((s || '').trim()); }

// =============================================================
// Notifications
// =============================================================
function enqueueNotification({ kind, title, body }) {
  state.notifications.push({ kind, title, body, createdAt: Date.now() });
  if (state.notifications.length > MAX_NOTIFICATIONS) {
    state.notifications = state.notifications.slice(-MAX_NOTIFICATIONS);
  }
  renderNotifications();
}

// =============================================================
// UI: Main tab switching
// =============================================================
els.mainTabs.forEach(btn => btn.addEventListener('click', () => {
  els.mainTabs.forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  $(`tab-${btn.dataset.tab}`)?.classList.add('active');
}));

// Sub-tab switching (notifications panel)
els.subTabs.forEach(btn => btn.addEventListener('click', () => {
  els.subTabs.forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.subtab-pane').forEach(p => p.classList.remove('active'));
  $(`subtab-${btn.dataset.subtab}`)?.classList.add('active');
}));

// =============================================================
// UI: Connection
// =============================================================
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

// =============================================================
// Archipelago callbacks
// =============================================================
ap.onConnected = (slotData, checkedLocs) => {
  // Merge server-checked locations
  for (const c of checkedLocs) state.checkedLocations.add(c);

  applySlotData(slotData);
  loadManualConsumptions();        // seed from localStorage as initial value
  ap.sendGet([manualConsumptionsServerKey()]); // server value will arrive via onRetrieved and override if present

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
  if (tags.includes('TaskipelagoSync') &&
      data.type === 'taskipelago_manual_sync' &&
      data.client_id !== CLIENT_ID &&
      data.seed === state.seedName &&
      data.slot_name === (els.slotInput.value || '').trim()) {
    applyManualConsumptions(data.manual_consumptions);
  }

  if (!tags.includes('DeathLink')) return;

  // Ignore self-sent bounces
  const ownSlot = (els.slotInput.value || '').trim() || 'Taskipelago';
  if ((data.source || '') === ownSlot) return;

  // Amnesty
  if (state.deathLinkAmnestyLeft > 0) {
    state.deathLinkAmnestyLeft--;
    return;
  }
  state.deathLinkAmnestyLeft = state.deathLinkAmnesty;

  const pool    = state.deathLinkPool;
  const weights = state.deathLinkWeights;

  let task;
  if (pool.length) {
    const w = pool.map((_, i) => Math.max(0, parseFloat(weights[i]) || 1));
    const total = w.reduce((a, b) => a + b, 0);
    if (total > 0) {
      let r = Math.random() * total;
      task = pool[pool.findIndex((_, i) => { r -= w[i]; return r <= 0; })];
    } else {
      task = pool[Math.floor(Math.random() * pool.length)];
    }
  } else {
    task = 'No pool entries configured. Make something up, I guess';
  }

  const source = data.source || 'Unknown';
  const cause  = data.cause  || '';
  enqueueNotification({
    kind:  'deathlink',
    title: 'DEATHLINK!',
    body:  `From: ${source}${cause ? '\n' + cause : ''}\n\nTask: ${task}`,
  });
};

ap.onPrintJSON = (parts, msgType, senderSlot) => {
  appendConsoleHTML(printJsonToHTML(parts, senderSlot));
};

// =============================================================
// Item notification
// =============================================================
function showItemNotification(it) {
  if (!it || typeof it.item !== 'number') return;

  // Skip completion tokens
  const baseToken = state.baseTokenId;
  const nTasks    = state.tasks.length;
  if (typeof baseToken === 'number' && nTasks > 0) {
    const off = it.item - baseToken;
    if (off >= 0 && off < nTasks) return;
  }

  // Resolve name
  const base = state.baseItemId;
  let name = null;
  if (typeof base === 'number') {
    const idx = it.item - base;
    if (idx >= 0 && idx < state.items.length && state.items[idx]) {
      name = state.items[idx];
    }
  }
  if (!name || !name.trim() || isFiller(name)) return;
  if (name.startsWith('Task Complete ')) return;

  // Sender
  let sender = '';
  if (it.player != null) sender = ap.resolvePlayerName(it.player);

  enqueueNotification({
    kind:  'reward',
    title: 'Reward Received!',
    body:  `${name.trim()}${sender ? `\n(from ${sender})` : ''}`,
  });
}

// =============================================================
// Region helpers
// =============================================================
let regionProgressExpanded = true;

function buildRegionColorMap() {
  const m = {};
  for (let i = 0; i < state.regions.length; i++) {
    const c = state.regionColors[i];
    if (c) m[state.regions[i]] = c;
  }
  return m;
}

function renderRegionProgress() {
  const section = $('region-progress-section');
  if (!section) return;
  const connected = state.connState === 'connected' && state.regions.length > 0;
  if (!connected) {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');

  const list = $('region-progress-list');
  if (!regionProgressExpanded) return;

  const checked = allChecked();
  const rColors = buildRegionColorMap();
  const frag = document.createDocumentFragment();

  for (const rname of state.regions) {
    const color = rColors[rname] || '#808080';
    const indices = state.taskRegion.map((r, i) => r === rname ? i : -1).filter(i => i >= 0);
    const total = indices.length;
    const done = state.baseCompleteId !== null
      ? indices.filter(i => checked.has(state.baseCompleteId + i)).length
      : 0;
    const pct = total > 0 ? done / total : 0;

    const row = document.createElement('div');
    row.className = 'region-progress-row';

    const nameEl = document.createElement('span');
    nameEl.className = 'region-progress-name';
    nameEl.textContent = rname;
    row.appendChild(nameEl);

    const barOuter = document.createElement('div');
    barOuter.className = 'region-progress-bar-outer';
    const barInner = document.createElement('div');
    barInner.className = 'region-progress-bar-inner';
    barInner.style.width = `${Math.round(pct * 100)}%`;
    barInner.style.backgroundColor = color;
    barOuter.appendChild(barInner);
    row.appendChild(barOuter);

    const countEl = document.createElement('span');
    countEl.className = 'region-progress-count';
    countEl.textContent = `${done}/${total}`;
    row.appendChild(countEl);

    frag.appendChild(row);
  }

  list.innerHTML = '';
  list.appendChild(frag);
}

// =============================================================
// Rendering: all panels
// =============================================================
function renderAll() {
  renderTasks();
  renderRegionProgress();
  renderNotifications();
  renderItems();
  renderConsumables();
}

// =============================================================
// Rendering: tasks
// =============================================================
function renderTasks() {
  const connected = !!(
    state.tasks.length &&
    state.baseRewardId !== null &&
    state.baseCompleteId !== null &&
    state.connState === 'connected'
  );

  // Option bar visibility
  const yamlLock = state.lockPrereqs;
  const effectiveLock = yamlLock || state.localEnforce;

  if (connected && !yamlLock && !state.bingoMode) {
    els.enforceHeader.classList.remove('hidden');
  } else {
    els.enforceHeader.classList.add('hidden');
  }

  if (connected && !state.bingoMode) {
    els.showLockedHeader.classList.remove('hidden');
  } else {
    els.showLockedHeader.classList.add('hidden');
  }

  if (connected && effectiveLock && state.hideUnreachable && !state.bingoMode) {
    els.showLockedWrapper.classList.remove('hidden');
  } else {
    els.showLockedWrapper.classList.add('hidden');
  }

  // DeathLink button
  if (connected && state.deathLinkEnabled) {
    els.deathLinkBtn.classList.remove('hidden');
  } else {
    els.deathLinkBtn.classList.add('hidden');
  }

  if (!connected) {
    els.tasksList.innerHTML = '<div style="padding:10px;color:var(--muted);font-size:12px;">Connect to a server to see tasks.</div>';
    els.tasksList.classList.remove('hidden');
    els.bingoSection.classList.add('hidden');
    return;
  }

  if (state.bingoMode) {
    els.tasksList.classList.add('hidden');
    els.bingoSection.classList.remove('hidden');
    renderBingo();
    return;
  }

  els.bingoSection.classList.add('hidden');
  els.tasksList.classList.remove('hidden');

  const checked = allChecked();
  const frag = document.createDocumentFragment();

  for (let i = 0; i < state.tasks.length; i++) {
    const taskName = state.tasks[i];
    const completeId = state.baseCompleteId + i;
    const completed  = checked.has(completeId);

    // Task prereqs
    let taskPrereqOk = true;
    let taskPrereqText = '';
    if (i < state.taskPrereqs.length && state.taskPrereqs[i]) {
      taskPrereqText = String(state.taskPrereqs[i]).trim();
      if (taskPrereqText) taskPrereqOk = prereqsSatisfied(taskPrereqText, checked);
    }

    // Progressive group requirements
    const progReqs = (Array.isArray(state.taskProgressiveReqs[i]) ? state.taskProgressiveReqs[i] : []);

    // Item prereqs
    let itemPrereqOk = true;
    let itemPrereqText = '';
    if (i < state.itemPrereqs.length && state.itemPrereqs[i]) {
      itemPrereqText = String(state.itemPrereqs[i]).trim();
      if (itemPrereqText) itemPrereqOk = itemPrereqsSatisfied(itemPrereqText, progReqs);
    }

    const progHints = [];
    for (const req of progReqs) {
      const g = req.group ?? req[0];
      const c = req.count ?? req[1] ?? 1;
      if (!progressiveReqSatisfied(g, c)) progHints.push(`group '${g}' (need ${c})`);
    }

    // Region requirements
    const regionReqs = (Array.isArray(state.taskRegionReqs[i]) ? state.taskRegionReqs[i] : []);
    let regionOk = true;
    const regionHints = [];
    for (const req of regionReqs) {
      const r   = req.region ?? req[0];
      const abs = req.abs_count ?? null;
      const pct = req.pct ?? req[1] ?? 100;
      if (abs !== null) {
        if (!regionReqSatisfiedAbs(r, abs, checked)) {
          regionOk = false;
          regionHints.push(`region '${r}' (need ${abs} tasks)`);
        }
      } else {
        if (!regionReqSatisfied(r, pct, checked)) {
          regionOk = false;
          regionHints.push(`region '${r}' (${pct}% completed)`);
        }
      }
    }

    // Cost
    const branches = state.taskCostAmounts[i] || [];
    const hasCost  = branches.length > 0;
    const costPaid = !hasCost || !effectiveLock || taskCostIsPaid(i);

    const otherPrereqsOk = taskPrereqOk && itemPrereqOk && regionOk;
    const costOnlyLocked = otherPrereqsOk && !costPaid;

    const wouldHide = !otherPrereqsOk && state.hideUnreachable && effectiveLock;
    const showAsLocked = wouldHide && state.showLocked;
    if (wouldHide && !showAsLocked) continue;
    if (completed && state.hideCompleted) continue;

    const card = document.createElement('div');
    card.className = 'task-card';
    const _rColors = buildRegionColorMap();
    const _taskReg = state.taskRegion[i] || '';
    const _barColor = _taskReg ? (_rColors[_taskReg] || '') : '';
    card.style.borderLeft = _barColor ? `4px solid ${_barColor}` : '';

    const top = document.createElement('div');
    top.className = 'task-top';

    const nameEl = document.createElement('span');
    nameEl.className = 'task-name' +
      (showAsLocked ? ' locked' : completed ? ' completed' : '');
    nameEl.textContent = showAsLocked
      ? `${i + 1}. Locked Task`
      : completed
        ? `✔ ${i + 1}. ${taskName}`
        : `${i + 1}. ${taskName}`;
    top.appendChild(nameEl);

    const actions = document.createElement('div');
    actions.className = 'task-actions';

    const canMakeChange = branches.length > 1 && (i in state.taskPurchases);

    if (completed) {
      if (canMakeChange) {
        const mcBtn = document.createElement('button');
        mcBtn.textContent = 'Make Change';
        mcBtn.onclick = () => attemptMakeChange(i);
        actions.appendChild(mcBtn);
      }
    } else if (costOnlyLocked && effectiveLock) {
      const pBtn = document.createElement('button');
      pBtn.textContent = '$$ Purchase $$';
      pBtn.onclick = () => attemptPurchase(i);
      actions.appendChild(pBtn);

      if (canMakeChange) {
        const mcBtn = document.createElement('button');
        mcBtn.textContent = 'Make Change';
        mcBtn.onclick = () => attemptMakeChange(i);
        actions.appendChild(mcBtn);
      }
    } else {
      const canComplete = !(effectiveLock && (!otherPrereqsOk || !costPaid));

      if (canComplete && state.taskRewardPreviews !== 0) {
        const rName = state.sentItemNames[i] || '';
        const rPlayer = state.sentPlayerNames[i] || 'Unknown';
        if (rName) {
          const previewEl = document.createElement('span');
          previewEl.className = 'task-reward-preview';
          previewEl.textContent = `${rName} → ${rPlayer}`;
          top.appendChild(previewEl);
        }
        if (state.taskRewardPreviews === 2 && !state.hintRequestedIndices.has(i)) {
          state.hintRequestedIndices.add(i);
          ap.sendLocationScouts([state.baseRewardId + i], 1);
        }
      }

      const cBtn = document.createElement('button');
      cBtn.textContent = 'Complete';
      cBtn.disabled = !canComplete;
      cBtn.onclick = () => completeTask(i);

      if (canMakeChange) {
        const mcBtn = document.createElement('button');
        mcBtn.textContent = 'Make Change';
        mcBtn.onclick = () => attemptMakeChange(i);
        actions.appendChild(mcBtn);
      }
      actions.appendChild(cBtn);
    }

    top.appendChild(actions);
    card.appendChild(top);

    // Description
    const descText = !showAsLocked ? (state.taskDescriptions[i] || '') : '';
    if (descText) {
      const descEl = document.createElement('div');
      descEl.className = 'task-description';
      descEl.textContent = descText;
      card.appendChild(descEl);
    }

    // Hint lines
    if (!completed && taskPrereqText && !taskPrereqOk) {
      card.appendChild(makeHint(`Locked behind task(s): ${taskPrereqText}`));
    }
    if (!completed && (itemPrereqText || progHints.length) && !itemPrereqOk) {
      const parts = [];
      if (itemPrereqText) parts.push(resolveItemPrereqDisplay(itemPrereqText));
      parts.push(...progHints);
      card.appendChild(makeHint(`Locked behind item(s): ${parts.join(', ')}`));
    }
    if (!completed && regionHints.length && !regionOk) {
      card.appendChild(makeHint(`Locked behind region(s): ${regionHints.join(', ')}`));
    }
    if (!completed && costOnlyLocked && effectiveLock && branches.length) {
      const costParts = branches.map(branch =>
        branch.map(([name, amt]) => `${amt} ${name}`).join(' && ')
      );
      const costText = costParts.length > 1
        ? costParts.map(p => `(${p})`).join(' || ')
        : costParts[0];
      card.appendChild(makeHint(`Requires purchase: ${costText}`));
    }

    frag.appendChild(card);
  }

  els.tasksList.innerHTML = '';
  els.tasksList.appendChild(frag);
}

function makeHint(text) {
  const el = document.createElement('div');
  el.className = 'task-hint';
  el.textContent = text;
  return el;
}

function resolveItemPrereqDisplay(prereqText) {
  const parts = prereqText.split(',').map(s => s.trim()).filter(Boolean);
  return parts.map(p => {
    const n = parseInt(p, 10);
    if (!isNaN(n)) {
      const idx = n - 1;
      if (idx >= 0 && idx < state.items.length && state.items[idx]) return state.items[idx];
      return `Item #${n}`;
    }
    return p;
  }).join(', ');
}

// =============================================================
// Rendering: bingo board
// =============================================================
function renderBingo() {
  const X = state.bingoDimX;
  const Y = state.bingoDimY;
  const nSpaces = X * Y;

  if (state.tasks.length < nSpaces) {
    els.bingoGrid.innerHTML = '<div style="color:var(--muted);padding:8px">Waiting for task data...</div>';
    return;
  }

  els.bingoGrid.style.gridTemplateColumns = `repeat(${X}, 1fr)`;

  const checked   = allChecked();
  const received  = receivedItemIds();
  const base      = state.baseCompleteId;
  const baseItem  = state.baseItemId;
  const baseRew   = state.baseRewardId;

  const middle    = Math.floor(nSpaces / 2);
  const spDone    = Array.from({length: nSpaces}, (_, i) => checked.has(base + i));
  const spUnlocked = Array.from({length: nSpaces}, (_, i) =>
    (typeof baseItem === 'number' && received.has(baseItem + i)) || i === middle
  );

  const lines      = bingoLines(X, Y);
  const lineDone   = lines.map(line => line.every(s => spDone[s]));
  const nBingos    = lineDone.filter(Boolean).length;
  const needed     = Math.max(0, state.bingoal - nBingos);
  els.bingoCounter.textContent = `${nBingos} of ${lines.length} bingos complete (need ${needed} more)`;

  const inBingo = new Array(nSpaces).fill(false);
  lines.forEach((line, li) => {
    if (lineDone[li]) line.forEach(s => { inBingo[s] = true; });
  });

  // Auto-complete bingo lines
  lines.forEach((line, li) => {
    if (!lineDone[li]) return;
    const lineTaskIdx  = nSpaces + li;
    const lineCplId    = base + lineTaskIdx;
    const lineRewId    = baseRew + lineTaskIdx;
    if (!checked.has(lineCplId) && !state.pendingLocations.has(lineCplId)) {
      state.pendingLocations.add(lineCplId);
      ap.sendLocationChecks([lineCplId, lineRewId]);
    }
  });

  const frag = document.createDocumentFragment();
  for (let i = 0; i < nSpaces; i++) {
    const cell = document.createElement('div');
    cell.className = 'bingo-cell' +
      (inBingo[i] ? ' has-bingo' : spDone[i] ? ' is-done' : '');

    const txt = document.createElement('div');
    txt.className = 'cell-text';

    if (!spUnlocked[i]) {
      txt.textContent = 'Locked';
      txt.style.color = 'var(--muted)';
    } else if (spDone[i]) {
      txt.textContent = `✔ ${state.tasks[i]}`;
      txt.style.color = 'var(--muted)';
    } else {
      txt.textContent = state.tasks[i];
    }

    cell.appendChild(txt);

    if (spUnlocked[i] && !spDone[i]) {
      const btn = document.createElement('button');
      btn.textContent = 'Complete';
      btn.onclick = () => completeTask(i);
      cell.appendChild(btn);
    }

    frag.appendChild(cell);
  }

  els.bingoGrid.innerHTML = '';
  els.bingoGrid.appendChild(frag);
}

// =============================================================
// Rendering: notifications
// =============================================================
function renderNotifications() {
  const frag = document.createDocumentFragment();
  const list = [...state.notifications].reverse();

  for (let i = 0; i < list.length; i++) {
    const realIdx = state.notifications.length - 1 - i;
    const n = list[i];

    const card = document.createElement('div');
    card.className = 'notif-card';

    const hdr = document.createElement('div');
    hdr.className = 'notif-header';

    const title = document.createElement('div');
    title.className = 'notif-title';
    title.textContent = n.title;
    hdr.appendChild(title);

    const dismissBtn = document.createElement('button');
    dismissBtn.className = 'notif-dismiss';
    dismissBtn.textContent = 'Dismiss';
    dismissBtn.onclick = () => {
      state.notifications.splice(realIdx, 1);
      renderNotifications();
    };
    hdr.appendChild(dismissBtn);
    card.appendChild(hdr);

    const meta = document.createElement('div');
    meta.className = 'notif-meta';
    const ts = new Date(n.createdAt).toLocaleTimeString();
    meta.textContent = `${n.kind.toUpperCase()} • ${ts}`;
    card.appendChild(meta);

    const body = document.createElement('div');
    body.className = 'notif-body';
    body.textContent = n.body;
    card.appendChild(body);

    frag.appendChild(card);
  }

  els.notifList.innerHTML = '';
  if (!list.length) {
    els.notifList.innerHTML = '<div style="padding:8px;color:var(--muted);font-size:12px">No notifications.</div>';
  } else {
    els.notifList.appendChild(frag);
  }
}

// =============================================================
// Rendering: items received
// =============================================================
function renderItems() {
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

// =============================================================
// Manual consumption persistence + cross-client sync
// =============================================================
function manualConsumptionsKey() {
  const server = (els.serverInput.value || '').trim().toLowerCase();
  const slot   = (els.slotInput.value  || '').trim();
  const seed   = state.seedName || '';
  return `taskipelago_manual_v1::${server}::${slot}::${seed}`;
}

function manualConsumptionsServerKey() {
  const slot = (els.slotInput.value || '').trim();
  const seed = state.seedName || '';
  return `taskipelago_manual::${slot}::${seed}`;
}

function applyManualConsumptions(incoming) {
  if (!incoming || typeof incoming !== 'object') return;
  state.manualConsumptions = incoming;
  saveManualConsumptions();
  renderConsumables();
}

function loadManualConsumptions() {
  try {
    const raw = localStorage.getItem(manualConsumptionsKey());
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        state.manualConsumptions = parsed;
        return;
      }
    }
  } catch (_) {}
  state.manualConsumptions = {};
}

function saveManualConsumptions() {
  try {
    localStorage.setItem(manualConsumptionsKey(), JSON.stringify(state.manualConsumptions));
  } catch (_) {}
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
function renderConsumables() {
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

// =============================================================
// Rendering: console (PrintJSON -> colored HTML)
// =============================================================
const AP_COLORS = {
  red:       '#cc4444', green:    '#55aa55', yellow: '#aaaa44',
  blue:      '#5588cc', magenta:  '#aa55aa', cyan:   '#44aaaa',
  white:     '#cccccc', black:    '#555555', slateblue: '#6d8be8',
  plum:      '#af99ef', salmon:   '#fa8072',
};

function resolveItemName(id) {
  if (state.baseItemId !== null) {
    const idx = id - state.baseItemId;
    if (idx >= 0 && idx < state.items.length) return state.items[idx];
  }
  if (state.baseTokenId !== null) {
    const idx = id - state.baseTokenId;
    if (idx >= 0 && idx < state.tasks.length) return `${state.tasks[idx]} Token`;
  }
  return String(id);
}

function resolveLocationName(id) {
  if (state.baseCompleteId !== null) {
    const idx = id - state.baseCompleteId;
    if (idx >= 0 && idx < state.tasks.length) return state.tasks[idx];
  }
  if (state.baseRewardId !== null) {
    const idx = id - state.baseRewardId;
    if (idx >= 0 && idx < state.tasks.length) return `${state.tasks[idx]} Reward`;
  }
  return String(id);
}

function printJsonToHTML(parts, senderSlot) {
  let html = '';
  for (const part of parts) {
    const type = part.type || 'text';

    let displayText = part.text || '';
    if (type === 'player_id') {
      const slot = parseInt(displayText);
      displayText = ap.resolvePlayerName(slot) || displayText;
    } else if (type === 'item_id') {
      displayText = resolveItemName(parseInt(displayText));
    } else if (type === 'location_id') {
      displayText = resolveLocationName(parseInt(displayText));
    }

    const text = escapeHtml(displayText);

    let color = null;
    let bold  = false;

    if (type === 'player_id' || type === 'player_name') {
      color = (part.player === ap.ourSlot) ? AP_COLORS.magenta : AP_COLORS.yellow;
    } else if (type === 'item_id') {
      const f = part.flags || 0;
      if (f & 0b001)      color = AP_COLORS.plum;
      else if (f & 0b100) color = AP_COLORS.salmon;
      else                color = AP_COLORS.cyan;
    } else if (type === 'location_id') {
      color = AP_COLORS.green;
    } else if (type === 'entrance_name') {
      color = AP_COLORS.cyan;
    } else if (type === 'color') {
      color = AP_COLORS[part.color] || null;
      bold  = part.color === 'bold';
    }

    if (color || bold) {
      const style = [
        color ? `color:${color}` : '',
        bold  ? 'font-weight:bold' : '',
      ].filter(Boolean).join(';');
      html += `<span style="${style}">${text}</span>`;
    } else {
      html += text;
    }
  }
  return html;
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function appendConsoleHTML(html) {
  const line = document.createElement('div');
  line.innerHTML = html;
  els.consoleOutput.appendChild(line);
  els.consoleOutput.scrollTop = els.consoleOutput.scrollHeight;
}

function updateConsoleConnected(connected) {
  els.consoleInput.disabled = !connected;
  if (!connected) {
    els.consoleInput.placeholder = 'Must be connected to a multiworld';
    els.consoleInput.value = '';
  } else {
    els.consoleInput.placeholder = 'Send a message...';
  }
}

// =============================================================
// Console input
// =============================================================
function sendConsoleMessage() {
  if (state.connState !== 'connected') return;
  const msg = els.consoleInput.value.trim();
  if (!msg) return;
  els.consoleInput.value = '';
  appendConsoleHTML(`<span style="color:var(--muted)">&gt; ${escapeHtml(msg)}</span>`);
  ap.sendSay(msg);
}

els.consoleSendBtn.addEventListener('click', sendConsoleMessage);
els.consoleInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') sendConsoleMessage();
});

// =============================================================
// Checkbox handlers
// =============================================================
els.enforceCb.addEventListener('change', () => {
  state.localEnforce = els.enforceCb.checked;
  if (!state.localEnforce) {
    state.showLocked = false;
    els.showLockedCb.checked = false;
  }
  renderTasks();
});

els.showLockedCb.addEventListener('change', () => {
  state.showLocked = els.showLockedCb.checked;
  renderTasks();
});

els.hideCompletedCb.addEventListener('change', () => {
  state.hideCompleted = els.hideCompletedCb.checked;
  renderTasks();
});

// =============================================================
// Region progress toggle
// =============================================================
$('region-progress-toggle').addEventListener('click', () => {
  regionProgressExpanded = !regionProgressExpanded;
  const list = $('region-progress-list');
  const btn = $('region-progress-toggle');
  if (regionProgressExpanded) {
    list.classList.remove('hidden');
    btn.textContent = '▼ Regions';
    renderRegionProgress();
  } else {
    list.classList.add('hidden');
    btn.textContent = '▶ Regions';
  }
});

// =============================================================
// Notifications clear
// =============================================================
els.clearNotifsBtn.addEventListener('click', () => {
  state.notifications = [];
  renderNotifications();
});

// =============================================================
// Modal helper
// =============================================================
function showModal(title, desc, options, callback) {
  els.modalTitle.textContent = title;
  els.modalDesc.textContent  = desc;
  els.modalBtns.innerHTML    = '';

  const close = idx => {
    els.modalOverlay.classList.add('hidden');
    callback(idx);
  };

  for (let i = 0; i < options.length; i++) {
    const btn = document.createElement('button');
    btn.textContent = options[i];
    btn.onclick = () => close(i);
    els.modalBtns.appendChild(btn);
  }

  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = 'Cancel';
  cancelBtn.className   = 'modal-cancel';
  cancelBtn.onclick     = () => close(null);
  els.modalBtns.appendChild(cancelBtn);

  els.modalOverlay.classList.remove('hidden');
}

// Close modal on overlay click
els.modalOverlay.addEventListener('click', e => {
  if (e.target === els.modalOverlay) {
    els.modalOverlay.classList.add('hidden');
  }
});

// =============================================================
// Boot
// =============================================================
renderAll();
