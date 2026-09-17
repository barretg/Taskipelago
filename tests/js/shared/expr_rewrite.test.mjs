// v1.1 B0: name reference rewriting used by F4 (rename updates references).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { importModule } from '../helpers/env.mjs';

const { renameNameRefs, countNameRefs } = await importModule('shared/expr_rewrite.js');

test('renameNameRefs changes exactly the name tokens', () => {
  const cases = [
    ['x', 'zed', 1],
    ['x-50', 'zed-50', 1],
    ['x*3', 'zed*3', 1],
    ['(x || y) && 2', '(zed || y) && 2', 1],
    ['"Quoted x"', '"Quoted x"', 0],
    ['xy', 'xy', 0],
    ['x_y', 'x_y', 0],
    ['x,x-1,  x*2&&x||x', 'zed,zed-1,  zed*2&&zed||zed', 5],
    ['2 && "x" && x', '2 && "x" && zed', 1],
    ['', '', 0],
  ];
  for (const [input, expected, count] of cases) {
    assert.deepEqual(renameNameRefs(input, 'x', 'zed'), { text: expected, count }, input);
  }
});

test('renameNameRefs handles F8 names and suffix-like names', () => {
  assert.deepEqual(renameNameRefs('weapons+*3 || weapons+', 'weapons+', 'arms'), { text: 'arms*3 || arms', count: 2 });
  assert.deepEqual(renameNameRefs('chores--50', 'chores-', 'jobs'), { text: 'jobs-50', count: 1 });
  assert.deepEqual(renameNameRefs('chores--50', 'chores', 'jobs'), { text: 'chores--50', count: 0 });
  assert.equal(renameNameRefs(null, 'x', 'y').text, null);
});

test('countNameRefs', () => {
  assert.equal(countNameRefs('a && a-2 && (b || a*1)', 'a'), 3);
  assert.equal(countNameRefs('"a" && ab', 'a'), 0);
});
