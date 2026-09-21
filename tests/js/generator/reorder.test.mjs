// v1.1 F10: moving task / item rows remaps index references (model.js moveRow).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { importModule } from '../helpers/env.mjs';

const { defaultModel, newTask, newItem, moveRow } = await importModule('generator/model.js');

function tasksModel() {
  const m = defaultModel();
  const rows = [
    ['Task A', ''], ['Task B', '3'], ['Task C', '1 && 3'], ['Task D', '"Task C" || (1 || 1)'], ['Task E', 'chores-75 && prev && 2'],
  ];
  m.tasks = rows.map(([name, prereq]) => ({ ...newTask(), name, prereq }));
  m.goalTasks = '3 || 23';
  return m;
}

test('moving task 3 up remaps task prereqs and goal tasks, nothing else', () => {
  const m = tasksModel();
  assert.equal(moveRow(m, 'tasks', 2, 1, true), true);
  assert.deepEqual(m.tasks.map(t => [t.name, t.prereq]), [
    ['Task A', ''], ['Task C', '1 && 2'], ['Task B', '2'], ['Task D', '"Task C" || (1 || 1)'], ['Task E', 'chores-75 && prev && 3'],
  ]);
  assert.equal(m.goalTasks, '2 || 23');
});

test('moving an item remaps item prereqs and cost indices, not counts or quoted names', () => {
  const m = defaultModel();
  m.items = ['Key', 'Gem', 'Map'].map(name => ({ ...newItem(), name, filler: name === 'Map' }));
  m.tasks = [{ ...newTask(), name: 'A', itemPrereq: '2 || 1', cost: '2*3, "Gem"*2, 3' }];
  moveRow(m, 'items', 1, 2, true);
  assert.deepEqual(m.items.map(it => [it.name, it.filler]), [['Key', false], ['Map', true], ['Gem', false]]);
  assert.equal(m.tasks[0].itemPrereq, '3 || 1');
  assert.equal(m.tasks[0].cost, '3*3, "Gem"*2, 2');
});

test('with the toggle off only the rows move; out of range moves are refused', () => {
  const m = tasksModel();
  moveRow(m, 'tasks', 0, 1, false);
  assert.deepEqual(m.tasks.map(t => t.prereq), ['3', '', '1 && 3', '"Task C" || (1 || 1)', 'chores-75 && prev && 2']);
  assert.equal(m.goalTasks, '3 || 23');
  assert.equal(moveRow(m, 'tasks', 0, -1, true), false);
  assert.equal(moveRow(m, 'tasks', 4, 5, true), false);
});

test('moving a region row only reorders it; name references are untouched', () => {
  const m = defaultModel();
  m.regions = ['alpha', 'beta', 'gamma'].map(name => ({ name, pct: 100, color: '#111', prereq: '', parent: '' }));
  m.regions[2].prereq = 'alpha-50';
  m.tasks = [{ ...newTask(), name: 'A', region: 'gamma', prereq: 'beta*2' }];
  assert.equal(moveRow(m, 'regions', 0, 1, true), true);
  assert.deepEqual(m.regions.map(r => r.name), ['beta', 'alpha', 'gamma']);
  assert.equal(m.regions[2].prereq, 'alpha-50');
  assert.equal(m.tasks[0].prereq, 'beta*2');
  assert.equal(m.tasks[0].region, 'gamma');
  assert.equal(moveRow(m, 'regions', 2, 3, true), false);
});
