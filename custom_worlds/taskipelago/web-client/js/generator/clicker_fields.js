// Clicker mode (Tasclickpelago) as an overlay on the normal generator model.
//
// Clicker mode does not fork the editor: a clicker slot is an ordinary
// Taskipelago YAML with `clicker_mode: true` plus the extra lists below, so
// every existing panel (regions, item groups, DeathLink, randomization, style)
// keeps working unchanged. This module owns the parts the rest of the generator
// does not know about: the '<target>-<value>' spec grammar, which is kept in
// parity with clicker.py, and the numeric-expression preview.
import { pyGet, pyInt, pyListOr, pyStr, pyStrip } from '../shared/pyish.js';
import { evalNumExpr, numExprBindings, numExprConstants, parseNumExpr } from '../shared/num_expr.js';
import { UPGRADE_KINDS } from './model.js';

export { UPGRADE_KINDS };

export const KIND_LABELS = {
  none: 'Unlock only (no effect)',
  production: 'Production (/s)',
  click_power: 'Click power (+)',
  production_mult: 'Production multiplier (x)',
  click_mult: 'Click multiplier (x)',
  offline_mult: 'Offline multiplier (x)',
};

/** Kinds whose value may not reference CPS, because CPS is what they define. */
export const CLICK_KINDS = new Set(['click_power', 'click_mult']);

/** Kinds whose value is aimed at a target; the rest are global to the slot. */
export const TARGETED_KINDS = new Set(['production', 'offline_mult']);

/** The YAML key each kind writes into, parallel to `items`. */
const KIND_KEYS = {
  production: 'item_production',
  click_power: 'item_click_power',
  production_mult: 'item_production_mult',
  click_mult: 'item_click_mult',
  offline_mult: 'item_offline_mult',
};

export const OFFLINE_CAP_MAX = 168;

function safeInt(value, fallback) {
  const s = pyStrip(String(value ?? ''));
  if (!s) return fallback;
  const n = Number(s);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

// ---------------------------------------------------------------------------
// Target grammar (parity: clicker.py parse_target_specs)
// ---------------------------------------------------------------------------

/**
 * Render a target the way the rest of Taskipelago writes references: a task by
 * quoted name, a region by bare name, an index or '*' as typed.
 */
export function targetToken(target, taskNames) {
  const s = pyStrip(target);
  if (!s || s === '*') return '*';
  if (s.startsWith('"')) return s;
  if (taskNames.includes(s)) return `"${s}"`;
  return s;
}

/** Split "<target>-<value>" back into its two halves for the table. */
export function splitSpec(text) {
  const s = pyStrip(text);
  if (!s) return { target: '*', value: '' };
  const m = /^\s*("[^"]*"|\d+|\*|[^-]+?)\s*-\s*(.+)$/s.exec(s);
  if (!m) return { target: '*', value: s };
  const raw = pyStrip(m[1]);
  return { target: raw.startsWith('"') ? raw.slice(1, -1) : raw, value: pyStrip(m[2]) };
}

/**
 * Check one item's target against the task and region names, so a typo is
 * caught here instead of at generation time. Returns an error string or null.
 */
export function checkTarget(target, taskNames, regionNames) {
  for (const part of String(target ?? '').split('&&')) {
    const t = pyStrip(part);
    if (!t || t === '*' || /^\d+$/.test(t)) continue;
    const name = /^"([^"]*)"$/.test(t) ? t.slice(1, -1) : t;
    if (taskNames.includes(name) || regionNames.includes(name)) continue;
    return `targets '${t}', which is not a task or a region`;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Numeric cells
// ---------------------------------------------------------------------------

/**
 * Evaluate a numeric cell at both ends of the curve, for the preview beside
 * each expression input. Returns {ok, low, high} or {ok: false, error}.
 */
export function previewValue(text, nTasks) {
  const s = pyStrip(text);
  if (!s) return { ok: true, blank: true };
  let ast;
  try {
    ast = parseNumExpr(s);
  } catch (e) {
    return { ok: false, error: e.message };
  }
  const round = v => (Number.isFinite(v) ? Math.round(v * 1000) / 1000 : NaN);
  return {
    ok: true,
    low: round(evalNumExpr(ast, numExprBindings(nTasks, 0, 0))),
    high: round(evalNumExpr(ast, numExprBindings(nTasks, nTasks, nTasks))),
  };
}

/**
 * Curve fill: the usual geometric idle pacing. Writes the activations column
 * from a first cost and a growth factor; it stays editable afterwards.
 */
export function curveFill(tasks, first, growth) {
  const f = Number(first);
  const g = Number(growth);
  if (!Number.isFinite(f) || f < 1) return { error: ['Error', 'The first cost must be a number of at least 1.'] };
  if (!Number.isFinite(g) || g <= 0) return { error: ['Error', 'The growth factor must be a positive number.'] };
  return { tasks: tasks.map((t, i) => ({ ...t, activations: String(Math.max(1, Math.ceil(f * Math.pow(g, i)))) })) };
}

/** Worked offline example for the panel. */
export function offlineExample(model) {
  const cap = safeInt(model.clickerOfflineCapHours, 8);
  if (!model.clickerOffline) return 'Offline production is off.';
  if (cap === 0) return 'The cap is 0 hours, so no catch-up ever applies.';
  const raw = pyStrip(model.clickerOfflineRate) || '1';
  const n = Number(raw);
  if (!Number.isFinite(n)) return `Away up to ${cap}h at a rate of ${raw}.`;
  return `Away ${cap}h at ${n} = ${Math.round(cap * n * 100) / 100}h of production.`;
}

// ---------------------------------------------------------------------------
// Validation, export and import
// ---------------------------------------------------------------------------

/**
 * Validate the clicker-only cells. `tasks` and `items` are the exported rows
 * (already filtered and expanded by the caller). Returns an error pair or null.
 */
export function validateClicker(model, { taskNames, taskActivations, items, itemSpecs, regionNames }) {
  if (!model.clickerMode) return null;
  for (let i = 0; i < taskActivations.length; i++) {
    const v = pyStrip(taskActivations[i]);
    if (!v) continue;
    try {
      parseNumExpr(v, { allowLive: false });
    } catch (e) {
      return ['Error', `Task '${taskNames[i]}' activations: ${e.message}`];
    }
  }
  for (let i = 0; i < itemSpecs.length; i++) {
    const s = itemSpecs[i];
    if (s.kind === 'none' || !pyStrip(s.value)) continue;
    let ast;
    try {
      ast = parseNumExpr(pyStrip(s.value));
    } catch (e) {
      return ['Error', `Item '${items[i]}': ${e.message}`];
    }
    if (CLICK_KINDS.has(s.kind) && numExprConstants(ast).has('CPS')) {
      return ['Error', `Item '${items[i]}': 'CPS' is the click value and cannot be used in a click field.`];
    }
    if (!TARGETED_KINDS.has(s.kind)) continue;
    const why = checkTarget(s.target, taskNames, regionNames);
    if (why) return ['Error', `Item '${items[i]}' ${why}.`];
  }
  return null;
}

/**
 * The clicker-only keys for the Taskipelago block, given the same expanded rows
 * the normal export uses. Returns {} when clicker mode is off.
 */
export function clickerExportKeys(model, { taskActivations, itemSpecs, taskNames, regionRows }) {
  if (!model.clickerMode) return {};
  const some = list => list.some(Boolean);
  const spec = (s, kind) => {
    if (s.kind !== kind || !pyStrip(s.value)) return '';
    const value = pyStrip(s.value);
    return TARGETED_KINDS.has(kind) ? `${targetToken(s.target, taskNames)}-${value}` : value;
  };
  const out = {
    clicker_mode: true,
    task_activations: taskActivations.map(v => pyStrip(v)),
  };
  for (const [kind, key] of Object.entries(KIND_KEYS)) {
    const list = itemSpecs.map(s => spec(s, kind));
    // item_production is always written so a clicker slot is recognizable.
    if (key === 'item_production' || some(list)) out[key] = list;
  }
  if (regionRows.length) {
    out.region_distributed_production = regionRows.map(r => (r.distributed ? 'true' : 'false'));
    out.region_offline_rate = regionRows.map(r => pyStrip(r.offlineRate));
  }
  out.clicker_distribute_global = !!model.clickerDistributeGlobal;
  out.clicker_offline_progress = !!model.clickerOffline;
  out.clicker_offline_rate = [pyStrip(model.clickerOfflineRate) || '1'];
  out.clicker_offline_cap_hours = Math.max(0, Math.min(OFFLINE_CAP_MAX, safeInt(model.clickerOfflineCapHours, 8)));
  return out;
}

const at = (list, i) => (i < list.length ? pyStrip(pyStr(list[i])) : '');

/**
 * Per-task clicker fields at flat YAML slot `i`, to merge into the row the
 * importer is building. Absent keys simply yield the defaults.
 */
export function clickerTaskFields(block) {
  const activations = pyListOr(block, 'task_activations');
  return i => ({ activations: at(activations, i) });
}

/** Per-item clicker fields at flat YAML slot `i`. */
export function clickerItemFields(block) {
  const lists = Object.entries(KIND_KEYS).map(([kind, key]) => [kind, pyListOr(block, key)]);
  return i => {
    for (const [kind, list] of lists) {
      const raw = at(list, i);
      if (!raw) continue;
      if (!TARGETED_KINDS.has(kind)) return { clickerKind: kind, clickerTarget: '*', clickerValue: raw };
      const { target, value } = splitSpec(raw);
      return { clickerKind: kind, clickerTarget: target, clickerValue: value };
    }
    return { clickerKind: 'none', clickerTarget: '*', clickerValue: '' };
  };
}

/**
 * Slot-level and per-region clicker settings. Safe for any YAML: without
 * `clicker_mode` it only fills in the region columns, which stay at their
 * defaults when the keys are absent.
 */
export function clickerImportSettings(model, block) {
  const dist = pyListOr(block, 'region_distributed_production');
  const offRate = pyListOr(block, 'region_offline_rate');
  model.regions.forEach((r, i) => {
    r.distributed = at(dist, i).toLowerCase() === 'true';
    r.offlineRate = at(offRate, i);
  });

  if (!toggle(pyGet(block, 'clicker_mode', false))) return;
  model.clickerMode = true;
  model.clickerDistributeGlobal = toggle(pyGet(block, 'clicker_distribute_global', false));
  model.clickerOffline = toggle(pyGet(block, 'clicker_offline_progress', true));
  model.clickerOfflineRate = at(pyListOr(block, 'clicker_offline_rate'), 0) || '1';
  let cap = 8;
  try {
    cap = pyInt(pyGet(block, 'clicker_offline_cap_hours', 8));
  } catch (_) { /* keep the default */ }
  model.clickerOfflineCapHours = Math.max(0, Math.min(OFFLINE_CAP_MAX, cap));
}

/** AP toggle options arrive as booleans, 'true'/'false' or 1/0. */
function toggle(value) {
  if (typeof value === 'boolean') return value;
  return ['true', 'on', 'yes', '1'].includes(pyStrip(pyStr(value)).toLowerCase());
}
