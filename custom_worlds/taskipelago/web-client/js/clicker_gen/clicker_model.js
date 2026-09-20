// Tasclickpelago generator logic, mirroring bingo_model.js one-for-one:
// defaults, normalization, live counters, YAML export, a settings document and
// a loader that accepts either the settings file or a clicker_mode YAML.
//
// Unlike bingo there is no randomness here: the author lays out the ladder
// explicitly, so buildClickerExport is a pure function of the model.
import {
  PyError, isDict, pyGet, pyInt, pyListOr, pyStr, pyStrip, pyTruthy,
} from '../shared/pyish.js';
import { extractTaskipelagoBlock, toggleOption } from '../generator/yaml_import.js';
import { limitPlayerName } from '../generator/model.js';
import {
  THEME_COLORS, decodeThemeColors, defaultThemeColors, encodeThemeColors, normalizeStyleColors,
} from '../shared/theme.js';
import { isFillerExact } from '../shared/filler.js';
import { parseNumExpr, numExprBindings, evalNumExpr } from '../shared/num_expr.js';
import { nonEmptyLines } from '../bingo_gen/bingo_model.js';

export { nonEmptyLines };

// 'none' is an item that grants nothing: it exists purely as an AP unlock, to be
// named in a task's item prereqs.
export const UPGRADE_KINDS = ['none', 'production', 'click_power', 'production_mult', 'click_mult', 'offline_mult'];
export const ITEM_TYPES = ['progression', 'useful', 'junk'];

export function defaultTaskRow() {
  return { name: '', activations: '', region: '', prereq: '', itemPrereq: '' };
}

export function defaultRegionRow() {
  return { name: '', color: '', defaultPct: '', distributed: false, offlineRate: '' };
}

export function defaultUpgradeRow() {
  return {
    name: '', type: 'progression', count: 1, group: '',
    kind: 'production', target: '*', value: '',
  };
}

export function defaultClickerModel() {
  return {
    playerName: '', progressionBalancing: 50, accessibility: 'full',
    deathLinkEnabled: false, deathLinkAmnesty: 0, deathLinkLockTasks: false, deathLinkPool: '',
    tasks: [defaultTaskRow()],
    regions: [],
    upgrades: [defaultUpgradeRow()],
    distributeGlobal: false,
    offlineEnabled: true,
    offlineRate: '1',
    offlineCapHours: 8,
    goalTask: 0,            // 1-based task number; 0 = the last task
    styleColors: defaultThemeColors(THEME_COLORS),
  };
}

function normalizeRow(defaults, raw) {
  const row = { ...defaults };
  if (raw && typeof raw === 'object') for (const k of Object.keys(row)) if (raw[k] !== undefined) row[k] = raw[k];
  return row;
}

export function normalizeClickerModel(raw) {
  const model = defaultClickerModel();
  if (raw && typeof raw === 'object') for (const k of Object.keys(model)) if (raw[k] !== undefined) model[k] = raw[k];
  model.tasks = (Array.isArray(model.tasks) ? model.tasks : []).map(r => normalizeRow(defaultTaskRow(), r));
  model.regions = (Array.isArray(model.regions) ? model.regions : []).map(r => normalizeRow(defaultRegionRow(), r));
  model.upgrades = (Array.isArray(model.upgrades) ? model.upgrades : []).map(r => normalizeRow(defaultUpgradeRow(), r));
  if (!model.tasks.length) model.tasks = [defaultTaskRow()];
  if (!model.upgrades.length) model.upgrades = [defaultUpgradeRow()];
  model.styleColors = normalizeStyleColors(model.styleColors, THEME_COLORS);
  return model;
}

export function safeInt(value, fallback) {
  const s = pyStrip(String(value ?? ''));
  if (!s) return fallback;
  const n = Number(s);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

const namedTasks = model => model.tasks.filter(t => pyStrip(t.name));
const namedUpgrades = model => model.upgrades.filter(u => pyStrip(u.name));

/** Total item copies this slot puts in the pool (item_count expands rows). */
export function upgradeCopies(model) {
  return namedUpgrades(model).reduce((n, u) => n + Math.max(1, safeInt(u.count, 1)), 0);
}

/** Live counter labels and the sanity warnings shown under the tables. */
export function clickerCounts(model) {
  const tasks = namedTasks(model);
  const upgrades = namedUpgrades(model);
  const copies = upgradeCopies(model);
  const warnings = [];
  const producing = upgrades.some(u => u.kind === 'production' && pyStrip(u.value));
  const clicking = upgrades.some(u => (u.kind === 'click_power' || u.kind === 'click_mult') && pyStrip(u.value));
  if (tasks.length && !producing && !clicking) {
    warnings.push('No upgrade grants production or click power, so only the base click of 1 moves the game.');
  }
  // The apworld pads or trims the item list to one item per task, because the
  // slot contributes exactly one item per reward location to the multiworld.
  if (copies > tasks.length) {
    warnings.push(`${copies} upgrade copies but only ${tasks.length} task${tasks.length === 1 ? '' : 's'}; `
      + `the last ${copies - tasks.length} will be trimmed. Add tasks or reduce copies.`);
  } else if (tasks.length > copies) {
    warnings.push(`${tasks.length - copies} of ${tasks.length} items will be random filler `
      + `(${copies} upgrade cop${copies === 1 ? 'y' : 'ies'} for ${tasks.length} tasks).`);
  }
  if (!model.offlineEnabled) warnings.push('Offline production is off; the away rate and cap are ignored.');
  else if (safeInt(model.offlineCapHours, 8) === 0) warnings.push('The offline cap is 0 hours, so catch-up never applies.');
  const regionNames = model.regions.map(r => pyStrip(r.name)).filter(Boolean);
  for (const t of tasks) {
    const r = pyStrip(t.region);
    if (r && !regionNames.includes(r)) warnings.push(`Task '${pyStrip(t.name)}' names region '${r}', which is not in the Regions panel.`);
  }
  return {
    tasks: tasks.length,
    upgrades: upgrades.length,
    copies,
    regions: regionNames.length,
    warnings,
  };
}

/**
 * Worked offline example for the panel: "away 8h at 0.25 = 2h of production".
 * Only the static case is shown; an expression is left to the preview cells.
 */
export function offlineExample(model) {
  const cap = safeInt(model.offlineCapHours, 8);
  if (!model.offlineEnabled) return 'Offline production is off.';
  if (cap === 0) return 'The cap is 0 hours, so no catch-up ever applies.';
  const raw = pyStrip(model.offlineRate) || '1';
  const n = Number(raw);
  if (!Number.isFinite(n)) return `Away up to ${cap}h at a rate of ${raw}.`;
  const hours = Math.round(cap * n * 100) / 100;
  return `Away ${cap}h at ${n} = ${hours}h of production.`;
}

/**
 * Evaluate a numeric cell at both ends of the curve, for the preview shown
 * beside each expression input. Returns {ok, low, high} or {ok: false, error}.
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
  const low = evalNumExpr(ast, numExprBindings(nTasks, 0, 0));
  const high = evalNumExpr(ast, numExprBindings(nTasks, nTasks, nTasks));
  return { ok: true, low: round(low), high: round(high) };
}

// =============================================================
// Generator conveniences
// =============================================================

/**
 * Curve fill: the usual geometric idle pacing. First cost, growth factor, and
 * the activations column is filled and stays editable afterwards.
 */
export function curveFill(model, first, growth) {
  const f = Number(first);
  const g = Number(growth);
  if (!Number.isFinite(f) || f < 1) return { error: ['Error', 'The first cost must be a number of at least 1.'] };
  if (!Number.isFinite(g) || g <= 0) return { error: ['Error', 'The growth factor must be a positive number.'] };
  const tasks = model.tasks.map((t, i) => ({
    ...t,
    activations: String(Math.max(1, Math.ceil(f * Math.pow(g, i)))),
  }));
  return { tasks };
}

// =============================================================
// Export
// =============================================================

/**
 * Render a target the way the rest of Taskipelago writes references: a task by
 * quoted name, a region by bare name, or an index / '*' as typed.
 */
function targetToken(target, taskNames) {
  const s = pyStrip(target);
  if (!s || s === '*') return '*';
  if (s.startsWith('"')) return s;                     // already a quoted task
  if (taskNames.includes(s)) return `"${s}"`;
  return s;                                            // a region name or an index
}

export function buildClickerExport(model) {
  const fail = (title, message) => ({ error: [title, message] });
  const playerName = pyStrip(model.playerName);
  if (!playerName) return fail('Error', 'Player name is required.');

  const taskRows = namedTasks(model);
  if (!taskRows.length) return fail('Error', 'Add at least one task.');
  const taskNames = taskRows.map(t => pyStrip(t.name));
  if (new Set(taskNames).size !== taskNames.length) {
    return fail('Error', 'Task names must be unique; the target syntax refers to tasks by name.');
  }

  const upgradeRows = namedUpgrades(model);
  const upgradeNames = upgradeRows.map(u => pyStrip(u.name));
  if (new Set(upgradeNames).size !== upgradeNames.length) {
    return fail('Error', 'Upgrade names must be unique.');
  }
  const regionRows = model.regions.filter(r => pyStrip(r.name));
  const regionNames = regionRows.map(r => pyStrip(r.name));

  // Validate every numeric cell here so the author sees the error before the
  // apworld does, against the same grammar.
  for (const t of taskRows) {
    const v = pyStrip(t.activations);
    if (!v) continue;
    try {
      parseNumExpr(v, { allowLive: false });
    } catch (e) {
      return fail('Error', `Task '${pyStrip(t.name)}' activations: ${e.message}`);
    }
  }
  for (const u of upgradeRows) {
    const v = pyStrip(u.value);
    if (!v) continue;
    try {
      parseNumExpr(v);
    } catch (e) {
      return fail('Error', `Upgrade '${pyStrip(u.name)}': ${e.message}`);
    }
  }
  for (const t of taskRows) {
    const r = pyStrip(t.region);
    if (r && regionNames.length && !regionNames.includes(r)) {
      return fail('Error', `Task '${pyStrip(t.name)}' names region '${r}', which is not in the Regions panel.`);
    }
  }

  // Items are this slot's contribution to the multiworld pool, not per-task
  // rewards: the fill decides which location each one lands on, here or in
  // another world. The apworld pads the list with filler, or trims it, to one
  // item per task, so the Upgrades table stands on its own and every
  // item_-prefixed list below is parallel to it.
  const items = upgradeRows.map(u => pyStrip(u.name));
  const itemTypes = upgradeRows.map(u => (ITEM_TYPES.includes(u.type) ? u.type : 'progression'));
  const itemCount = upgradeRows.map(u => String(Math.max(1, safeInt(u.count, 1))));
  const copies = upgradeRows.reduce((n, u) => n + Math.max(1, safeInt(u.count, 1)), 0);
  const trimmed = Math.max(0, copies - taskRows.length);

  // Catch a target that is neither a task, a region, an index nor '*' here, so
  // the author is not sent to the apworld's error for a typo.
  for (const u of upgradeRows) {
    if (u.kind !== 'production' && u.kind !== 'offline_mult') continue;
    if (!pyStrip(u.value)) continue;
    for (const part of String(u.target ?? '').split('&&')) {
      const t = pyStrip(part);
      if (!t || t === '*' || /^\d+$/.test(t)) continue;
      const name = /^"([^"]*)"$/.test(t) ? t.slice(1, -1) : t;
      if (taskNames.includes(name) || regionNames.includes(name)) continue;
      return fail('Error', `Upgrade '${pyStrip(u.name)}' targets '${t}', which is not a task or a region.`);
    }
  }

  const specCell = (u, kind) => {
    const value = pyStrip(u.value);
    if (u.kind !== kind || !value) return '';
    return `${targetToken(u.target, taskNames)}-${value}`;
  };
  const plainCell = (u, kind) => (u.kind === kind ? pyStrip(u.value) : '');

  const itemGroups = upgradeRows.map(u => pyStrip(u.group));
  const itemProduction = upgradeRows.map(u => specCell(u, 'production'));
  const itemOfflineMult = upgradeRows.map(u => specCell(u, 'offline_mult'));
  const itemClickPower = upgradeRows.map(u => plainCell(u, 'click_power'));
  const itemProductionMult = upgradeRows.map(u => plainCell(u, 'production_mult'));
  const itemClickMult = upgradeRows.map(u => plainCell(u, 'click_mult'));

  const deathLinkPool = nonEmptyLines(model.deathLinkPool);
  if (model.deathLinkEnabled && !deathLinkPool.length) {
    return fail('Error', 'DeathLink is enabled but the pool is empty.\nAdd at least one entry or disable DeathLink.');
  }

  const goalNumber = safeInt(model.goalTask, 0);
  const goalIdx = goalNumber >= 1 && goalNumber <= taskNames.length ? goalNumber : taskNames.length;

  const styleColors = encodeThemeColors(model.styleColors, THEME_COLORS);
  const some = list => list.some(Boolean);

  const data = {
    name: playerName,
    game: 'Taskipelago',
    description: 'Tasclickpelago YAML',
    Taskipelago: {
      progression_balancing: safeInt(model.progressionBalancing, 50),
      accessibility: model.accessibility,
      death_link: model.deathLinkEnabled ? { true: 50, false: 0 } : { true: 0, false: 50 },
      tasks: taskNames,
      items,
      item_types: itemTypes,
      item_count: itemCount,
      task_prereqs: taskRows.map(t => pyStrip(t.prereq)),
      item_prereqs: taskRows.map(t => pyStrip(t.itemPrereq)),
      ...(some(itemGroups) ? { item_progressive_group: itemGroups } : {}),
      lock_prereqs: true,
      hide_unreachable_tasks: true,
      goal_tasks: [String(goalIdx)],
      death_link_pool: deathLinkPool,
      death_link_weights: [],
      death_link_amnesty: safeInt(model.deathLinkAmnesty, 0),
      death_link_lock_tasks: !!model.deathLinkLockTasks,
      ...(regionNames.length ? {
        regions: regionNames,
        region_colors: regionRows.map(r => pyStrip(r.color)),
        region_default_pcts: regionRows.map(r => pyStrip(r.defaultPct)),
        task_region: taskRows.map(t => pyStrip(t.region)),
      } : {}),
      clicker_mode: true,
      task_activations: taskRows.map(t => pyStrip(t.activations)),
      item_production: itemProduction,
      ...(some(itemClickPower) ? { item_click_power: itemClickPower } : {}),
      ...(some(itemProductionMult) ? { item_production_mult: itemProductionMult } : {}),
      ...(some(itemClickMult) ? { item_click_mult: itemClickMult } : {}),
      ...(some(itemOfflineMult) ? { item_offline_mult: itemOfflineMult } : {}),
      ...(regionNames.length ? {
        region_distributed_production: regionRows.map(r => (r.distributed ? 'true' : 'false')),
        region_offline_rate: regionRows.map(r => pyStrip(r.offlineRate)),
      } : {}),
      clicker_distribute_global: !!model.distributeGlobal,
      clicker_offline_progress: !!model.offlineEnabled,
      clicker_offline_rate: [pyStrip(model.offlineRate) || '1'],
      clicker_offline_cap_hours: Math.max(0, Math.min(168, safeInt(model.offlineCapHours, 8))),
      ...(styleColors.length ? { style_colors: styleColors } : {}),
    },
  };
  return { data, trimmed };
}

// =============================================================
// Settings document
// =============================================================

export function clickerSettingsDoc(model) {
  return {
    clicker_tasks: model.tasks.map(t => ({
      name: pyStrip(t.name), activations: pyStrip(t.activations),
      region: pyStrip(t.region), prereq: pyStrip(t.prereq), item_prereq: pyStrip(t.itemPrereq),
    })),
    clicker_regions: model.regions.map(r => ({
      name: pyStrip(r.name), color: pyStrip(r.color), default_pct: pyStrip(r.defaultPct),
      distributed: !!r.distributed, offline_rate: pyStrip(r.offlineRate),
    })),
    clicker_upgrades: model.upgrades.map(u => ({
      name: pyStrip(u.name), type: u.type, count: Math.max(1, safeInt(u.count, 1)),
      group: pyStrip(u.group), kind: u.kind, target: pyStrip(u.target),
      value: pyStrip(u.value),
    })),
    player_name: pyStrip(model.playerName),
    progression_balancing: safeInt(model.progressionBalancing, 50),
    accessibility: model.accessibility,
    death_link_enabled: !!model.deathLinkEnabled,
    death_link_amnesty: safeInt(model.deathLinkAmnesty, 0),
    death_link_lock_tasks: !!model.deathLinkLockTasks,
    death_link_pool: nonEmptyLines(model.deathLinkPool),
    clicker_distribute_global: !!model.distributeGlobal,
    clicker_offline_progress: !!model.offlineEnabled,
    clicker_offline_rate: pyStrip(model.offlineRate) || '1',
    clicker_offline_cap_hours: safeInt(model.offlineCapHours, 8),
    goal_task: safeInt(model.goalTask, 0),
    style_colors: encodeThemeColors(model.styleColors, THEME_COLORS),
  };
}

const intOr = (v, fallback) => pyInt(pyTruthy(v) ? v : fallback);
const linesOf = values => values.map(v => pyStrip(pyStr(v))).filter(Boolean).map(s => `${s}\n`).join('');

function loadCommon(model, doc) {
  const name = pyGet(doc, 'player_name', '');
  if (typeof name === 'string' && pyStrip(name)) model.playerName = limitPlayerName(pyStrip(name));
  try {
    model.progressionBalancing = intOr(pyGet(doc, 'progression_balancing', 50), 50);
    model.deathLinkAmnesty = intOr(pyGet(doc, 'death_link_amnesty', 0), 0);
    model.offlineCapHours = intOr(pyGet(doc, 'clicker_offline_cap_hours', 8), 8);
  } catch (e) {
    if (!(e instanceof PyError)) throw e;
  }
  const acc = pyGet(doc, 'accessibility', 'full');
  if (typeof acc === 'string' && pyStrip(acc)) model.accessibility = pyStrip(acc);
  model.deathLinkLockTasks = toggleOption(pyGet(doc, 'death_link_lock_tasks', false));
  model.deathLinkPool = linesOf(pyListOr(doc, 'death_link_pool'));
  model.distributeGlobal = toggleOption(pyGet(doc, 'clicker_distribute_global', false));
  const off = pyGet(doc, 'clicker_offline_progress', true);
  model.offlineEnabled = off === null || off === undefined ? true : toggleOption(off);
  model.styleColors = normalizeStyleColors(
    decodeThemeColors(pyListOr(doc, 'style_colors').map(pyStr)), THEME_COLORS);
}

function loadSettingsDoc(model, doc) {
  loadCommon(model, doc);
  model.deathLinkEnabled = pyTruthy(pyGet(doc, 'death_link_enabled', false));
  model.offlineRate = pyStrip(pyStr(pyGet(doc, 'clicker_offline_rate', '1'))) || '1';
  model.goalTask = safeInt(pyGet(doc, 'goal_task', 0), 0);
  model.tasks = pyListOr(doc, 'clicker_tasks').map(raw => ({
    name: pyStr(pyGet(raw, 'name', '')),
    activations: pyStr(pyGet(raw, 'activations', '')),
    region: pyStr(pyGet(raw, 'region', '')),
    prereq: pyStr(pyGet(raw, 'prereq', pyGet(raw, 'unlocked_by', ''))),
    itemPrereq: pyStr(pyGet(raw, 'item_prereq', '')),
  }));
  model.regions = pyListOr(doc, 'clicker_regions').map(raw => ({
    name: pyStr(pyGet(raw, 'name', '')),
    color: pyStr(pyGet(raw, 'color', '')),
    defaultPct: pyStr(pyGet(raw, 'default_pct', '')),
    distributed: pyTruthy(pyGet(raw, 'distributed', false)),
    offlineRate: pyStr(pyGet(raw, 'offline_rate', '')),
  }));
  model.upgrades = pyListOr(doc, 'clicker_upgrades').map(raw => ({
    name: pyStr(pyGet(raw, 'name', '')),
    type: pyStr(pyGet(raw, 'type', 'progression')) || 'progression',
    count: safeInt(pyGet(raw, 'count', 1), 1),
    group: pyStr(pyGet(raw, 'group', '')),
    kind: pyStr(pyGet(raw, 'kind', 'production')) || 'production',
    target: pyStr(pyGet(raw, 'target', '*')),
    value: pyStr(pyGet(raw, 'value', '')),
  }));
}

/** Split "<target>-<value>" back into its two halves for the table. */
function splitSpec(text) {
  const s = pyStrip(text);
  if (!s) return { target: '*', value: '' };
  const m = /^\s*("[^"]*"|\d+|\*|[^-]+?)\s*-\s*(.+)$/s.exec(s);
  if (!m) return { target: '*', value: s };
  const raw = pyStrip(m[1]);
  return { target: raw.startsWith('"') ? raw.slice(1, -1) : raw, value: pyStrip(m[2]) };
}

const at = (list, i, fallback = '') => (i < list.length ? pyStrip(pyStr(list[i])) : fallback);

function loadYamlDoc(model, doc) {
  const [playerName, block] = extractTaskipelagoBlock(doc);
  if (!isDict(block)) return ['error', 'Error', 'Could not find a Taskipelago section in this YAML.'];
  if (!pyTruthy(pyGet(block, 'clicker_mode', null))) {
    return ['error', 'Error', 'This YAML does not have clicker_mode enabled.'];
  }
  if (playerName) model.playerName = limitPlayerName(playerName);
  loadCommon(model, block);

  const dl = pyGet(block, 'death_link', null);
  if (isDict(dl)) {
    try {
      const t = intOr(pyGet(dl, 'true', 0), 0);
      const f = intOr(pyGet(dl, 'false', 0), 0);
      model.deathLinkEnabled = t > 0 && t >= f;
    } catch (e) {
      if (!(e instanceof PyError)) throw e;
    }
  } else if (typeof dl === 'boolean' || typeof dl === 'number') {
    model.deathLinkEnabled = pyTruthy(dl);
  }

  const rate = pyListOr(block, 'clicker_offline_rate');
  model.offlineRate = rate.length ? pyStrip(pyStr(rate[0])) || '1' : '1';

  const tasks = pyListOr(block, 'tasks').map(pyStr);
  const activations = pyListOr(block, 'task_activations');
  const regionOf = pyListOr(block, 'task_region');
  const items = pyListOr(block, 'items', pyGet(block, 'rewards', [])).map(pyStr);
  const taskPrereqs = pyListOr(block, 'task_prereqs');
  const taskItemPrereqs = pyListOr(block, 'item_prereqs');
  const itemTypes = pyListOr(block, 'item_types');
  const itemCount = pyListOr(block, 'item_count');
  const itemGroups = pyListOr(block, 'item_progressive_group');
  const production = pyListOr(block, 'item_production');
  const clickPower = pyListOr(block, 'item_click_power');
  const prodMult = pyListOr(block, 'item_production_mult');
  const clickMult = pyListOr(block, 'item_click_mult');
  const offlineMult = pyListOr(block, 'item_offline_mult');

  // Items are a pool contribution, not per-task rewards, so the task rows take
  // nothing from the item lists. Filler entries are the apworld's padding.
  model.tasks = tasks.map((name, i) => ({
    name: pyStrip(name),
    activations: at(activations, i),
    region: at(regionOf, i),
    prereq: at(taskPrereqs, i),
    itemPrereq: at(taskItemPrereqs, i),
  }));

  const regions = pyListOr(block, 'regions').map(pyStr);
  const colors = pyListOr(block, 'region_colors');
  const pcts = pyListOr(block, 'region_default_pcts');
  const dist = pyListOr(block, 'region_distributed_production');
  const offRate = pyListOr(block, 'region_offline_rate');
  model.regions = regions.map((name, i) => ({
    name: pyStrip(name),
    color: at(colors, i),
    defaultPct: at(pcts, i),
    distributed: toggleOption(i < dist.length ? dist[i] : false),
    offlineRate: at(offRate, i),
  }));

  const fillers = pyListOr(block, 'item_fillers');
  model.upgrades = items.map((name, i) => {
    // Padding the apworld added, or filler the author marked: not an upgrade.
    if (pyTruthy(i < fillers.length ? fillers[i] : false) || isFillerExact(pyStrip(name))) return null;
    const row = {
      ...defaultUpgradeRow(),
      name: pyStrip(name),
      type: at(itemTypes, i, 'progression') || 'progression',
      count: Math.max(1, safeInt(at(itemCount, i, '1'), 1)),
      group: at(itemGroups, i),
    };
    const prod = at(production, i);
    const off = at(offlineMult, i);
    if (prod) { const s = splitSpec(prod); row.kind = 'production'; row.target = s.target; row.value = s.value; }
    else if (off) { const s = splitSpec(off); row.kind = 'offline_mult'; row.target = s.target; row.value = s.value; }
    else if (at(clickPower, i)) { row.kind = 'click_power'; row.value = at(clickPower, i); }
    else if (at(prodMult, i)) { row.kind = 'production_mult'; row.value = at(prodMult, i); }
    else if (at(clickMult, i)) { row.kind = 'click_mult'; row.value = at(clickMult, i); }
    else { row.kind = 'none'; }
    return row;
  }).filter(Boolean);

  const goal = pyListOr(block, 'goal_tasks');
  model.goalTask = goal.length ? safeInt(pyStrip(pyStr(goal[0])), 0) : 0;
  return null;
}

/**
 * A settings document (a mapping with "clicker_tasks") or a clicker_mode YAML.
 * Returns { ok, model, messages, kind }; throws PyError where the shared
 * Python-ish helpers do.
 */
export function loadClickerDoc(current, doc) {
  const model = structuredClone(current);
  if (isDict(doc) && Object.hasOwn(doc, 'clicker_tasks')) {
    loadSettingsDoc(model, doc);
    return { ok: true, model: normalizeClickerModel(model), messages: [], kind: 'settings' };
  }
  const error = loadYamlDoc(model, doc);
  if (error) return { ok: false, model: current, messages: [error], kind: 'yaml' };
  return { ok: true, model: normalizeClickerModel(model), messages: [], kind: 'yaml' };
}
