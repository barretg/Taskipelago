import { state, els } from './state.js';
import { $ } from '../shared/dom.js';
import {
  allChecked, prereqsSatisfied, itemPrereqsSatisfied, progressiveReqSatisfied,
  regionPrereqSatisfied, regionReqSatisfied, regionReqSatisfiedAbs, taskCostIsPaid,
  completeTask, attemptPurchase, attemptMakeChange,
} from './logic.js';
import { renderBingo } from './bingo_board.js';
import { isManualTask, renderClicker } from './clicker_board.js';
import { ap } from './state.js';
import { getUiPref, setUiPref } from '../shared/ui_prefs.js';
import { h } from '../shared/dom.js';
import { completeDeathLinkEntry, isDeathLinkLocked, pendingDeathLinks } from './deathlink_queue.js';

// =============================================================
// Region helpers
// =============================================================
let regionProgressExpanded = true;
let subregionsExpanded = null;  // Set of expanded parent region names (lazy, from UI prefs)

function buildRegionColorMap() {
  const m = {};
  for (let i = 0; i < state.regions.length; i++) {
    const c = state.regionColors[i];
    if (c) m[state.regions[i]] = c;
  }
  return m;
}

/**
 * Subregions: state.regionParent maps a region to the region it is displayed
 * under. Nesting is one level, so a parent that itself names a parent is
 * ignored and its children are shown at the top level.
 */
function regionParentOf(rname) {
  const p = state.regionParent ? state.regionParent[rname] : '';
  if (!p || p === rname || !state.regions.includes(p)) return '';
  const gp = state.regionParent ? state.regionParent[p] : '';
  return gp && gp !== p && state.regions.includes(gp) ? '' : p;
}

/** Parent region name -> its subregion names, in region order. */
function buildSubregionMap() {
  const kids = new Map();
  for (const rname of state.regions) {
    const p = regionParentOf(rname);
    if (!p) continue;
    if (!kids.has(p)) kids.set(p, []);
    kids.get(p).push(rname);
  }
  return kids;
}

function expandedSubregions() {
  if (!subregionsExpanded) {
    const saved = getUiPref('expandedSubregions', []);
    subregionsExpanded = new Set(Array.isArray(saved) ? saved : []);
  }
  return subregionsExpanded;
}

/** Completed / total task slots directly assigned to one region. */
function regionCounts(rname, checked) {
  const indices = state.taskRegion.map((r, i) => (r === rname ? i : -1)).filter(i => i >= 0);
  const done = state.baseCompleteId !== null
    ? indices.filter(i => checked.has(state.baseCompleteId + i)).length
    : 0;
  return { done, total: indices.length };
}

function regionProgressRow(rname, { color, done, total, sub, kids, onToggle, expanded }) {
  const pct = total > 0 ? done / total : 0;
  const row = document.createElement('div');
  row.className = 'region-progress-row' + (sub ? ' region-progress-sub' : '')
    + (kids ? ' has-subregions' : '');

  const caret = document.createElement('span');
  caret.className = 'region-progress-caret';
  caret.textContent = kids ? (expanded ? '\u25bc' : '\u25b6') : '';
  row.appendChild(caret);

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

  if (kids) {
    row.setAttribute('role', 'button');
    row.tabIndex = 0;
    row.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    row.title = `${kids} subregion${kids === 1 ? '' : 's'} - click to ${expanded ? 'collapse' : 'expand'}`;
    row.addEventListener('click', onToggle);
    row.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onToggle();
      }
    });
  }
  return row;
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
  const kidsOf = buildSubregionMap();
  const open = expandedSubregions();
  const frag = document.createDocumentFragment();

  const toggleParent = rname => {
    if (open.has(rname)) open.delete(rname);
    else open.add(rname);
    setUiPref('expandedSubregions', [...open]);
    renderRegionProgress();
  };

  for (const rname of state.regions) {
    if (regionParentOf(rname)) continue;  // shown under its parent instead
    const kids = kidsOf.get(rname) || [];
    const expanded = open.has(rname);
    // A parent's bar rolls up its own tasks and every task in its subregions.
    const own = regionCounts(rname, checked);
    const totals = kids.reduce((acc, k) => {
      const c = regionCounts(k, checked);
      return { done: acc.done + c.done, total: acc.total + c.total };
    }, own);

    frag.appendChild(regionProgressRow(rname, {
      color: rColors[rname] || '#808080',
      done: totals.done, total: totals.total, sub: false,
      kids: kids.length, expanded, onToggle: () => toggleParent(rname),
    }));
    if (!kids.length || !expanded) continue;
    for (const kid of kids) {
      const c = regionCounts(kid, checked);
      frag.appendChild(regionProgressRow(kid, {
        color: rColors[kid] || '#808080', done: c.done, total: c.total, sub: true, kids: 0,
      }));
    }
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
/**
 * Whether task `i` is completed and whether anything still locks it, with the
 * human-readable reasons. Shared by the task list and the clicker board so both
 * agree on exactly one notion of "unlocked".
 *
 * `effectiveLock` defaults to the YAML setting plus the local override, which
 * is what the task list uses; cost only locks a task when it is on.
 */
export function taskAvailability(i, checked = allChecked(), effectiveLock = state.lockPrereqs || state.localEnforce) {
  const completed = state.baseCompleteId !== null && checked.has(state.baseCompleteId + i);

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

  // A region "Depends on" that uses task(...) / item(...) ships as one expression.
  const regionName = state.taskRegion[i] || '';
  const regionExprText = (state.regionPrereqExprs || {})[regionName] || '';
  const regionExprOk = !regionExprText || regionPrereqSatisfied(regionName, checked);
  if (!regionExprOk) regionOk = false;

  const otherPrereqsOk = taskPrereqOk && itemPrereqOk && regionOk;
  const costOnlyLocked = otherPrereqsOk && !costPaid;

  const reasons = [];
  if (taskPrereqText && !taskPrereqOk) reasons.push(`Locked behind task(s): ${taskPrereqText}`);
  if ((itemPrereqText || progHints.length) && !itemPrereqOk) {
    const parts = [];
    if (itemPrereqText) parts.push(itemPrereqText);
    parts.push(...progHints);
    reasons.push(`Locked behind item(s): ${parts.join(', ')}`);
  }
  if (regionHints.length && !regionOk) reasons.push(`Locked behind region(s): ${regionHints.join(', ')}`);
  if (!regionExprOk) reasons.push(`Locked behind region '${regionName}': ${regionExprText}`);
  if (costOnlyLocked && effectiveLock) reasons.push('Requires purchase');

  return {
    completed,
    unlocked: otherPrereqsOk && costPaid,
    reasons,
    taskPrereqOk, taskPrereqText, itemPrereqOk, itemPrereqText, progHints,
    regionOk, regionHints, branches, hasCost, costPaid, otherPrereqsOk, costOnlyLocked,
  };
}

export function renderTasks() {
  renderDeathLinkCards();
  const dlLocked = isDeathLinkLocked();
  els.tasksList.classList.toggle('locked-dl', dlLocked);
  els.bingoSection.classList.toggle('locked-dl', dlLocked);
  if (els.clickerSection) els.clickerSection.classList.toggle('locked-dl', dlLocked);
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
    if (els.clickerSection) els.clickerSection.classList.add('hidden');
    return;
  }

  if (state.bingoMode) {
    els.tasksList.classList.add('hidden');
    els.bingoSection.classList.remove('hidden');
    if (els.clickerSection) els.clickerSection.classList.add('hidden');
    renderBingo();
    return;
  }

  if (state.clickerMode) {
    els.tasksList.classList.add('hidden');
    els.bingoSection.classList.add('hidden');
    els.clickerSection.classList.remove('hidden');
    renderClicker();
    // Manual tasks opt out of clicking, so they keep the ordinary task row,
    // Complete button and all, in their own section under the cards.
    if (els.clickerManualList) {
      renderTaskCards(els.clickerManualList, effectiveLock, dlLocked, isManualTask);
      if (els.clickerManual) {
        els.clickerManual.classList.toggle('hidden', !els.clickerManualList.children.length);
      }
    }
    return;
  }

  els.bingoSection.classList.add('hidden');
  if (els.clickerSection) els.clickerSection.classList.add('hidden');
  els.tasksList.classList.remove('hidden');
  if (els.clickerManual) els.clickerManual.classList.add('hidden');

  renderTaskCards(els.tasksList, effectiveLock, dlLocked);
}

/**
 * The ordinary task cards, into `container`. `include` filters which task
 * indices are drawn, which is how clicker mode puts its manual tasks in a
 * section of their own; everything else renders the full list.
 */
function renderTaskCards(container, effectiveLock, dlLocked, include = null) {
  const checked = allChecked();
  const frag = document.createDocumentFragment();

  for (let i = 0; i < state.tasks.length; i++) {
    if (include && !include(i)) continue;
    const taskName = state.tasks[i];
    const { completed,
      taskPrereqOk, taskPrereqText, itemPrereqOk, itemPrereqText, progHints,
      regionOk, regionHints, branches, costPaid, otherPrereqsOk, costOnlyLocked,
    } = taskAvailability(i, checked, effectiveLock);

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

  container.innerHTML = '';
  container.appendChild(frag);
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
