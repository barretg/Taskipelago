// YAML Generator, tutorial, Community YAMLs and Taskipelabingo tabs in jsdom
// (UNIFY 5.3, 5.5-5.8): editing, the item row rules, dialogs, draft autosave,
// export downloads and imports.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, bootApp, importModule, $, errors, wait, jsonResponse } from '../helpers/env.mjs';

const communityFiles = {
  abc123def456: 'name: Chores\ngame: Taskipelago\nTaskipelago:\n  tasks: [Sweep, Mop]\n  items: [Broom, Bucket]\n  item_count: ["1", "1"]\n',
};
let communityCalls = 0;

const window = setupDom({
  config: {
    mode: 'hosted', version: '1.1.0', communityEndpoint: 'https://script.example/exec',
    features: { insecureWs: false, localStorageService: false }, launch: null, token: null,
  },
  fetch: async url => {
    const u = new URL(url);
    if (u.origin !== 'https://script.example') return { ok: false, status: 404, json: async () => ({}) };
    communityCalls++;
    if (u.searchParams.get('action') === 'list') {
      return jsonResponse([{ file_id: 'abc123def456', filename: 'Chores_Barret_1-0-2.yaml', slot: 'Chores', author: 'Barret', version: '1.0.2' }]);
    }
    const text = communityFiles[u.searchParams.get('id')];
    return jsonResponse(text ? { file_id: u.searchParams.get('id'), filename: 'Chores_Barret_1-0-2.yaml', text } : { error: 'Unknown community YAML.' });
  },
});

const downloads = [];
URL.createObjectURL = blob => {
  const url = `blob:test/${downloads.length}`;
  downloads.push({ url, blob });
  return url;
};
URL.revokeObjectURL = () => {};
const anchorClick = window.HTMLAnchorElement.prototype.click;
window.HTMLAnchorElement.prototype.click = function click() {
  const d = downloads.find(x => x.url === this.href);
  if (d) d.name = this.download;
  else anchorClick.call(this);
};

await bootApp();

const { loadYaml } = await importModule('shared/yaml11.js');
const { generatorModel, applyDoc, DRAFT_KEY } = await importModule('generator/generator.js');
const { STEPS } = await importModule('generator/tutorial.js');
const doc = window.document;

const root = () => $('generator-root');
const input = (el, value) => {
  el.value = value;
  el.dispatchEvent(new window.Event('input', { bubbles: true }));
};
const change = (el, props) => {
  Object.assign(el, props);
  el.dispatchEvent(new window.Event('change', { bubbles: true }));
};
const button = (scope, label) => [...scope.querySelectorAll('button')].find(b => b.textContent === label);
const topDialog = () => [...doc.querySelectorAll('.dialog-overlay')].pop();
const dialogText = () => topDialog()?.querySelector('.dialog-box').textContent || '';
async function answer(label) {
  await wait(5);
  const dlg = topDialog();
  assert.ok(dlg, `expected a dialog to answer "${label}"`);
  button(dlg, label).click();
  await wait(5);
}

test('generator and bingo tabs are in the tab bar', () => {
  const tabs = [...doc.querySelectorAll('#main-tabs .tab-btn')].map(b => b.textContent);
  assert.deepEqual(tabs, ['Connect and Play', 'Text Console', 'YAML Generator', 'Taskipelabingo']);
  button(doc.getElementById('main-tabs'), 'YAML Generator').click();
  assert.ok($('tab-generator').classList.contains('active'));
  assert.equal(doc.title, 'Taskipelago');
});

test('starts from the legacy default state with one empty task row', () => {
  const m = generatorModel();
  assert.equal(m.tasks.length, 1);
  assert.equal(m.items.length, 0);
  assert.equal(root().querySelectorAll('.gt-task').length, 1);
  assert.equal(root().querySelector('.item-counter').textContent, '0/1 items');
  assert.equal(localStorage.getItem(DRAFT_KEY), null, 'loading the default model does not write a draft');
});

test('player name is limited to 16 characters', () => {
  const name = $('gen-player-name');
  input(name, 'An Extremely Long Player Name');
  assert.equal(name.value, 'An Extremely Lon');
  assert.equal(generatorModel().playerName, 'An Extremely Lon');
  input(name, 'Tester');
});

test('filler, consumable and progressive group follow the legacy row rules', async () => {
  const groupRow = root().querySelector('.gen-groups');
  input(groupRow.querySelector('input'), 'keys');
  button(groupRow, 'Add Group').click();
  await wait(5);
  assert.deepEqual(generatorModel().progGroups, ['keys']);

  button(root(), 'Add Item').click();
  const row = () => root().querySelector('.gt-item');
  const [name] = row().querySelectorAll('input[type="text"]');
  input(name, 'Key');
  const [filler, consumable] = row().querySelectorAll('input[type="checkbox"]');
  const [type, group] = row().querySelectorAll('select');

  change(group, { value: 'keys' });
  assert.equal(type.value, 'progression');
  assert.ok(type.disabled && filler.disabled);

  change(group, { value: '' });
  assert.equal(generatorModel().items[0].type, 'useful');
  assert.ok(!filler.disabled);

  change(consumable, { checked: true });
  assert.equal(generatorModel().items[0].type, 'progression');
  assert.ok(group.disabled);
  change(consumable, { checked: false });

  change(filler, { checked: true });
  const it = generatorModel().items[0];
  assert.equal(it.type, 'junk');
  assert.ok(row().querySelector('input[type="text"]').disabled);
  change(row().querySelectorAll('input[type="checkbox"]')[0], { checked: false });
  assert.equal(generatorModel().items[0].name, 'Key');
  assert.equal(generatorModel().items[0].type, 'useful');
});

test('regions: add, invalid name error, rename updates task rows, remove', async () => {
  const regions = root().querySelector('details.gen-section');
  const addRow = regions.querySelector('.add-row');
  input(addRow.querySelector('input[type="text"]'), 'bad1');
  button(addRow, 'Add Region').click();
  await wait(5);
  assert.match(dialogText(), /Region name 'bad1' is invalid/);
  await answer('OK');

  input(addRow.querySelector('input[type="text"]'), 'chores');
  button(addRow, 'Add Region').click();
  await wait(5);
  assert.deepEqual(generatorModel().regions, [{ name: 'chores', pct: 100, color: '#e05c5c', prereq: '' }]);

  const taskRegion = root().querySelector('.gt-task select');
  change(taskRegion, { value: 'chores' });
  const nameInput = regions.querySelector('.region-row:not(.region-head) .region-name');
  nameInput.value = 'house';
  nameInput.dispatchEvent(new window.Event('blur'));
  await wait(5);
  assert.equal(generatorModel().tasks[0].region, 'house');
  assert.equal(root().querySelector('.gt-task select').value, 'house');

  button(regions.querySelector('.region-row:not(.region-head)'), 'Remove').click();
  await wait(5);
  assert.equal(generatorModel().tasks[0].region, '');
  assert.match(regions.textContent, /No regions defined\./);
});

test('export shows legacy validation errors, then downloads YAML PyYAML-compatible text', async () => {
  button(root(), 'Export YAML').click();
  await wait(5);
  assert.match(dialogText(), /No tasks defined\./);
  await answer('OK');

  input(root().querySelector('.gt-task input[type="text"]'), 'yes');
  button(root(), 'Add Task').click();
  input([...root().querySelectorAll('.gt-task')].pop().querySelector('input[type="text"]'), 'Cook');
  button(root(), 'Export YAML').click();
  await wait(5);
  assert.match(dialogText(), /Unbalanced Counts.*Task slots: 2 {2}\| {2}Item slots: 1.*Export anyway\?/s);
  await answer('No');
  assert.equal(topDialog(), undefined);
  button(root(), 'Export YAML').click();
  await answer('Yes');
  assert.match(dialogText(), /YAML exported as:\nTester\.yaml/);
  await answer('OK');

  const last = downloads[downloads.length - 1];
  assert.equal(last.name, 'Tester.yaml');
  const data = loadYaml(await last.blob.text());
  assert.equal(data.name, 'Tester');
  assert.deepEqual(data.Taskipelago.tasks, ['yes', 'Cook']);
  assert.deepEqual(data.Taskipelago.items, ['Key']);
  assert.deepEqual(data.Taskipelago.progressive_groups, ['keys']);
});

test('draft autosaves and reloads through normalizeModel', async () => {
  await wait(450);
  const draft = JSON.parse(localStorage.getItem(DRAFT_KEY));
  assert.equal(draft.playerName, 'Tester');
  assert.equal(draft.items[0].name, 'Key');
});

test('import replaces the editor and reports unbalanced counts', async () => {
  const pending = applyDoc(loadYaml('name: Imported\nTaskipelago:\n  tasks: [A, A, B]\n  items: [X]\n'), 'Imported YAML from:\ntest.yaml');
  await wait(5);
  assert.match(dialogText(), /Task slots: 3 {2}\| {2}Item slots: 1/);
  await answer('OK');
  assert.match(dialogText(), /Imported YAML from:\ntest\.yaml/);
  await answer('OK');
  assert.equal(await pending, true);
  assert.equal($('gen-player-name').value, 'Imported');
  assert.equal(root().querySelectorAll('.gt-task').length, 2);
  assert.equal(root().querySelector('.gt-task .count-input').value, '2');
});

test('reset asks first', async () => {
  button(root(), 'Reset').click();
  await wait(5);
  await answer('No');
  assert.equal(generatorModel().playerName, 'Imported');
  button(root(), 'Reset').click();
  await answer('Yes');
  assert.equal(generatorModel().playerName, '');
  assert.equal(root().querySelectorAll('.gt-task').length, 1);
});

test('tutorial shows the legacy steps plus the hosted/launcher step', () => {
  button(root(), 'Tutorial').click();
  const panel = doc.querySelector('.tutorial-panel');
  assert.ok(panel);
  assert.equal(STEPS.length, 19);
  assert.match(panel.textContent, /Welcome to the YAML Generator/);
  assert.match(panel.textContent, /Step 1 of 19/);
  for (let i = 0; i < 17; i++) button(panel, 'Next >').click();
  assert.match(panel.textContent, /Hosted Page and Launcher Client/);
  button(panel, 'Next >').click();
  assert.match(panel.textContent, /Export, Import, and Reset/);
  button(panel, 'Finish').click();
  assert.equal(doc.querySelector('.tutorial-panel'), null);
});

test('tooltips carry the legacy help text', () => {
  const tips = [...root().querySelectorAll('[data-tip]')].map(t => t.dataset.tip);
  assert.ok(tips.some(t => t.startsWith('Which tasks must be COMPLETED before this task can be checked off.')));
  assert.ok(tips.some(t => t.startsWith('Mark this item as a consumable (currency).')));
});

test('community YAMLs list and import through the endpoint', async () => {
  button(root(), 'Community YAMLs').click();
  await wait(20);
  const dlg = topDialog();
  assert.match(dlg.textContent, /Chores.*Barret.*1\.0\.2/);
  assert.ok(dlg.querySelector('a[href="https://script.example/exec"]'));
  button(dlg, 'Import YAML').click();
  await wait(20);
  assert.match(dialogText(), /Imported YAML from community file:\nChores_Barret_1-0-2\.yaml/);
  await answer('OK');
  assert.equal(generatorModel().playerName, 'Chores');
  assert.deepEqual(generatorModel().tasks.map(t => t.name), ['Sweep', 'Mop']);
  assert.ok(communityCalls >= 2);
  assert.ok(JSON.parse(localStorage.getItem('taskipelago_community_cache')).entries.length === 1);
});

test('bingo tab counts, validates and exports', async () => {
  const bingo = $('bingo-gen-root');
  const areas = bingo.querySelectorAll('textarea');
  input(areas[0], Array.from({ length: 9 }, (_, i) => `Cell ${i + 1}`).join('\n'));
  assert.match(bingo.textContent, /need 25, have 9 \(need 16 more\)/);
  const [x, y] = bingo.querySelectorAll('input[type="number"]');
  input(x, '3');
  input(y, '3');
  assert.match(bingo.textContent, /need 9, have 9 \(enough\)/);
  assert.match(bingo.textContent, /Reward slots available: 9 - all 9 slots will be filler/);

  button(bingo, 'Export Bingo YAML').click();
  await wait(5);
  assert.match(dialogText(), /Player name is required\./);
  await answer('OK');

  input(bingo.querySelector('input[type="text"]'), 'Bingo Tester');
  button(bingo, 'Export Bingo YAML').click();
  await wait(5);
  await answer('OK');
  const data = loadYaml(await downloads[downloads.length - 1].blob.text());
  assert.equal(data.Taskipelago.bingo_mode, true);
  assert.equal(data.Taskipelago.tasks.length, 9 + 8);
  assert.equal(data.Taskipelago.bingoal, 3);

  await wait(450);
  assert.equal(JSON.parse(localStorage.getItem('taskipelago_draft_bingo')).x, '3');
});

test('no runtime errors', () => {
  assert.deepEqual(errors.map(e => String(e?.stack || e)), []);
});
