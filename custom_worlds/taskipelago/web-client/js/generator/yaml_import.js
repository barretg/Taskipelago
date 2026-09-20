// Port of _extract_taskipelago_block and _populate_from_taskipelago_doc
// (legacy_client/client.py:2919-2945, 3309-3630), UNIFY 5.3.
//
// Documents come from shared/yaml11.js so values have PyYAML types, and every
// str()/int()/bool()/list() the legacy client applied is reproduced with
// shared/pyish.js. That keeps every YAML exported by any released version
// (tests/parity/yaml_corpus/) importing exactly as it did in the Tk client.
import { isFillerExact, randomFiller as defaultRandomFiller } from '../shared/filler.js';
import { collapseCopyGroups, remapPrereqIndices, remapCostIndices } from '../shared/expr_rewrite.js';
import { mapScopedText } from '../shared/prereq_parser.js';
import {
  PyError, isDict, pyGet, pyInt, pyList, pyListOr, pyStr, pyStrip, pyTruthy,
} from '../shared/pyish.js';
import { decodeThemeColors, normalizeStyleColors } from '../shared/theme.js';
import {
  REGION_COLOR_PALETTE, REWARD_TYPE_VALUES, limitPlayerName,
  newItem, newTask, newDeathLink, normalizeRegionParents, onFillerToggle, onConsumableToggle,
  setItemProgGroup,
} from './model.js';
import { clickerImportSettings, clickerItemFields, clickerTaskFields } from './clicker_fields.js';
import { finalCounts, normalizeGroupType } from './randomize_check.js';

export const NO_BLOCK_MESSAGE = "Could not find a 'Taskipelago' section in this YAML.\n"
  + 'Expected either:\n'
  + '  - root: { name: ..., Taskipelago: {...} }\n'
  + '  - or a player entry: { <player>: { Taskipelago: {...} } }';

/** Returns [playerName | null, block | null]. */
export function extractTaskipelagoBlock(doc) {
  if (!isDict(doc)) return [null, null];
  if (isDict(pyGet(doc, 'Taskipelago'))) {
    const name = pyGet(doc, 'name');
    return [typeof name === 'string' ? pyStrip(name) : null, doc.Taskipelago];
  }
  for (const [k, v] of Object.entries(doc)) {
    if (isDict(v) && isDict(pyGet(v, 'Taskipelago'))) return [k, v.Taskipelago];
  }
  return [null, null];
}

/** try: body except (the named Python exception types): fallback */
function attempt(body, fallback, catches = null) {
  try {
    return body();
  } catch (e) {
    if (!(e instanceof PyError)) throw e;
    if (catches && !catches.includes(e.pyType)) throw e;
    return fallback;
  }
}

const VALUE_OR_TYPE = ['ValueError', 'TypeError'];

/**
 * An AP Toggle value as written by hand or by the generator: bool, number,
 * "true"/"on"/"yes"/"1", or a weights dict ({true: 50, false: 0}). v1.1 F3.
 */
export function toggleOption(v) {
  if (isDict(v)) {
    return attempt(() => {
      const t = pyInt(pyTruthy(pyGet(v, 'true', 0)) ? pyGet(v, 'true', 0) : 0);
      const f = pyInt(pyTruthy(pyGet(v, 'false', 0)) ? pyGet(v, 'false', 0) : 0);
      return t > 0 && t >= f;
    }, false);
  }
  if (typeof v === 'string') return ['true', 'on', 'yes', '1'].includes(pyStrip(v).toLowerCase());
  return pyTruthy(v);
}
const str = (v, fallback = '') => (v === null || v === undefined ? fallback : pyStrip(pyStr(v)));
const at = (list, i, fn, fallback = '') => (i < list.length ? fn(list[i]) : fallback);
const isTrueText = v => str(v).toLowerCase() === 'true';

/**
 * Apply a parsed YAML document to a copy of the editor model.
 * Returns { ok, model, messages }, messages being [kind, title, text] with kind
 * 'error' or 'warning'. Throws PyError where the legacy client raised.
 */
export function importDoc(current, doc, { randomFiller = defaultRandomFiller } = {}) {
  const model = structuredClone(current);
  const messages = [];
  const [playerName, block] = extractTaskipelagoBlock(doc);
  if (!isDict(block)) {
    messages.push(['error', 'Error', NO_BLOCK_MESSAGE]);
    return { ok: false, model, messages };
  }

  // --------- Global settings ---------
  if (playerName) model.playerName = limitPlayerName(playerName);

  attempt(() => {
    model.progressionBalancing = pyInt(pyGet(block, 'progression_balancing', pyInt(model.progressionBalancing)));
  });

  const acc = pyGet(block, 'accessibility', model.accessibility);
  if (typeof acc === 'string' && pyStrip(acc)) model.accessibility = pyStrip(acc);

  const dl = pyGet(block, 'death_link', null);
  let enabled = !!model.deathLinkEnabled;
  if (isDict(dl)) {
    attempt(() => {
      const t = pyInt(pyTruthy(pyGet(dl, 'true', 0)) ? pyGet(dl, 'true', 0) : 0);
      const f = pyInt(pyTruthy(pyGet(dl, 'false', 0)) ? pyGet(dl, 'false', 0) : 0);
      enabled = t > 0 && t >= f;
    });
  } else if (typeof dl === 'boolean' || typeof dl === 'number') {
    enabled = pyTruthy(dl);
  }
  model.deathLinkEnabled = enabled;

  attempt(() => {
    const v = pyGet(block, 'death_link_amnesty', pyInt(model.deathLinkAmnesty));
    model.deathLinkAmnesty = pyInt(pyTruthy(v) ? v : 0);
  });

  // v1.1 F7: style colors; keys the export omitted fall back to their defaults.
  model.styleColors = normalizeStyleColors(decodeThemeColors(pyListOr(block, 'style_colors').map(pyStr)));

  model.lockPrereqs = pyTruthy(pyGet(block, 'lock_prereqs', !!model.lockPrereqs));
  model.hideUnreachable = pyTruthy(pyGet(block, 'hide_unreachable_tasks', !!model.hideUnreachable));

  let trp = attempt(() => {
    const v = pyGet(block, 'task_reward_previews', 0);
    return pyInt(pyTruthy(v) ? v : 0);
  }, 0, VALUE_OR_TYPE);
  if (![0, 1, 2].includes(trp)) trp = 0;
  model.taskRewardPreviews = trp;

  model.goalTasks = pyListOr(block, 'goal_tasks').map(pyStr).join(', ');

  // --------- Progressive groups and regions (before rows) ---------
  model.progGroups = pyListOr(block, 'progressive_groups').map(g => pyStrip(pyStr(g))).filter(Boolean);
  // v1.1 F6: colors parallel to the groups, with the region palette-by-index fallback.
  const rawGroupColors = pyListOr(block, 'progressive_group_colors');
  model.progGroupColors = Object.fromEntries(model.progGroups.map((g, i) => {
    const color = i < rawGroupColors.length ? pyStrip(pyStr(rawGroupColors[i])) : '';
    return [g, color || REGION_COLOR_PALETTE[i % REGION_COLOR_PALETTE.length]];
  }));
  model.deathLinkLockTasks = toggleOption(pyGet(block, 'death_link_lock_tasks', false)); // v1.1 F3

  const rawRegions = pyListOr(block, 'regions');
  const rawPcts = pyListOr(block, 'region_default_pcts');
  const rawColors = pyListOr(block, 'region_colors');
  const rawRegionPrereqs = pyListOr(block, 'region_prereqs');
  const rawRegionParents = pyListOr(block, 'region_parent');
  const regionNames = rawRegions.map(r => pyStrip(pyStr(r))).filter(Boolean);
  const regionInfo = new Map();
  regionNames.forEach((name, i) => {
    const pct = attempt(() => (i < rawPcts.length ? pyInt(rawPcts[i]) : 100), 100, VALUE_OR_TYPE);
    const color = i < rawColors.length ? pyStrip(pyStr(rawColors[i])) : '';
    regionInfo.set(name, {
      pct,
      color: color || REGION_COLOR_PALETTE[i % REGION_COLOR_PALETTE.length],
      prereq: i < rawRegionPrereqs.length ? pyStrip(pyStr(rawRegionPrereqs[i])) : '',
      parent: i < rawRegionParents.length ? pyStrip(pyStr(rawRegionParents[i])) : '',
    });
  });
  model.regions = regionNames.map(name => ({ name, ...regionInfo.get(name) }));
  model.nextColorIdx = regionNames.length;

  // Randomized regions and item group types (optional parallel lists; absent = defaults).
  const rawRegionPicks = pyListOr(block, 'region_random_pick');
  const rawRegionOrders = pyListOr(block, 'region_random_order');
  model.regionRandom = {};
  regionNames.forEach((name, i) => {
    const pick = i < rawRegionPicks.length ? pyStrip(pyStr(rawRegionPicks[i])) : '';
    const order = i < rawRegionOrders.length
      && pyStrip(pyStr(rawRegionOrders[i])).toLowerCase() === 'true';
    if (pick) model.regionRandom[name] = { on: true, pick, order };
  });
  // Drops parent links a hand-written YAML got wrong (missing, nested or randomized).
  normalizeRegionParents(model);
  const rawTypes = pyListOr(block, 'group_types');
  const rawGroupPicks = pyListOr(block, 'group_random_pick');
  const rawGroupPcts = pyListOr(block, 'group_default_pcts');
  model.groupSettings = {};
  model.progGroups.forEach((g, i) => {
    const at = list => (i < list.length ? pyStrip(pyStr(list[i])) : '');
    const s = { type: normalizeGroupType(at(rawTypes)), pick: at(rawGroupPicks), pct: at(rawGroupPcts) };
    if (s.type !== 'progressive' || s.pick || s.pct) model.groupSettings[g] = s;
  });

  // --------- Tasks ---------
  const tasksRaw = pyListOr(block, 'tasks');
  const prereqsRaw = pyListOr(block, 'task_prereqs');
  const taskRegionsRaw = pyListOr(block, 'task_region');
  const taskPriorityRaw = pyListOr(block, 'task_priority');
  const taskCostsRaw = pyListOr(block, 'task_cost');
  const taskDescRaw = pyListOr(block, 'task_description');
  const itemPrereqsSource = pyGet(block, 'item_prereqs', pyGet(block, 'reward_prereqs', []));
  const itemPrereqsRaw = pyTruthy(itemPrereqsSource) ? pyList(itemPrereqsSource) : [];
  const taskCountRaw = pyGet(block, 'task_count', null);

  const tasks = [];
  const clickerTaskAt = clickerTaskFields(block);
  const taskFields = i => ({
    prereq: at(prereqsRaw, i, str),
    region: at(taskRegionsRaw, i, str),
    priority: at(taskPriorityRaw, i, isTrueText, false),
    cost: at(taskCostsRaw, i, str),
    desc: at(taskDescRaw, i, str),
    itemPrereq: at(itemPrereqsRaw, i, str),
    ...clickerTaskAt(i),
  });
  if (taskCountRaw !== null) {
    const counts = Array.isArray(taskCountRaw) ? taskCountRaw : [taskCountRaw];
    tasksRaw.forEach((t, i) => {
      const count = attempt(() => (i < counts.length ? Math.max(1, pyInt(counts[i])) : 1), 1, VALUE_OR_TYPE);
      tasks.push({ name: str(t), count, ...taskFields(i) });
    });
  } else {
    // Crunch consecutive identical task names into single rows with a count.
    let i = 0;
    while (i < tasksRaw.length) {
      const name = str(tasksRaw[i]);
      let j = i + 1;
      while (j < tasksRaw.length && str(tasksRaw[j]) === name) j++;
      tasks.push({ name, count: j - i, ...taskFields(i) });
      i = j;
    }
  }

  // --------- Items (new and legacy key names) ---------
  const itemsRaw = pyListOr(block, 'items', pyGet(block, 'rewards', []));
  const typesRaw = pyListOr(block, 'item_types', pyGet(block, 'reward_types', []));
  const fillersRaw = pyListOr(block, 'item_fillers');
  const groupsRaw = pyListOr(block, 'item_progressive_group', pyGet(block, 'reward_progressive_group', []));
  const consumableRaw = pyListOr(block, 'item_consumable');
  const itemCountRaw = pyGet(block, 'item_count', null);

  const items = [];
  const clickerItemAt = clickerItemFields(block);
  let flatToRow;
  const typeAt = i => at(typesRaw, i, v => str(v, 'useful'), 'useful');
  const fillerAt = i => (i < fillersRaw.length ? fillersRaw[i] : null);
  const groupAt = i => at(groupsRaw, i, str);
  const consumableAt = i => at(consumableRaw, i, isTrueText, false);

  if (itemCountRaw !== null) {
    const counts = Array.isArray(itemCountRaw) ? itemCountRaw : [itemCountRaw];
    const names = itemsRaw.map(v => str(v));
    const countAt = i => attempt(() => (i < counts.length ? Math.max(1, pyInt(counts[i])) : 1), 1, VALUE_OR_TYPE);
    const flatCounts = names.map((_, i) => countAt(i));
    const isFlatFiller = i => fillerAt(i) === true || (fillerAt(i) === null && isFillerExact(names[i]));
    // Collapse consecutive filler entries (from an expanded export) into one row.
    flatToRow = names.map(() => []);
    let i = 0;
    while (i < names.length) {
      if (isFlatFiller(i)) {
        let total = flatCounts[i];
        let j = i + 1;
        while (j < names.length && isFlatFiller(j)) total += flatCounts[j++];
        items.push({
          name: names[i], type: typeAt(i), filler: true, group: '', consumable: false, count: total,
          ...clickerItemAt(i),
        });
        for (let k = i; k < j; k++) flatToRow[k] = [items.length];
        i = j;
      } else {
        items.push({
          name: names[i], type: typeAt(i), filler: fillerAt(i), group: groupAt(i),
          consumable: consumableAt(i), count: flatCounts[i], ...clickerItemAt(i),
        });
        flatToRow[i] = [items.length];
        i++;
      }
    }
  } else {
    // Crunch consecutive identical item names.
    flatToRow = itemsRaw.map(() => []);
    let i = 0;
    while (i < itemsRaw.length) {
      const name = str(itemsRaw[i]);
      let j = i + 1;
      while (j < itemsRaw.length && str(itemsRaw[j]) === name) j++;
      for (let k = i; k < j; k++) flatToRow[k] = [items.length + 1];
      items.push({
        name, type: typeAt(i), filler: fillerAt(i), group: groupAt(i),
        consumable: consumableAt(i), count: j - i, ...clickerItemAt(i),
      });
      i = j;
    }
  }

  // Numeric item references are one per exported row; shift them onto collapsed rows.
  if (flatToRow.some((rows, k) => rows.length !== 1 || rows[0] !== k + 1)) {
    for (const t of tasks) {
      t.itemPrereq = remapPrereqIndices(collapseCopyGroups(t.itemPrereq, flatToRow), flatToRow);
      t.cost = remapCostIndices(t.cost, flatToRow);
    }
    // A region "Depends on" carries item indices only inside its item(...) scope.
    for (const r of model.regions) {
      r.prereq = mapScopedText(r.prereq, null,
        t => remapPrereqIndices(collapseCopyGroups(t, flatToRow), flatToRow));
    }
  }

  // Randomized regions and random-choice groups balance on the final per-seed counts.
  const { tasks: totalTaskSlots, items: totalItemSlots } = finalCounts(model, tasks, items);
  if (totalTaskSlots !== totalItemSlots) {
    messages.push(['warning', 'Unbalanced Counts',
      'Unbalanced item and task counts can lead to generation failures.\n\n'
      + `Task slots: ${totalTaskSlots}  |  Item slots: ${totalItemSlots}`]);
  }

  // --------- Rows ---------
  const regionSet = new Set(regionNames);
  model.tasks = tasks.map(t => ({
    ...newTask(),
    name: t.name, prereq: t.prereq, itemPrereq: t.itemPrereq, cost: t.cost,
    priority: !!t.priority, count: t.count, desc: t.desc,
    region: regionSet.has(t.region) ? t.region : '',
    activations: t.activations, manual: !!t.manual,
  }));

  model.items = items.map(src => {
    const it = newItem();
    const type = REWARD_TYPE_VALUES.includes(src.type) ? src.type : 'useful';
    it.type = type;
    it.ui.savedType = type;
    it.count = src.count;
    it.clickerKind = src.clickerKind;
    it.clickerTarget = src.clickerTarget;
    it.clickerValue = src.clickerValue;
    const isFiller = typeof src.filler === 'boolean' ? src.filler : isFillerExact(src.name);
    if (isFiller) {
      it.filler = true;
      onFillerToggle(it, randomFiller, model);
    } else {
      it.name = src.name;
      if (src.consumable) {
        it.consumable = true;
        onConsumableToggle(it, model);
      } else if (model.progGroups.includes(src.group)) {
        setItemProgGroup(it, src.group, model);
      }
    }
    return it;
  });

  // --------- DeathLink pool ---------
  const pool = pyListOr(block, 'death_link_pool');
  let weights = pyListOr(block, 'death_link_weights');
  if (weights.length < pool.length) weights = weights.concat(Array(pool.length - weights.length).fill('1'));
  weights = weights.slice(0, pool.length);
  model.deathLink = [];
  pool.forEach((txt, i) => {
    const text = str(txt);
    if (!text) return;
    const w = weights[i];
    model.deathLink.push({ ...newDeathLink(), text, weight: str(w, '1') || '1' });
  });

  // --------- Clicker mode (no-op for a plain Taskipelago YAML) ---------
  clickerImportSettings(model, block);

  return { ok: true, model, messages };
}
