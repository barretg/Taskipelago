// task(...) / item(...) scopes in task prereqs, item prereqs and the goal:
// the client evaluates each scope against its own index space.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, bootApp, importModule } from '../helpers/env.mjs';

setupDom();
await bootApp();
const { ap, state } = await importModule('play/state.js');
const logic = await importModule('play/logic.js');
const { mapScopedText } = await importModule('shared/prereq_parser.js');
const { scopedLeaves } = await importModule('generator/randomize_check.js');

function setup({ items = [], checked = [] } = {}) {
  state.baseItemId = 300;
  state.baseCompleteId = 100;
  state.rewardProgressiveGroup = ['Gear', 'Gear', '', ''];
  state.taskRegion = ['', '', '', ''];
  ap.itemsReceived = items.map(i => ({ item: 300 + i }));
  return new Set(checked.map(t => 100 + t));
}

test('task prereq: item(...) OR task', () => {
  let checked = setup();
  assert.equal(logic.prereqsSatisfied('item(1) || 2', checked), false);
  checked = setup({ items: [0] });
  assert.equal(logic.prereqsSatisfied('item(1) || 2', checked), true);
  checked = setup({ checked: [1] });
  assert.equal(logic.prereqsSatisfied('item(1) || 2', checked), true);
});

test('task prereq: item(...) group count', () => {
  const checked = setup({ items: [0] });
  assert.equal(logic.prereqsSatisfied('item(Gear*2)', checked), false);
  setup({ items: [0, 1] });
  assert.equal(logic.prereqsSatisfied('item(Gear*2)', checked), true);
});

test('item prereq: task(...) OR item', () => {
  let checked = setup();
  assert.equal(logic.itemPrereqsSatisfied('1 || task(3)', [], checked), false);
  checked = setup({ checked: [2] });
  assert.equal(logic.itemPrereqsSatisfied('1 || task(3)', [], checked), true);
});

test('plain prereqs are unchanged', () => {
  const checked = setup({ items: [1], checked: [0] });
  assert.equal(logic.prereqsSatisfied('1 && 2', checked), false);
  assert.equal(logic.prereqsSatisfied('1', checked), true);
  assert.equal(logic.itemPrereqsSatisfied('2', [], checked), true);
});

test('mapScopedText maps each domain, home included', () => {
  const t = s => `T[${s}]`;
  const i = s => `I[${s}]`;
  assert.equal(mapScopedText('1 || item(2)', t, i, 'task'), 'T[1 || ]item(I[2])');
  assert.equal(mapScopedText('1 || task(2 && item(3))', t, i, 'item'), 'I[1 || ]task(T[2 && ]item(I[3]))');
  // Region prereqs (no home) leave text outside the scopes alone.
  assert.equal(mapScopedText('chores && item(2)', t, i), 'chores && item(I[2])');
  assert.equal(mapScopedText('item (2)', t, i, 'task'), 'item(I[2])');
});

test('scopedLeaves honours the home domain', () => {
  const ast = ['or', [0, ['scoped_item', [1]], ['scoped_task', [2]]]];
  assert.deepEqual(scopedLeaves(ast, 'task', 'task'), [0, 2]);
  assert.deepEqual(scopedLeaves(ast, 'item', 'task'), [1]);
  assert.deepEqual(scopedLeaves(ast, 'task'), [2]);
});
