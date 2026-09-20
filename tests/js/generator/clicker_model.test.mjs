// Tasclickpelago generator: export shape, the settings/YAML round trip, and
// curve fill. No DOM.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, importModule } from '../helpers/env.mjs';

setupDom();
const {
  buildClickerExport, clickerCounts, clickerSettingsDoc, curveFill,
  defaultClickerModel, loadClickerDoc, normalizeClickerModel, offlineExample, previewValue,
} = await importModule('clicker_gen/clicker_model.js');

function sample() {
  const m = defaultClickerModel();
  m.playerName = 'Clicker';
  m.tasks = [
    { name: 'Wash', activations: '10', region: 'House', prereq: '', itemPrereq: '' },
    { name: 'Cook', activations: '20', region: 'Kitchen', prereq: '1', itemPrereq: '"Sponge"' },
    { name: 'Bake', activations: '30', region: 'Kitchen', prereq: '2', itemPrereq: '' },
  ];
  m.regions = [
    { name: 'House', color: '#5c8de0', defaultPct: '100', distributed: false, offlineRate: '' },
    { name: 'Kitchen', color: '', defaultPct: '', distributed: true, offlineRate: '0.25' },
  ];
  m.upgrades = [
    { name: 'Sponge', type: 'progression', count: 1, group: '', kind: 'production', target: 'Wash', value: '1.5' },
    { name: 'Oven', type: 'progression', count: 2, group: '', kind: 'production_mult', target: '*', value: '1.15' },
  ];
  m.offlineRate = '0.5';
  m.offlineCapHours = 4;
  m.goalTask = 3;
  return m;
}

test('items are the pool contribution, one row per upgrade, parallel item_ lists', () => {
  const { data, error } = buildClickerExport(sample());
  assert.equal(error, undefined);
  const b = data.Taskipelago;
  assert.deepEqual(b.tasks, ['Wash', 'Cook', 'Bake']);
  // One row per upgrade, independent of the tasks; item_count carries copies.
  assert.deepEqual(b.items, ['Sponge', 'Oven']);
  assert.deepEqual(b.item_count, ['1', '2']);
  assert.deepEqual(b.item_types, ['progression', 'progression']);
  assert.equal(b.item_fillers, undefined);   // the apworld pads with filler itself
  assert.equal(b.clicker_mode, true);
  assert.deepEqual(b.task_activations, ['10', '20', '30']);
  assert.deepEqual(b.task_prereqs, ['', '1', '2']);
  assert.deepEqual(b.item_prereqs, ['', '"Sponge"', '']);
  assert.deepEqual(b.item_production, ['"Wash"-1.5', '']);
  assert.deepEqual(b.item_production_mult, ['', '1.15']);
  assert.equal(b.item_click_power, undefined);   // nothing to say, so nothing emitted
  assert.deepEqual(b.goal_tasks, ['3']);
});

test('export carries the region and offline settings', () => {
  const { data } = buildClickerExport(sample());
  const b = data.Taskipelago;
  assert.deepEqual(b.regions, ['House', 'Kitchen']);
  assert.deepEqual(b.task_region, ['House', 'Kitchen', 'Kitchen']);
  assert.deepEqual(b.region_distributed_production, ['false', 'true']);
  assert.deepEqual(b.region_offline_rate, ['', '0.25']);
  assert.equal(b.clicker_offline_progress, true);
  assert.deepEqual(b.clicker_offline_rate, ['0.5']);
  assert.equal(b.clicker_offline_cap_hours, 4);
  assert.equal(b.clicker_distribute_global, false);
});

test('copies beyond the task count are reported as trimmed', () => {
  const m = sample();
  assert.equal(buildClickerExport(m).trimmed, 0);   // 3 copies, 3 tasks
  m.upgrades[1].count = 5;                          // 6 copies, 3 tasks
  assert.equal(buildClickerExport(m).trimmed, 3);
});

test('export rejects what the apworld would reject, with the same grammar', () => {
  let m = sample();
  m.playerName = '';
  assert.match(buildClickerExport(m).error[1], /Player name is required/);

  m = sample();
  m.tasks[0].activations = 'N_TASKS_UNLOCKED';
  assert.match(buildClickerExport(m).error[1], /changes during play/);

  m = sample();
  m.upgrades[0].value = '1 +';
  assert.match(buildClickerExport(m).error[1], /Upgrade 'Sponge'/);

  m = sample();
  m.tasks[0].region = 'Garden';
  assert.match(buildClickerExport(m).error[1], /not in the Regions panel/);
});

test('counts warn when the item slots and upgrade copies do not line up', () => {
  const m = sample();
  assert.deepEqual(clickerCounts(m).warnings, []);   // 3 copies, 3 tasks

  m.upgrades[1].count = 5;
  assert.ok(clickerCounts(m).warnings.some(w => /the last 3 will be trimmed/.test(w)));

  m.upgrades[1].count = 1;                            // 2 copies, 3 tasks
  assert.ok(clickerCounts(m).warnings.some(w => /1 of 3 items will be random filler/.test(w)));
});

test('settings round-trip through the .clicker document', () => {
  const m = sample();
  const doc = clickerSettingsDoc(m);
  const loaded = loadClickerDoc(defaultClickerModel(), doc);
  assert.equal(loaded.kind, 'settings');
  assert.equal(loaded.ok, true);
  assert.deepEqual(buildClickerExport(loaded.model).data, buildClickerExport(m).data);
});

test('a clicker YAML imports back into an equivalent model', () => {
  const m = sample();
  const { data } = buildClickerExport(m);
  const loaded = loadClickerDoc(defaultClickerModel(), data);
  assert.equal(loaded.kind, 'yaml');
  assert.equal(loaded.ok, true);
  const again = buildClickerExport(loaded.model).data.Taskipelago;
  assert.deepEqual(again.tasks, data.Taskipelago.tasks);
  assert.deepEqual(again.items, data.Taskipelago.items);
  assert.deepEqual(again.item_count, data.Taskipelago.item_count);
  assert.deepEqual(again.task_prereqs, data.Taskipelago.task_prereqs);
  assert.deepEqual(again.item_production, data.Taskipelago.item_production);
  assert.deepEqual(again.task_activations, data.Taskipelago.task_activations);
  assert.deepEqual(again.region_distributed_production, data.Taskipelago.region_distributed_production);
  assert.equal(again.clicker_offline_cap_hours, 4);
});

test('a YAML without clicker_mode is refused', () => {
  const doc = { name: 'X', game: 'Taskipelago', Taskipelago: { tasks: ['A'] } };
  const r = loadClickerDoc(defaultClickerModel(), doc);
  assert.equal(r.ok, false);
  assert.match(r.messages[0][2], /does not have clicker_mode enabled/);
});

test('curve fill writes a geometric activations column', () => {
  const m = sample();
  const { tasks, error } = curveFill(m, 10, 2);
  assert.equal(error, undefined);
  assert.deepEqual(tasks.map(t => t.activations), ['10', '20', '40']);
  assert.match(curveFill(m, 0, 2).error[1], /at least 1/);
  assert.match(curveFill(m, 10, 0).error[1], /positive number/);
});

test('counts and warnings describe the model', () => {
  const m = sample();
  const c = clickerCounts(m);
  assert.equal(c.tasks, 3);
  assert.equal(c.upgrades, 2);
  assert.equal(c.copies, 3);
  assert.equal(c.regions, 2);
  assert.deepEqual(c.warnings, []);

  const bare = defaultClickerModel();
  bare.tasks = [{ ...bare.tasks[0], name: 'Wash' }];
  assert.ok(clickerCounts(bare).warnings.some(w => /only the base click/.test(w)));
});

test('the offline example spells out rate times cap', () => {
  const m = sample();
  assert.equal(offlineExample(m), 'Away 4h at 0.5 = 2h of production.');
  m.offlineEnabled = false;
  assert.match(offlineExample(m), /off/);
});

test('an expression cell previews both ends of the curve', () => {
  assert.deepEqual(previewValue('2', 10), { ok: true, low: 2, high: 2 });
  assert.deepEqual(previewValue('0.1 * N_TASKS_UNLOCKED', 10), { ok: true, low: 0, high: 1 });
  assert.equal(previewValue('1 +', 10).ok, false);
  assert.equal(previewValue('  ', 10).blank, true);
});

test('normalizeClickerModel repairs a partial draft', () => {
  const m = normalizeClickerModel({ playerName: 'X', tasks: [{ name: 'A' }] });
  assert.equal(m.tasks.length, 1);
  assert.equal(m.tasks[0].activations, '');
  assert.equal(m.upgrades.length, 1);
  assert.equal(m.offlineCapHours, 8);
});

test('targets use the normal reference syntax: bare region, quoted task', () => {
  const m = sample();
  m.upgrades = [
    { name: 'Mitts', type: 'progression', count: 1, group: '', kind: 'production', target: 'Kitchen', value: '0.5' },
    { name: 'Sponge', type: 'progression', count: 1, group: '', kind: 'production', target: 'Wash', value: '1.5' },
    { name: 'Timer', type: 'progression', count: 1, group: '', kind: 'offline_mult', target: '2', value: '2' },
  ];
  const { data, error } = buildClickerExport(m);
  assert.equal(error, undefined);
  assert.deepEqual(data.Taskipelago.item_production, ['Kitchen-0.5', '"Wash"-1.5', '']);
  assert.deepEqual(data.Taskipelago.item_offline_mult, ['', '', '2-2']);
});

test('a target that is neither a task nor a region is refused', () => {
  const m = sample();
  m.upgrades[0].target = 'Garage';
  const { error } = buildClickerExport(m);
  assert.match(error[1], /targets 'Garage', which is not a task or a region/);
});

test('an unlock-only item grants nothing but still enters the pool', () => {
  const m = sample();
  m.upgrades = [
    { name: 'Kitchen Key', type: 'progression', count: 1, group: '', kind: 'none', target: '*', value: '' },
    { name: 'Sponge', type: 'progression', count: 1, group: '', kind: 'production', target: 'Wash', value: '1.5' },
  ];
  const { data, error } = buildClickerExport(m);
  assert.equal(error, undefined);
  const b = data.Taskipelago;
  assert.deepEqual(b.items, ['Kitchen Key', 'Sponge']);
  assert.deepEqual(b.item_production, ['', '"Wash"-1.5']);
  assert.equal(b.item_click_power, undefined);
});
