// INDEX*Y / "Name"*Y item prereqs: the first Y copies of an item row with count > 1.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { importModule } from '../helpers/env.mjs';

const { loadYaml, dumpYaml } = await importModule('shared/yaml11.js');
const { defaultModel, normalizeModel } = await importModule('generator/model.js');
const { importDoc } = await importModule('generator/yaml_import.js');
const { buildExport } = await importModule('generator/yaml_export.js');
const { remapPrereqIndices, collapseCopyGroups } = await importModule('shared/expr_rewrite.js');

const randomFiller = () => 'RANDOM FILLER';
const confirm = async () => true;

function model(itemPrereqs) {
  return normalizeModel({
    playerName: 'P',
    tasks: itemPrereqs.map((itemPrereq, i) => ({ name: `T${i + 1}`, itemPrereq, count: 2 })),
    items: [
      { name: 'Key', count: 1 },
      { name: '', filler: true, count: 3 },
      { name: 'Sword', count: 2 },
    ],
  });
}

test('remapPrereqIndices keeps INDEX*Y and expands split rows to an AND of the first Y', () => {
  const map = [[1], [2, 3, 4], [5]];
  assert.equal(remapPrereqIndices('2*2', map), '(2 && 3)');
  assert.equal(remapPrereqIndices('2*1 || 2*3', map), '2 || (2 && 3 && 4)');
  assert.equal(remapPrereqIndices('3*2 && 2', map), '5*2 && (2 || 3 || 4)');
  assert.equal(remapPrereqIndices('"x"*2 && weapons*2', map), '"x"*2 && weapons*2');
  assert.equal(remapPrereqIndices('3*2', [[1], [2], [3]], false), '3*2');
});

test('collapseCopyGroups only reverses leading copies of one row', () => {
  const flat = [[1], [2], [2], [2], [3]];
  assert.equal(collapseCopyGroups('(2 && 3) || 1', flat), '2*2 || 1');
  assert.equal(collapseCopyGroups('(2 && 3 && 4)', flat), '2*3');
  assert.equal(collapseCopyGroups('(3 && 4)', flat), '(3 && 4)');
  assert.equal(collapseCopyGroups('(1 && 2)', flat), '(1 && 2)');
  assert.equal(collapseCopyGroups('"a (2 && 3)" && (2&&3)', flat), '"a (2 && 3)" && 2*2');
});

test('export translates INDEX*Y and import restores it', async () => {
  const prereqs = ['2*2', '"Sword"*2 && 1', '2*3 || 3*1', '2'];
  const r = await buildExport(model(prereqs), { confirm, randomFiller });
  assert.ok(r.data, JSON.stringify(r.error));
  assert.deepEqual(r.data.Taskipelago.item_prereqs,
    ['(2 && 3)', '"Sword"*2 && 1', '(2 && 3 && 4) || 5*1', '(2 || 3 || 4)']);
  const back = importDoc(defaultModel(), loadYaml(dumpYaml(r.data)), { randomFiller });
  assert.deepEqual(back.model.tasks.map(t => t.itemPrereq), ['2*2', '"Sword"*2 && 1', '2*3 || 3*1', '2']);
});

test('export rejects copy counts above the row count or outside item prereqs', async () => {
  let r = await buildExport(model(['3*3']), { confirm, randomFiller });
  assert.match(r.error[1], /'3\*3' in item prereq on task 1 asks for 3 copies but item 3 has a count of 2/);
  r = await buildExport(model(['"Sword"*5']), { confirm, randomFiller });
  assert.match(r.error[1], /asks for 5 copies/);
  const m = model(['']);
  m.tasks[0].prereq = '1*2';
  r = await buildExport(m, { confirm, randomFiller });
  assert.match(r.error[1], /copy counts can only be used in item prereqs/);
});
