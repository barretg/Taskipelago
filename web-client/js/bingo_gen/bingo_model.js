// Taskipelabingo generator logic (UNIFY 5.5), ported from legacy_client/client.py
// _export_bingo_yaml, _save_bingo_settings, _load_bingo_settings_doc and
// _load_bingo_yaml_doc (5713-6055) plus _bingo_lines, _gen_bingoal_expr,
// _collapse_items_by_count and _expand_by_count (325-526). Randomness is
// injectable so tests/parity/generator_parity.py can compare against the
// legacy code with a fixed choice.
import { isFillerExact, randomFiller } from '../shared/filler.js';
import {
  PyError, isDict, pyGet, pyInt, pyListOr, pyStr, pyStrip, pyTruthy,
} from '../shared/pyish.js';
import { extractTaskipelagoBlock, toggleOption } from '../generator/yaml_import.js';
import { limitPlayerName } from '../generator/model.js';
import {
  THEME_COLORS, decodeThemeColors, defaultThemeColors, encodeThemeColors, normalizeStyleColors,
} from '../shared/theme.js';

export function defaultBingoModel() {
  return {
    playerName: '', x: 5, y: 5, bingoal: 3, progressionBalancing: 50, accessibility: 'full',
    deathLinkEnabled: false, deathLinkAmnesty: 0, spaces: '', rewards: '', deathLinkPool: '',
    deathLinkLockTasks: false, // v1.1 F3
    // v1.1 F7: theme key -> hex. A bingo slot themes the board colors too.
    styleColors: defaultThemeColors(THEME_COLORS),
  };
}

export function normalizeBingoModel(raw) {
  const model = defaultBingoModel();
  if (raw && typeof raw === 'object') for (const k of Object.keys(model)) if (raw[k] !== undefined) model[k] = raw[k];
  model.styleColors = normalizeStyleColors(model.styleColors, THEME_COLORS);
  return model;
}

/** Python random.sample / random.shuffle / random.choice(FILLER_ITEMS). */
export const defaultRng = {
  sample(pool, n) {
    const copy = [...pool];
    for (let i = 0; i < n; i++) {
      const j = i + Math.floor(Math.random() * (copy.length - i));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy.slice(0, n);
  },
  shuffle(list) {
    for (let i = list.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [list[i], list[j]] = [list[j], list[i]];
    }
  },
  filler: randomFiller,
};

const LINE_BREAK = /\r\n|[\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]/;

/** [line.strip() for line in text.splitlines() if line.strip()] */
export function nonEmptyLines(text) {
  return String(text ?? '').split(LINE_BREAK).map(pyStrip).filter(Boolean);
}

/** TaskipelagoApp._safe_int */
export function safeInt(value, fallback) {
  try {
    return pyInt(value);
  } catch (_) {
    return fallback;
  }
}

export function dedupeNames(names) {
  const seen = new Map();
  return names.map(n => {
    const count = (seen.get(n) || 0) + 1;
    seen.set(n, count);
    return count === 1 ? n : `${n} (${count})`;
  });
}

export function collapseItemsByCount(names, types, fillers) {
  const order = [];
  const counts = new Map();
  names.forEach((name, i) => {
    const key = JSON.stringify([name, types[i], fillers[i]]);
    if (!counts.has(key)) {
      counts.set(key, 0);
      order.push([key, name, types[i], fillers[i]]);
    }
    counts.set(key, counts.get(key) + 1);
  });
  return {
    names: order.map(o => o[1]), types: order.map(o => o[2]),
    fillers: order.map(o => o[3]), counts: order.map(o => counts.get(o[0])),
  };
}

export function expandByCount(values, counts) {
  const out = [];
  const n = Math.min(values.length, counts.length);
  for (let i = 0; i < n; i++) {
    let c;
    try {
      c = Math.max(1, pyInt(counts[i]));
    } catch (_) {
      c = 1;
    }
    for (let k = 0; k < c; k++) out.push(values[i]);
  }
  return out;
}

/** 0-based cell indices for every row, column and full-length diagonal. */
export function bingoLines(X, Y) {
  const lines = [];
  for (let r = 0; r < Y; r++) lines.push(Array.from({ length: X }, (_, c) => r * X + c));
  for (let c = 0; c < X; c++) lines.push(Array.from({ length: Y }, (_, r) => r * X + c));
  const d = Math.min(X, Y);
  for (let r0 = 0; r0 < Y - d + 1; r0++) {
    for (let c0 = 0; c0 < X - d + 1; c0++) lines.push(Array.from({ length: d }, (_, i) => (r0 + i) * X + (c0 + i)));
  }
  for (let r0 = 0; r0 < Y - d + 1; r0++) {
    for (let c0 = d - 1; c0 < X; c0++) lines.push(Array.from({ length: d }, (_, i) => (r0 + i) * X + (c0 - i)));
  }
  return lines;
}

function* combinations(items, k) {
  const idx = Array.from({ length: k }, (_, i) => i);
  if (k > items.length) return;
  for (;;) {
    yield idx.map(i => items[i]);
    let i = k - 1;
    while (i >= 0 && idx[i] === i + items.length - k) i--;
    if (i < 0) return;
    idx[i]++;
    for (let j = i + 1; j < k; j++) idx[j] = idx[j - 1] + 1;
  }
}

// The legacy client froze building these; C(18, 9) for a 7x5 board is 48620 terms.
const MAX_GOAL_TERMS = 100000;

/** Number of "(a && b ...)" terms genBingoalExpr would write, capped just past the limit. */
export function goalTermCount(nLines, bingoal) {
  if (nLines === 0 || bingoal <= 0 || bingoal >= nLines) return 1;
  let terms = 1;
  for (let i = 1; i <= bingoal; i++) {
    terms = (terms * (nLines - bingoal + i)) / i;
    if (terms > MAX_GOAL_TERMS) return MAX_GOAL_TERMS + 1;
  }
  return Math.round(terms);
}

export function genBingoalExpr(nSpaces, nLines, bingoal) {
  if (nLines === 0 || bingoal <= 0) return '';
  bingoal = Math.min(bingoal, nLines);
  const lineIds = Array.from({ length: nLines }, (_, i) => nSpaces + i + 1);
  if (bingoal === nLines) return lineIds.join(', ');
  const terms = [];
  for (const combo of combinations(lineIds, bingoal)) terms.push(`(${combo.join(' && ')})`);
  return terms.join(' || ');
}

/** Live counter labels under the Spaces and Rewards boxes. */
export function bingoCounts(model) {
  const X = safeInt(model.x, 5);
  const Y = safeInt(model.y, 5);
  const needed = X * Y;
  const have = nonEmptyLines(model.spaces).length;
  let suffix;
  if (have >= needed) suffix = have === needed ? ' (enough)' : ` (${have - needed} extra)`;
  else suffix = ` (need ${needed - have} more)`;
  const nFiller = 1 + bingoLines(X, Y).length;
  const haveRw = nonEmptyLines(model.rewards).length;
  let rwSuffix;
  if (haveRw === 0) rwSuffix = `all ${nFiller} slots will be filler`;
  else if (haveRw === nFiller) rwSuffix = `all ${nFiller} slots covered`;
  else if (haveRw > nFiller) rwSuffix = `all ${nFiller} slots covered, ${haveRw - nFiller} unused`; // v1.1 F9
  else rwSuffix = `${haveRw} replaced, ${nFiller - haveRw} remain filler`;
  return {
    spaces: `Enter one space per line (need ${needed}, have ${have}${suffix})`,
    rewards: `Reward slots available: ${nFiller} - ${rwSuffix}`,
  };
}

/**
 * _export_bingo_yaml. Resolves to { data, unusedRewards } or { error: [title, message] }.
 * Board sizes below 1 are rejected here; the legacy client crashed on them.
 * v1.1 F9: the free space defaults to filler like line rewards (legacy gave it a
 * dead "Bingo r,c Unlock" progression item), and unusedRewards counts user
 * rewards beyond the available slots so the UI can confirm before exporting.
 */
export function buildBingoExport(model, rng = defaultRng) {
  const fail = (title, message) => ({ error: [title, message] });
  const playerName = pyStrip(model.playerName);
  if (!playerName) return fail('Error', 'Player name is required.');

  const X = safeInt(model.x, 5);
  const Y = safeInt(model.y, 5);
  let bingoal = safeInt(model.bingoal, 3);
  if (X < 1 || Y < 1) return fail('Error', 'Columns (X) and Rows (Y) must be at least 1.');
  const nSpaces = X * Y;

  const spacesPool = nonEmptyLines(model.spaces);
  if (spacesPool.length < nSpaces) {
    return fail('Error', `Need at least ${nSpaces} spaces for a ${X}x${Y} board, but only ${spacesPool.length} entered.`);
  }
  const selected = dedupeNames(rng.sample(spacesPool, nSpaces));

  const tasks = [];
  const rewards = [];
  const taskPrereqs = [];
  const rewardPrereqs = [];
  const rewardTypes = [];
  const itemFillers = [];
  const middle = Math.floor(nSpaces / 2);
  for (let i = 0; i < nSpaces; i++) {
    const r = Math.floor(i / X);
    const c = i % X;
    const free = i === middle;
    tasks.push(selected[i]);
    rewards.push(free ? rng.filler() : `Bingo ${r + 1},${c + 1} Unlock`);
    itemFillers.push(free);
    taskPrereqs.push('');
    rewardPrereqs.push(free ? '' : String(i + 1));
    rewardTypes.push(free ? 'junk' : 'progression');
  }

  const lines = bingoLines(X, Y);
  const L = lines.length;
  const d = Math.min(X, Y);
  const nMainDiags = (Y - d + 1) * (X - d + 1);
  const nAntiDiags = nMainDiags;
  lines.forEach((line, li) => {
    let name;
    if (li < Y) name = `Row ${li + 1} Bingo`;
    else if (li < Y + X) name = `Column ${li - Y + 1} Bingo`;
    else if (li < Y + X + nMainDiags) {
      const idx = li - Y - X;
      name = nMainDiags === 1 ? 'Diagonal Bingo (↘)' : `Diagonal Bingo (↘ #${idx + 1})`;
    } else {
      const idx = li - Y - X - nMainDiags;
      name = nAntiDiags === 1 ? 'Diagonal Bingo (↙)' : `Diagonal Bingo (↙ #${idx + 1})`;
    }
    tasks.push(name);
    rewards.push(rng.filler());
    itemFillers.push(true);
    taskPrereqs.push(line.map(s => s + 1).join(', '));
    rewardPrereqs.push('');
    rewardTypes.push('junk');
  });

  const deathLinkPool = nonEmptyLines(model.deathLinkPool);
  if (model.deathLinkEnabled && !deathLinkPool.length) {
    return fail('Error', 'DeathLink is enabled but the pool is empty.\nAdd at least one entry or disable DeathLink.');
  }

  // User rewards replace filler slots (free space, then line tasks).
  const rewardPool = nonEmptyLines(model.rewards);
  rng.shuffle(rewardPool);
  let next = 0;
  const take = () => (next < rewardPool.length ? rewardPool[next++] : null);
  let userReward = take();
  if (userReward) {
    rewards[middle] = userReward;
    rewardTypes[middle] = 'useful';
    itemFillers[middle] = false;
  }
  for (let li = 0; li < L; li++) {
    userReward = take();
    if (userReward) {
      rewards[nSpaces + li] = userReward;
      rewardTypes[nSpaces + li] = 'useful';
      itemFillers[nSpaces + li] = false;
    }
  }

  bingoal = Math.max(1, Math.min(bingoal, L));
  if (goalTermCount(L, bingoal) > MAX_GOAL_TERMS) {
    return fail('Error', `Bingos to goal ${bingoal} of ${L} lines makes a goal expression too large to export. `
      + 'Choose a number closer to 1 or to the number of lines.');
  }
  const goalExpr = genBingoalExpr(nSpaces, L, bingoal);
  const collapsed = collapseItemsByCount(rewards, rewardTypes, itemFillers);
  // Board unlock rows are distinct first occurrences, so merges never shift them and
  // the String(i + 1) item prereqs above stay valid.
  console.assert(rewards.slice(0, nSpaces).every((rw, i) => i === middle || collapsed.names[i] === rw),
    'bingo export: board unlock item rows shifted after collapse');

  const styleColors = encodeThemeColors(model.styleColors, THEME_COLORS);

  const data = {
    name: playerName,
    game: 'Taskipelago',
    description: 'Taskipelabingo YAML',
    Taskipelago: {
      progression_balancing: safeInt(model.progressionBalancing, 50),
      accessibility: model.accessibility,
      death_link: model.deathLinkEnabled ? { true: 50, false: 0 } : { true: 0, false: 50 },
      progressive_groups: [],
      item_progressive_group: collapsed.names.map(() => ''),
      tasks,
      items: collapsed.names,
      item_types: collapsed.types,
      item_fillers: collapsed.fillers,
      item_count: collapsed.counts.map(String),
      task_prereqs: taskPrereqs,
      item_prereqs: rewardPrereqs,
      lock_prereqs: true,
      hide_unreachable_tasks: true,
      goal_tasks: goalExpr ? [goalExpr] : [],
      death_link_pool: deathLinkPool,
      death_link_weights: [],
      death_link_amnesty: safeInt(model.deathLinkAmnesty, 0),
      death_link_lock_tasks: !!model.deathLinkLockTasks,
      bingo_mode: true,
      bingo_dimension_x: X,
      bingo_dimension_y: Y,
      bingoal,
      // v1.1 F7: only non-default colors, so an untouched Style panel adds nothing.
      ...(styleColors.length ? { style_colors: styleColors } : {}),
    },
  };
  return { data, unusedRewards: rewardPool.length - next };
}

/** _save_bingo_settings document (.bingo file). */
export function bingoSettingsDoc(model) {
  return {
    spaces: nonEmptyLines(model.spaces),
    rewards: nonEmptyLines(model.rewards),
    player_name: pyStrip(model.playerName),
    bingo_x: safeInt(model.x, 5),
    bingo_y: safeInt(model.y, 5),
    bingoal: safeInt(model.bingoal, 3),
    progression_balancing: safeInt(model.progressionBalancing, 50),
    accessibility: model.accessibility,
    death_link_enabled: !!model.deathLinkEnabled,
    death_link_amnesty: safeInt(model.deathLinkAmnesty, 0),
    death_link_lock_tasks: !!model.deathLinkLockTasks,
    death_link_pool: nonEmptyLines(model.deathLinkPool),
    style_colors: encodeThemeColors(model.styleColors, THEME_COLORS), // v1.1 F7
  };
}

const intOr = (v, fallback) => pyInt(pyTruthy(v) ? v : fallback);
const linesOf = values => values.map(v => pyStrip(pyStr(v))).filter(Boolean).map(s => `${s}\n`).join('');

function loadSettingsDoc(model, doc) {
  const name = pyGet(doc, 'player_name', '');
  if (typeof name === 'string' && pyStrip(name)) model.playerName = limitPlayerName(pyStrip(name));
  try {
    model.x = intOr(pyGet(doc, 'bingo_x', 5), 5);
    model.y = intOr(pyGet(doc, 'bingo_y', 5), 5);
    model.bingoal = intOr(pyGet(doc, 'bingoal', 3), 3);
    model.progressionBalancing = intOr(pyGet(doc, 'progression_balancing', 50), 50);
  } catch (e) {
    if (!(e instanceof PyError)) throw e;
  }
  const acc = pyGet(doc, 'accessibility', 'full');
  if (typeof acc === 'string' && pyStrip(acc)) model.accessibility = pyStrip(acc);
  model.deathLinkEnabled = pyTruthy(pyGet(doc, 'death_link_enabled', false));
  try {
    model.deathLinkAmnesty = intOr(pyGet(doc, 'death_link_amnesty', 0), 0);
  } catch (e) {
    if (!(e instanceof PyError)) throw e;
  }
  model.deathLinkLockTasks = toggleOption(pyGet(doc, 'death_link_lock_tasks', false));
  model.deathLinkPool = linesOf(pyListOr(doc, 'death_link_pool'));
  model.spaces = linesOf(pyListOr(doc, 'spaces'));
  model.rewards = linesOf(pyListOr(doc, 'rewards'));
  model.styleColors = normalizeStyleColors(
    decodeThemeColors(pyListOr(doc, 'style_colors').map(pyStr)), THEME_COLORS);
}

function loadYamlDoc(model, doc) {
  const [playerName, block] = extractTaskipelagoBlock(doc);
  if (!isDict(block)) return ['error', 'Error', 'Could not find a Taskipelago section in this YAML.'];
  if (!pyTruthy(pyGet(block, 'bingo_mode', null))) {
    return ['error', 'Error', 'This YAML does not have bingo_mode enabled.'];
  }
  if (playerName) model.playerName = limitPlayerName(playerName);

  const X = intOr(pyGet(block, 'bingo_dimension_x', 5), 5);
  const Y = intOr(pyGet(block, 'bingo_dimension_y', 5), 5);
  try {
    model.x = X;
    model.y = Y;
    model.bingoal = intOr(pyGet(block, 'bingoal', 3), 3);
    model.progressionBalancing = intOr(pyGet(block, 'progression_balancing', 50), 50);
  } catch (e) {
    if (!(e instanceof PyError)) throw e;
  }
  const acc = pyGet(block, 'accessibility', 'full');
  if (typeof acc === 'string' && pyStrip(acc)) model.accessibility = pyStrip(acc);

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
  try {
    model.deathLinkAmnesty = intOr(pyGet(block, 'death_link_amnesty', 0), 0);
  } catch (e) {
    if (!(e instanceof PyError)) throw e;
  }
  model.deathLinkLockTasks = toggleOption(pyGet(block, 'death_link_lock_tasks', false));
  model.deathLinkPool = linesOf(pyListOr(block, 'death_link_pool'));
  model.styleColors = normalizeStyleColors(
    decodeThemeColors(pyListOr(block, 'style_colors').map(pyStr)), THEME_COLORS);

  const tasks = pyListOr(block, 'tasks');
  model.spaces = linesOf(tasks.slice(0, X * Y));

  let rewards = pyListOr(block, 'items', pyGet(block, 'rewards', []));
  const countRaw = pyGet(block, 'item_count', null);
  if (countRaw !== null) rewards = expandByCount(rewards, Array.isArray(countRaw) ? countRaw : [countRaw]);
  // Content-based: every non-filler, non-board-unlock entry is a user reward.
  model.rewards = rewards
    .map(rw => pyStrip(pyStr(rw)))
    .filter(rw => rw && !isFillerExact(rw) && !rw.startsWith('Bingo '))
    .map(rw => `${rw}\n`).join('');
  return null;
}

/**
 * _load_bingo: a settings document (a mapping with "spaces") or a bingo YAML.
 * Returns { ok, model, messages, kind } with kind 'settings' | 'yaml'; throws
 * PyError where the legacy client raised.
 */
export function loadBingoDoc(current, doc) {
  const model = structuredClone(current);
  if (isDict(doc) && Object.hasOwn(doc, 'spaces')) {
    loadSettingsDoc(model, doc);
    return { ok: true, model, messages: [], kind: 'settings' };
  }
  const error = loadYamlDoc(model, doc);
  if (error) return { ok: false, model: current, messages: [error], kind: 'yaml' };
  return { ok: true, model, messages: [], kind: 'yaml' };
}
