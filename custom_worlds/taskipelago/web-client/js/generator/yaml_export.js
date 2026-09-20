// Port of export_yaml (legacy_client/client.py:2947-3292), UNIFY 5.3.
// Every validation, its order and its message text match the legacy client;
// tests/parity/export_golden.json holds the reference results.
import { parsePrereq, parseCostExpr, mapScopedText, validateRefName } from '../shared/prereq_parser.js';
import { randomFiller as defaultRandomFiller } from '../shared/filler.js';
import { remapPrereqIndices, remapCostIndices } from '../shared/expr_rewrite.js';
import { pyInt, pySlice, pyStrip } from '../shared/pyish.js';
import { dumpYaml } from '../shared/yaml11.js';
import { encodeThemeColors } from '../shared/theme.js';
import {
  MAX_TASK_DESCRIPTION_LEN, isReservedWord, taskData, itemData,
} from './model.js';
import { clickerExportKeys, validateClicker } from './clicker_fields.js';
import { checkRandomization, groupSetting, regionRandom, usesRandomization } from './randomize_check.js';

/** _resolve_name_refs: "Quoted Name" -> first matching 1-based index. */
export function resolveNameRefs(text, names) {
  const errors = [];
  const result = text.replace(/"([^"]*)"/g, (whole, name) => {
    const i = names.indexOf(name);
    if (i >= 0) return String(i + 1);
    errors.push(`No entry found named "${name}"`);
    return whole;
  });
  return [result, errors];
}

/** _convert_cost_idx_to_quote: idx*N -> "Name"*N so costs survive row expansion. */
export function convertCostIdxToQuote(costText, itemNames) {
  return costText.replace(/"[^"]*"\*?\d*|\b(\d+)(?:\*(\d+))?\b/g, (whole, idxText, count) => {
    if (idxText === undefined) return whole;
    const idx = Number(idxText);
    if (idx >= 1 && idx <= itemNames.length && itemNames[idx - 1]) {
      return `"${itemNames[idx - 1]}"*${count || '1'}`;
    }
    return whole;
  });
}

/** [idx, y] for every INDEX*Y node in a prereq AST. */
function itemCopyRefs(node) {
  if (!Array.isArray(node)) return [];
  if (node[0] === 'item_copies') return [[node[1], node[2]]];
  if (node[0] === 'and' || node[0] === 'or') return node[1].flatMap(itemCopyRefs);
  return [];
}

function duplicates(names) {
  const seen = new Map();
  for (const n of names) seen.set(n, (seen.get(n) || 0) + 1);
  return [...seen].filter(([, c]) => c > 1).map(([n]) => n);
}

/**
 * Build the export document from the editor model.
 *   confirm(title, message) -> Promise<boolean>  (unbalanced-count prompt)
 * Resolves to { data } on success, { error: [title, message] } on a validation
 * failure, or { cancelled: true } when the confirm is declined.
 */
export async function buildExport(model, { confirm, randomFiller = defaultRandomFiller } = {}) {
  const fail = (title, message) => ({ error: [title, message] });

  const playerName = pyStrip(model.playerName);
  if (!playerName) return fail('Error', 'Player name is required.');

  const tasks = [];
  const taskPrereqs = [];
  let itemPrereqsRaw = [];
  let taskCosts = [];
  const taskRegions = [];
  const taskPriorities = [];
  const taskCounts = [];
  const taskDescriptions = [];
  const taskActivations = [];
  const taskManual = [];
  for (const row of model.tasks) {
    const t = taskData(row);
    if (!t.name) continue;
    tasks.push(t.name);
    taskPrereqs.push(t.prereq);
    itemPrereqsRaw.push(t.itemPrereq);
    taskCosts.push(t.cost);
    taskRegions.push(t.region);
    taskPriorities.push(t.priority);
    taskCounts.push(t.count);
    taskDescriptions.push(pySlice(t.desc, MAX_TASK_DESCRIPTION_LEN));
    taskActivations.push(t.activations);
    taskManual.push(t.manual);
  }
  if (!tasks.length) return fail('Error', 'No tasks defined.');

  const dupTasks = duplicates(tasks);
  if (dupTasks.length) {
    return fail('Duplicate Task Names',
      'Duplicate task names are not allowed - use the Count field for multiple copies:\n' + dupTasks.join('\n'));
  }

  const rawItemNames = [];
  const itemRows = []; // per editor row, for randomization checks
  const rawItemConsumables = [];
  const rawItemCounts = [];
  // itemRowExportIdxs[row] = 1-based indices the editor row occupies in the exported list.
  const itemRowExportIdxs = [];
  const items = [];
  const itemTypes = [];
  const itemFillers = [];
  const itemProgGroups = [];
  const itemConsumables = [];
  const itemCounts = [];
  // Parallel to `items`, so an expanded filler row repeats its (empty) spec.
  const itemSpecs = [];
  const specOf = it => ({ kind: it.clickerKind, target: it.clickerTarget, value: it.clickerValue });
  const noSpec = { kind: 'none', target: '*', value: '' };
  for (const row of model.items) {
    const it = itemData(row);
    rawItemNames.push(it.name);
    rawItemCounts.push(it.count);
    itemRows.push({ name: it.name, count: it.count, group: it.progGroup, filler: it.filler || !it.name });
    const isFillerRow = it.filler || !it.name;
    rawItemConsumables.push(isFillerRow ? false : it.consumable);
    const start = items.length + 1;
    if (isFillerRow && it.count > 1) {
      for (let k = 0; k < it.count; k++) {
        items.push(randomFiller());
        itemTypes.push('junk');
        itemFillers.push(true);
        itemProgGroups.push('');
        itemConsumables.push(false);
        itemCounts.push(1);
        itemSpecs.push(noSpec);
      }
    } else {
      items.push(isFillerRow ? randomFiller() : it.name);
      itemTypes.push(isFillerRow ? 'junk' : (it.type || 'junk'));
      itemFillers.push(isFillerRow);
      itemProgGroups.push(isFillerRow ? '' : it.progGroup);
      itemConsumables.push(isFillerRow ? false : it.consumable);
      itemCounts.push(it.count);
      itemSpecs.push(isFillerRow ? noSpec : specOf(it));
    }
    const idxs = [];
    for (let k = start; k <= items.length; k++) idxs.push(k);
    itemRowExportIdxs.push(idxs);
  }

  const dupItems = duplicates(items.filter((name, i) => !itemFillers[i] && name));
  if (dupItems.length) {
    return fail('Duplicate Item Names',
      'Duplicate item names are not allowed - use the Count field for multiple copies:\n' + dupItems.join('\n'));
  }

  const regionNames = model.regions.map(r => r.name);
  // Region fields come from name-keyed dicts in the legacy client: duplicates share the last entry.
  const regionByName = new Map(model.regions.map(r => [r.name, r]));
  // v1.1 F8: unified name rule; reserved words keep their own message below.
  const badNames = names => names.filter(n => !isReservedWord(n) && validateRefName(n))
    .map(n => `${n} (${validateRefName(n)})`);
  const badRegions = badNames(regionNames);
  if (badRegions.length) {
    return fail('Invalid Region Names',
      'The following region names are invalid and cannot be exported:\n\n' + badRegions.join('\n'));
  }
  const reservedRegions = regionNames.filter(isReservedWord);
  if (reservedRegions.length) {
    return fail('Invalid Region Names',
      'The following region names are reserved words and cannot be exported:\n\n' + reservedRegions.join('\n'));
  }
  const badGroups = badNames(model.progGroups);
  if (badGroups.length) {
    return fail('Invalid Progressive Group Names',
      'The following progressive group names are invalid and cannot be exported:\n\n' + badGroups.join('\n'));
  }
  const reservedGroups = model.progGroups.filter(isReservedWord);
  if (reservedGroups.length) {
    return fail('Invalid Progressive Group Names',
      'The following progressive group names are reserved words and cannot be exported:\n\n'
      + reservedGroups.join('\n'));
  }

  // Subregions: parents must exist, nesting is one level, randomized regions are never parents.
  const parentErrors = [];
  const usesParents = model.regions.some(r => r.parent);
  for (const r of model.regions) {
    if (!r.parent) continue;
    const p = regionByName.get(r.parent);
    if (!p) parentErrors.push(`${r.name}: parent region '${r.parent}' does not exist.`);
    else if (p.name === r.name) parentErrors.push(`${r.name}: a region cannot be its own parent.`);
    else if (p.parent) {
      parentErrors.push(`${r.name}: parent '${p.name}' is itself a subregion; nesting is one level deep.`);
    } else if (regionRandom(model, p.name).on) {
      parentErrors.push(`${r.name}: parent '${p.name}' is randomized; randomized regions cannot be parents.`);
    }
  }
  if (parentErrors.length) {
    return fail('Invalid Subregions',
      'The following region parent settings must be fixed before exporting:\n\n' + parentErrors.join('\n'));
  }

  let totalTaskSlots = taskCounts.reduce((a, b) => a + b, 0);
  let totalItemSlots = itemCounts.reduce((a, b) => a + b, 0);
  const randomized = usesRandomization(model);
  let regionPrereqs = regionNames.map(n => regionByName.get(n).prereq ?? '');
  const randomCheck = () => checkRandomization({
    model, tasks, taskCounts, taskRegions, regionNames, regionPrereqs, itemRows,
    taskPrereqs: taskPrereqs.map(t => resolveNameRefs(t, tasks)[0]),
    itemPrereqs: itemPrereqsRaw.map(t => resolveNameRefs(t, rawItemNames)[0]),
    goal: pyStrip(model.goalTasks),
  });
  if (randomized.regions || randomized.groups) {
    // Balance against the final per-seed counts after random selection.
    const { finalTasks, finalItems } = randomCheck();
    totalTaskSlots = finalTasks;
    totalItemSlots = finalItems;
  }
  if (totalTaskSlots !== totalItemSlots) {
    const proceed = await confirm('Unbalanced Counts',
      'Warning: Unbalanced item and task slot counts will cause generation failures.\n\n'
      + `Task slots: ${totalTaskSlots}  |  Item slots: ${totalItemSlots}\n\nExport anyway?`);
    if (!proceed) return { cancelled: true };
  }

  const quoteErrors = [];
  tasks.forEach((t, i) => { if (t.includes('"')) quoteErrors.push(`Task ${i + 1} name contains a quotation mark.`); });
  rawItemNames.forEach((n, i) => { if (n && n.includes('"')) quoteErrors.push(`Item ${i + 1} name contains a quotation mark.`); });
  if (quoteErrors.length) return fail('Invalid Names', quoteErrors.join('\n'));

  const nameErrors = [];
  taskPrereqs.forEach((tpr, i) => {
    nameErrors.push(...resolveNameRefs(tpr, tasks)[1].map(e => `Task ${i + 1} task prereqs: ${e}`));
  });
  itemPrereqsRaw.forEach((ipr, i) => {
    nameErrors.push(...resolveNameRefs(ipr, rawItemNames)[1].map(e => `Task ${i + 1} item prereqs: ${e}`));
  });
  // Quoted names inside a region's task(...) / item(...) scopes.
  regionNames.forEach(name => {
    mapScopedText(regionByName.get(name).prereq,
      t => { nameErrors.push(...resolveNameRefs(t, tasks)[1].map(e => `Region '${name}' depends on: ${e}`)); return t; },
      t => { nameErrors.push(...resolveNameRefs(t, rawItemNames)[1].map(e => `Region '${name}' depends on: ${e}`)); return t; });
  });
  if (nameErrors.length) return fail('Unresolved Names', 'Unresolved name references:\n\n' + nameErrors.join('\n'));

  taskCosts = taskCosts.map(c => convertCostIdxToQuote(c, rawItemNames));

  const deathLinkPool = [];
  const deathLinkWeights = [];
  for (const row of model.deathLink) {
    const text = pyStrip(row.text);
    const weight = pyStrip(row.weight);
    if (!text) continue;
    deathLinkPool.push(text);
    deathLinkWeights.push(weight || '1');
  }
  const dlOn = !!model.deathLinkEnabled;
  if (dlOn && !deathLinkPool.length) {
    return fail('Error',
      'DeathLink is enabled, but the DeathLink Task Pool is empty.\n'
      + 'Add at least one DeathLink task or disable DeathLink.');
  }

  const goalTasksRaw = pyStrip(model.goalTasks);

  const regionSet = new Set(regionNames);
  const groupSet = new Set(model.progGroups);
  const consumableSet = new Set(rawItemNames.filter((n, i) => rawItemConsumables[i] && n));
  const nTasks = tasks.length;
  const nItems = rawItemNames.length;
  const exprErrors = [];
  const attempt = (fn, prefix = '') => {
    try {
      fn();
    } catch (e) {
      exprErrors.push(prefix + e.message);
    }
  };
  taskPrereqs.forEach((tpr, i) => {
    if (!tpr) return;
    const [resolved] = resolveNameRefs(tpr, tasks);
    attempt(() => parsePrereq(resolved, nTasks, i, 'task prereq', groupSet, regionSet));
  });
  itemPrereqsRaw.forEach((ipr, i) => {
    if (!ipr) return;
    const [resolved] = resolveNameRefs(ipr, rawItemNames);
    attempt(() => {
      for (const [idx, y] of itemCopyRefs(parsePrereq(resolved, nItems, i, 'item prereq', groupSet))) {
        if (y > rawItemCounts[idx]) {
          throw new Error(`Taskipelago: '${idx + 1}*${y}' in item prereq on task ${i + 1} asks for ${y} copies `
            + `but item ${idx + 1} has a count of ${rawItemCounts[idx]}.`);
        }
      }
    });
  });
  taskCosts.forEach((cost, i) => {
    if (cost) attempt(() => parseCostExpr(cost, consumableSet, rawItemNames), `Task ${i + 1} cost: `);
  });
  if (goalTasksRaw) {
    const [resolvedGoal, goalNameErrors] = resolveNameRefs(goalTasksRaw, tasks);
    if (goalNameErrors.length) exprErrors.push('Goal tasks: ' + goalNameErrors.join('; '));
    else attempt(() => parsePrereq(resolvedGoal, nTasks, 0, 'goal tasks', null, regionSet), 'Goal tasks: ');
  }
  // A region "Depends on" may wrap an ordinary task or item expression in
  // task(...) / item(...); each scope validates in its own index space.
  const regionScopes = {
    task: { n: nTasks, groups: null, regions: regionSet, const: nTasks, label: 'region task prereq' },
    item: { n: nItems, groups: groupSet, regions: null, const: nTasks, label: 'region item prereq' },
  };
  for (const name of regionNames) {
    const rpr = regionByName.get(name).prereq;
    if (!rpr) continue;
    const resolved = mapScopedText(rpr,
      t => resolveNameRefs(t, tasks)[0], t => resolveNameRefs(t, rawItemNames)[0]);
    attempt(() => parsePrereq(
      resolved, 0, 0, 'region prereq', null, regionSet, `region '${name}'`, nTasks, regionScopes));
  }
  if (exprErrors.length) {
    return fail('Invalid Expressions',
      'The following expressions could not be parsed and must be fixed before exporting:\n\n' + exprErrors.join('\n'));
  }
  if (randomized.regions || randomized.groups) {
    const { errors } = randomCheck();
    if (errors.length) {
      return fail('Invalid Randomization',
        'The following randomized region or item group settings must be fixed before exporting:\n\n'
        + errors.join('\n'));
    }
  }

  if (itemRowExportIdxs.some((idxs, i) => idxs.length !== 1 || idxs[0] !== i + 1)) {
    itemPrereqsRaw = itemPrereqsRaw.map(t => remapPrereqIndices(t, itemRowExportIdxs));
    taskCosts = taskCosts.map(t => remapCostIndices(t, itemRowExportIdxs));
    // Only the item(...) scope of a region "Depends on" holds item indices.
    regionPrereqs = regionPrereqs.map(t =>
      mapScopedText(t, null, inner => remapPrereqIndices(inner, itemRowExportIdxs)));
  }

  const clickerError = validateClicker(model, {
    taskNames: tasks, taskActivations, items, itemSpecs, regionNames,
    taskManual, taskRegions,
  });
  if (clickerError) return { error: clickerError };

  const styleColors = encodeThemeColors(model.styleColors);

  const data = {
    name: playerName,
    game: 'Taskipelago',
    description: 'YAML template for Taskipelago',
    Taskipelago: {
      progression_balancing: pyInt(model.progressionBalancing),
      accessibility: model.accessibility,
      death_link: { true: dlOn ? 50 : 0, false: dlOn ? 0 : 50 },

      progressive_groups: [...model.progGroups],
      progressive_group_colors: model.progGroups.map(g => ( // v1.1 F6
        model.progGroupColors && Object.hasOwn(model.progGroupColors, g) ? model.progGroupColors[g] : '')),
      item_progressive_group: itemProgGroups,
      // Emitted only when used, so older exports and older apworlds are unaffected.
      ...(randomized.groups ? {
        group_types: model.progGroups.map(g => groupSetting(model, g).type),
        group_random_pick: model.progGroups.map(g => {
          const s = groupSetting(model, g);
          return s.type === 'random-choice' ? s.pick : '';
        }),
        group_default_pcts: model.progGroups.map(g => groupSetting(model, g).pct),
      } : {}),

      regions: regionNames,
      region_default_pcts: regionNames.map(n => regionByName.get(n).pct ?? 100),
      region_colors: regionNames.map(n => regionByName.get(n).color ?? ''),
      region_prereqs: regionPrereqs,
      // Emitted only when subregions are used, so older apworlds are unaffected.
      ...(usesParents ? { region_parent: regionNames.map(n => regionByName.get(n).parent ?? '') } : {}),
      ...(randomized.regions ? {
        region_random_pick: regionNames.map(n => {
          const rr = regionRandom(model, n);
          return rr.on ? rr.pick : '';
        }),
        region_random_order: regionNames.map(n => {
          const rr = regionRandom(model, n);
          return rr.on && rr.order ? 'true' : 'false';
        }),
      } : {}),
      task_region: taskRegions,
      task_priority: taskPriorities.map(p => (p ? 'true' : 'false')),

      tasks,
      task_count: taskCounts.map(String),
      task_description: taskDescriptions,
      items,
      item_types: itemTypes,
      item_fillers: itemFillers,
      item_consumable: itemConsumables.map(c => (c ? 'true' : 'false')),
      item_count: itemCounts.map(String),
      task_prereqs: taskPrereqs,
      item_prereqs: itemPrereqsRaw,
      task_cost: taskCosts,
      lock_prereqs: !!model.lockPrereqs,
      hide_unreachable_tasks: !!model.hideUnreachable,
      task_reward_previews: model.taskRewardPreviews,
      goal_tasks: goalTasksRaw ? [goalTasksRaw] : [],

      death_link_pool: deathLinkPool,
      death_link_weights: deathLinkWeights,
      death_link_amnesty: pyInt(model.deathLinkAmnesty),
      death_link_lock_tasks: !!model.deathLinkLockTasks, // v1.1 F3
      // v1.1 F7: only non-default colors, so an all-default Style section adds nothing.
      ...clickerExportKeys(model, {
        taskActivations, taskManual, itemSpecs, taskNames: tasks,
        regionRows: regionNames.map(n => regionByName.get(n)),
      }),
      ...(styleColors.length ? { style_colors: styleColors } : {}),
    },
  };
  return { data };
}

export const exportText = data => dumpYaml(data);
