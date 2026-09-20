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
    if (a.unlocked && !a.completed) eligible.push(i);
  }
  const bindings = numExprBindings(n, nUnlocked, nCompleted);
  const counts = itemCopyCounts();

  // Click value: a channel of its own. The production multiplier never touches
  // it, and the click multiplier never touches production.
  let clickAdd = 0;
  let clickMult = 1;
  const clickItems = [];
  for (let k = 0; k < counts.length; k++) {
    if (!counts[k]) continue;
    const p = evalNum(state.itemClickPower[k], bindings, 0);
    if (p > 0) {
      clickAdd += p * counts[k];
      clickItems.push({ name: state.items[k], power: p, copies: counts[k] });
    }
    const raw = state.itemClickMult[k];
    if (raw === null || raw === undefined) continue;
    const m = evalNum(raw, bindings, 1);
    if (m > 0) {
      clickMult *= Math.pow(m, counts[k]);
      clickItems.push({ name: state.items[k], mult: m, copies: counts[k] });
    }
  }
  const clickValue = (1 + clickAdd) * clickMult;
  // CPS is the click value. Binding it here, after the click channel and
  // before production, is what keeps it from being self-referential: the click
  // fields that define it are parsed with CPS rejected.
  bindings.CPS = clickValue;

  // Global production multiplier: every received copy stacks multiplicatively.
  let globalMult = 1;
  const multItems = [];
  for (let k = 0; k < counts.length; k++) {
    if (!counts[k]) continue;
    const raw = state.itemProductionMult[k];
    if (raw === null || raw === undefined) continue;
    const m = evalNum(raw, bindings, 1);
    if (!(m > 0)) continue;
    globalMult *= Math.pow(m, counts[k]);
    multItems.push({ name: state.items[k], mult: m, copies: counts[k] });
  }

  // Base production, from the per-item target specs.
  const base = new Array(n).fill(0);
  const eligSet = new Set(eligible);
  const inRegion = {};
  for (const i of eligible) {
    const r = state.taskRegion[i] || '';
    (inRegion[r] || (inRegion[r] = [])).push(i);
  }
  for (let k = 0; k < counts.length; k++) {
    if (!counts[k]) continue;
    const specs = state.itemProduction[k];
    if (!Array.isArray(specs)) continue;
    for (const spec of specs) {
      const rate = evalNum(spec.rate, bindings, 0) * counts[k];
      if (!(rate > 0)) continue;
      if (spec.kind === 'task') {
        // Locked and completed tasks never receive activations, and the
        // discarded amount is not banked.
        if (eligSet.has(spec.ref)) base[spec.ref] += rate;
      } else if (spec.kind === 'region') {
        const targets = inRegion[spec.ref] || [];
        if (!targets.length) continue;
        const each = state.regionDistributed[spec.ref] ? rate / targets.length : rate;
        for (const i of targets) base[i] += each;
      } else if (spec.kind === 'all') {
        if (!eligible.length) continue;
        const each = state.clickerDistributeGlobal ? rate / eligible.length : rate;
        for (const i of eligible) base[i] += each;
      }
    }
  }

  // Offline multipliers, per task, from item_offline_mult.
  let offlineMult = null;
  if (offline) {
    offlineMult = new Array(n).fill(1);
    for (let k = 0; k < counts.length; k++) {
      if (!counts[k]) continue;
      const specs = state.itemOfflineMult[k];
      if (!Array.isArray(specs)) continue;
      for (const spec of specs) {
        const m = evalNum(spec.rate, bindings, 1);
        if (!(m > 0)) continue;
        const factor = Math.pow(m, counts[k]);
        if (spec.kind === 'task') {
          if (spec.ref >= 0 && spec.ref < n) offlineMult[spec.ref] *= factor;
        } else if (spec.kind === 'region') {
          for (let i = 0; i < n; i++) if ((state.taskRegion[i] || '') === spec.ref) offlineMult[i] *= factor;
        } else {
          for (let i = 0; i < n; i++) offlineMult[i] *= factor;
        }
      }
    }
  }

  const rate = new Array(n).fill(0);
  for (const i of eligible) {
    let r = base[i] * globalMult;
    if (offline) r *= offlineRateFactor(i, bindings) * offlineMult[i];
    rate[i] = r;
  }

  return {
    avail, eligible, bindings, counts, base, rate,
    globalMult, multItems, clickValue, clickAdd, clickMult, clickItems,
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
  state.clickerProgress[i] = Math.min(need, taskProgress(i) + m.clickValue);
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

/**
 * Which tasks are on the board, in order, following the existing
 * hideUnreachable / showLocked / hideCompleted rules rather than bingo's blunt
 * "Locked" cell.
 */
function visibleTasks(m) {
  const effectiveLock = state.lockPrereqs || state.localEnforce;
  const out = [];
  for (let i = 0; i < m.nTasks; i++) {
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
      stats.appendChild(prog);
      stats.appendChild(rate);
      card.appendChild(stats);

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
      nodes.set(i, { prog, bar, rate, btn });
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
    const need = requiredActivations(row.i);
    const have = taskProgress(row.i);
    n.prog.textContent = `${fmt(have, 1)} / ${need}`;
    n.bar.style.width = `${Math.min(100, (have / need) * 100)}%`;
    const r = m.rate[row.i] || 0;
    n.rate.textContent = row.locked ? 'locked' : r > 0 ? `+${fmt(r)}/s` : 'click only';
    if (n.btn) n.btn.disabled = dlLocked;
  }
}

function renderHeader(m) {
  if (!els.clickerHeader) return;
  let total = 0;
  for (const i of m.eligible) total += m.rate[i];

  const lines = [];
  // The total is a sum, so never pair it with a 'base' figure: that sum shrinks
  // as tasks complete and reads as the base rate dropping. Attribute the rates
  // per task instead, grouped by base, since targeted items give tasks
  // different rates.
  const plural = c => `${c} task${c === 1 ? '' : 's'}`;
  lines.push(`${fmt(total)}/s total across ${plural(m.eligible.length)}`);

  const byBase = new Map();
  for (const i of m.eligible) {
    const b = m.base[i];
    if (b > 0) byBase.set(b, (byBase.get(b) || 0) + 1);
  }
  if (byBase.size) {
    const parts = [...byBase].sort((a, b) => b[0] - a[0]).map(([b, c]) => (m.globalMult === 1
      ? `${fmt(b)}/s on ${plural(c)}`
      : `${fmt(b * m.globalMult)}/s on ${plural(c)} (${fmt(b)} base × ${fmt(m.globalMult)})`));
    lines.push('Per task: ' + parts.join(', '));
  }
  lines.push(`Click: ${fmt(m.clickValue)} per click ((1 + ${fmt(m.clickAdd)} click power) × ${fmt(m.clickMult)} click multiplier)`);
  if (state.clickerOffline) {
    const away = Math.max(0, evalNum(state.clickerOfflineRate, m.bindings, 1));
    lines.push(`Offline: ×${fmt(away)}, capped at ${state.clickerOfflineCapHours}h`);
  } else {
    lines.push('Offline production is off.');
  }
  lines.push(`N_TASKS ${m.nTasks} · UNLOCKED ${m.nUnlocked} · LOCKED ${m.nLocked} · COMPLETED ${m.nCompleted}`);
  if (m.multItems.length) {
    lines.push('Production multipliers: ' + m.multItems
      .map(x => `${x.name} ×${fmt(x.mult)}${x.copies > 1 ? ` (${x.copies})` : ''}`).join(', '));
  }
  if (m.clickItems.length) {
    lines.push('Click upgrades: ' + m.clickItems
      .map(x => `${x.name} ${x.mult !== undefined ? `×${fmt(x.mult)}` : `+${fmt(x.power)}`}${x.copies > 1 ? ` (${x.copies})` : ''}`)
      .join(', '));
  }

  els.clickerHeader.innerHTML = '';
  for (const text of lines) {
    const el = document.createElement('div');
    el.className = 'clicker-header-line';
    el.textContent = text;
    els.clickerHeader.appendChild(el);
  }
}
