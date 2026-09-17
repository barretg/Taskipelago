// YAML Generator editor state (UNIFY 5.3). Pure data plus the state rules the
// legacy Tk rows enforced (legacy_client/client.py:951-1291, 2521-2918), so
// yaml_export.js / yaml_import.js can be parity-tested without a DOM.
//
// Values are raw widget values, like the Tk variables: counts and percentages
// may be strings until export converts them. Each item keeps a `ui` object with
// the ItemRow's saved values and disabled flags; it is never exported.
import { RESERVED_WORDS, validateRefName } from '../shared/prereq_parser.js';
import { isFillerExact, randomFiller as defaultRandomFiller } from '../shared/filler.js';
import { pyInt, pyStrip } from '../shared/pyish.js';

export const MAX_TASK_DESCRIPTION_LEN = 100;
export const MAX_PLAYER_NAME_LEN = 16;
export const REGION_COLOR_PALETTE = [
  '#e05c5c', '#e0955c', '#e0d45c', '#8de05c',
  '#5ce09a', '#5cd4e0', '#5c8de0', '#7b5ce0',
  '#c05ce0', '#e05cb4', '#a0a0a0', '#5ce0c8',
];
export const REWARD_TYPE_VALUES = ['junk', 'useful', 'progression', 'trap'];
export const DEFAULT_REWARD_TYPE = 'useful';
export const TASK_REWARD_PREVIEW_LABELS = ['No Previews', 'Scout Previews', 'Hint Previews'];

export const isReservedWord = name => RESERVED_WORDS.has(name.toLowerCase());

/** Code-point truncation, as _limit_var_length does on every write. */
export function limitPlayerName(name) {
  const chars = Array.from(name);
  return chars.length > MAX_PLAYER_NAME_LEN ? chars.slice(0, MAX_PLAYER_NAME_LEN).join('') : name;
}

export function newTask() {
  return { name: '', prereq: '', itemPrereq: '', cost: '', region: '', priority: false, count: 1, desc: '' };
}

export function newItem() {
  return {
    name: '', filler: false, type: DEFAULT_REWARD_TYPE, progGroup: '', consumable: false, count: 1,
    ui: {
      savedType: DEFAULT_REWARD_TYPE, savedItem: '', savedGroup: '',
      nameDisabled: false, typeDisabled: false, fillerDisabled: false,
      consumableDisabled: false, groupDisabled: false,
    },
  };
}

export const newDeathLink = () => ({ text: '', weight: '1' });

/** State after TaskipelagoApp.__init__ / reset_yaml_generator: one empty task row. */
export function defaultModel() {
  return {
    playerName: '',
    progressionBalancing: 50,
    accessibility: 'full',
    deathLinkEnabled: false,
    deathLinkAmnesty: 0,
    lockPrereqs: true,
    hideUnreachable: true,
    taskRewardPreviews: 0,
    goalTasks: '',
    progGroups: [],
    regions: [],
    nextColorIdx: 0,
    tasks: [newTask()],
    items: [],
    deathLink: [],
  };
}

/** Disabled flags implied by an item's values, for drafts saved without row state. */
function impliedUi(it) {
  const ui = newItem().ui;
  if (it.filler) {
    Object.assign(ui, { nameDisabled: true, typeDisabled: true, consumableDisabled: true, groupDisabled: true });
  } else if (it.consumable) {
    Object.assign(ui, { typeDisabled: true, groupDisabled: true, savedType: DEFAULT_REWARD_TYPE });
  } else if (it.progGroup) {
    Object.assign(ui, { typeDisabled: true, fillerDisabled: true });
  }
  return ui;
}

/** Restore a saved draft onto a fresh model, tolerating missing or older fields. */
export function normalizeModel(raw) {
  const model = defaultModel();
  if (!raw || typeof raw !== 'object') return model;
  for (const k of Object.keys(model)) if (raw[k] !== undefined) model[k] = raw[k];
  model.tasks = (Array.isArray(model.tasks) ? model.tasks : []).map(t => ({ ...newTask(), ...t }));
  model.items = (Array.isArray(model.items) ? model.items : []).map(it => {
    const merged = { ...newItem(), ...it };
    return { ...merged, ui: { ...impliedUi(merged), ...(it && it.ui) } };
  });
  model.deathLink = (Array.isArray(model.deathLink) ? model.deathLink : []).map(d => ({ ...newDeathLink(), ...d }));
  model.regions = (Array.isArray(model.regions) ? model.regions : [])
    .map(r => ({ name: '', pct: 100, color: '', prereq: '', ...r }));
  model.progGroups = Array.isArray(model.progGroups) ? model.progGroups : [];
  return model;
}

/** IntVar.get() followed by max(1, int(...)), falling back to 1. */
export function rowCount(value) {
  try {
    return Math.max(1, pyInt(value));
  } catch (_) {
    return 1;
  }
}

/** TaskRow.get_data */
export function taskData(t) {
  return {
    name: pyStrip(t.name), prereq: pyStrip(t.prereq), itemPrereq: pyStrip(t.itemPrereq),
    cost: pyStrip(t.cost), region: pyStrip(t.region), priority: !!t.priority,
    count: rowCount(t.count), desc: pyStrip(t.desc),
  };
}

/** ItemRow.get_data */
export function itemData(it) {
  return {
    name: pyStrip(it.name), filler: !!it.filler,
    type: pyStrip(it.type).toLowerCase() || 'useful',
    progGroup: pyStrip(it.progGroup), consumable: !!it.consumable, count: rowCount(it.count),
  };
}

/** Item counter label: "items/tasks items"; warn when they differ. */
export function slotCounts(model) {
  const sum = rows => {
    try {
      return rows.reduce((acc, r) => acc + Math.max(1, pyInt(r.count)), 0);
    } catch (_) {
      return rows.length;
    }
  };
  return { tasks: sum(model.tasks), items: sum(model.items) };
}

// ---------------------------------------------------------------------------
// ItemRow state machine. Each function mirrors the Tk command or variable trace
// of the same name, in the same statement order (traces fire mid-function).
// ---------------------------------------------------------------------------

function onProgGroupChange(it) {
  const u = it.ui;
  if (it.progGroup) {
    if (!it.filler) {
      const current = pyStrip(it.type).toLowerCase();
      if (current !== 'progression') u.savedType = current;
    }
    it.type = 'progression';
    u.typeDisabled = true;
    u.fillerDisabled = true;
  } else {
    if (!it.consumable) {
      u.typeDisabled = false;
      it.type = u.savedType || DEFAULT_REWARD_TYPE;
    }
    if (!it.filler && !it.consumable) u.fillerDisabled = false;
  }
}

/** prog_group_var.set(group), firing its trace. */
export function setItemProgGroup(it, group) {
  it.progGroup = group;
  onProgGroupChange(it);
}

/** Checkbox command after filler_var changed to it.filler. */
export function onFillerToggle(it, randomFiller = defaultRandomFiller) {
  const u = it.ui;
  if (it.filler) {
    const current = pyStrip(it.name);
    if (current && !isFillerExact(current)) u.savedItem = current;
    const currentType = pyStrip(it.type).toLowerCase();
    if (currentType) u.savedType = currentType;
    u.savedGroup = it.progGroup;
    setItemProgGroup(it, '');
    u.groupDisabled = true;
    it.consumable = false;
    u.consumableDisabled = true;
    it.name = randomFiller();
    u.nameDisabled = true;
    it.type = 'junk';
    u.typeDisabled = true;
  } else {
    u.nameDisabled = false;
    it.name = u.savedItem;
    u.consumableDisabled = false;
    if (it.consumable) {
      onConsumableToggle(it);
    } else {
      u.groupDisabled = false;
      setItemProgGroup(it, u.savedGroup);
    }
  }
}

/** Checkbox command after consumable_var changed to it.consumable. */
export function onConsumableToggle(it) {
  const u = it.ui;
  if (it.consumable) {
    const currentType = pyStrip(it.type).toLowerCase();
    if (currentType !== 'progression') u.savedType = currentType || DEFAULT_REWARD_TYPE;
    it.type = 'progression';
    u.typeDisabled = true;
    if (!u.savedGroup) u.savedGroup = it.progGroup;
    setItemProgGroup(it, '');
    u.groupDisabled = true;
  } else if (!it.filler) {
    u.typeDisabled = false;
    it.type = u.savedType || DEFAULT_REWARD_TYPE;
    u.groupDisabled = false;
    setItemProgGroup(it, u.savedGroup);
  }
}

// ---------------------------------------------------------------------------
// Progressive groups and regions. Validation returns [title, message] or null.
// ---------------------------------------------------------------------------

export function addProgGroup(model, rawName) {
  const name = pyStrip(rawName);
  if (!name) return ['Error', 'Group name cannot be empty.'];
  const why = validateRefName(name);
  if (why) return ['Error', `Group name '${name}' ${why}.`];
  if (model.progGroups.includes(name)) return ['Error', `Progressive group '${name}' already exists.`];
  model.progGroups.push(name);
  return null;
}

export function removeProgGroup(model, name) {
  const idx = model.progGroups.indexOf(name);
  if (idx >= 0) model.progGroups.splice(idx, 1);
  for (const it of model.items) if (it.progGroup === name) setItemProgGroup(it, '');
  syncItemGroups(model);
}

/** ItemRow.update_groups on every row. */
export function syncItemGroups(model) {
  for (const it of model.items) {
    if (it.progGroup !== '' && !model.progGroups.includes(it.progGroup)) setItemProgGroup(it, '');
  }
}

export function addRegion(model, rawName, pct) {
  const name = pyStrip(rawName);
  if (!name) return ['Error', 'Region name cannot be empty.'];
  const why = validateRefName(name);
  if (why) return ['Error', `Region name '${name}' ${why}.`];
  if (model.regions.some(r => r.name === name)) return ['Error', `Region '${name}' already exists.`];
  const color = REGION_COLOR_PALETTE[model.nextColorIdx % REGION_COLOR_PALETTE.length];
  model.nextColorIdx += 1;
  model.regions.push({ name, pct: pyInt(pct), color, prereq: '' });
  return null;
}

export function removeRegion(model, name) {
  model.regions = model.regions.filter(r => r.name !== name);
  for (const t of model.tasks) if (t.region === name) t.region = '';
  syncTaskRegions(model);
}

/** TaskRow.update_regions on every row. */
export function syncTaskRegions(model) {
  for (const t of model.tasks) {
    if (t.region !== '' && !model.regions.some(r => r.name === t.region)) t.region = '';
  }
}

/**
 * Legacy rename semantics (v1.1_PLAN Phase U amendment): renames the region and
 * task-row assignments only; expression text is not rewritten until F4.
 */
export function renameRegion(model, oldName, rawNew) {
  const newName = pyStrip(rawNew);
  if (newName === oldName || !newName) return null;
  const why = validateRefName(newName);
  if (why) return ['Error', `Region name '${newName}' ${why}.`];
  if (model.regions.some(r => r.name === newName)) return ['Error', `Region '${newName}' already exists.`];
  const region = model.regions.find(r => r.name === oldName);
  if (!region) return null;
  region.name = newName;
  for (const t of model.tasks) if (t.region === oldName) t.region = newName;
  syncTaskRegions(model);
  return null;
}

/** _commit_region_pct: clamp to 0-100, keep the old value when not a number. */
export function commitRegionPct(region, raw) {
  try {
    region.pct = Math.max(0, Math.min(100, pyInt(raw)));
  } catch (_) { /* keep */ }
  return region.pct;
}
