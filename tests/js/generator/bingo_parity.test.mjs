// UNIFY 5.5 / M5: the JS Taskipelabingo generator must export, save settings,
// count and load exactly like the legacy Tk tab (tests/parity/generator_golden.json,
// "bingo"). Randomness follows legacy_generator.FixedRandom.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { importModule } from '../helpers/env.mjs';

const PARITY = fileURLToPath(new URL('../../parity/', import.meta.url));
const { bingo } = JSON.parse(readFileSync(PARITY + 'generator_golden.json', 'utf8'));

const { dumpYaml } = await importModule('shared/yaml11.js');
const { PyError } = await importModule('shared/pyish.js');
const { FILLER_ITEMS } = await importModule('shared/filler.js');
const {
  buildBingoExport, bingoSettingsDoc, bingoCounts, loadBingoDoc, defaultBingoModel, goalTermCount, genBingoalExpr,
} = await importModule('bingo_gen/bingo_model.js');

const fixedRng = {
  sample: (pool, n) => [...pool].reverse().slice(0, n),
  shuffle: list => list.reverse(),
  filler: () => FILLER_ITEMS[0],
};

function pyLoadAll(texts) {
  const script = 'import json, sys, yaml\nprint(json.dumps([yaml.safe_load(t) for t in json.load(sys.stdin)]))';
  return JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['-c', script], { input: JSON.stringify(texts) }).toString());
}

const mismatch = (label, expected, actual) => (JSON.stringify(expected) === JSON.stringify(actual) ? [] : [{ label, expected, actual }]);

test('bingo exports match the legacy tab after a PyYAML round trip', () => {
  assert.ok(bingo.exports.length >= 9);
  const runs = bingo.exports.map(c => {
    const r = buildBingoExport(structuredClone(c.model), fixedRng);
    return { c, messages: r.error ? [['error', ...r.error]] : [], text: r.data ? dumpYaml(r.data) : null };
  });
  const loaded = pyLoadAll(runs.filter(r => r.text !== null).map(r => r.text));
  const bad = runs.flatMap(run => mismatch(run.c.name, run.c.result,
    { data: run.text === null ? null : loaded.shift(), messages: run.messages }));
  assert.deepEqual(bad, []);
});

test('bingo settings files match', () => {
  const texts = bingo.settings.map(c => dumpYaml(bingoSettingsDoc(structuredClone(c.model))));
  const loaded = pyLoadAll(texts);
  assert.deepEqual(bingo.settings.flatMap((c, i) => mismatch(c.name, c.result, loaded[i])), []);
});

test('bingo counter labels match', () => {
  assert.deepEqual(bingo.counts.flatMap((c, i) => mismatch(String(i), c.result, bingoCounts(c.model))), []);
});

test('bingo loads match', () => {
  const bad = bingo.loads.flatMap(c => {
    let actual;
    try {
      const r = loadBingoDoc(defaultBingoModel(), structuredClone(c.doc));
      actual = { kind: r.kind, exception: null, ok: r.ok, model: r.model, messages: r.messages };
    } catch (e) {
      if (!(e instanceof PyError)) throw e;
      actual = { kind: c.result.kind, exception: e.pyType, model: null, messages: [] };
    }
    return mismatch(c.name, c.result, actual);
  });
  assert.deepEqual(bad, []);
});

test('oversized goal expressions are refused instead of freezing', () => {
  assert.equal(goalTermCount(18, 9), 48620);
  assert.equal(genBingoalExpr(35, 18, 9).split(' || ').length, 48620);
  assert.ok(goalTermCount(42, 21) > 100000);
  const spaces = Array.from({ length: 400 }, (_, i) => `S${i}`).join('\n');
  const r = buildBingoExport({ ...defaultBingoModel(), playerName: 'Big', x: 20, y: 20, bingoal: 21, spaces }, fixedRng);
  assert.equal(r.error[0], 'Error');
  assert.match(r.error[1], /too large/);
});
