// UNIFY 5.4 parity: the JS parser must produce the Python golden AST / error text.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { importModule } from '../helpers/env.mjs';

const golden = JSON.parse(readFileSync(fileURLToPath(new URL('../../parity/prereq_golden.json', import.meta.url)), 'utf8'));
const { parsePrereq, parseCostExpr, RESERVED_WORDS } = await importModule('shared/prereq_parser.js');

function run(c) {
  try {
    const ast = c.kind === 'prereq'
      ? parsePrereq(c.text, c.n, c.task_index, c.label, c.groups, c.regions, c.location_label)
      : parseCostExpr(c.text, c.consumables, c.items);
    return { ast };
  } catch (e) {
    return { error: e.message };
  }
}

test('reserved words match Python', () => {
  assert.deepEqual([...RESERVED_WORDS].sort(), ['prev', 'sequential']);
});

test('every corpus case matches the Python golden output', () => {
  assert.ok(golden.cases.length > 100);
  const mismatches = golden.cases
    .map(c => ({ kind: c.kind, text: c.text, python: c.result, js: run(c) }))
    .filter(m => JSON.stringify(m.python) !== JSON.stringify(m.js));
  assert.deepEqual(mismatches, []);
});

test('F8: validateRefName unified name rule', async () => {
  const { validateRefName } = await importModule('shared/prereq_parser.js');
  for (const ok of ['weapons+', 'side-quests!', '_x', 'café', 'weap-']) assert.equal(validateRefName(ok), null, ok);
  for (const bad of ['', '1up', 'a b', 'x(y', 'a"b', 'a,b', 'prev', 'Sequential', 'a&&b', 'a||b', '-x', '+x']) {
    assert.notEqual(validateRefName(bad), null, bad);
  }
});

test('F8: evaluator splits suffixes on names with non-letters', async () => {
  const { evalPrereqExpr } = await importModule('shared/eval_prereq.js');
  const seen = [];
  const counts = { 'weapons+': 2 };
  const nameFn = (name, n) => { seen.push([name, n]); return n === null ? true : (counts[name] || 0) >= n; };
  assert.equal(evalPrereqExpr('weapons+*3', () => true, nameFn), false);
  counts['weapons+'] = 3;
  assert.equal(evalPrereqExpr('weapons+*3', () => true, nameFn), true);
  evalPrereqExpr('weap--2', () => true, nameFn);
  assert.deepEqual(seen.at(-1), ['weap-', null]);
});
