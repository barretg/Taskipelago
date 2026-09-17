// Taskipelabingo tab (UNIFY 5.5, legacy client.py:5518-5710). Logic lives in
// bingo_model.js; every edit autosaves a draft to device storage (3.2).
import * as storage from '../shared/storage.js';
import { $, h } from '../shared/dom.js';
import { alertDialog, confirmDialog } from '../shared/dialog.js';
import { downloadText, pickTextFile, safeFileName } from '../shared/files.js';
import { PyError } from '../shared/pyish.js';
import { dumpYaml, loadYaml } from '../shared/yaml11.js';
import { limitPlayerName } from '../generator/model.js';
import {
  bingoCounts, bingoSettingsDoc, buildBingoExport, defaultBingoModel, loadBingoDoc, normalizeBingoModel,
} from './bingo_model.js';

export const DRAFT_KEY = 'taskipelago_draft_bingo';
const SAVE_DELAY_MS = 400;

let model = defaultBingoModel();
const els = {};
let saveTimer = null;

function saveDraft() {
  clearTimeout(saveTimer);
  saveTimer = null;
  storage.set(DRAFT_KEY, model);
}

function changed({ save = true } = {}) {
  const counts = bingoCounts(model);
  els.spacesCount.textContent = counts.spaces;
  els.rewardsCount.textContent = counts.rewards;
  if (!save) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveDraft, SAVE_DELAY_MS);
}

const FIELDS = [
  ['playerName', 'value'], ['x', 'value'], ['y', 'value'], ['bingoal', 'value'],
  ['progressionBalancing', 'value'], ['accessibility', 'value'], ['deathLinkEnabled', 'checked'],
  ['deathLinkAmnesty', 'value'], ['spaces', 'value'], ['rewards', 'value'], ['deathLinkPool', 'value'],
];

function loadModel(next) {
  model = next;
  for (const [key, prop] of FIELDS) els[key][prop] = prop === 'checked' ? !!model[key] : model[key];
  changed({ save: false });
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

async function exportBingo() {
  const result = buildBingoExport(model);
  if (result.error) {
    await alertDialog('error', ...result.error);
    return;
  }
  if (result.unusedRewards > 0) {
    const n = result.unusedRewards;
    if (!(await confirmDialog('Unused Rewards', `${n} reward${n === 1 ? '' : 's'} will be unused. Export anyway?`))) return;
  }
  const fileName = `${safeFileName(result.data.name)}.yaml`;
  downloadText(fileName, dumpYaml(result.data));
  await alertDialog('info', 'Success', `Bingo YAML exported as:\n${fileName}`);
}

async function saveSettings() {
  const doc = bingoSettingsDoc(model);
  const fileName = `${safeFileName(doc.player_name, 'taskipelabingo')}.bingo`;
  downloadText(fileName, dumpYaml(doc));
  await alertDialog('info', 'Saved', `Bingo settings saved as:\n${fileName}`);
}

async function loadFile() {
  const file = await pickTextFile('.bingo,.yaml,.yml');
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
    result = loadBingoDoc(model, doc);
  } catch (e) {
    if (!(e instanceof PyError)) throw e;
    await alertDialog('error', 'Error', `Failed to load file:\n${e.message}`);
    return;
  }
  for (const [kind, title, text] of result.messages) await alertDialog(kind, title, text);
  if (!result.ok) return;
  loadModel(result.model);
  saveDraft();
  if (result.kind === 'settings') await alertDialog('info', 'Loaded', `Bingo settings loaded from:\n${file.name}`);
  else await alertDialog('info', 'Imported', `Imported Bingo YAML from:\n${file.name}`);
}

async function clearTab() {
  if (!(await confirmDialog('Clear Taskipelabingo', 'Clear every field and start over?\n\nThis cannot be undone.'))) return;
  loadModel(defaultBingoModel());
  saveDraft();
}

function build(root) {
  els.spacesCount = h('div', { className: 'muted-text bingo-count' });
  els.rewardsCount = h('div', { className: 'muted-text bingo-count' });
  const label = (text, node) => h('label', { className: 'inline-label' }, text, node);
  root.replaceChildren(
    h('div', { className: 'gen-scroll bingo-gen' },
      h('fieldset', { className: 'panel' }, h('legend', {}, 'Bingo Settings'),
        h('div', { className: 'gen-namebar' },
          label('Player Name:', bind('playerName', h('input', { type: 'text', spellcheck: false, autocomplete: 'off' })))),
        h('div', { className: 'gen-settings' },
          label('Columns (X):', numberInput('x', 1, 20)),
          label('Rows (Y):', numberInput('y', 1, 20)),
          label('Bingos to goal:', numberInput('bingoal', 1, 100)),
          label('Prog. Balancing:', numberInput('progressionBalancing', 0, 99)),
          label('Accessibility:', bind('accessibility', h('select', {},
            ['full', 'items', 'minimal'].map(v => h('option', { value: v }, v))))))),
      h('div', { className: 'bingo-columns' },
        h('fieldset', { className: 'panel' }, h('legend', {}, 'Spaces (one per line)'), els.spacesCount,
          bind('spaces', h('textarea', { className: 'bingo-text', spellcheck: false, 'aria-label': 'Spaces' }))),
        h('fieldset', { className: 'panel' }, h('legend', {}, 'Rewards (one per line, optional)'), els.rewardsCount,
          bind('rewards', h('textarea', { className: 'bingo-text', spellcheck: false, 'aria-label': 'Rewards' })))),
      h('fieldset', { className: 'panel' }, h('legend', {}, 'DeathLink'),
        h('div', { className: 'gen-settings' },
          h('label', { className: 'check-label' }, bind('deathLinkEnabled', h('input', { type: 'checkbox' })), 'Enable DeathLink'),
          label('Amnesty:', numberInput('deathLinkAmnesty', 0, 999))),
        h('label', { className: 'stack-label' }, 'Pool (one per line):',
          bind('deathLinkPool', h('textarea', { className: 'bingo-dl-text', rows: 3, spellcheck: false }))))),
    h('div', { className: 'gen-bottom' },
      h('span', { className: 'spacer' }),
      h('button', { type: 'button', onclick: clearTab }, 'Clear'),
      h('button', { type: 'button', onclick: saveSettings }, 'Save Settings'),
      h('button', { type: 'button', onclick: loadFile }, 'Load'),
      h('button', { type: 'button', className: 'primary', onclick: exportBingo }, 'Export Bingo YAML')),
  );
}

export function initBingoGen(root = $('bingo-gen-root')) {
  if (!root) return;
  build(root);
  loadModel(normalizeBingoModel(storage.get(DRAFT_KEY)));
  addEventListener('pagehide', () => {
    if (!saveTimer) return;
    saveDraft();
    storage.flush(true);
  });
}
