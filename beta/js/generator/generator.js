// YAML Generator tab (UNIFY 5.3). Editor state lives in ctx.model
// (generator/model.js); every edit autosaves a draft to device storage (3.2).
import * as storage from '../shared/storage.js';
import { $, h } from '../shared/dom.js';
import { alertDialog, confirmDialog } from '../shared/dialog.js';
import { downloadText, pickTextFile, safeFileName } from '../shared/files.js';
import { PyError } from '../shared/pyish.js';
import { tipHeader } from '../shared/tooltip.js';
import { getUiPref, setUiPref } from '../shared/ui_prefs.js';
import { dumpYaml, loadYaml } from '../shared/yaml11.js';
import { TIPS } from './legacy_text.js';
import {
  DEATHLINK_LOCK_TIP, MAX_PLAYER_NAME_LEN, TASK_REWARD_PREVIEW_LABELS, defaultModel, limitPlayerName, normalizeModel, slotCounts,
} from './model.js';
import { buildExport } from './yaml_export.js';
import { importDoc } from './yaml_import.js';
import { addTask, renderTaskTable } from './task_rows.js';
import { addItem, renderItemTable } from './item_rows.js';
import { buildRegionAddRow, renderRegions } from './regions.js';
import { buildGroupAddRow, renderProgGroups } from './prog_groups.js';
import { addDeathLink, renderDeathLinkTable } from './deathlink_rows.js';
import { openTutorial } from './tutorial.js';
import { openCommunityYamls } from './community.js';
import { reorderUpdatesRefs, setReorderUpdatesRefs } from './reorder.js';
import { openFindReplace } from './find_replace.js';

export const DRAFT_KEY = 'taskipelago_draft_generator';
const SAVE_DELAY_MS = 400;
const SECTION_DEFAULTS = { regions: false, tasks: true, items: true, deathlink: false };

const ctx = { model: defaultModel(), changed, root: null, openSection };
const els = {};
let saveTimer = null;

function saveDraft() {
  clearTimeout(saveTimer);
  saveTimer = null;
  storage.set(DRAFT_KEY, ctx.model);
}

function changed(parts = {}, { save = true } = {}) {
  if (parts.tasks) renderTaskTable(els.tasks, ctx);
  if (parts.items) renderItemTable(els.items, ctx);
  if (parts.regions) renderRegions(els.regions, ctx);
  if (parts.groups) renderProgGroups(els.groups, ctx);
  if (parts.deathlink) renderDeathLinkTable(els.deathlink, ctx);
  if (parts.goal) els.goalTasks.value = ctx.model.goalTasks;
  updateCounter();
  if (parts.focusLast) {
    const rows = els[parts.focusLast].querySelectorAll('.gt-task, .gt-item, .dl-row:not(.gt-head)');
    rows[rows.length - 1]?.querySelector('input')?.focus();
  }
  if (!save) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveDraft, SAVE_DELAY_MS);
}

function updateCounter() {
  const { tasks, items } = slotCounts(ctx.model);
  els.counter.textContent = `${items}/${tasks} items`;
  els.counter.classList.toggle('warning-text', items !== tasks);
}

/** Show a whole new model (reset, import, draft restore). Callers save when it is a change. */
function loadModel(model) {
  ctx.model = model;
  const m = ctx.model;
  els.playerName.value = m.playerName;
  els.lockPrereqs.checked = !!m.lockPrereqs;
  els.hideUnreachable.checked = !!m.hideUnreachable;
  els.rewardPreviews.value = String(m.taskRewardPreviews);
  els.goalTasks.value = m.goalTasks;
  els.progression.value = m.progressionBalancing;
  els.accessibility.value = m.accessibility;
  els.deathLinkEnabled.checked = !!m.deathLinkEnabled;
  els.deathLinkLock.checked = !!m.deathLinkLockTasks;
  els.amnesty.value = m.deathLinkAmnesty;
  changed({ tasks: true, items: true, regions: true, groups: true, deathlink: true }, { save: false });
}

// ---------------------------------------------------------------------------
// Import / export / reset
// ---------------------------------------------------------------------------

/**
 * Apply a parsed YAML document. Shows the legacy error and warning dialogs;
 * resolves true when the editor was replaced.
 */
export async function applyDoc(doc, successMessage = '') {
  let result;
  try {
    result = importDoc(ctx.model, doc);
  } catch (e) {
    if (!(e instanceof PyError)) throw e;
    await alertDialog('error', 'Error', `Failed to import YAML:\n${e.message}`);
    return false;
  }
  for (const [kind, title, text] of result.messages) if (kind === 'error') await alertDialog('error', title, text);
  if (!result.ok) return false;
  loadModel(result.model);
  saveDraft();
  for (const [kind, title, text] of result.messages) if (kind === 'warning') await alertDialog('warning', title, text);
  if (successMessage) await alertDialog('info', 'Imported', successMessage);
  return true;
}

async function importYaml() {
  const file = await pickTextFile();
  if (!file) return;
  let doc;
  try {
    if (file.error) throw file.error;
    doc = loadYaml(file.text);
  } catch (e) {
    await alertDialog('error', 'Error', `Failed to read YAML:\n${e.message}`);
    return;
  }
  await applyDoc(doc, `Imported YAML from:\n${file.name}`);
}

async function exportYaml() {
  let result;
  try {
    result = await buildExport(ctx.model, { confirm: confirmDialog });
  } catch (e) {
    await alertDialog('error', 'Error', `Export failed:\n${e.message}`);
    return;
  }
  if (result.error) {
    await alertDialog('error', ...result.error);
    return;
  }
  if (result.cancelled) return;
  const fileName = `${safeFileName(result.data.name)}.yaml`;
  downloadText(fileName, dumpYaml(result.data));
  await alertDialog('info', 'Success', `YAML exported as:\n${fileName}`);
}

async function resetGenerator() {
  const ok = await confirmDialog('Reset YAML Generator',
    'Clear every field and start over?\n\nThis cannot be undone. Export first if you want to keep your work.');
  if (!ok) return;
  loadModel(defaultModel());
  saveDraft();
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

/** Expand a collapsible section (F5 find); the toggle listener stores the change. */
function openSection(key) {
  if (els.sections?.[key]) els.sections[key].open = true;
}

function section(key, title, ...body) {
  let open = getUiPref('generatorSections', {})[key] ?? SECTION_DEFAULTS[key];
  const details = h('details', { className: 'gen-section', open },
    h('summary', {}, title),
    h('div', { className: 'gen-section-body' }, ...body));
  // Creating an open <details> also fires toggle; only store real changes.
  details.addEventListener('toggle', () => {
    if (details.open === open) return;
    open = details.open;
    const prefs = { ...getUiPref('generatorSections', {}) };
    prefs[key] = details.open;
    setUiPref('generatorSections', prefs);
  });
  els.sections = els.sections || {};
  els.sections[key] = details;
  return details;
}

const setting = (key, parse = v => v) => e => {
  ctx.model[key] = parse(e.target.type === 'checkbox' ? e.target.checked : e.target.value);
  changed();
};

function build(root) {
  els.playerName = h('input', {
    type: 'text', spellcheck: false, autocomplete: 'off', id: 'gen-player-name',
    oninput: e => {
      const limited = limitPlayerName(e.target.value);
      if (limited !== e.target.value) e.target.value = limited;
      ctx.model.playerName = limited;
      changed();
    },
  });
  const nameStrip = h('div', { className: 'gen-namebar' },
    h('label', { className: 'inline-label', htmlFor: 'gen-player-name' }, 'Player Name:'),
    els.playerName,
    h('span', { className: 'muted-text' }, `(max ${MAX_PLAYER_NAME_LEN} chars)`),
    h('span', { className: 'spacer' }),
    h('label', {
      className: 'check-label',
      title: 'When on, moving a task or item with the up/down carets also updates index references to it.',
    }, h('input', {
      type: 'checkbox', checked: reorderUpdatesRefs(), id: 'gen-reorder-refs',
      onchange: e => setReorderUpdatesRefs(e.target.checked),
    }), 'Reordering updates references'),
    h('button', { type: 'button', onclick: () => openFindReplace(ctx) }, 'Find/Replace'),
    h('button', { type: 'button', onclick: () => openCommunityYamls(applyDoc) }, 'Community YAMLs'),
    h('button', { type: 'button', onclick: openTutorial }, 'Tutorial'));

  els.regions = h('div', { className: 'region-list' });
  const regions = section('regions', 'Regions', els.regions, buildRegionAddRow(ctx));

  els.lockPrereqs = h('input', { type: 'checkbox', onchange: setting('lockPrereqs') });
  els.hideUnreachable = h('input', { type: 'checkbox', onchange: setting('hideUnreachable') });
  els.rewardPreviews = h('select', { onchange: setting('taskRewardPreviews', Number) },
    TASK_REWARD_PREVIEW_LABELS.map((label, i) => h('option', { value: String(i) }, label)));
  els.goalTasks = h('input', {
    type: 'text', spellcheck: false, className: 'goal-input', dataset: { field: 'goalTasks' }, oninput: setting('goalTasks'),
  });
  els.tasks = h('div', { className: 'gen-table gen-task-table' });
  const tasks = section('tasks', 'Tasks',
    h('div', { className: 'gen-settings' },
      h('label', { className: 'check-label' }, els.lockPrereqs, 'In logic only (lock task completion behind prereqs)'),
      h('label', { className: 'check-label' }, els.hideUnreachable, 'Hide Unreachable Tasks'),
      h('label', { className: 'inline-label' }, tipHeader('Reward Previews:', TIPS.reward_preview), els.rewardPreviews),
      h('label', { className: 'inline-label' }, tipHeader('Goal task(s):', TIPS.goal_tasks), els.goalTasks,
        h('span', { className: 'muted-text' }, '(blank = all)'))),
    h('div', { className: 'gen-table-scroll' }, els.tasks),
    h('div', { className: 'btn-row' }, h('button', { type: 'button', onclick: () => addTask(ctx) }, 'Add Task')));

  els.progression = h('input', { type: 'number', min: 0, max: 99, className: 'count-input', oninput: setting('progressionBalancing') });
  els.accessibility = h('select', { onchange: setting('accessibility') },
    ['full', 'items', 'minimal'].map(v => h('option', { value: v }, v)));
  els.counter = h('span', { className: 'muted-text item-counter' });
  els.groups = h('div', { className: 'region-list' });
  els.items = h('div', { className: 'gen-table gen-item-table' });
  const items = section('items', 'Items',
    h('div', { className: 'gen-settings' },
      h('label', { className: 'inline-label' }, 'Progression Balancing (0-99):', els.progression),
      h('label', { className: 'inline-label' }, 'Accessibility:', els.accessibility),
      els.counter),
    h('fieldset', { className: 'panel gen-groups' }, h('legend', {}, 'Item Groups'), els.groups, buildGroupAddRow(ctx)),
    h('div', { className: 'gen-table-scroll' }, els.items),
    h('div', { className: 'btn-row' }, h('button', { type: 'button', onclick: () => addItem(ctx) }, 'Add Item')));

  els.deathLinkEnabled = h('input', { type: 'checkbox', onchange: setting('deathLinkEnabled') });
  els.amnesty = h('input', { type: 'number', min: 0, max: 999, className: 'count-input', oninput: setting('deathLinkAmnesty') });
  els.deathLinkLock = h('input', { type: 'checkbox', onchange: setting('deathLinkLockTasks') });
  els.deathlink = h('div', { className: 'dl-table' });
  const deathlink = section('deathlink', 'DeathLink',
    h('div', { className: 'gen-settings' },
      h('label', { className: 'check-label' }, els.deathLinkEnabled, 'Enable DeathLink'),
      h('label', { className: 'inline-label' }, 'Amnesty:', els.amnesty),
      h('label', { className: 'check-label' },
        els.deathLinkLock, tipHeader('Lock other tasks until DeathLink tasks are done', DEATHLINK_LOCK_TIP))),
    els.deathlink,
    h('div', { className: 'btn-row' }, h('button', { type: 'button', onclick: () => addDeathLink(ctx) }, 'Add DeathLink Task')));

  const bottom = h('div', { className: 'gen-bottom' },
    h('button', { type: 'button', onclick: resetGenerator }, 'Reset'),
    h('span', { className: 'spacer' }),
    h('button', { type: 'button', onclick: importYaml }, 'Import YAML'),
    h('button', { type: 'button', className: 'primary', onclick: exportYaml }, 'Export YAML'));

  root.replaceChildren(h('div', { className: 'gen-scroll' }, nameStrip, regions, tasks, items, deathlink), bottom);
}

export function initGenerator(root = $('generator-root')) {
  if (!root) return;
  ctx.root = root;
  build(root);
  document.addEventListener('keydown', e => {
    const key = e.key.toLowerCase();
    if (!(e.ctrlKey || e.metaKey) || e.altKey || (key !== 'f' && key !== 'h')) return;
    if (!document.getElementById('tab-generator')?.classList.contains('active')) return;
    e.preventDefault();
    openFindReplace(ctx, key === 'h' ? 'replace' : 'find');
  });
  loadModel(normalizeModel(storage.get(DRAFT_KEY)));
  addEventListener('pagehide', () => {
    if (!saveTimer) return;
    saveDraft();
    storage.flush(true);
  });
}

/** Test hook: the live editor model. */
export const generatorModel = () => ctx.model;
