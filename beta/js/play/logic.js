import { ap, state } from './state.js';
import { evalPrereqExpr } from '../shared/eval_prereq.js';
import { isFiller } from '../shared/filler.js';
import { showModal } from '../shared/modal.js';
import { enqueueNotification } from './notifications.js';
import { renderTasks } from './tasks.js';
import { renderConsumables } from './consumables.js';
import { writePurchase } from '../shared/server_state.js';

// Port of legacy_client/client.py _bingo_lines
export function bingoLines(X, Y) {
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
export function allChecked() {
  const s = new Set(ap.checkedLocations);
  for (const c of state.pendingLocations) s.add(c);
  return s;
}

export function prereqsSatisfied(prereqText, checked) {
  if (!prereqText || state.baseCompleteId === null) return true;
  return evalPrereqExpr(prereqText, idx1 =>
    checked.has(state.baseCompleteId + idx1 - 1)
  );
}

export function receivedItemIds() {
  const out = new Set();
  for (const it of ap.itemsReceived) {
    if (it && typeof it.item === 'number') out.add(it.item);
  }
  return out;
}

export function itemPrereqsSatisfied(prereqText, progReqs) {
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

export function progressiveReqSatisfied(group, required) {
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

export function regionReqSatisfied(rname, pct, checked) {
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

export function regionReqSatisfiedAbs(rname, requiredCount, checked) {
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
export function consumableReceivedCounts() {
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

export function consumableSpentCounts() {
  const totals = {};
  for (const deduction of Object.values(state.taskPurchases)) {
    for (const [name, amt] of Object.entries(deduction)) {
      totals[name] = (totals[name] || 0) + amt;
    }
  }
  return totals;
}

export function consumableBalance() {
  const recv = consumableReceivedCounts();
  const spent = consumableSpentCounts();
  const manual = state.manualConsumptions;
  const all = new Set([...Object.keys(recv), ...Object.keys(spent), ...Object.keys(manual)]);
  const bal = {};
  for (const n of all) bal[n] = (recv[n] || 0) - (spent[n] || 0) - (manual[n] || 0);
  return bal;
}

export function consumableItemNames() {
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

export function progressiveGroupCounts() {
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

export function taskCostIsPaid(idx) {
  const branches = (state.taskCostAmounts[idx] || []);
  if (!branches.length) return true;
  return idx in state.taskPurchases;
}

export function recalcPurchasesFromCompleted() {
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
// Goal completion
// =============================================================
export function maybeSendGoal() {
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
export function completeTask(taskIdx) {
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
export function attemptPurchase(taskIdx) {
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
    writePurchase(taskIdx, state.taskPurchases[taskIdx]);
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

export function attemptMakeChange(taskIdx) {
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
      writePurchase(taskIdx, state.taskPurchases[taskIdx]);
      renderTasks();
      renderConsumables();
    }
  });
}
