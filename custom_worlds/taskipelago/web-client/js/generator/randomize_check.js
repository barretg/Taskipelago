// Randomized regions and item group types: export-time validation mirroring the
// apworld's generation step 5b (randomize.py), plus the resolved final counts.
import { parsePrereq } from '../shared/prereq_parser.js';

export const GROUP_TYPES = ['progressive', 'random-choice', 'aesthetic'];

export function normalizeGroupType(t) {
  const v = String(t || '').trim().toLowerCase();
  return GROUP_TYPES.includes(v) ? v : 'progressive';
}

/** Settings for a group with defaults applied: { type, pick, pct }. */
export function groupSetting(model, name) {
  const s = (model.groupSettings && model.groupSettings[name]) || {};
  return { type: normalizeGroupType(s.type), pick: String(s.pick ?? '').trim(), pct: String(s.pct ?? '').trim() };
}

/** Randomize state for a region: { on, pick, order }. */
export function regionRandom(model, name) {
  const s = (model.regionRandom && model.regionRandom[name]) || {};
  return { on: !!s.on, pick: String(s.pick ?? '').trim(), order: !!s.order };
}

/** True when any region or group setting differs from the defaults (new YAML keys needed). */
export function usesRandomization(model) {
  const regions = (model.regions || []).some(r => regionRandom(model, r.name).on);
  const groups = (model.progGroups || []).some(g => {
    const s = groupSetting(model, g);
    return s.type !== 'progressive' || s.pct !== '';
  });
  return { regions, groups };
}

/** 'N' or 'N%' -> { value, pct }; '' -> null. Throws with a user-facing message. */
export function parsePick(text, label) {
  const t = String(text || '').trim();
  if (!t) return null;
  const m = /^(\d+)(%?)$/.exec(t);
  if (!m) throw new Error(`${label} pick '${t}' is invalid. Use a positive whole number N or N%.`);
  const value = Number(m[1]);
  const pct = m[2] === '%';
  if (value < 1) throw new Error(`${label} pick '${t}' must be at least 1.`);
  if (pct && value > 100) throw new Error(`${label} pick '${t}' must be at most 100%.`);
  return { value, pct };
}

/** Resolved keep count; percent rounds up with a minimum of 1. Throws when above count. */
export function resolvePick(pick, count, label) {
  const n = pick.pct ? Math.max(1, Math.ceil(count * pick.value / 100)) : pick.value;
  if (n > count) throw new Error(`${label} keeps ${n} but only has ${count} candidate(s).`);
  return n;
}

/**
 * Final per-seed task and item counts after random selection, for balance warnings.
 * taskRows: [{ count, region }], itemRows: [{ count, group, filler }]. Invalid picks count as keep-all.
 */
export function finalCounts(model, taskRows, itemRows) {
  const keep = (text, count) => {
    try {
      const pick = parsePick(text, '');
      return pick ? Math.min(resolvePick(pick, count, ''), count) : count;
    } catch (_) { return count; }
  };
  let tasks = taskRows.reduce((a, t) => a + t.count, 0);
  for (const name of model.regions.map(r => r.name)) {
    const rr = regionRandom(model, name);
    if (!rr.on) continue;
    const count = taskRows.reduce((a, t) => a + (t.region === name ? t.count : 0), 0);
    tasks -= count - keep(rr.pick, count);
  }
  let items = itemRows.reduce((a, r) => a + r.count, 0);
  for (const g of model.progGroups) {
    const s = groupSetting(model, g);
    if (s.type !== 'random-choice' || !s.pick) continue;
    const count = itemRows.reduce((a, r) => a + (!r.filler && r.group === g ? r.count : 0), 0);
    items -= count - keep(s.pick, count);
  }
  return { tasks, items };
}

const WALK_PARENTS = ['and', 'or', 'scoped_task', 'scoped_item'];

function walk(node, fn) {
  if (node === null || node === undefined) return;
  fn(node);
  if (Array.isArray(node) && WALK_PARENTS.includes(node[0])) node[1].forEach(c => walk(c, fn));
}

/** Int leaves of one scope only: 'task' keeps task(...), 'item' keeps item(...). */
export function scopedLeaves(node, domain) {
  if (node === null || node === undefined) return [];
  if (typeof node === 'number') return [];
  const op = node[0];
  if (op === 'scoped_task' || op === 'scoped_item') {
    return op === `scoped_${domain}` ? leaves(node[1][0]) : [];
  }
  if (op === 'and' || op === 'or') return node[1].flatMap(c => scopedLeaves(c, domain));
  return [];
}

export function leaves(node) {
  const out = [];
  walk(node, n => { if (typeof n === 'number') out.push(n); });
  return out;
}

const nodesOf = (node, ops) => {
  const out = [];
  walk(node, n => { if (Array.isArray(n) && ops.includes(n[0])) out.push(n); });
  return out;
};

/** Minimal satisfying sets of task leaves (DNF); region refs pin nothing. */
export function goalMinimalSets(node, cap = 4096) {
  const dnf = n => {
    if (n === null || n === undefined) return [[]];
    if (typeof n === 'number') return [[n]];
    if (n[0] === 'or') return n[1].flatMap(dnf);
    if (n[0] === 'and') {
      let acc = [[]];
      for (const c of n[1]) {
        const child = dnf(c);
        const next = new Map();
        for (const a of acc) {
          for (const b of child) {
            const s = [...new Set([...a, ...b])].sort((x, y) => x - y);
            next.set(s.join(','), s);
          }
        }
        acc = [...next.values()];
        if (acc.length > cap) throw new Error('Goal tasks expression is too complex to guarantee with randomized regions.');
      }
      return acc;
    }
    return [[]];
  };
  const sets = dnf(node).sort((a, b) => a.length - b.length);
  const minimal = [];
  for (const s of sets) if (!minimal.some(m => m.every(x => s.includes(x)))) minimal.push(s);
  return minimal;
}

/**
 * Validate randomization settings against the exported rows.
 *   tasks, taskCounts, taskRegions, taskPrereqs (quoted names resolved), goal (raw text)
 *   itemRows: [{ name, count, group, filler }] per editor item row
 *   itemPrereqs (quoted names resolved), regionNames, regionPrereqs, model
 * Returns { errors, finalTasks, finalItems }.
 */
export function checkRandomization(o) {
  const errors = [];
  const { model } = o;
  const regionSet = new Set(o.regionNames);
  const groupSet = new Set(model.progGroups);
  const tryIt = (prefix, fn) => {
    try { fn(); } catch (e) { errors.push(prefix + e.message.replace(/^Taskipelago: /, '')); }
  };

  // Region picks
  const regionKeep = new Map();
  let finalTasks = o.taskCounts.reduce((a, b) => a + b, 0);
  for (const name of o.regionNames) {
    const rr = regionRandom(model, name);
    if (!rr.on) continue;
    const count = o.tasks.reduce((a, _t, i) => a + (o.taskRegions[i] === name ? o.taskCounts[i] : 0), 0);
    tryIt('', () => {
      const pick = parsePick(rr.pick, `Region '${name}'`);
      if (!pick) throw new Error(`Region '${name}' is randomized but has no pick. Enter N or N%.`);
      const n = resolvePick(pick, count, `Region '${name}'`);
      regionKeep.set(name, n);
      finalTasks -= count - n;
    });
  }
  const randomOf = i => (regionKeep.has(o.taskRegions[i]) ? o.taskRegions[i] : '');

  // Task prereqs: no individual refs into randomized regions, no sequential there, no self region refs.
  o.taskPrereqs.forEach((text, i) => {
    if (!text) return;
    let ast;
    try { ast = parsePrereq(text, o.tasks.length, i, 'task prereq', null, regionSet); } catch (_) { return; }
    if (randomOf(i) && nodesOf(ast, ['seq_flag']).length) {
      errors.push(`Task ${i + 1} uses 'sequential' inside randomized region '${randomOf(i)}'.`);
    }
    for (const leaf of leaves(ast)) {
      if (randomOf(leaf)) {
        errors.push(`Task ${i + 1} references task ${leaf + 1} inside randomized region '${randomOf(leaf)}'. `
          + 'Reference the region as a whole instead.');
      }
    }
    for (const [, name] of nodesOf(ast, ['region_ref', 'region_abs'])) {
      if (name === o.taskRegions[i]) errors.push(`Task ${i + 1} cannot depend on its own region '${name}'.`);
    }
    for (const [, name, k] of nodesOf(ast, ['region_abs'])) {
      if (regionKeep.has(name) && k > regionKeep.get(name)) {
        errors.push(`Task ${i + 1} uses '${name}*${k}' but randomized region '${name}' keeps ${regionKeep.get(name)}.`);
      }
    }
  });
  const nItemRows = o.itemRows.length;
  const regionScopes = {
    task: { n: o.tasks.length, groups: null, regions: regionSet,
            const: o.tasks.length, label: 'region task prereq' },
    item: { n: nItemRows, groups: groupSet, regions: null,
            const: o.tasks.length, label: 'region item prereq' },
  };
  o.regionNames.forEach((name, ri) => {
    const text = o.regionPrereqs[ri];
    if (!text) return;
    let ast;
    try {
      ast = parsePrereq(text, 0, 0, 'region prereq', null, regionSet,
        `region '${name}'`, o.tasks.length, regionScopes);
    } catch (_) { return; }
    for (const [, dep, k] of nodesOf(ast, ['region_abs'])) {
      if (regionKeep.has(dep) && k > regionKeep.get(dep)) {
        errors.push(`Region '${name}' uses '${dep}*${k}' but randomized region '${dep}' keeps ${regionKeep.get(dep)}.`);
      }
    }
    // task(...) must not single out a task that randomization may drop.
    for (const leaf of scopedLeaves(ast, 'task')) {
      if (randomOf(leaf)) {
        errors.push(`Region '${name}' depends on task ${leaf + 1} inside randomized region `
          + `'${randomOf(leaf)}'. Reference the region as a whole instead.`);
      }
    }
  });

  // Goal guarantee. Goal indices are per task copy, as in generation.
  if (o.goal && regionKeep.size) {
    const yamlNames = [];
    const yamlRegion = [];
    o.tasks.forEach((t, i) => {
      for (let c = 0; c < o.taskCounts[i]; c++) { yamlNames.push(t); yamlRegion.push(o.taskRegions[i]); }
    });
    const resolved = o.goal.replace(/"([^"]*)"/g, (whole, name) => {
      const k = yamlNames.indexOf(name);
      return k >= 0 ? String(k + 1) : whole;
    });
    tryIt('Goal tasks: ', () => {
      const ast = parsePrereq(resolved, yamlNames.length, 0, 'goal tasks', null, regionSet);
      for (const [, name, k] of nodesOf(ast, ['region_abs'])) {
        if (regionKeep.has(name) && k > regionKeep.get(name)) {
          throw new Error(`'${name}*${k}' but randomized region '${name}' keeps ${regionKeep.get(name)}.`);
        }
      }
      const feasible = goalMinimalSets(ast).some(s => [...regionKeep].every(
        ([r, n]) => s.filter(t => yamlRegion[t] === r).length <= n));
      if (!feasible) {
        throw new Error('cannot be satisfied: every way to meet the goal needs more tasks from a randomized '
          + 'region than it keeps.');
      }
    });
  }

  // Item groups
  let finalItems = o.itemRows.reduce((a, r) => a + r.count, 0);
  const groupSize = new Map();
  for (const g of model.progGroups) {
    const s = groupSetting(model, g);
    const count = o.itemRows.reduce((a, r) => a + (!r.filler && r.group === g ? r.count : 0), 0);
    groupSize.set(g, count);
    if (s.pct !== '') {
      const v = /^\d+$/.test(s.pct) ? Number(s.pct) : NaN;
      if (!(v >= 0 && v <= 100)) errors.push(`Group '${g}' default % must be a whole number from 0 to 100.`);
    }
    if (s.type === 'random-choice' && s.pick) {
      tryIt('', () => {
        const n = resolvePick(parsePick(s.pick, `Group '${g}'`), count, `Group '${g}'`);
        groupSize.set(g, n);
        finalItems -= count - n;
      });
    }
  }
  o.itemPrereqs.forEach((text, i) => {
    if (!text) return;
    let ast;
    try { ast = parsePrereq(text, o.itemRows.length, i, 'item prereq', groupSet); } catch (_) { return; }
    const refs = [...leaves(ast), ...nodesOf(ast, ['item_copies']).map(n => n[1])];
    for (const leaf of refs) {
      const row = o.itemRows[leaf];
      if (row && !row.filler && row.group && groupSetting(model, row.group).type === 'random-choice') {
        errors.push(`Task ${i + 1} item prereq references item ${leaf + 1} inside random-choice group `
          + `'${row.group}'. Reference the group instead.`);
      }
    }
    for (const [op, g, n] of nodesOf(ast, ['group_ref', 'group_count'])) {
      const s = groupSetting(model, g);
      if (s.type === 'progressive') continue;
      if (op === 'group_count' && n > (groupSize.get(g) || 0)) {
        errors.push(`Task ${i + 1} uses '${g}*${n}' but group '${g}' keeps ${groupSize.get(g) || 0} item(s).`);
      }
      if (op === 'group_ref' && n !== null && n > 100) {
        errors.push(`Task ${i + 1} uses '${g}-${n}' but the percentage must be 0-100.`);
      }
    }
  });

  // Region item(...) scopes, once the per-group keep counts are known.
  o.regionNames.forEach((name, ri) => {
    const text = o.regionPrereqs[ri];
    if (!text) return;
    let ast;
    try {
      ast = parsePrereq(text, 0, 0, 'region prereq', null, regionSet,
        `region '${name}'`, o.tasks.length, regionScopes);
    } catch (_) { return; }
    for (const leaf of scopedLeaves(ast, 'item')) {
      const row = o.itemRows[leaf];
      if (row && !row.filler && row.group && groupSetting(model, row.group).type === 'random-choice') {
        errors.push(`Region '${name}' depends on item ${leaf + 1} inside random-choice group `
          + `'${row.group}'. Reference the group instead.`);
      }
    }
    for (const [op, g, k] of nodesOf(ast, ['group_ref', 'group_count'])) {
      if (op === 'group_ref') continue; // rejected at generation; count mode only
      if (groupSetting(model, g).type === 'progressive') continue;
      if (k > (groupSize.get(g) || 0)) {
        errors.push(`Region '${name}' uses '${g}*${k}' but group '${g}' keeps ${groupSize.get(g) || 0} item(s).`);
      }
    }
  });

  return { errors, finalTasks, finalItems };
}
