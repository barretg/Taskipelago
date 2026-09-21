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

/**
 * Kinds whose value is aimed at a target, which is every kind that grants
 * something: click power and both multipliers are adjustable per target too.
 * Only 'none' (unlock only) has nothing to aim.
 */
export const TARGETED_KINDS = new Set([
  'production', 'click_power', 'production_mult', 'click_mult', 'offline_mult',
]);

/**
 * Kinds that were slot-wide before targeting existed, and so still export a
 * bare value when they target '*'. That keeps a generated YAML readable by an
 * older apworld, and is exactly how the Python side reads a bare value back.
 */
export const BARE_STAR_KINDS = new Set(['click_power', 'production_mult', 'click_mult']);

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

/** Positions of `sep` outside quotes and parentheses (parity: clicker.py _top_level). */
function topLevel(text, sep) {
  const out = [];
  let depth = 0;
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') quoted = !quoted;
    else if (!quoted) {
      if (ch === '(') depth++;
      else if (ch === ')') depth = Math.max(0, depth - 1);
      else if (depth === 0 && text.startsWith(sep, i)) {
        out.push(i);
        i += sep.length - 1;
      }
    }
  }
  return out;
}

function splitTop(text, sep) {
  const parts = [];
  let start = 0;
  for (const i of topLevel(text, sep)) {
    parts.push(text.slice(start, i));
    start = i + sep.length;
  }
  parts.push(text.slice(start));
  return parts;
}

/** Drop parentheses that wrap the whole of `text`. */
function stripParens(text) {
  let t = text.trim();
  while (t.startsWith('(')) {
    let depth = 0;
    let quoted = false;
    let close = -1;
    for (let i = 0; i < t.length; i++) {
      const ch = t[i];
      if (ch === '"') quoted = !quoted;
      else if (!quoted && (ch === '(' || ch === ')')) {
        depth += ch === '(' ? 1 : -1;
        if (depth === 0) { close = i; break; }
      }
    }
    if (close !== t.length - 1) break;
    t = t.slice(1, -1).trim();
  }
  return t;
}

/**
 * Flatten a target list ('Kitchen && "Bake Bread"', '( A && B )') into its
 * atoms, honouring quotes and parentheses (parity: clicker.py split_target_list).
 */
export function splitTargetList(text) {
  const t = stripParens(String(text ?? ''));
  const parts = splitTop(t, '&&');
  if (parts.length === 1) return t ? [t] : [];
  return parts.flatMap(splitTargetList);
}

/**
 * Split "<target>-<value>" back into its two halves for the table.
 *
 * A bare name may itself contain '-' ('Up-Stairs-2'), so each top-level '-' is
 * tried and the first whose left side names a known region (or a quoted task,
 * index or '*') wins; otherwise the first '-' is used.
 *
 * `regionNames` also disambiguates the untargeted spelling: without it, the value
 * `N_TASKS - 1` reads as a target called 'N_TASKS'. A bare name that is not a
 * region, in a string that is itself a valid expression, is a value aimed at
 * '*' (parity: clicker.py parse_target_specs bare_ok). `bareOk` turns that off
 * for kinds that always carry a target.
 */
export function splitSpec(text, regionNames = null, bareOk = true) {
  const s = pyStrip(text);
  if (!s) return { target: '*', value: '' };
  const parts = splitTop(s, '&&').map(p => pyStrip(p)).filter(Boolean);
  if (parts.length > 1) {
    // One row holds one value: several parts that share it rejoin as a list.
    const halves = parts.map(p => splitOne(p, regionNames, bareOk));
    if (halves.every(h => h.split && h.value === halves[0].value)) {
      return { target: halves.flatMap(h => h.atoms).join(' && '), value: halves[0].value };
    }
  }
  const one = splitOne(s, regionNames, bareOk);
  if (!one.split) return { target: '*', value: s };
  const target = one.atoms.length === 1 && one.atoms[0].startsWith('"')
    ? one.atoms[0].slice(1, -1) : one.atoms.join(' && ');
  return { target, value: one.value };
}

function splitOne(s, regionNames, bareOk) {
  const known = atoms => atoms.length > 0 && atoms.every(a =>
    a.startsWith('"') || a === '*' || /^\d+$/.test(a) || (regionNames && regionNames.includes(a)));
  const cands = [];
  for (const i of topLevel(s, '-')) {
    const target = pyStrip(s.slice(0, i));
    const value = pyStrip(s.slice(i + 1));
    if (target && value) cands.push({ atoms: splitTargetList(target), value });
  }
  if (!cands.length) return { split: false };
  const pick = cands.find(c => known(c.atoms)) || cands[0];
  if (regionNames && bareOk && !known(pick.atoms) && isNumExpr(s)) return { split: false };
  return { split: true, ...pick };
}

function isNumExpr(text) {
  try {
    parseNumExpr(text);
    return true;
  } catch (_) {
    return false;
  }
}

/**
 * Check one item's target against the task and region names, so a typo is
 * caught here instead of at generation time. `manual` reports whether a task or
 * a region is manual, so a grant cannot be aimed at a non-clicker task, which
 * would silently grant nothing. Returns an error string or null.
 */
export function checkTarget(target, taskNames, regionNames, manual = null) {
  for (const part of splitTargetList(target)) {
    const t = pyStrip(part);
    if (!t || t === '*' || /^\d+$/.test(t)) continue;
    const name = /^"([^"]*)"$/.test(t) ? t.slice(1, -1) : t;
    if (taskNames.includes(name)) {
      if (manual && manual.task(name)) {
        return `targets manual task '${name}', which is an ordinary task and never reads clicker grants`;
      }
      continue;
    }
    if (regionNames.includes(name)) {
      if (manual && manual.region(name)) {
        return `targets region '${name}', in which every task is manual`;
      }
      continue;
    }
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
export function validateClicker(model, {
  taskNames, taskActivations, items, itemSpecs, regionNames,
  taskManual = [], taskRegions = [],
}) {
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
    const why = checkTarget(s.target, taskNames, regionNames, manualLookup(model, {
      taskNames, taskManual, taskRegions,
    }));
    if (why) return ['Error', `Item '${items[i]}' ${why}.`];
  }
  return null;
}

/**
 * Which task and region names are manual, for checkTarget. A task is manual on
 * its own flag or through its region; a region counts as manual only when every
 * task in it is, since a mixed region still has clicker tasks to grant to.
 */
function manualLookup(model, { taskNames, taskManual, taskRegions }) {
  const regionManual = {};
  for (const r of model.regions || []) regionManual[r.name] = !!r.manual;
  const isManual = i => !!taskManual[i] || !!regionManual[taskRegions[i]];
  const byName = {};
  taskNames.forEach((name, i) => { byName[name] = isManual(i); });
  return {
    task: name => !!byName[name],
    region: name => {
      if (regionManual[name]) return true;
      const members = taskNames.filter((_, i) => taskRegions[i] === name);
      return members.length > 0 && members.every(t => byName[t]);
    },
  };
}

/**
 * The clicker-only keys for the Taskipelago block, given the same expanded rows
 * the normal export uses. Returns {} when clicker mode is off.
 */
export function clickerExportKeys(model, {
  taskActivations, taskManual, taskAutoComplete, itemSpecs, taskNames, regionRows,
}) {
  if (!model.clickerMode) return {};
  const some = list => list.some(Boolean);
  const spec = (s, kind) => {
    if (s.kind !== kind || !pyStrip(s.value)) return '';
    const value = pyStrip(s.value);
    if (!TARGETED_KINDS.has(kind)) return value;
    const atoms = splitTargetList(s.target);
    const tokens = (atoms.length ? atoms : ['*']).map(a => targetToken(a, taskNames));
    // A slot-wide grant keeps its old bare spelling.
    if (BARE_STAR_KINDS.has(kind) && tokens.length === 1 && tokens[0] === '*') return value;
    // Several targets share the value as a parenthesized group.
    return tokens.length > 1 ? `(${tokens.join(' && ')})-${value}` : `${tokens[0]}-${value}`;
  };
  const out = {
    clicker_mode: true,
    task_activations: taskActivations.map(v => pyStrip(v)),
  };
  // Only written when something is marked manual, so an ordinary clicker slot
  // exports exactly the keys it did before.
  const manual = (taskManual || []).map(v => (v ? 'true' : 'false'));
  if (manual.some(v => v === 'true')) out.task_manual = manual;
  const auto = (taskAutoComplete || []).map(v => (v ? 'true' : 'false'));
  if (auto.some(v => v === 'true')) out.task_auto_complete = auto;
  for (const [kind, key] of Object.entries(KIND_KEYS)) {
    const list = itemSpecs.map(s => spec(s, kind));
    // item_production is always written so a clicker slot is recognizable.
    if (key === 'item_production' || some(list)) out[key] = list;
  }
  if (regionRows.length) {
    out.region_distributed_production = regionRows.map(r => (r.distributed ? 'true' : 'false'));
    if (regionRows.some(r => r.manual)) {
      out.region_manual = regionRows.map(r => (r.manual ? 'true' : 'false'));
    }
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
  const manual = pyListOr(block, 'task_manual');
  const auto = pyListOr(block, 'task_auto_complete');
  return i => ({
    activations: at(activations, i),
    manual: at(manual, i).toLowerCase() === 'true',
    autoComplete: at(auto, i).toLowerCase() === 'true',
  });
}

/** Per-item clicker fields at flat YAML slot `i`. */
export function clickerItemFields(block) {
  const lists = Object.entries(KIND_KEYS).map(([kind, key]) => [kind, pyListOr(block, key)]);
  const regionNames = pyListOr(block, 'regions').map(v => pyStrip(pyStr(v))).filter(Boolean);
  return i => {
    for (const [kind, list] of lists) {
      const raw = at(list, i);
      if (!raw) continue;
      if (!TARGETED_KINDS.has(kind)) return { clickerKind: kind, clickerTarget: '*', clickerValue: raw };
      // The three formerly slot-wide kinds may carry a bare value.
      const { target, value } = splitSpec(raw, regionNames, BARE_STAR_KINDS.has(kind));
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
  const manual = pyListOr(block, 'region_manual');
  model.regions.forEach((r, i) => {
    r.distributed = at(dist, i).toLowerCase() === 'true';
    r.offlineRate = at(offRate, i);
    r.manual = at(manual, i).toLowerCase() === 'true';
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
