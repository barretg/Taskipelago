// YAML Generator tab (UNIFY 5.3). Editor state lives in ctx.model
// (generator/model.js); every edit autosaves a draft to device storage (3.2).
import * as storage from '../shared/storage.js';
import { $, h } from '../shared/dom.js';
import { alertDialog, confirmDialog } from '../shared/dialog.js';
import { downloadText, pickTextFile, safeFileName } from '../shared/files.js';
import { PyError, pyInt } from '../shared/pyish.js';
import { tipHeader } from '../shared/tooltip.js';
import { getUiPref, setUiPref } from '../shared/ui_prefs.js';
import { dumpYaml, loadYaml } from '../shared/yaml11.js';
import { TIPS } from './legacy_text.js';
import {
  DEATHLINK_LOCK_TIP, MAX_PLAYER_NAME_LEN, TASK_REWARD_PREVIEW_LABELS, defaultModel, limitPlayerName, normalizeModel, slotCounts,
} from './model.js';
import { finalCounts, usesRandomization } from './randomize_check.js';
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
import { STYLE_SECTION_TIP, renderStyleColors, resetStyleColors } from './style_section.js';
import { curveFill, offlineExample } from './clicker_fields.js';
import { TIPS as CLICKER_TIPS } from './clicker_cells.js';

export const DRAFT_KEY = 'taskipelago_draft_generator';
const SAVE_DELAY_MS = 400;
const SECTION_DEFAULTS = {
  regions: false, tasks: true, items: true, clicker: false, deathlink: false, style: false,
};

const GLOBAL_SPLIT_TIP = 'Split a rate aimed at * evenly among the eligible tasks, instead of '
  + 'granting it in full to each of them.';

const CLICKER_TIP = 'Tasclickpelago: each task needs a number of activations instead of one '
  + 'Complete press. Clicking adds your click value, and items you receive can add activations per '
  + 'second on their own.\n\n'
  + 'Turning this on adds the clicker columns to the task and item tables and the Clicker section '
  + 'below. Everything else on this tab keeps working the same way, and turning it off again '
  + 'exports a plain Taskipelago YAML.';

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
  if (parts.style) renderStyleColors(els.style, styleOpts());
  if (parts.clicker) syncClicker();
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
  const { tasks, items } = counterCounts(ctx.model);
  els.counter.textContent = `${items}/${tasks} items`;
  els.counter.classList.toggle('warning-text', items !== tasks);
}

/** Slot counts for the header; per-seed final counts when regions or groups are randomized. */
function counterCounts(model) {
  const used = usesRandomization(model);
  if (!used.regions && !used.groups) return slotCounts(model);
  const count = r => { try { return Math.max(1, pyInt(r.count)); } catch (_) { return 1; } };
  return finalCounts(
    model,
    model.tasks.map(t => ({ count: count(t), region: t.region })),
    model.items.map(it => ({ count: count(it), group: it.progGroup, filler: !!it.filler })),
  );
}

/** Reflect clicker mode: the section only exists while the mode is on. */
function syncClicker() {
  const on = !!ctx.model.clickerMode;
  els.clickerToggle.checked = on;
  els.sections.clicker.classList.toggle('hidden', !on);
  els.distributeGlobal.checked = !!ctx.model.clickerDistributeGlobal;
  els.offlineEnabled.checked = !!ctx.model.clickerOffline;
  els.offlineRate.value = ctx.model.clickerOfflineRate;
  els.offlineCap.value = ctx.model.clickerOfflineCapHours;
  els.offlineExample.textContent = offlineExample(ctx.model);
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
  changed({ tasks: true, items: true, regions: true, groups: true, deathlink: true, style: true, clicker: true },
    { save: false });
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

async function runCurveFill() {
  const result = curveFill(ctx.model.tasks, els.curveFirst.value, els.curveGrowth.value);
  if (result.error) {
    await alertDialog('error', ...result.error);
    return;
  }
  ctx.model.tasks = result.tasks;
  changed({ tasks: true });
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

/** Style section wiring: the pickers read and write ctx.model.styleColors. */
const styleOpts = () => ({
  get: () => ctx.model.styleColors,
  set: colors => { ctx.model.styleColors = colors; },
  onChange: () => changed(),
});

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

  els.clickerToggle = h('input', {
    type: 'checkbox', id: 'gen-clicker-mode',
    onchange: e => {
      ctx.model.clickerMode = e.target.checked;
      changed({ tasks: true, items: true, regions: true, clicker: true });
    },
  });
  const modeStrip = h('div', { className: 'gen-namebar' },
    h('label', { className: 'check-label' }, els.clickerToggle,
      tipHeader('Enable Tasclickpelago', CLICKER_TIP)));

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

  els.curveFirst = h('input', { type: 'text', className: 'count-input', value: '10', spellcheck: false });
  els.curveGrowth = h('input', { type: 'text', className: 'count-input', value: '1.5', spellcheck: false });
  els.distributeGlobal = h('input', { type: 'checkbox', onchange: setting('clickerDistributeGlobal') });
  els.offlineEnabled = h('input', {
    type: 'checkbox',
    onchange: e => { ctx.model.clickerOffline = e.target.checked; changed({ clicker: true }); },
  });
  els.offlineRate = h('input', {
    type: 'text', className: 'count-input', spellcheck: false,
    oninput: e => { ctx.model.clickerOfflineRate = e.target.value; changed({ clicker: true }); },
  });
  els.offlineCap = h('input', {
    type: 'number', min: 0, max: 168, className: 'count-input',
    oninput: e => { ctx.model.clickerOfflineCapHours = e.target.value; changed({ clicker: true }); },
  });
  els.offlineExample = h('div', { className: 'muted-text' });
  const clicker = section('clicker', 'Clicker',
    h('div', { className: 'gen-settings' },
      h('label', { className: 'check-label' }, els.distributeGlobal,
        tipHeader('Distribute global production', GLOBAL_SPLIT_TIP)),
      h('label', { className: 'inline-label' }, 'First cost:', els.curveFirst),
      h('label', { className: 'inline-label' }, 'Growth:', els.curveGrowth),
      h('button', {
        type: 'button', onclick: runCurveFill,
        title: 'Fill the Activations column geometrically: first cost, then multiplied by growth each row.',
      }, 'Curve Fill')),
    h('div', { className: 'gen-settings' },
      h('label', { className: 'check-label' }, els.offlineEnabled, 'Offline production'),
      h('label', { className: 'inline-label' },
        tipHeader('Away rate:', CLICKER_TIPS.offlineRate), els.offlineRate),
      h('label', { className: 'inline-label' }, 'Cap (hours):', els.offlineCap)),
    els.offlineExample);

  els.style = h('div', { className: 'style-grid' });
  const style = section('style', 'Style',
    h('div', { className: 'gen-settings' },
      tipHeader('Colors applied while connected to this slot', STYLE_SECTION_TIP)),
    els.style,
    h('div', { className: 'btn-row' },
      h('button', {
        type: 'button', onclick: () => resetStyleColors(els.style, styleOpts()),
      }, 'Reset Colors')));

  const bottom = h('div', { className: 'gen-bottom' },
    h('button', { type: 'button', onclick: resetGenerator }, 'Reset'),
    h('span', { className: 'spacer' }),
    h('button', { type: 'button', onclick: importYaml }, 'Import YAML'),
    h('button', { type: 'button', className: 'primary', onclick: exportYaml }, 'Export YAML'));

  root.replaceChildren(
    h('div', { className: 'gen-scroll' }, nameStrip, modeStrip, regions, tasks, items, clicker, deathlink, style),
    bottom);
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
