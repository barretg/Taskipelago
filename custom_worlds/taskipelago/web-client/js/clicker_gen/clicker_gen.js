// Tasclickpelago tab. Logic lives in clicker_model.js; every edit autosaves a
// draft to device storage, the same pattern the other two generator tabs use.
import * as storage from '../shared/storage.js';
import { $, h } from '../shared/dom.js';
import { alertDialog, confirmDialog } from '../shared/dialog.js';
import { downloadText, pickTextFile, safeFileName } from '../shared/files.js';
import { PyError } from '../shared/pyish.js';
import { dumpYaml, loadYaml } from '../shared/yaml11.js';
import { DEATHLINK_LOCK_TIP as DL_LOCK_TIP, MAX_PLAYER_NAME_LEN, limitPlayerName } from '../generator/model.js';
import { STYLE_SECTION_TIP, renderStyleColors, resetStyleColors } from '../generator/style_section.js';
import { THEME_COLORS } from '../shared/theme.js';
import { TIPS } from '../generator/legacy_text.js';
import { tipHeader } from '../shared/tooltip.js';
import { getUiPref, setUiPref } from '../shared/ui_prefs.js';
import { NUM_CONSTANTS } from '../shared/num_expr.js';
import {
  ITEM_TYPES, UPGRADE_KINDS, buildClickerExport, clickerCounts, clickerSettingsDoc,
  curveFill, defaultClickerModel, defaultRegionRow, defaultTaskRow, defaultUpgradeRow,
  loadClickerDoc, normalizeClickerModel, offlineExample, previewValue, safeInt,
} from './clicker_model.js';

export const DRAFT_KEY = 'taskipelago_draft_clicker';
const SAVE_DELAY_MS = 400;

const KIND_LABELS = {
  none: 'Unlock only (no effect)',
  production: 'Production (/s)',
  click_power: 'Click power (+)',
  production_mult: 'Production multiplier (x)',
  click_mult: 'Click multiplier (x)',
  offline_mult: 'Offline multiplier (x)',
};

let model = defaultClickerModel();
const els = {};
let saveTimer = null;

function saveDraft() {
  clearTimeout(saveTimer);
  saveTimer = null;
  storage.set(DRAFT_KEY, model);
}

function changed({ save = true, rebuild = false } = {}) {
  const counts = clickerCounts(model);
  els.taskCount.textContent = `${counts.tasks} task${counts.tasks === 1 ? '' : 's'}`;
  els.upgradeCount.textContent = `${counts.upgrades} upgrade${counts.upgrades === 1 ? '' : 's'}, `
    + `${counts.copies} cop${counts.copies === 1 ? 'y' : 'ies'} of ${counts.tasks} item slot${counts.tasks === 1 ? '' : 's'}`;
  els.warnings.replaceChildren(...counts.warnings.map(w => h('div', { className: 'gen-warning' }, w)));
  els.offlineExample.textContent = offlineExample(model);
  if (rebuild) renderTables();
  else refreshPreviews();
  if (!save) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveDraft, SAVE_DELAY_MS);
}

// =============================================================
// Small field helpers
// =============================================================

/** A text/number cell bound to one row property. */
function cell(row, key, opts = {}) {
  const node = h('input', {
    type: opts.type || 'text', spellcheck: false, autocomplete: 'off',
    className: opts.className || 'clicker-cell',
    placeholder: opts.placeholder || '',
    value: row[key] ?? '',
  });
  node.addEventListener('input', () => { row[key] = node.value; changed(); });
  return node;
}

function checkCell(row, key) {
  const node = h('input', { type: 'checkbox' });
  node.checked = !!row[key];
  node.addEventListener('change', () => { row[key] = node.checked; changed(); });
  return node;
}

function selectCell(row, key, values, labels = {}) {
  const node = h('select', {}, values.map(v => h('option', { value: v }, labels[v] || v)));
  node.value = row[key];
  node.addEventListener('change', () => { row[key] = node.value; changed({ rebuild: false }); });
  return node;
}

/** Region picker fed by the Regions table, as in the YAML Generator task table. */
function regionCell(row) {
  const node = h('select', {});
  // Filled on demand so renaming a region in the Regions table is picked up
  // without rebuilding (and losing focus in) the table being typed into.
  const sync = () => {
    const names = model.regions.map(r => String(r.name || '').trim()).filter(Boolean);
    const current = String(row.region || '').trim();
    if (current && !names.includes(current)) names.push(current);
    node.replaceChildren(h('option', { value: '' }, ''), ...names.map(n => h('option', { value: n }, n)));
    node.value = current;
  };
  sync();
  node.addEventListener('mousedown', sync);
  node.addEventListener('focus', sync);
  node.addEventListener('change', () => { row.region = node.value; changed(); });
  return node;
}

/**
 * A numeric cell plus a live preview of both ends of the curve, so an
 * expression like `0.1 * N_TASKS_UNLOCKED` is not opaque before export.
 */
function exprCell(row, key, placeholder) {
  const input = cell(row, key, { placeholder });
  const preview = h('span', { className: 'clicker-preview' });
  const wrap = h('div', { className: 'clicker-expr' }, input, preview);
  previews.push({ row, key, preview });
  return wrap;
}

let previews = [];

function refreshPreviews() {
  const nTasks = model.tasks.filter(t => String(t.name ?? '').trim()).length;
  for (const { row, key, preview } of previews) {
    const r = previewValue(row[key], nTasks);
    if (r.blank) { preview.textContent = ''; preview.classList.remove('is-error'); continue; }
    if (!r.ok) {
      preview.textContent = r.error;
      preview.classList.add('is-error');
      continue;
    }
    preview.classList.remove('is-error');
    preview.textContent = r.low === r.high ? `= ${r.low}` : `${r.low} → ${r.high}`;
  }
}

/** Constants palette: clicking one appends it to the last focused expression. */
let lastExprInput = null;
function constantsPalette() {
  return h('div', { className: 'clicker-constants' },
    h('span', { className: 'muted-text' }, 'Insert:'),
    ...NUM_CONSTANTS.map(c => h('button', {
      type: 'button', className: 'chip', onclick: () => insertConstant(c),
    }, c)));
}

function insertConstant(name) {
  const input = lastExprInput;
  if (!input) return;
  const value = input.value ? `${input.value} ${name}` : name;
  input.value = value;
  input.dispatchEvent(new Event('input'));
  input.focus();
}

// =============================================================
// Tables
// =============================================================

function rowButtons(list, row, defaults) {
  return h('div', { className: 'clicker-row-btns' },
    h('button', {
      type: 'button', title: 'Insert a row below',
      onclick: () => { list.splice(list.indexOf(row) + 1, 0, defaults()); changed({ rebuild: true }); },
    }, '+'),
    h('button', {
      type: 'button', title: 'Remove this row',
      onclick: () => {
        const i = list.indexOf(row);
        if (i >= 0) list.splice(i, 1);
        if (!list.length) list.push(defaults());
        changed({ rebuild: true });
      },
    }, '−'));
}

function renderTables() {
  previews = [];
  els.taskRows.replaceChildren(...model.tasks.map((row, i) => h('tr', {},
    h('td', { className: 'clicker-num' }, String(i + 1)),
    h('td', {}, cell(row, 'name', { placeholder: 'Task name' })),
    h('td', {}, exprCell(row, 'activations', '1')),
    h('td', {}, regionCell(row)),
    h('td', {}, cell(row, 'prereq', { placeholder: '1  or  "Task"  or  region' })),
    h('td', {}, cell(row, 'itemPrereq', { placeholder: '1  or  "Item"' })),
    h('td', {}, rowButtons(model.tasks, row, defaultTaskRow)))));

  els.regionRows.replaceChildren(...model.regions.map(row => h('tr', {},
    h('td', {}, cell(row, 'name', { placeholder: 'Region name' })),
    h('td', {}, cell(row, 'color', { placeholder: '#5c8de0' })),
    h('td', {}, cell(row, 'defaultPct', { placeholder: '100' })),
    h('td', { className: 'clicker-check' }, checkCell(row, 'distributed')),
    h('td', {}, exprCell(row, 'offlineRate', 'inherit')),
    h('td', {}, rowButtons(model.regions, row, defaultRegionRow)))));

  els.upgradeRows.replaceChildren(...model.upgrades.map(row => h('tr', {},
    h('td', {}, cell(row, 'name', { placeholder: 'Upgrade name' })),
    h('td', {}, selectCell(row, 'type', ITEM_TYPES)),
    h('td', {}, cell(row, 'count', { type: 'number', className: 'count-input' })),
    h('td', {}, cell(row, 'group', { placeholder: 'Progressive group' })),
    h('td', {}, selectCell(row, 'kind', UPGRADE_KINDS, KIND_LABELS)),
    h('td', {}, cell(row, 'target', { placeholder: '*' })),
    h('td', {}, exprCell(row, 'value', '1')),
    h('td', {}, rowButtons(model.upgrades, row, defaultUpgradeRow)))));

  for (const { preview } of previews) {
    const input = preview.previousSibling;
    input.addEventListener('focus', () => { lastExprInput = input; });
  }
  refreshPreviews();
}

// =============================================================
// Model wiring
// =============================================================

const FIELDS = [
  ['playerName', 'value'], ['progressionBalancing', 'value'], ['accessibility', 'value'],
  ['deathLinkEnabled', 'checked'], ['deathLinkAmnesty', 'value'], ['deathLinkLockTasks', 'checked'],
  ['deathLinkPool', 'value'], ['distributeGlobal', 'checked'], ['offlineEnabled', 'checked'],
  ['offlineRate', 'value'], ['offlineCapHours', 'value'], ['goalTask', 'value'],
];

const styleOpts = () => ({
  specs: THEME_COLORS,
  get: () => model.styleColors,
  set: colors => { model.styleColors = colors; },
  onChange: () => changed(),
});

function loadModel(next) {
  model = next;
  for (const [key, prop] of FIELDS) els[key][prop] = prop === 'checked' ? !!model[key] : model[key];
  renderStyleColors(els.style, styleOpts());
  changed({ save: false, rebuild: true });
}

function bind(key, node) {
  els[key] = node;
  const prop = node.type === 'checkbox' ? 'checked' : 'value';
  node.addEventListener(node.tagName === 'SELECT' || node.type === 'checkbox' ? 'change' : 'input', () => {
    let value = node[prop];
    if (key === 'playerName') {
      value = limitPlayerName(value);
      if (value !== node.value) node.value = value;
    }
    model[key] = value;
    changed();
  });
  return node;
}

const numberInput = (key, min, max) => bind(key, h('input', { type: 'number', min, max, step: 1, className: 'count-input' }));

// =============================================================
// Conveniences
// =============================================================

async function runCurveFill() {
  const first = els.curveFirst.value;
  const growth = els.curveGrowth.value;
  const result = curveFill(model, first, growth);
  if (result.error) {
    await alertDialog('error', ...result.error);
    return;
  }
  model.tasks = result.tasks;
  changed({ rebuild: true });
}

// =============================================================
// File actions
// =============================================================

async function exportClicker() {
  const result = buildClickerExport(model);
  if (result.error) {
    await alertDialog('error', ...result.error);
    return;
  }
  if (result.trimmed > 0) {
    const n = result.trimmed;
    const ok = await confirmDialog('Too Many Upgrade Copies',
      `This slot has one item per task, so the last ${n} upgrade cop${n === 1 ? 'y' : 'ies'} `
      + 'will be trimmed and never enter the pool.\n\nExport anyway?');
    if (!ok) return;
  }
  const fileName = `${safeFileName(result.data.name)}.yaml`;
  downloadText(fileName, dumpYaml(result.data));
  await alertDialog('info', 'Success', `Tasclickpelago YAML exported as:\n${fileName}`);
}

async function saveSettings() {
  const doc = clickerSettingsDoc(model);
  const fileName = `${safeFileName(doc.player_name, 'tasclickpelago')}.clicker`;
  downloadText(fileName, dumpYaml(doc));
  await alertDialog('info', 'Saved', `Clicker settings saved as:\n${fileName}`);
}

async function loadFile() {
  const file = await pickTextFile('.clicker,.yaml,.yml');
  if (!file) return;
  let doc;
  try {
    if (file.error) throw file.error;
    doc = loadYaml(file.text);
  } catch (e) {
    await alertDialog('error', 'Error', `Failed to read file:\n${e.message}`);
    return;
  }
  let result;
  try {
    result = loadClickerDoc(model, doc);
  } catch (e) {
    if (!(e instanceof PyError)) throw e;
    await alertDialog('error', 'Error', `Failed to load file:\n${e.message}`);
    return;
  }
  for (const [kind, title, text] of result.messages) await alertDialog(kind, title, text);
  if (!result.ok) return;
  loadModel(result.model);
  saveDraft();
  if (result.kind === 'settings') await alertDialog('info', 'Loaded', `Clicker settings loaded from:\n${file.name}`);
  else await alertDialog('info', 'Imported', `Imported Tasclickpelago YAML from:\n${file.name}`);
}

async function clearTab() {
  if (!(await confirmDialog('Clear Tasclickpelago', 'Clear every field and start over?\n\nThis cannot be undone.'))) return;
  loadModel(defaultClickerModel());
  saveDraft();
}

// =============================================================
// Layout
// =============================================================

// [label, tooltip] gets the same "?" marker the YAML Generator tables use.
const headRow = labels => h('thead', {}, h('tr', {},
  labels.map(l => (Array.isArray(l) ? h('th', {}, tipHeader(l[0], l[1])) : h('th', {}, l)))));

// Collapsible sections, mirroring the YAML Generator tab. Open state persists
// per section under its own UI pref key.
const SECTION_PREF = 'clickerSections';
const SECTION_DEFAULTS = {
  intro: true, settings: true, tasks: true, upgrades: true,
  regions: false, offline: false, deathlink: false, style: false,
};

function section(key, title, ...body) {
  let open = getUiPref(SECTION_PREF, {})[key] ?? SECTION_DEFAULTS[key];
  const details = h('details', { className: 'gen-section', open },
    h('summary', {}, title),
    h('div', { className: 'gen-section-body' }, ...body));
  // Creating an open <details> also fires toggle; only store real changes.
  details.addEventListener('toggle', () => {
    if (details.open === open) return;
    open = details.open;
    setUiPref(SECTION_PREF, { ...getUiPref(SECTION_PREF, {}), [key]: details.open });
  });
  return details;
}

const INTRO = 'Tasclickpelago turns your task list into an idle game. Each task needs a number of '
  + 'activations instead of one Complete press: clicking adds your click value, and upgrades you '
  + 'receive add activations per second on their own.\n\n'
  + 'A locked task never accrues anything, from any source, and nothing is banked for it, so an '
  + 'upgrade aimed at content you have not reached yet does nothing until you reach it.\n\n'
  + 'Every numeric cell accepts a plain number or a small expression over N_TASKS, '
  + 'N_TASKS_UNLOCKED, N_TASKS_LOCKED and N_TASKS_COMPLETED. The preview under each cell shows '
  + 'the value at both ends of the curve. Activations take N_TASKS only, since the requirement is '
  + 'fixed when the seed is generated.\n\n'
  + 'Upgrades are what this slot puts into the multiworld pool, not per-task rewards: '
  + 'Archipelago decides where each one lands, which may be another player\'s world. Copies sets '
  + 'how many of an upgrade enter the pool, and each copy you receive adds its rate again.\n\n'
  + 'The slot contributes exactly one item per task, so total copies above the task count are '
  + 'trimmed and any shortfall becomes random filler.\n\n'
  + 'Everything else works like the YAML Generator tab. Tasks carry task prereqs and item '
  + 'prereqs with the same syntax, and references read the same way everywhere: a quoted '
  + '"Task Name", a bare region name, or a number. An upgrade set to "Unlock only" grants '
  + 'nothing and exists purely to be named in a task\'s item prereqs.';

const TARGET_TIP = 'Who the value applies to, in the usual Taskipelago reference syntax: * for '
  + 'every task, a bare Region name for one region, or a quoted "Task Name" or task number for one '
  + 'task. Join several with &&.';
const ACTIVATION_TIP = 'Activations needed to finish this task. Blank means 1. N_TASKS only.';
const GRANTS_TIP = 'Production adds activations per second. Click power adds to the value of one '
  + 'click. The two multiplier channels are separate: a production multiplier never touches clicks '
  + 'and a click multiplier never touches production. Copies of a multiplier stack multiplicatively.';
const COPIES_TIP = 'How many copies of this upgrade go into the multiworld pool (item_count). '
  + 'Each copy adds its rate again when you receive it.';
const DISTRIBUTED_TIP = 'Off: the rate applies in full to each eligible task in the region. '
  + 'On: the rate is split evenly among them, so the region\'s total throughput stays constant '
  + 'and each share rises as siblings complete.';
const OFFLINE_RATE_TIP = 'The fraction of live production that accrues while away. Blank inherits '
  + 'the global away rate.';

function build(root) {
  els.taskCount = h('span', { className: 'muted-text bingo-count' });
  els.upgradeCount = h('span', { className: 'muted-text bingo-count' });
  els.warnings = h('div', { className: 'clicker-warnings' });
  els.offlineExample = h('div', { className: 'muted-text' });
  els.taskRows = h('tbody');
  els.regionRows = h('tbody');
  els.upgradeRows = h('tbody');
  els.style = h('div', { className: 'style-grid' });
  els.curveFirst = h('input', { type: 'number', min: 1, step: 1, value: 10, className: 'count-input' });
  els.curveGrowth = h('input', { type: 'number', min: 0.01, step: 0.05, value: 1.5, className: 'count-input' });
  const label = (text, node) => h('label', { className: 'inline-label' }, text, node);

  const nameStrip = h('div', { className: 'gen-namebar' },
    h('label', { className: 'inline-label', htmlFor: 'clicker-player-name' }, 'Player Name:'),
    bind('playerName', h('input', {
      type: 'text', spellcheck: false, autocomplete: 'off', id: 'clicker-player-name',
    })),
    h('span', { className: 'muted-text' }, `(max ${MAX_PLAYER_NAME_LEN} chars)`),
    h('span', { className: 'spacer' }));

  const intro = section('intro', 'How Tasclickpelago Works',
    h('div', { className: 'clicker-intro' }, INTRO));

  const settings = section('settings', 'Clicker Settings',
    h('div', { className: 'gen-settings' },
      label('Prog. Balancing:', numberInput('progressionBalancing', 0, 99)),
      label('Accessibility:', bind('accessibility', h('select', {},
        ['full', 'items', 'minimal'].map(v => h('option', { value: v }, v))))),
      label('Goal task #:', numberInput('goalTask', 0, 999)),
      h('label', { className: 'check-label', title: 'Split a *-targeted rate evenly among the eligible tasks.' },
        bind('distributeGlobal', h('input', { type: 'checkbox' })), 'Distribute global production')),
    els.warnings);

  const tasks = section('tasks', 'Tasks',
    h('div', { className: 'clicker-toolbar' }, els.taskCount,
      h('span', { className: 'spacer' }),
      label('First cost:', els.curveFirst),
      label('Growth:', els.curveGrowth),
      h('button', { type: 'button', onclick: runCurveFill, title: 'Fill the activations column geometrically.' }, 'Curve Fill')),
    h('div', { className: 'gen-table-scroll' },
      h('table', { className: 'clicker-table' },
        headRow(['#', 'Task', ['Activations', ACTIVATION_TIP], ['Region', TIPS.region_col],
          ['Task prereqs', TIPS.task_prereq], ['Item prereqs', TIPS.item_prereq], '']),
        els.taskRows)),
    h('div', { className: 'btn-row' },
      h('button', {
        type: 'button',
        onclick: () => { model.tasks.push(defaultTaskRow()); changed({ rebuild: true }); },
      }, 'Add Task')));

  const upgrades = section('upgrades', 'Upgrades',
    h('div', { className: 'clicker-toolbar' }, els.upgradeCount,
      h('span', { className: 'spacer' }),
      constantsPalette()),
    h('div', { className: 'gen-table-scroll' },
      h('table', { className: 'clicker-table' },
        headRow(['Upgrade', 'Item type', ['Copies', COPIES_TIP], 'Group', ['Grants', GRANTS_TIP],
          ['Target', TARGET_TIP], 'Value', '']),
        els.upgradeRows)),
    h('div', { className: 'btn-row' },
      h('button', {
        type: 'button',
        onclick: () => { model.upgrades.push(defaultUpgradeRow()); changed({ rebuild: true }); },
      }, 'Add Upgrade')));

  const regions = section('regions', 'Regions',
    h('div', { className: 'clicker-toolbar' },
      h('span', { className: 'muted-text' }, 'Distributed splits a region rate among its eligible tasks.')),
    h('div', { className: 'gen-table-scroll' },
      h('table', { className: 'clicker-table' },
        headRow(['Region', 'Color', 'Default %', ['Distributed', DISTRIBUTED_TIP],
          ['Offline rate', OFFLINE_RATE_TIP], '']),
        els.regionRows)),
    h('div', { className: 'btn-row' },
      h('button', {
        type: 'button',
        onclick: () => { model.regions.push(defaultRegionRow()); changed({ rebuild: true }); },
      }, 'Add Region')));

  const offline = section('offline', 'Offline Production',
    h('div', { className: 'gen-settings' },
      h('label', { className: 'check-label' },
        bind('offlineEnabled', h('input', { type: 'checkbox' })), 'Enable offline production'),
      label('Away rate:', bind('offlineRate', h('input', { type: 'text', spellcheck: false, className: 'clicker-cell' }))),
      label('Cap (hours):', numberInput('offlineCapHours', 0, 168))),
    els.offlineExample);

  const deathlink = section('deathlink', 'DeathLink',
    h('div', { className: 'gen-settings' },
      h('label', { className: 'check-label' }, bind('deathLinkEnabled', h('input', { type: 'checkbox' })), 'Enable DeathLink'),
      label('Amnesty:', numberInput('deathLinkAmnesty', 0, 999)),
      h('label', { className: 'check-label', title: DL_LOCK_TIP },
        bind('deathLinkLockTasks', h('input', { type: 'checkbox' })), 'Lock other tasks until DeathLink tasks are done')),
    h('label', { className: 'stack-label' }, 'Pool (one per line):',
      bind('deathLinkPool', h('textarea', { className: 'bingo-dl-text', rows: 3, spellcheck: false }))));

  const style = section('style', 'Style',
    h('div', { className: 'muted-text', title: STYLE_SECTION_TIP }, 'Colors applied while connected to this slot'),
    els.style,
    h('div', { className: 'btn-row' },
      h('button', { type: 'button', onclick: () => resetStyleColors(els.style, styleOpts()) }, 'Reset Colors')));

  const bottom = h('div', { className: 'gen-bottom' },
    h('button', { type: 'button', onclick: clearTab }, 'Clear'),
    h('span', { className: 'spacer' }),
    h('button', { type: 'button', onclick: saveSettings }, 'Save Settings'),
    h('button', { type: 'button', onclick: loadFile }, 'Load'),
    h('button', { type: 'button', className: 'primary', onclick: exportClicker }, 'Export Clicker YAML'));

  root.replaceChildren(
    h('div', { className: 'gen-scroll clicker-gen' },
      nameStrip, intro, settings, tasks, upgrades, regions, offline, deathlink, style),
    bottom);
}

export function initClickerGen(root = $('clicker-gen-root')) {
  if (!root) return;
  build(root);
  loadModel(normalizeClickerModel(storage.get(DRAFT_KEY)));
  addEventListener('pagehide', () => {
    if (!saveTimer) return;
    saveDraft();
    storage.flush(true);
  });
}
