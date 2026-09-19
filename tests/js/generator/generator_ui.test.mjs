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
  assert.deepEqual(tabs, ['Connect and Play', 'Text Console', 'Hints', 'YAML Generator', 'Taskipelabingo']);
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
  assert.match(dialogText(), /Region name 'bad1' must not contain digits/);
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

test('F4: renaming a region or group offers to update references; remove warns', async () => {
  const { buildExport } = await importModule('generator/yaml_export.js');
  assert.equal(await applyDoc({
    name: 'Refs', game: 'Taskipelago',
    Taskipelago: {
      regions: ['chores', 'fun'], region_default_pcts: [100, 100], region_prereqs: ['', 'chores-50'],
      tasks: ['chores', 'B', 'C'], task_count: ['1', '1', '1'], task_region: ['chores', 'fun', ''],
      task_prereqs: ['', 'chores*1', '"chores" || fun'], goal_tasks: ['chores && 3'],
      progressive_groups: ['keys'], items: ['Key', 'Gem', 'Map'], item_count: ['1', '1', '1'],
      item_progressive_group: ['keys', '', ''], item_prereqs: ['', 'keys-1', ''],
    },
  }), true);
  const m = generatorModel();
  const regions = root().querySelector('details.gen-section');
  const regionName = () => regions.querySelector('.region-row:not(.region-head) .region-name');
  const rename = async (el, value) => {
    el.value = value;
    el.dispatchEvent(new window.Event('blur'));
    el.dispatchEvent(new window.Event('blur')); // a second blur while the prompt is open is ignored
    await wait(5);
  };

  await rename(regionName(), 'house');
  assert.match(dialogText(), /3 expressions reference 'chores'\. Update them to 'house'\?/);
  assert.equal(doc.querySelectorAll('.dialog-overlay').length, 1);
  await answer('Cancel');
  assert.equal(regionName().value, 'chores');
  assert.equal(m.regions[0].name, 'chores');

  await rename(regionName(), 'house');
  await answer('Rename only');
  assert.equal(m.regions[0].name, 'house');
  assert.equal(m.tasks[0].region, 'house');
  assert.equal(m.tasks[1].prereq, 'chores*1');

  await rename(regionName(), 'chores');
  assert.equal(doc.querySelectorAll('.dialog-overlay').length, 0, 'no references to house, no prompt');
  await rename(regionName(), 'house');
  await answer('Update');
  assert.deepEqual([m.tasks[1].prereq, m.tasks[2].prereq, m.regions[1].prereq, m.goalTasks],
    ['house*1', '"chores" || fun', 'house-50', 'house && 3']);
  assert.equal(root().querySelector('.goal-input').value, 'house && 3');
  assert.equal(root().querySelectorAll('.gt-task')[1].querySelectorAll('input[type="text"]')[1].value, 'house*1');

  const groupName = () => root().querySelector('.gen-groups .gen-group-row .region-name');
  await rename(groupName(), 'tools');
  assert.match(dialogText(), /1 expression references 'keys'\. Update it to 'tools'\?/);
  await answer('Update');
  assert.deepEqual(m.progGroups, ['tools']);
  assert.equal(m.items[0].progGroup, 'tools');
  assert.equal(m.tasks[1].itemPrereq, 'tools-1');
  assert.equal(root().querySelector('.gt-item').querySelectorAll('select')[1].value, 'tools');

  const result = await buildExport(m, { confirm: async () => true });
  assert.ok(result.data, JSON.stringify(result.error));

  button(regions.querySelector('.region-row:not(.region-head)'), 'Remove').click();
  await wait(5);
  assert.match(dialogText(), /3 expressions still reference 'house' and will fail to export/);
  await answer('No');
  assert.equal(m.regions.length, 2);
  button(root().querySelector('.gen-groups .gen-group-row'), 'Remove').click();
  await wait(5);
  await answer('Yes');
  assert.deepEqual(m.progGroups, []);
  assert.equal(m.items[0].progGroup, '');
});

test('F10: carets move rows, keep focus, and follow the references toggle', async () => {
  const m = generatorModel();
  const taskRows = () => root().querySelectorAll('.gt-task');
  const carets = i => taskRows()[i].querySelectorAll('.caret-btn');
  assert.ok(carets(0)[0].disabled, 'first row cannot move up');
  assert.ok(carets(taskRows().length - 1)[1].disabled, 'last row cannot move down');
  const names = () => m.tasks.map(t => t.name);
  const before = names();
  const goal = m.goalTasks;
  carets(2)[0].click();
  assert.deepEqual(names(), [before[0], before[2], before[1]]);
  assert.equal(doc.activeElement, carets(1)[0]);
  assert.equal(root().querySelector('.goal-input').value, m.goalTasks);
  assert.notEqual(m.goalTasks, goal);

  const toggle = $('gen-reorder-refs');
  assert.equal(toggle.checked, true);
  change(toggle, { checked: false });
  const goalNow = m.goalTasks;
  carets(2)[0].click();
  assert.deepEqual(names(), before);
  assert.equal(m.goalTasks, goalNow);
  carets(1)[0].click();
  assert.equal(doc.activeElement, carets(0)[1], 'moved to the top: focus falls back to the down caret');
  carets(0)[1].click();
  assert.deepEqual(names(), before);
  change(toggle, { checked: true });
  assert.equal(JSON.parse(localStorage.getItem('taskipelago_ui')).reorderUpdatesRefs, true);
});

test('F5: find and replace panel', async () => {
  assert.equal(await applyDoc({
    name: 'Finder', game: 'Taskipelago',
    Taskipelago: {
      tasks: Array.from({ length: 40 }, (_, i) => `Task ${i + 1}`), task_count: Array(40).fill('1'),
      task_description: Array.from({ length: 40 }, (_, i) => (i === 5 ? 'wash the dog' : '')),
      task_prereqs: Array.from({ length: 40 }, (_, i) => (i === 39 ? '"Task 1" && "Task 12"' : '')),
      items: ['Dog Treat', 'Treat'], item_count: ['39', '1'], item_fillers: [false, true],
      death_link: { true: 50, false: 0 }, death_link_pool: ['Walk the dog'],
    },
  }), true);
  const m = generatorModel();
  const sections = [...root().querySelectorAll('details.gen-section')];
  const deathlink = sections.find(d => d.querySelector('summary').textContent === 'DeathLink');
  deathlink.open = false;
  const scrolled = [];
  window.Element.prototype.scrollIntoView = function scrollIntoView() { scrolled.push(this); };

  // Ctrl+F only on the generator tab.
  [...doc.querySelectorAll('#main-tabs .tab-btn')][0].click();
  doc.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'f', ctrlKey: true, bubbles: true, cancelable: true }));
  assert.equal(doc.querySelector('.find-panel'), null);
  [...doc.querySelectorAll('#main-tabs .tab-btn')].find(b => b.dataset.tab === 'generator').click();
  const ev = new window.KeyboardEvent('keydown', { key: 'h', ctrlKey: true, bubbles: true, cancelable: true });
  doc.dispatchEvent(ev);
  assert.ok(ev.defaultPrevented);
  const panel = doc.querySelector('.find-panel');
  assert.ok(panel);
  const [find, replace] = panel.querySelectorAll('input[type="text"]');
  assert.equal(doc.activeElement, replace);
  const status = () => panel.querySelector('.find-status').textContent;

  input(find, 'dog');
  button(panel, 'Find Next').click();
  assert.match(status(), /Match 1 of 3: Task 6 description: wash the dog/);
  assert.ok(root().querySelector('[data-field="tasks.5.desc"]').classList.contains('find-highlight'));
  button(panel, 'Find Next').click();
  assert.match(status(), /Match 2 of 3 \(Item 1 name\)/);
  const itemName = root().querySelector('[data-field="items.0.name"]');
  assert.equal(doc.activeElement, itemName);
  assert.deepEqual([itemName.selectionStart, itemName.selectionEnd], [0, 3]);
  button(panel, 'Find Next').click();
  assert.equal(deathlink.open, true, 'collapsed section expands');
  assert.equal(scrolled.at(-1), root().querySelector('[data-field="deathlink.0.text"]'));
  button(panel, 'Find Previous').click();
  assert.match(status(), /Match 2 of 3/);

  input(find, 'Task 1');
  change(panel.querySelector('input[data-scope="taskNames"]'), { checked: false });
  change(panel.querySelectorAll('.find-options input')[1], { checked: true });
  button(panel, 'Find Next').click();
  assert.match(status(), /Match 1 of 1 \(Task 40 task prereqs\)/);
  assert.equal(scrolled.at(-1), root().querySelector('[data-field="tasks.39.prereq"]'), 'far-down row scrolled into view');
  input(replace, 'Task 2');
  button(panel, 'Replace').click();
  assert.equal(m.tasks[39].prereq, '"Task 2" && "Task 12"');
  assert.match(status(), /Replaced 1\. No matches|^Replaced 1\. $/);

  change(panel.querySelector('input[data-scope="taskNames"]'), { checked: true });
  change(panel.querySelectorAll('.find-options input')[1], { checked: false });
  input(find, 'task');
  input(replace, 'Chore');
  m.items[1].name = 'Task filler';
  button(panel, 'Replace All').click();
  await wait(5);
  assert.match(dialogText(), /Replace 42 occurrences in 41 fields\?/);
  await answer('Yes');
  assert.equal(status(), 'Replaced 42');
  assert.equal(m.tasks[0].name, 'Chore 1');
  assert.equal(root().querySelector('[data-field="tasks.0.name"]').value, 'Chore 1');
  assert.equal(m.items[1].name, 'Task filler', 'filler row untouched');

  await wait(450);
  const draft = JSON.parse(localStorage.getItem(DRAFT_KEY));
  assert.equal(draft.tasks[39].prereq, '"Chore 2" && "Chore 12"');

  panel.querySelector('input').dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  assert.equal(doc.querySelector('.find-panel'), null);
  [...doc.querySelectorAll('#main-tabs .tab-btn')][0].click();
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

test('tutorial shows the legacy steps plus the hosted/launcher and v1.1 steps', () => {
  button(root(), 'Tutorial').click();
  const panel = doc.querySelector('.tutorial-panel');
  assert.ok(panel);
  assert.equal(STEPS.length, 26);
  const titles = STEPS.map(s => s[0]);
  const after = (a, b) => assert.equal(titles.indexOf(b), titles.indexOf(a) + 1, `${b} follows ${a}`);
  after('Regions', 'Randomized Regions and Dependencies');
  after('Item Groups (Progressive, Random-Choice, Aesthetic)', 'Group Types, Keep and Default %');
  after('Group Types, Keep and Default %', 'Group Colors and Renaming');
  after('Item Count and Item Settings', 'Reordering Tasks and Items');
  after('Reordering Tasks and Items', 'Find and Replace');
  after('DeathLink (Optional Challenge)', 'DeathLink Task Cards and Lock');
  after('While Playing: Hints and Item Filters', 'Hosted Page and Launcher Client');
  assert.match(panel.textContent, /Welcome to the YAML Generator/);
  assert.match(panel.textContent, /Step 1 of 26/);
  for (let i = 0; i < 24; i++) button(panel, 'Next >').click();
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
  assert.equal(data.Taskipelago.item_fillers[4], true, 'F9: free space is filler');

  // F9: more rewards than slots asks first; declining exports nothing.
  input(areas[1], Array.from({ length: 11 }, (_, i) => `Prize ${i + 1}`).join('\n'));
  assert.match(bingo.textContent, /all 9 slots covered, 2 unused/);
  const before = downloads.length;
  button(bingo, 'Export Bingo YAML').click();
  await wait(5);
  assert.match(dialogText(), /2 rewards will be unused\. Export anyway\?/);
  await answer('No');
  assert.equal(downloads.length, before);
  button(bingo, 'Export Bingo YAML').click();
  await wait(5);
  await answer('Yes');
  await wait(5);
  await answer('OK');
  assert.equal(downloads.length, before + 1);

  await wait(450);
  assert.equal(JSON.parse(localStorage.getItem('taskipelago_draft_bingo')).x, '3');
});

test('no runtime errors', () => {
  assert.deepEqual(errors.map(e => String(e?.stack || e)), []);
});
