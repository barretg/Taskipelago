// Tasclickpelago: the clicker board, its accrual loop and its persistence.
//
// The apworld runs no simulation; slot_data carries the rates and requirements
// and everything below happens here. state.clickerProgress is the authority for
// how many activations each task has accrued; it is merged max-wise with data
// storage so two open clients cannot roll each other back.
import { ap, state, els } from './state.js';
import { allChecked, completeTask } from './logic.js';
import { taskAvailability } from './tasks.js';
import { isDeathLinkLocked } from './deathlink_queue.js';
import { evalNumExpr, numExprBindings } from '../shared/num_expr.js';
import {
  mergeClickerProgress, writeClickerProgress, flushClickerProgress,
} from '../shared/server_state.js';

// Accrual granularity: fast enough to look continuous, cheap enough to ignore.
export const TICK_MS = 250;

let loopTimer = null;
let offlineApplied = false;   // catch-up runs once per connection
let lastSignature = '';       // rebuild the DOM only when the visible set changes
const nodes = new Map();      // task index -> {progress, bar, rate}

// =============================================================
// Reading slot_data values
// =============================================================

/** A slot_data numeric field is either a plain number or a numeric-expression AST. */
function evalNum(value, bindings, fallback = 0) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : fallback;
  if (value && typeof value === 'object') {
    const v = evalNumExpr(value, bindings);
    return Number.isFinite(v) ? v : fallback;
  }
  return fallback;
}

export const KIND_TASK = 'task';
export const KIND_REGION = 'region';
export const KIND_ALL = 'all';

/**
 * One item's grants of one kind. A seed generated before targeting sends a
 * bare value, which connection.js has already normalized to a '*' spec, so
 * anything that is not a list simply grants nothing.
 */
function specList(value) {
  return Array.isArray(value) ? value : [];
}

/**
 * The tasks a spec aims at, inside `pool` (all tasks for the click channels,
 * the eligible ones for production). `byRegion` indexes that same pool.
 */
function aim(spec, pool, poolSet, byRegion) {
  if (!spec) return [];
  if (spec.kind === KIND_TASK) return poolSet.has(spec.ref) ? [spec.ref] : [];
  if (spec.kind === KIND_REGION) return byRegion[spec.ref] || [];
  return pool;
}

/** How a spec's target reads in the HUD. */
export function targetLabel(spec) {
  if (!spec || spec.kind === KIND_ALL) return 'all tasks';
  if (spec.kind === KIND_REGION) return spec.ref || 'no region';
  const i = spec.ref;
  return `${i + 1}. ${state.tasks[i] ?? '?'}`;
}

/** How many copies of each item index have been received. */
export function itemCopyCounts() {
  const counts = new Array(state.items.length).fill(0);
  const base = state.baseItemId;
  if (typeof base !== 'number') return counts;
  for (const it of ap.itemsReceived) {
    if (!it || typeof it.item !== 'number') continue;
    const idx = it.item - base;
    if (idx >= 0 && idx < counts.length) counts[idx] += 1;
  }
  return counts;
}

/** Activations needed to finish task `i`; blank or absent means one. */
export function requiredActivations(i) {
  const v = state.taskActivations[i];
  return Number.isFinite(v) && v >= 1 ? Math.round(v) : 1;
}

/**
 * A manual task opts out of clicker mode entirely: it is never clickable, never
 * receives production, and the task pane renders it as an ordinary task row
 * below the clicker cards. Set per task (task_manual) or per region
 * (region_manual) and folded into one list by the apworld.
 */
export function isManualTask(i) {
  return !!state.taskManual[i];
}

export function taskProgress(i) {
  const v = state.clickerProgress[i];
  return Number.isFinite(v) && v > 0 ? v : 0;
}

// =============================================================
// The model behind one tick
// =============================================================

/**
 * One pass over the board: who is eligible, what the constants bind to, and
 * what every eligible task earns per second. `offline` swaps the live rate for
 * the away rate. Recomputed from scratch each tick and each settle segment,
 * because completing a task moves every constant.
 */
export function clickerModel({ offline = false, checked = allChecked() } = {}) {
  const n = state.tasks.length;
  const avail = [];
  let nCompleted = 0;
  let nUnlocked = 0;      // completed tasks count as unlocked
  const eligible = [];
  for (let i = 0; i < n; i++) {
    const a = taskAvailability(i, checked);
    avail.push(a);
    if (a.completed) nCompleted++;
    if (a.unlocked || a.completed) nUnlocked++;
    if (a.unlocked && !a.completed && !isManualTask(i)) eligible.push(i);
  }
  const bindings = numExprBindings(n, nUnlocked, nCompleted);
  const counts = itemCopyCounts();

  // Two pools. The click channels describe every clicker task, so a card can
  // show its own click value whatever its state; production only ever reaches
  // an eligible (unlocked, incomplete) one. A manual task is in neither: it is
  // an ordinary Taskipelago task and reads no clicker grant at all.
  const allTasks = [];
  const allRegions = {};
  for (let i = 0; i < n; i++) {
    if (isManualTask(i)) continue;
    allTasks.push(i);
    (allRegions[state.taskRegion[i] || ''] || (allRegions[state.taskRegion[i] || ''] = [])).push(i);
  }
  const allSet = new Set(allTasks);
  const eligSet = new Set(eligible);
  const eligRegions = {};
  for (const i of eligible) {
    const r = state.taskRegion[i] || '';
    (eligRegions[r] || (eligRegions[r] = [])).push(i);
  }

  const grants = [];      // every grant in play, for the HUD

  // Click channel, per task: a channel of its own. The production multiplier
  // never touches it, and the click multiplier never touches production.
  const clickAdd = new Array(n).fill(0);
  const clickMultPer = new Array(n).fill(1);
  let starAdd = 0;        // the slot-wide ('*') part, for the summary figures
  let starMult = 1;
  const clickItems = [];
  for (let k = 0; k < counts.length; k++) {
    if (!counts[k]) continue;
    for (const spec of specList(state.itemClickPower[k])) {
      const p = evalNum(spec.rate, bindings, 0);
      if (!(p > 0)) continue;
      const add = p * counts[k];
      for (const i of aim(spec, allTasks, allSet, allRegions)) clickAdd[i] += add;
      if (spec.kind === KIND_ALL) starAdd += add;
      const g = { name: state.items[k], copies: counts[k], kind: 'click_power', spec, power: p };
      grants.push(g);
      clickItems.push(g);
    }
    for (const spec of specList(state.itemClickMult[k])) {
      const m = evalNum(spec.rate, bindings, 1);
      if (!(m > 0)) continue;
      const factor = Math.pow(m, counts[k]);
      for (const i of aim(spec, allTasks, allSet, allRegions)) clickMultPer[i] *= factor;
      if (spec.kind === KIND_ALL) starMult *= factor;
      const g = { name: state.items[k], copies: counts[k], kind: 'click_mult', spec, mult: m };
      grants.push(g);
      clickItems.push(g);
    }
  }
  // Indexed by task, so a manual task simply keeps the base click value of 1
  // that it never uses.
  const taskClickValue = [];
  for (let i = 0; i < n; i++) taskClickValue.push((1 + clickAdd[i]) * clickMultPer[i]);
  // The slot-wide click value: what a task with no click grant of its own is
  // worth, and what CPS binds to outside a targeted expression.
  const clickValue = (1 + starAdd) * starMult;
  const clickAddTotal = starAdd;
  const clickMult = starMult;

  // CPS is the click value. Binding it here, after the click channel and
  // before production, is what keeps it from being self-referential: the click
  // fields that define it are parsed with CPS rejected. Click power is per
  // target, so CPS binds per task: in a rate aimed at a task, it is that task's
  // click value.
  bindings.CPS = clickValue;
  const perTask = new Map();
  const bindFor = i => {
    let b = perTask.get(i);
    if (!b) {
      b = { ...bindings, CPS: taskClickValue[i] };
      perTask.set(i, b);
    }
    return b;
  };

  // Production multiplier, per task. Every received copy stacks
  // multiplicatively, over the tasks the item aims at.
  const prodMult = new Array(n).fill(1);
  let globalMult = 1;     // the '*' part, for the summary figures
  const multItems = [];
  for (let k = 0; k < counts.length; k++) {
    if (!counts[k]) continue;
    for (const spec of specList(state.itemProductionMult[k])) {
      const targets = aim(spec, allTasks, allSet, allRegions);
      if (!targets.length && spec.kind !== KIND_ALL) continue;
      for (const i of targets) {
        const m = evalNum(spec.rate, bindFor(i), 1);
        if (m > 0) prodMult[i] *= Math.pow(m, counts[k]);
      }
      const shown = evalNum(spec.rate, bindings, 1);
      if (!(shown > 0)) continue;
      if (spec.kind === KIND_ALL) globalMult *= Math.pow(shown, counts[k]);
      const g = { name: state.items[k], copies: counts[k], kind: 'production_mult', spec, mult: shown };
      grants.push(g);
      multItems.push(g);
    }
  }

  // Base production, from the per-item target specs.
  const base = new Array(n).fill(0);
  for (let k = 0; k < counts.length; k++) {
    if (!counts[k]) continue;
    for (const spec of specList(state.itemProduction[k])) {
      // Locked, completed and manual tasks never receive activations, and the
      // discarded amount is not banked.
      const targets = aim(spec, eligible, eligSet, eligRegions);
      const split = (spec.kind === KIND_REGION && state.regionDistributed[spec.ref])
        || (spec.kind === KIND_ALL && state.clickerDistributeGlobal);
      const divisor = split && targets.length ? targets.length : 1;
      for (const i of targets) {
        const rate = evalNum(spec.rate, bindFor(i), 0) * counts[k];
        if (rate > 0) base[i] += rate / divisor;
      }
      const shown = evalNum(spec.rate, bindings, 0) * counts[k];
      if (shown > 0) {
        grants.push({ name: state.items[k], copies: counts[k], kind: 'production', spec, rate: shown });
      }
    }
  }

  // Offline multipliers, per task, from item_offline_mult.
  let offlineMult = null;
  for (let k = 0; k < counts.length; k++) {
    if (!counts[k]) continue;
    for (const spec of specList(state.itemOfflineMult[k])) {
      const m = evalNum(spec.rate, bindings, 1);
      if (!(m > 0)) continue;
      grants.push({ name: state.items[k], copies: counts[k], kind: 'offline_mult', spec, mult: m });
    }
  }
  if (offline) {
    offlineMult = new Array(n).fill(1);
    for (let k = 0; k < counts.length; k++) {
      if (!counts[k]) continue;
      for (const spec of specList(state.itemOfflineMult[k])) {
        for (const i of aim(spec, allTasks, allSet, allRegions)) {
          const m = evalNum(spec.rate, bindFor(i), 1);
          if (m > 0) offlineMult[i] *= Math.pow(m, counts[k]);
        }
      }
    }
  }

  const rate = new Array(n).fill(0);
  for (const i of eligible) {
    let r = base[i] * prodMult[i];
    if (offline) r *= offlineRateFactor(i, bindFor(i)) * offlineMult[i];
    rate[i] = r;
  }

  return {
    avail, eligible, clickerTasks: allTasks, bindings, counts, base, rate, prodMult, grants,
    globalMult, multItems, clickValue, clickAdd: clickAddTotal, clickMult, clickItems,
    taskClickValue, taskClickAdd: clickAdd, taskClickMult: clickMultPer,
    nTasks: n, nUnlocked, nCompleted, nLocked: n - nUnlocked,
  };
}

/** region_offline_rate for this task's region, else the slot-wide rate. */
export function offlineRateFactor(i, bindings) {
  const region = state.taskRegion[i] || '';
  const override = region ? state.regionOfflineRate[region] : undefined;
  if (override !== undefined && override !== null) return Math.max(0, evalNum(override, bindings, 1));
  return Math.max(0, evalNum(state.clickerOfflineRate, bindings, 1));
}

// =============================================================
// Accrual
// =============================================================

/**
 * Apply `seconds` of production as a settle loop: a completion unlocks other
 * tasks and moves every task-count constant, so each segment re-binds the
 * constants and applies only the remaining time. Bounded by the task count.
 */
export function settle(seconds, { offline = false } = {}) {
  let remaining = seconds;
  let guard = state.tasks.length + 1;
  let completedAny = false;

  while (remaining > 1e-9 && guard-- > 0) {
    const m = clickerModel({ offline });
    if (!m.eligible.length) break;

    // The soonest completion bounds this segment; nothing else changes the model.
    let tNext = Infinity;
    for (const i of m.eligible) {
      if (!(m.rate[i] > 0)) continue;
      const t = (requiredActivations(i) - taskProgress(i)) / m.rate[i];
      if (t < tNext) tNext = t;
    }
    const step = Math.min(remaining, tNext);
    if (!(step > 0) && !Number.isFinite(tNext)) break;

    const finished = [];
    for (const i of m.eligible) {
      if (!(m.rate[i] > 0)) continue;
      const need = requiredActivations(i);
      const next = taskProgress(i) + m.rate[i] * step;
      // Overflow is discarded; progress freezes at the requirement.
      state.clickerProgress[i] = Math.min(need, next);
      if (state.clickerProgress[i] >= need) finished.push(i);
    }
    remaining -= step;
    if (!finished.length) break;
    for (const i of finished) completeTask(i);
    completedAny = true;
  }
  return completedAny;
}

/** A manual click on one task. Returns true when the task completed. */
export function clickTask(i) {
  if (!state.clickerMode || isDeathLinkLocked()) return false;
  const m = clickerModel();
  if (!m.eligible.includes(i)) return false;
  const need = requiredActivations(i);
  // Click power is per target, so a click is worth this task's click value.
  state.clickerProgress[i] = Math.min(need, taskProgress(i) + m.taskClickValue[i]);
  saveClickerProgress();
  if (state.clickerProgress[i] >= need) {
    completeTask(i);
    return true;
  }
  renderClicker();
  return false;
}

function clickerTick() {
  if (state.connState !== 'connected' || !state.clickerMode) return;
  const now = Date.now();
  // A DeathLink lock freezes the board the way it disables Complete buttons.
  if (isDeathLinkLocked()) { state.clickerLastTick = now; return; }
  const prev = state.clickerLastTick || now;
  const dt = Math.max(0, (now - prev) / 1000);
  state.clickerLastTick = now;
  if (dt <= 0) return;
  const completedAny = settle(dt);
  writeClickerProgress(state.clickerProgress, now);
  if (completedAny) return; // completeTask already re-rendered
  renderClicker();
}

/**
 * Offline catch-up, once per connection: at most clicker_offline_cap_hours of
 * elapsed time, at the away rate. Cap 0 disables catch-up while leaving the
 * rest of the offline configuration in place.
 */
export function applyOfflineCatchUp(now = Date.now()) {
  if (offlineApplied) return 0;
  offlineApplied = true;
  const since = state.clickerLastTick;
  state.clickerLastTick = now;
  if (!state.clickerOffline || !since || now <= since) return 0;
  const capSec = Math.max(0, state.clickerOfflineCapHours) * 3600;
  const elapsed = Math.min((now - since) / 1000, capSec);
  if (!(elapsed > 0)) return 0;
  settle(elapsed, { offline: true });
  writeClickerProgress(state.clickerProgress, now);
  return elapsed;
}

// =============================================================
// Persistence
// =============================================================

/**
 * Fold a value read from data storage into the live progress map: the initial
 * Retrieved, and every SetReply from another client.
 */
export function applyServerClickerProgress(value, initial = false) {
  const merged = mergeClickerProgress({ p: state.clickerProgress, t: state.clickerLastTick }, value);
  state.clickerProgress = merged.p;
  if (initial || merged.t > state.clickerLastTick) state.clickerLastTick = merged.t;
  if (initial && state.clickerMode) applyOfflineCatchUp();
}

export function saveClickerProgress(tickMs = Date.now()) {
  state.clickerLastTick = tickMs;
  writeClickerProgress(state.clickerProgress, tickMs);
}

// A closing or backgrounded tab should not lose the last few seconds of the
// debounce window.
if (typeof addEventListener === 'function') {
  addEventListener('pagehide', () => flushClickerProgress());
  addEventListener('visibilitychange', () => {
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') flushClickerProgress();
  });
}

export function startClickerLoop() {
  stopClickerLoop();
  if (!state.clickerMode) return;
  offlineApplied = false;
  loopTimer = setInterval(clickerTick, TICK_MS);
}

export function stopClickerLoop() {
  if (loopTimer) { clearInterval(loopTimer); loopTimer = null; }
  offlineApplied = false;
  lastSignature = '';
  nodes.clear();
  flushClickerProgress();
}

export function clickerLoopRunning() {
  return loopTimer !== null;
}

// =============================================================
// Rendering
// =============================================================

function fmt(n, places = 2) {
  if (!Number.isFinite(n)) return '0';
  const r = Math.round(n * 10 ** places) / 10 ** places;
  return String(r);
}

/** Group task indices by a value, highest value first. */
function groupBy(indices, valueOf) {
  const map = new Map();
  for (const i of indices) {
    const v = valueOf(i);
    (map.get(v) || map.set(v, []).get(v)).push(i);
  }
  return [...map].sort((a, b) => b[0] - a[0]);
}

/**
 * Which tasks are on the board, in order, following the existing
 * hideUnreachable / showLocked / hideCompleted rules rather than bingo's blunt
 * "Locked" cell.
 */
function visibleTasks(m) {
  const effectiveLock = state.lockPrereqs || state.localEnforce;
  const out = [];
  for (let i = 0; i < m.nTasks; i++) {
    if (isManualTask(i)) continue;   // rendered as a normal task row instead
    const a = m.avail[i];
    const wouldHide = !a.otherPrereqsOk && state.hideUnreachable && effectiveLock;
    if (wouldHide && !state.showLocked) continue;
    if (a.completed && state.hideCompleted) continue;
    out.push({ i, locked: !a.unlocked, hiddenName: wouldHide, completed: a.completed, reasons: a.reasons });
  }
  return out;
}

export function renderClicker() {
  if (!els.clickerGrid) return;
  const m = clickerModel();
  const rows = visibleTasks(m);

  const sig = rows.map(r => `${r.i}:${r.locked ? 'L' : ''}${r.completed ? 'C' : ''}${r.hiddenName ? 'H' : ''}`).join(',');
  if (sig !== lastSignature) {
    lastSignature = sig;
    buildGrid(rows, m);
  }
  updateGrid(rows, m);
  renderHeader(m);
}

function buildGrid(rows, m) {
  nodes.clear();
  const frag = document.createDocumentFragment();
  for (const row of rows) {
    const i = row.i;
    const card = document.createElement('div');
    card.className = 'clicker-card' + (row.completed ? ' is-done' : row.locked ? ' is-locked' : '');

    const name = document.createElement('div');
    name.className = 'clicker-name';
    name.textContent = row.hiddenName
      ? `${i + 1}. Locked Task`
      : row.completed
        ? `✔ ${i + 1}. ${state.tasks[i]}`
        : `${i + 1}. ${state.tasks[i]}`;
    card.appendChild(name);

    if (!row.completed) {
      const barOuter = document.createElement('div');
      barOuter.className = 'clicker-bar';
      const bar = document.createElement('div');
      bar.className = 'clicker-bar-fill';
      barOuter.appendChild(bar);
      card.appendChild(barOuter);

      const stats = document.createElement('div');
      stats.className = 'clicker-stats';
      const prog = document.createElement('span');
      prog.className = 'clicker-progress';
      const rate = document.createElement('span');
      rate.className = 'clicker-rate';
      // Click power is adjustable per target, so the value of a click belongs
      // on the card rather than only in the header.
      const click = document.createElement('span');
      click.className = 'clicker-click-value';
      stats.appendChild(prog);
      stats.appendChild(rate);
      stats.appendChild(click);
      card.appendChild(stats);

      // What is aimed at this task in particular.
      const detail = document.createElement('div');
      detail.className = 'clicker-detail';
      card.appendChild(detail);

      let btn = null;
      if (row.locked) {
        const why = document.createElement('div');
        why.className = 'clicker-hint';
        why.textContent = `No production while locked. ${row.hiddenName ? '' : row.reasons.join('; ')}`.trim();
        card.appendChild(why);
      } else {
        btn = document.createElement('button');
        btn.className = 'clicker-click-btn';
        btn.textContent = 'Click';
        btn.onclick = () => clickTask(i);
        card.appendChild(btn);
      }
      nodes.set(i, { prog, bar, rate, click, detail, btn, card });
    }
    frag.appendChild(card);
  }
  els.clickerGrid.innerHTML = '';
  els.clickerGrid.appendChild(frag);
}

function updateGrid(rows, m) {
  const dlLocked = isDeathLinkLocked();
  for (const row of rows) {
    const n = nodes.get(row.i);
    if (!n) continue;
    const i = row.i;
    const need = requiredActivations(i);
    const have = taskProgress(i);
    n.prog.textContent = `${fmt(have, 1)} / ${need}`;
    n.bar.style.width = `${Math.min(100, (have / need) * 100)}%`;
    const r = m.rate[i] || 0;
    n.rate.textContent = row.locked ? 'locked' : r > 0 ? `+${fmt(r)}/s` : 'click only';
    n.click.textContent = row.locked ? '' : `click +${fmt(m.taskClickValue[i])}`;

    // Targeted grants: what makes this task different from the rest.
    const aimed = grantsForTask(m, i).filter(g => g.spec && g.spec.kind !== KIND_ALL);
    n.detail.textContent = aimed.length
      ? aimed.map(g => `${g.name} ${grantAmount(g)}`).join(' · ')
      : '';
    n.card.title = cardBreakdown(m, i, row);
    if (n.btn) {
      n.btn.disabled = dlLocked;
      n.btn.textContent = `Click +${fmt(m.taskClickValue[i])}`;
    }
  }
}

/** Every grant in play that reaches task `i`. */
export function grantsForTask(m, i) {
  const region = state.taskRegion[i] || '';
  return m.grants.filter(g => {
    const spec = g.spec;
    if (!spec || spec.kind === KIND_ALL) return true;
    if (spec.kind === KIND_REGION) return spec.ref === region;
    return spec.ref === i;
  });
}

/** How one grant reads on a card: '+0.5/s', '+2/click', 'x1.5'. */
function grantAmount(g) {
  const copies = g.copies > 1 ? ` (x${g.copies})` : '';
  if (g.kind === 'production') return `+${fmt(g.rate)}/s${copies}`;
  if (g.kind === 'click_power') return `+${fmt(g.power)}/click${copies}`;
  if (g.kind === 'click_mult') return `x${fmt(g.mult)} click${copies}`;
  if (g.kind === 'offline_mult') return `x${fmt(g.mult)} offline${copies}`;
  return `x${fmt(g.mult)}${copies}`;
}

/** The full arithmetic behind one card, as its tooltip. */
function cardBreakdown(m, i, row) {
  const lines = [];
  if (row.locked) {
    lines.push('Locked: no production, not clickable.');
  } else {
    const mult = m.prodMult[i];
    lines.push(`Production: ${fmt(m.base[i])} base${mult === 1 ? '' : ` x ${fmt(mult)} multiplier`} = ${fmt(m.rate[i])}/s`);
  }
  lines.push(`Click: (1 + ${fmt(m.taskClickAdd[i])} click power) x ${fmt(m.taskClickMult[i])} click multiplier = ${fmt(m.taskClickValue[i])}`);
  const region = state.taskRegion[i] || '';
  if (region) lines.push(`Region: ${region}`);
  const grants = grantsForTask(m, i);
  if (grants.length) {
    lines.push('Grants reaching this task:');
    for (const g of grants) {
      lines.push(`  ${g.name} ${grantAmount(g)} -> ${targetLabel(g.spec)}`);
    }
  }
  return lines.join('\n');
}

function renderHeader(m) {
  if (!els.clickerHeader) return;
  let total = 0;
  for (const i of m.eligible) total += m.rate[i];

  const lines = [];
  // The total is a sum, so never pair it with a 'base' figure: that sum shrinks
  // as tasks complete and reads as the base rate dropping. Attribute the rates
  // per task instead, grouped by value, since targeted items give tasks
  // different rates and now different click values too.
  const plural = c => `${c} task${c === 1 ? '' : 's'}`;
  lines.push(`${fmt(total)}/s total across ${plural(m.eligible.length)}`);

  const rateGroups = groupBy(m.eligible, i => m.rate[i]).filter(([v]) => v > 0);
  if (rateGroups.length) {
    lines.push('Per task: ' + rateGroups.map(([v, ids]) => {
      const mult = m.prodMult[ids[0]];
      const sameMult = ids.every(i => m.prodMult[i] === mult);
      return sameMult && mult !== 1
        ? `${fmt(v)}/s on ${plural(ids.length)} (${fmt(m.base[ids[0]])} base × ${fmt(mult)})`
        : `${fmt(v)}/s on ${plural(ids.length)}`;
    }).join(', '));
  }

  // Click value is per task now, so show the spread when there is one.
  const clickGroups = groupBy(m.eligible.length ? m.eligible : m.clickerTasks,
    i => m.taskClickValue[i]);
  if (!clickGroups.length) {
    // Nothing to click: no tasks at all.
  } else if (clickGroups.length === 1) {
    const i = clickGroups[0][1][0];
    lines.push(`Click: ${fmt(m.taskClickValue[i])} per click ((1 + ${fmt(m.taskClickAdd[i])} click power) × ${fmt(m.taskClickMult[i])} click multiplier)`);
  } else {
    lines.push('Click: ' + clickGroups
      .map(([v, ids]) => `${fmt(v)} per click on ${plural(ids.length)}`).join(', '));
  }

  if (state.clickerOffline) {
    const away = Math.max(0, evalNum(state.clickerOfflineRate, m.bindings, 1));
    lines.push(`Offline: ×${fmt(away)}, capped at ${state.clickerOfflineCapHours}h`);
  } else {
    lines.push('Offline production is off.');
  }
  lines.push(`N_TASKS ${m.nTasks} · UNLOCKED ${m.nUnlocked} · LOCKED ${m.nLocked} · COMPLETED ${m.nCompleted}`);

  // Every grant in play, by kind, each with the target it is aimed at, so a
  // per-task upgrade is as legible here as a slot-wide one.
  const KIND_TITLES = [
    ['production', 'Production'],
    ['production_mult', 'Production multipliers'],
    ['click_power', 'Click power'],
    ['click_mult', 'Click multipliers'],
    ['offline_mult', 'Offline multipliers'],
  ];
  for (const [kind, title] of KIND_TITLES) {
    const rows = m.grants.filter(g => g.kind === kind);
    if (!rows.length) continue;
    lines.push(`${title}: ` + rows
      .map(g => `${g.name} ${grantAmount(g)} → ${targetLabel(g.spec)}`).join(', '));
  }

  els.clickerHeader.innerHTML = '';
  for (const text of lines) {
    const el = document.createElement('div');
    el.className = 'clicker-header-line';
    el.textContent = text;
    els.clickerHeader.appendChild(el);
  }
}
