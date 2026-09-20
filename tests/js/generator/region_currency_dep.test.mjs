// A region "Depends on" may not reference a consumable currency item: a currency
// is spent on task costs, so "received" cannot stably gate a region.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { importModule } from '../helpers/env.mjs';

const { normalizeModel } = await importModule('generator/model.js');
const { buildExport } = await importModule('generator/yaml_export.js');

const randomFiller = () => 'RANDOM FILLER';
const confirm = async () => true;

function model(prereq) {
  return normalizeModel({
    playerName: 'P',
    regions: [
      { name: 'Hall', pct: 100, color: '', prereq: '' },
      { name: 'Kitchen', pct: 100, color: '', prereq },
    ],
    tasks: [
      { name: 'Sweep', region: 'Hall' },
      { name: 'Mop', region: 'Hall' },
      { name: 'Bake', region: 'Kitchen', cost: '"Gold"' },
    ],
    items: [
      { name: 'Broom' },
      { name: 'Gold', consumable: true },
      { name: 'Oven' },
    ],
  });
}

test('export rejects a region depending on a currency item', async () => {
  for (const expr of ['item(2)', 'item("Gold")', 'item(1 || "Gold")', 'item(2) && Hall']) {
    const r = await buildExport(model(expr), { confirm, randomFiller });
    assert.match(r.error[1], /consumable currency/, `expected rejection for ${expr}`);
  }
});

test('export still allows a region depending on a normal item', async () => {
  const r = await buildExport(model('item(1)'), { confirm, randomFiller });
  assert.ok(r.data, JSON.stringify(r.error));
  assert.equal(r.data.Taskipelago.region_prereqs[1], 'item(1)');
});
