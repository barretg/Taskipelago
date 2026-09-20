// Randomized regions and item group types in the generator: export validation
// (mirrors apworld step 5b), final balance counts, and YAML round trips.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { importModule } from '../helpers/env.mjs';

const { loadYaml, dumpYaml } = await importModule('shared/yaml11.js');
const { defaultModel, normalizeModel, renameRegion, renameProgGroup, removeRegion, removeProgGroup } =
  await importModule('generator/model.js');
const { importDoc } = await importModule('generator/yaml_import.js');
const { buildExport } = await importModule('generator/yaml_export.js');
const { parsePick, resolvePick, goalMinimalSets } = await importModule('generator/randomize_check.js');

const randomFiller = () => 'RANDOM FILLER';

function base(extra = {}) {
  return normalizeModel({
    playerName: 'P',
    regions: [{ name: 'pool', pct: 100, color: '', prereq: '' }],
    tasks: [
      { name: 'Free' },
      ...['A', 'B', 'C', 'D'].map(name => ({ name, region: 'pool' })),
    ],
    items: ['i1', 'i2', 'i3'].map(name => ({ name })),
    regionRandom: { pool: { on: true, pick: '2' } },
    ...extra,
  });
}

async function run(m) {
  const confirms = [];
  const r = await buildExport(m, { confirm: async (t, msg) => { confirms.push(msg); return true; }, randomFiller });
  return { ...r, confirms };
}

test('pick parsing and resolution', () => {
  assert.deepEqual(parsePick('3', 'x'), { value: 3, pct: false });
  assert.deepEqual(parsePick('40%', 'x'), { value: 40, pct: true });
  assert.equal(parsePick('', 'x'), null);
  for (const bad of ['0', '0%', '101%', 'abc', '-1', '2.5']) assert.throws(() => parsePick(bad, 'x'));
  assert.equal(resolvePick({ value: 40, pct: true }, 6, 'x'), 3);
  assert.equal(resolvePick({ value: 1, pct: true }, 6, 'x'), 1);
  assert.throws(() => resolvePick({ value: 7, pct: false }, 6, 'x'));
});

test('goal minimal sets', () => {
  assert.deepEqual(goalMinimalSets(['or', [['and', [3, 4]], 9]]), [[9], [3, 4]]);
  assert.deepEqual(goalMinimalSets(['or', [1, ['and', [1, 2]]]]), [[1]]);
});

test('export emits region_random_pick only when used and balances final counts', async () => {
  const r = await run(base());
  assert.equal(r.error, undefined);
  assert.deepEqual(r.data.Taskipelago.region_random_pick, ['2']);
  assert.deepEqual(r.data.Taskipelago.region_random_order, ['false']);
  const shuffled = await run(base({ regionRandom: { pool: { on: true, pick: '2', order: true } } }));
  assert.deepEqual(shuffled.data.Taskipelago.region_random_order, ['true']);
  assert.equal(r.confirms.length, 0); // 1 + 2 kept tasks == 3 items
  const plain = await run(base({ regionRandom: {} }));
  assert.equal('region_random_pick' in plain.data.Taskipelago, false);
  assert.equal('region_random_order' in plain.data.Taskipelago, false);
  assert.match(plain.confirms[0], /Task slots: 5 {2}\| {2}Item slots: 3/);
});

test('export rejects invalid randomization', async () => {
  const cases = [
    [{ regionRandom: { pool: { on: true, pick: '9' } } }, /keeps 9 but only has 4/],
    [{ regionRandom: { pool: { on: true, pick: '' } } }, /has no pick/],
    [{ regionRandom: { pool: { on: true, pick: '0%' } } }, /at least 1/],
  ];
  for (const [extra, re] of cases) {
    const r = await run(base(extra));
    assert.equal(r.error[0], 'Invalid Randomization');
    assert.match(r.error[1], re);
  }
});

test('export rejects individual refs into a randomized region', async () => {
  const withPrereq = (row, prereq) => {
    const m = base();
    m.tasks[row].prereq = prereq;
    return m;
  };
  for (const [row, prereq] of [[0, '2'], [0, '"B"'], [2, 'prev'], [3, 'sequential'], [1, 'pool-50']]) {
    const r = await run(withPrereq(row, prereq));
    assert.equal(r.error?.[0], 'Invalid Randomization', `${row}: ${prereq}`);
  }
  const ok = await run(withPrereq(1, '1'));
  assert.equal(ok.error, undefined);
  const whole = await run(withPrereq(0, 'pool*2'));
  assert.equal(whole.error, undefined);
  const tooMany = await run(withPrereq(0, 'pool*3'));
  assert.match(tooMany.error[1], /keeps 2/);
});

test('goal feasibility', async () => {
  const goal = g => run(base({ goalTasks: g, regionRandom: { pool: { on: true, pick: '1' } } }));
  assert.equal((await goal('2 || 3')).error, undefined);
  assert.equal((await goal('"A"')).error, undefined);
  assert.match((await goal('2 && 3')).error[1], /cannot be satisfied/);
  assert.equal((await goal('1')).error, undefined);
});

test('item group settings export, validation and forbidden refs', async () => {
  const m = normalizeModel({
    playerName: 'P',
    tasks: ['T1', 'T2', 'T3'].map(name => ({ name })),
    progGroups: ['gem', 'deco'],
    items: [
      { name: 'G1', progGroup: 'gem' }, { name: 'G2', progGroup: 'gem' }, { name: 'G3', progGroup: 'gem' },
      { name: 'D1', progGroup: 'deco' }, { name: 'x' },
    ],
    groupSettings: { gem: { type: 'random-choice', pick: '1', pct: '' }, deco: { type: 'aesthetic', pick: '', pct: '50' } },
  });
  const r = await run(m);
  assert.equal(r.error, undefined);
  assert.deepEqual(r.data.Taskipelago.group_types, ['random-choice', 'aesthetic']);
  assert.deepEqual(r.data.Taskipelago.group_random_pick, ['1', '']);
  assert.deepEqual(r.data.Taskipelago.group_default_pcts, ['', '50']);
  assert.equal(r.confirms.length, 0); // 5 items - 2 dropped == 3 tasks

  m.tasks[1].itemPrereq = '2';
  assert.match((await run(m)).error[1], /random-choice group 'gem'/);
  m.tasks[1].itemPrereq = 'gem*2';
  assert.match((await run(m)).error[1], /keeps 1 item/);
  m.tasks[1].itemPrereq = '4 && deco*1 && gem';
  assert.equal((await run(m)).error, undefined);
  m.groupSettings.deco.pct = '150';
  assert.match((await run(m)).error[1], /default %/);

  const plain = normalizeModel({ ...structuredClone(m), groupSettings: {} });
  plain.tasks[1].itemPrereq = '';
  assert.equal('group_types' in (await run(plain)).data.Taskipelago, false);
});

test('YAML round trip keeps the settings', async () => {
  const m = base({
    progGroups: ['gem'],
    groupSettings: { gem: { type: 'aesthetic', pick: '', pct: '75' } },
  });
  m.items[0].progGroup = 'gem';
  const { data } = await run(m);
  const back = importDoc(defaultModel(), loadYaml(dumpYaml(data)), { randomFiller }).model;
  assert.deepEqual(back.regionRandom, { pool: { on: true, pick: '2', order: false } });
  assert.deepEqual(back.groupSettings, { gem: { type: 'aesthetic', pick: '', pct: '75' } });
});

test('rename and remove carry the settings', () => {
  const m = base({ progGroups: ['gem'], groupSettings: { gem: { type: 'aesthetic', pick: '', pct: '' } } });
  renameRegion(m, 'pool', 'lake');
  renameProgGroup(m, 'gem', 'jewel');
  assert.deepEqual(Object.keys(m.regionRandom), ['lake']);
  assert.deepEqual(Object.keys(m.groupSettings), ['jewel']);
  removeRegion(m, 'lake');
  removeProgGroup(m, 'jewel');
  assert.deepEqual([m.regionRandom, m.groupSettings], [{}, {}]);
});
