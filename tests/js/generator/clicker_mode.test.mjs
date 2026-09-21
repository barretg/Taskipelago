// Clicker mode as an overlay on the normal generator: the extra columns export
// and import losslessly, and a plain Taskipelago YAML is untouched by them.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { importModule } from '../helpers/env.mjs';

const { loadYaml, dumpYaml } = await importModule('shared/yaml11.js');
const { defaultModel, normalizeModel } = await importModule('generator/model.js');
const { importDoc } = await importModule('generator/yaml_import.js');
const { buildExport } = await importModule('generator/yaml_export.js');
const { splitSpec, splitTargetList, targetToken, checkTarget, previewValue } = await importModule('generator/clicker_fields.js');

const randomFiller = () => 'RANDOM FILLER';
const confirm = async () => true;

function clickerModel(over = {}) {
  return normalizeModel({
    playerName: 'P',
    clickerMode: true,
    regions: [
      { name: 'Kitchen', pct: 100, color: '#111111', distributed: true, offlineRate: '0.5' },
      { name: 'Garage', pct: 100, color: '#222222' },
    ],
    tasks: [
      { name: 'Bake Bread', region: 'Kitchen', activations: '10' },
      { name: 'Fix Car', region: 'Garage', activations: '2 * N_TASKS', prereq: '"Bake Bread"' },
    ],
    items: [
      { name: 'Oven', clickerKind: 'production', clickerTarget: 'Kitchen', clickerValue: '0.5' },
      { name: 'Wrench', clickerKind: 'production', clickerTarget: 'Fix Car', clickerValue: '1' },
      { name: 'Gloves', clickerKind: 'click_power', clickerValue: '2' },
      { name: 'Manual', clickerKind: 'none' },
      { name: '', filler: true, count: 2 },
    ],
    ...over,
  });
}

const build = m => buildExport(m, { confirm, randomFiller });
const roundTrip = data => importDoc(defaultModel(), loadYaml(dumpYaml(data)), { randomFiller });

test('splitSpec and targetToken round-trip each reference form', () => {
  assert.deepEqual(splitSpec('"Bake Bread"-0.5'), { target: 'Bake Bread', value: '0.5' });
  assert.deepEqual(splitSpec('Kitchen-0.25'), { target: 'Kitchen', value: '0.25' });
  assert.deepEqual(splitSpec('3-1'), { target: '3', value: '1' });
  assert.deepEqual(splitSpec('*-2'), { target: '*', value: '2' });
  assert.deepEqual(splitSpec(''), { target: '*', value: '' });

  const names = ['Bake Bread'];
  assert.equal(targetToken('Bake Bread', names), '"Bake Bread"');
  assert.equal(targetToken('Kitchen', names), 'Kitchen');
  assert.equal(targetToken('3', names), '3');
  assert.equal(targetToken('', names), '*');
});

test('splitSpec keeps dashed names and rejoins shared values', () => {
  assert.deepEqual(splitSpec('Up-Stairs-2', ['Up-Stairs']), { target: 'Up-Stairs', value: '2' });
  assert.deepEqual(splitSpec('"A-B"-2'), { target: 'A-B', value: '2' });
  assert.deepEqual(splitSpec('Kitchen-2 && "Sweep"-2', ['Kitchen']), { target: 'Kitchen && "Sweep"', value: '2' });
  assert.deepEqual(splitSpec('(Kitchen && "Sweep")-2', ['Kitchen']), { target: 'Kitchen && "Sweep"', value: '2' });
});

test('splitTargetList honours parens and quotes', () => {
  assert.deepEqual(splitTargetList('( name && nametwo )'), ['name', 'nametwo']);
  assert.deepEqual(splitTargetList('"a && b" && (c)'), ['"a && b"', 'c']);
  assert.deepEqual(splitTargetList('name-restofname'), ['name-restofname']);
});

test('checkTarget accepts tasks, regions, indices and *', () => {
  const tasks = ['Bake Bread'];
  const regions = ['Kitchen'];
  assert.equal(checkTarget('*', tasks, regions), null);
  assert.equal(checkTarget('Kitchen', tasks, regions), null);
  assert.equal(checkTarget('"Bake Bread"', tasks, regions), null);
  assert.equal(checkTarget('2', tasks, regions), null);
  assert.equal(checkTarget('Kitchen && "Bake Bread"', tasks, regions), null);
  assert.equal(checkTarget('( Kitchen && "Bake Bread" )', tasks, regions), null);
  assert.match(checkTarget('Basement', tasks, regions), /not a task or a region/);
});

test('previewValue shows both ends of a live curve', () => {
  assert.deepEqual(previewValue('', 4), { ok: true, blank: true });
  assert.deepEqual(previewValue('2', 4), { ok: true, low: 2, high: 2 });
  assert.deepEqual(previewValue('N_TASKS_COMPLETED', 4), { ok: true, low: 0, high: 4 });
  assert.equal(previewValue('2 +', 4).ok, false);
});

test('export writes the clicker lists parallel to the exported rows', async () => {
  const r = await build(clickerModel());
  assert.ok(r.data, JSON.stringify(r.error));
  const b = r.data.Taskipelago;
  assert.equal(b.clicker_mode, true);
  assert.deepEqual(b.task_activations, ['10', '2 * N_TASKS']);
  // Two filler copies expand, so the spec lists stay parallel to `items`.
  assert.equal(b.items.length, 6);
  assert.deepEqual(b.item_production, ['Kitchen-0.5', '"Fix Car"-1', '', '', '', '']);
  assert.deepEqual(b.item_click_power, ['', '', '2', '', '', '']);
  assert.ok(!('item_click_mult' in b), 'unused kinds are left out');
  assert.deepEqual(b.region_distributed_production, ['true', 'false']);
  assert.deepEqual(b.region_offline_rate, ['0.5', '']);
  assert.equal(b.clicker_offline_progress, true);
  assert.deepEqual(b.clicker_offline_rate, ['1']);
  assert.equal(b.clicker_offline_cap_hours, 8);
});

test('a clicker slot round-trips back into the same rows', async () => {
  const r = await build(clickerModel());
  const { ok, model } = roundTrip(r.data);
  assert.ok(ok);
  assert.equal(model.clickerMode, true);
  assert.deepEqual(model.tasks.map(t => t.activations), ['10', '2 * N_TASKS']);
  assert.deepEqual(model.items.map(it => [it.clickerKind, it.clickerTarget, it.clickerValue]), [
    ['production', 'Kitchen', '0.5'],
    ['production', 'Fix Car', '1'],
    ['click_power', '*', '2'],
    ['none', '*', ''],
    ['none', '*', ''],
  ]);
  assert.deepEqual(model.regions.map(g => [g.distributed, g.offlineRate]),
    [[true, '0.5'], [false, '']]);
  // A second pass is byte-identical, so nothing drifts on repeated editing.
  const again = await build(model);
  assert.deepEqual(again.data, r.data);
});

test('a plain Taskipelago YAML gains no clicker keys and imports with the defaults', async () => {
  const plain = normalizeModel({
    playerName: 'P',
    regions: [{ name: 'Kitchen', pct: 100, color: '#111111' }],
    tasks: [{ name: 'Bake Bread', region: 'Kitchen' }],
    items: [{ name: 'Oven' }],
  });
  const r = await build(plain);
  assert.ok(r.data, JSON.stringify(r.error));
  const keys = Object.keys(r.data.Taskipelago);
  assert.deepEqual(keys.filter(k => k.startsWith('clicker_') || k.startsWith('item_prod')
    || k === 'task_activations' || k.startsWith('region_offline')), []);

  const { model } = roundTrip(r.data);
  assert.equal(model.clickerMode, false);
  assert.deepEqual(model.tasks.map(t => t.activations), ['']);
  assert.deepEqual(model.items.map(it => it.clickerKind), ['none']);
  assert.deepEqual(model.regions.map(g => [g.distributed, g.offlineRate]), [[false, '']]);

  // Turning clicker mode on for that same slot keeps every normal setting.
  model.clickerMode = true;
  const on = await build(model);
  assert.ok(on.data, JSON.stringify(on.error));
  for (const [k, v] of Object.entries(r.data.Taskipelago)) {
    assert.deepEqual(on.data.Taskipelago[k], v, `key ${k} changed`);
  }
  assert.equal(on.data.Taskipelago.clicker_mode, true);
});

test('export rejects a bad activation expression, target or value', async () => {
  let m = clickerModel();
  m.tasks[0].activations = 'N_TASKS_COMPLETED';
  let r = await build(m);
  assert.match(r.error[1], /Task 'Bake Bread' activations/);

  m = clickerModel();
  m.items[0].clickerTarget = 'Basement';
  r = await build(m);
  assert.match(r.error[1], /Item 'Oven' targets 'Basement'/);

  m = clickerModel();
  m.items[0].clickerValue = '0.5 *';
  r = await build(m);
  assert.match(r.error[1], /Item 'Oven'/);
});

test('CPS exports in a production value and is refused in a click field', async () => {
  let m = clickerModel();
  m.items[0].clickerValue = '0.5 * CPS';
  let r = await build(m);
  assert.ok(r.data, JSON.stringify(r.error));
  assert.equal(r.data.Taskipelago.item_production[0], 'Kitchen-0.5 * CPS');
  const { model } = roundTrip(r.data);
  assert.equal(model.items[0].clickerValue, '0.5 * CPS');

  for (const kind of ['click_power', 'click_mult']) {
    m = clickerModel();
    m.items[2].clickerKind = kind;
    m.items[2].clickerValue = '2 * CPS';
    r = await build(m);
    assert.match(r.error[1], /'CPS' is the click value and cannot be used in a click field/);
  }

  // Activations are fixed at generation, so CPS is refused there like the other
  // live constants.
  m = clickerModel();
  m.tasks[0].activations = 'CPS';
  r = await build(m);
  assert.match(r.error[1], /changes during play/);
});

test('manual tasks and manual regions export and round-trip', async () => {
  const m = clickerModel();
  m.tasks[0].manual = true;
  m.regions[1].manual = true;
  // Every task is manual here, so nothing may be aimed at one.
  m.items[0].clickerKind = 'none';
  m.items[1].clickerKind = 'none';
  const r = await build(m);
  assert.ok(r.data, JSON.stringify(r.error));
  const b = r.data.Taskipelago;
  assert.deepEqual(b.task_manual, ['true', 'false']);
  assert.deepEqual(b.region_manual, ['false', 'true']);

  const { ok, model } = roundTrip(r.data);
  assert.ok(ok);
  assert.deepEqual(model.tasks.map(t => t.manual), [true, false]);
  assert.deepEqual(model.regions.map(g => g.manual), [false, true]);
  const again = await build(model);
  assert.deepEqual(again.data, r.data);
});

test('a slot with nothing manual writes no manual keys', async () => {
  const r = await build(clickerModel());
  const b = r.data.Taskipelago;
  assert.ok(!('task_manual' in b));
  assert.ok(!('region_manual' in b));
  const { model } = roundTrip(r.data);
  assert.deepEqual(model.tasks.map(t => t.manual), [false, false]);
  assert.deepEqual(model.regions.map(g => g.manual), [false, false]);
});

test('auto-complete exports only when set and round-trips', async () => {
  let r = await build(clickerModel());
  assert.ok(!('task_auto_complete' in r.data.Taskipelago));
  const m = clickerModel();
  m.tasks[1].autoComplete = true;
  r = await build(m);
  assert.deepEqual(r.data.Taskipelago.task_auto_complete, ['false', 'true']);
  const { ok, model } = roundTrip(r.data);
  assert.ok(ok);
  assert.deepEqual(model.tasks.map(t => t.autoComplete), [false, true]);
});

test('click power and the multipliers carry a target too', async () => {
  const m = clickerModel();
  m.items[2].clickerTarget = 'Bake Bread';          // click power on one task
  m.items[3].clickerKind = 'production_mult';
  m.items[3].clickerTarget = 'Kitchen';
  m.items[3].clickerValue = '2';
  const r = await build(m);
  assert.ok(r.data, JSON.stringify(r.error));
  const b = r.data.Taskipelago;
  assert.deepEqual(b.item_click_power, ['', '', '"Bake Bread"-2', '', '', '']);
  assert.deepEqual(b.item_production_mult, ['', '', '', 'Kitchen-2', '', '']);

  const { model } = roundTrip(r.data);
  assert.deepEqual(model.items.map(it => [it.clickerKind, it.clickerTarget, it.clickerValue]), [
    ['production', 'Kitchen', '0.5'],
    ['production', 'Fix Car', '1'],
    ['click_power', 'Bake Bread', '2'],
    ['production_mult', 'Kitchen', '2'],
    ['none', '*', ''],
  ]);
});

test('an untargeted click value still imports as a slot-wide grant', async () => {
  const r = await build(clickerModel());
  // The pre-targeting spelling, including a value that contains a minus.
  const data = JSON.parse(JSON.stringify(r.data));
  data.Taskipelago.item_click_power = ['', '', 'N_TASKS - 1', '', '', ''];
  const { model } = roundTrip(data);
  assert.deepEqual(
    [model.items[2].clickerKind, model.items[2].clickerTarget, model.items[2].clickerValue],
    ['click_power', '*', 'N_TASKS - 1'],
  );
});

test('a bad target on a click field is caught before export', async () => {
  const m = clickerModel();
  m.items[2].clickerTarget = 'Basement';
  const r = await build(m);
  assert.match(r.error[1], /Item 'Gloves' targets 'Basement'/);
});

test('a grant cannot be aimed at a non-clicker task', async () => {
  // Straight at a manual task.
  let m = clickerModel();
  m.tasks[0].manual = true;
  m.items[0].clickerKind = 'none';        // Oven aims at Kitchen, checked first
  m.items[2].clickerTarget = 'Bake Bread';
  let r = await build(m);
  assert.match(r.error[1], /Item 'Gloves' targets manual task 'Bake Bread'/);

  // Through its region: a task in a manual region is manual too.
  m = clickerModel();
  m.regions[1].manual = true;
  m.items[1].clickerKind = 'none';        // Wrench aims at Fix Car, checked first
  m.items[2].clickerTarget = 'Fix Car';
  r = await build(m);
  assert.match(r.error[1], /Item 'Gloves' targets manual task 'Fix Car'/);

  // A region with no clicker task left in it.
  m = clickerModel();
  m.tasks[0].manual = true;
  r = await build(m);
  assert.match(r.error[1], /Item 'Oven' targets region 'Kitchen', in which every task is manual/);

  // A region that still has a clicker task is fine.
  m = clickerModel();
  m.tasks[1].manual = true;
  r = await build(m);
  assert.match(r.error[1], /targets manual task 'Fix Car'/);   // Wrench aims straight at it
  m.items[1].clickerKind = 'none';
  r = await build(m);
  assert.ok(r.data, JSON.stringify(r.error));
});
