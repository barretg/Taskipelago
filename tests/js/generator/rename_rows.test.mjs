// Renaming a task / item row updates "Quoted" references (model.js countRowRenameRefs / rewriteRowRenameRefs).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { importModule } from '../helpers/env.mjs';

const { defaultModel, newTask, newItem, countRowRenameRefs, rewriteRowRenameRefs } = await importModule('generator/model.js');

function model() {
  const m = defaultModel();
  m.items = ['Key', 'Gem'].map(name => ({ ...newItem(), name }));
  m.tasks = [
    { ...newTask(), name: 'Task A' },
    { ...newTask(), name: 'Task B', prereq: '"Task A" && item("Key")', itemPrereq: '"Key" || task("Task A")', cost: '"Key"*2' },
  ];
  m.goalTasks = '"Task A" || item("Key")';
  m.regions = [{ name: 'chores', pct: 100, prereq: '"Task A" && task("Task A") && item("Key")', color: '' }];
  return m;
}

test('renaming a task rewrites quoted task names in their scopes only', () => {
  const m = model();
  m.tasks[0].name = 'Task Z';
  assert.equal(countRowRenameRefs(m, 'tasks', 0, 'Task A'), 4);
  assert.equal(rewriteRowRenameRefs(m, 'tasks', 0, 'Task A'), 4);
  assert.equal(m.tasks[1].prereq, '"Task Z" && item("Key")');
  assert.equal(m.tasks[1].itemPrereq, '"Key" || task("Task Z")');
  assert.equal(m.goalTasks, '"Task Z" || item("Key")');
  assert.equal(m.regions[0].prereq, '"Task A" && task("Task Z") && item("Key")');
});

test('renaming an item rewrites item prereqs, item scopes and costs', () => {
  const m = model();
  m.items[0].name = 'Door Key';
  assert.equal(rewriteRowRenameRefs(m, 'items', 0, 'Key'), 5);
  assert.equal(m.tasks[1].prereq, '"Task A" && item("Door Key")');
  assert.equal(m.tasks[1].itemPrereq, '"Door Key" || task("Task A")');
  assert.equal(m.tasks[1].cost, '"Door Key"*2');
  assert.equal(m.goalTasks, '"Task A" || item("Door Key")');
});

test('no refs when the rename is blank, a no-op, shadowed or collides', () => {
  const m = model();
  m.tasks[0].name = '  Task A ';
  assert.equal(countRowRenameRefs(m, 'tasks', 0, 'Task A'), 0);
  m.tasks[0].name = '';
  assert.equal(countRowRenameRefs(m, 'tasks', 0, 'Task A'), 0);
  m.tasks[0].name = 'Task B';
  assert.equal(countRowRenameRefs(m, 'tasks', 0, 'Task A'), 0);
  // An earlier row with the old name is what the references resolve to.
  m.tasks[0].name = 'Task A';
  m.tasks[1].name = 'Task Q';
  assert.equal(countRowRenameRefs(m, 'tasks', 1, 'Task A'), 0);
});
