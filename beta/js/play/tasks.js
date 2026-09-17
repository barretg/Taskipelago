import { state, els } from './state.js';
import { $ } from '../shared/dom.js';
import {
  allChecked, prereqsSatisfied, itemPrereqsSatisfied, progressiveReqSatisfied,
  regionReqSatisfied, regionReqSatisfiedAbs, taskCostIsPaid,
  completeTask, attemptPurchase, attemptMakeChange,
} from './logic.js';
import { renderBingo } from './bingo_board.js';
import { ap } from './state.js';
import { getUiPref, setUiPref } from '../shared/ui_prefs.js';
import { h } from '../shared/dom.js';
import { completeDeathLinkEntry, isDeathLinkLocked, pendingDeathLinks } from './deathlink_queue.js';

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

export function renderRegionProgress() {
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
// DeathLink task cards (v1.1 F3), pinned above everything else
// =============================================================
export function renderDeathLinkCards() {
  const box = els.deathLinkCards;
  if (!box) return;
  const entries = state.connState === 'connected' ? pendingDeathLinks() : [];
  box.classList.toggle('hidden', !entries.length);
  const cards = entries.map(e => h('div', { className: 'task-card dl-task-card', dataset: { id: e.id } },
    h('div', { className: 'task-top' },
      h('span', { className: 'task-name' }, `DeathLink: ${e.task}`),
      h('div', { className: 'task-actions' },
        h('button', { type: 'button', onclick: () => completeDeathLinkEntry(e.id) }, 'Complete'))),
    h('div', { className: 'task-description' }, `From ${e.source}${e.cause ? `: ${e.cause}` : ''}`)));
  if (entries.length && isDeathLinkLocked()) {
    cards.push(h('div', { className: 'task-hint dl-lock-hint' }, 'Locked until your DeathLink task(s) are done'));
  }
  box.replaceChildren(...cards);
}

// =============================================================
// Rendering: tasks
// =============================================================
export function renderTasks() {
  renderDeathLinkCards();
  const dlLocked = isDeathLinkLocked();
  els.tasksList.classList.toggle('locked-dl', dlLocked);
  els.bingoSection.classList.toggle('locked-dl', dlLocked);
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

    if (dlLocked) for (const btn of actions.querySelectorAll('button')) btn.disabled = true;
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

function setRegionProgressExpanded(expanded) {
  regionProgressExpanded = expanded;
  const list = $('region-progress-list');
  const btn = $('region-progress-toggle');
  if (expanded) {
    list.classList.remove('hidden');
    btn.textContent = '▼ Regions';
    renderRegionProgress();
  } else {
    list.classList.add('hidden');
    btn.textContent = '▶ Regions';
  }
}

export function initTasks() {
  // Per-device UI toggles (UNIFY 3.2)
  state.localEnforce = !!getUiPref('enforceLocally', false);
  state.hideCompleted = !!getUiPref('hideCompleted', false);
  els.enforceCb.checked = state.localEnforce;
  els.hideCompletedCb.checked = state.hideCompleted;
  if (getUiPref('regionsCollapsed', false)) setRegionProgressExpanded(false);

  els.enforceCb.addEventListener('change', () => {
    state.localEnforce = els.enforceCb.checked;
    setUiPref('enforceLocally', state.localEnforce);
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
    setUiPref('hideCompleted', state.hideCompleted);
    renderTasks();
  });

  $('region-progress-toggle').addEventListener('click', () => {
    setRegionProgressExpanded(!regionProgressExpanded);
    setUiPref('regionsCollapsed', !regionProgressExpanded);
  });
}
