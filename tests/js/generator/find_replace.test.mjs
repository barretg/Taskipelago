// v1.1 F5: find and replace engine (generator/find_replace.js), no DOM.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { importModule } from '../helpers/env.mjs';

const { defaultModel, newTask, newItem, newDeathLink } = await importModule('generator/model.js');
const { collectTargets, findRegExp, findMatches, replaceMatch, replaceAll } = await importModule('generator/find_replace.js');

function model() {
  const m = defaultModel();
  m.goalTasks = '"Chore" || 2';
  m.tasks = [
    { ...newTask(), name: 'Chore', desc: 'chore time', prereq: '', itemPrereq: '"Chore Key"', cost: '"Chore Key"*2' },
    { ...newTask(), name: 'Big chores', prereq: '"Chore" && chores-50' },
  ];
  m.items = [{ ...newItem(), name: 'Chore Key' }, { ...newItem(), name: 'Chore filler', filler: true }];
  m.deathLink = [{ ...newDeathLink(), text: 'Do a chore (a.k.a. $1)' }];
  m.regions = [{ name: 'chores', pct: 100, color: '', prereq: 'Chore' }];
  return m;
}

const count = (m, find, opts, scopes) => findMatches(collectTargets(m, scopes), findRegExp(find, opts)).length;

test('targets follow section order and skip filler items', () => {
  const fields = collectTargets(model()).map(t => t.field);
  assert.deepEqual(fields, [
    'goalTasks',
    'tasks.0.name', 'tasks.0.desc', 'tasks.0.prereq', 'tasks.0.itemPrereq', 'tasks.0.cost',
    'tasks.1.name', 'tasks.1.desc', 'tasks.1.prereq', 'tasks.1.itemPrereq', 'tasks.1.cost',
    'items.0.name', 'deathlink.0.text', 'regions.0.prereq',
  ]);
  assert.deepEqual(collectTargets(model(), { taskNames: false, descriptions: false, taskPrereqs: false, itemPrereqs: false,
    costs: false, deathLink: false, regionPrereqs: false, goalTasks: false }).map(t => t.field), ['items.0.name']);
});

test('match case, whole word and special characters', () => {
  const m = model();
  assert.equal(count(m, 'chore'), 11);
  assert.equal(count(m, 'chore', { matchCase: true }), 4);
  assert.equal(count(m, 'chore', { wholeWord: true }), 9);
  assert.equal(count(m, 'chore', { wholeWord: true, matchCase: true }), 2);
  assert.equal(count(m, '"Chore"', { wholeWord: true }), 2);
  assert.equal(count(m, '(a.k.a. $1)'), 1);
  assert.equal(count(m, ''), 0);
  assert.equal(count(m, 'chore', {}, { taskPrereqs: false }), 9);
});

test('replace one match and replace all', () => {
  const m = model();
  const re = findRegExp('chore', { wholeWord: true });
  const matches = findMatches(collectTargets(m), re);
  replaceMatch(matches[1], 'Dish');
  assert.equal(m.tasks[0].name, 'Dish');
  assert.deepEqual(replaceAll(collectTargets(m), findRegExp('chore', { wholeWord: true }), '$&-x'), { count: 8, fields: 8 });
  assert.equal(m.goalTasks, '"$&-x" || 2');
  assert.equal(m.items[1].name, 'Chore filler', 'filler rows are not replaced');
  assert.equal(m.tasks[1].prereq, '"$&-x" && chores-50');
});

test('descriptions stay within the length limit', () => {
  const m = model();
  replaceAll(collectTargets(m), findRegExp('time'), 'x'.repeat(200));
  assert.equal(Array.from(m.tasks[0].desc).length, 100);
});
