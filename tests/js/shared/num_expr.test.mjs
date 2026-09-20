// Parity: web-client/js/shared/num_expr.js must agree with
// custom_worlds/taskipelago/prereq_parser.py on the numeric expression grammar.
// The one deliberate difference: Python raises on division by zero, the client
// returns NaN so a bad seed cannot freeze the accrual loop.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { importModule } from '../helpers/env.mjs';

const golden = JSON.parse(readFileSync(
  fileURLToPath(new URL('../../parity/num_expr_golden.json', import.meta.url)), 'utf8'));
const {
  parseNumExpr, evalNumExpr, numExprConstants, numExprIsStatic, numExprToInt, numExprBindings,
} = await importModule('shared/num_expr.js');

function run(c, bindings) {
  let ast;
  try {
    ast = parseNumExpr(c.text, { label: c.label ?? 'numeric expression', locationLabel: c.location_label ?? null, allowLive: c.allow_live ?? true });
  } catch (e) {
    return { error: e.message };
  }
  return {
    ast,
    constants: [...numExprConstants(ast)].sort(),
    static: numExprIsStatic(ast),
    values: bindings.map(b => {
      const v = evalNumExpr(ast, b);
      return Number.isFinite(v) ? { v: Math.round(v * 1e10) / 1e10, i: numExprToInt(v) } : { error: 'nan' };
    }),
  };
}

test('every corpus case matches the Python golden output', () => {
  const mismatches = [];
  for (const c of golden.cases) {
    const js = run(c, golden.bindings);
    const py = c.result;
    // Python's "division by zero" exception is the client's NaN.
    const normalize = r => JSON.stringify(r, (k, v) => (k === 'error' ? 'ERR' : v));
    if (normalize(py) !== normalize(js)) mismatches.push({ text: c.text, py, js });
  }
  assert.deepEqual(mismatches, []);
});

test('error text matches Python wherever the client also refuses to parse', () => {
  for (const c of golden.cases) {
    if (!c.result.error) continue;
    const js = run(c, golden.bindings);
    assert.equal(js.error, c.result.error, c.text);
  }
});

test('numExprBindings keeps completed tasks inside the unlocked count', () => {
  const b = numExprBindings(10, 6, 4);
  assert.deepEqual(b, { N_TASKS: 10, N_TASKS_UNLOCKED: 6, N_TASKS_LOCKED: 4, N_TASKS_COMPLETED: 4 });
});

test('a plain number is a valid AST (the folded slot_data form)', () => {
  assert.equal(evalNumExpr(2.5, {}), 2.5);
  assert.ok(Number.isNaN(evalNumExpr(null, {})));
  assert.ok(Number.isNaN(evalNumExpr({ const: 'N_TASKS' }, {})));
});
