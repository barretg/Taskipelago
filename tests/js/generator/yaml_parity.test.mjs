// UNIFY 5.3 / M4 gate: the JS YAML Generator must import and export exactly
// like the legacy Tk generator (tests/parity/generator_golden.json). Export
// text is read back with PyYAML ($PYTHON, default python3), as the apworld does.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { importModule } from '../helpers/env.mjs';

const PARITY = fileURLToPath(new URL('../../parity/', import.meta.url));
const golden = JSON.parse(readFileSync(PARITY + 'generator_golden.json', 'utf8'));
const PLACEHOLDER = golden.placeholder;

const { loadYaml, dumpYaml } = await importModule('shared/yaml11.js');
const { PyError } = await importModule('shared/pyish.js');
const { defaultModel, normalizeModel } = await importModule('generator/model.js');
const { importDoc } = await importModule('generator/yaml_import.js');
const { buildExport } = await importModule('generator/yaml_export.js');

const randomFiller = () => 'RANDOM FILLER';

/** Same shape as legacy_generator.harvest. */
function harvest(model) {
  const { ui: _ui, ...rest } = model;
  return {
    ...rest,
    items: model.items.map(({ ui: _itemUi, ...it }) => ({ ...it, name: it.filler ? PLACEHOLDER : it.name })),
  };
}

function pyLoadAll(texts) {
  const script = 'import json, sys, yaml\n'
    + 'print(json.dumps([yaml.safe_load(t) for t in json.load(sys.stdin)]))';
  const out = execFileSync(process.env.PYTHON || 'python3', ['-c', script], { input: JSON.stringify(texts) });
  return JSON.parse(out.toString());
}

test('every corpus YAML imports like the legacy generator', () => {
  assert.ok(golden.imports.length >= 14);
  const mismatches = [];
  for (const entry of golden.imports) {
    const text = readFileSync(`${PARITY}yaml_corpus/${entry.file}`, 'utf8');
    let js;
    try {
      const doc = loadYaml(text);
      try {
        const r = importDoc(defaultModel(), doc, { randomFiller });
        js = { ok: r.ok, exception: null, model: harvest(r.model), messages: r.messages };
        if (!r.ok) js.model = harvest(defaultModel());
      } catch (e) {
        if (!(e instanceof PyError)) throw e;
        js = { ok: false, exception: e.pyType, model: null, messages: [] };
      }
    } catch (e) {
      if (e instanceof PyError) throw e;
      js = { load_error: true };
    }
    let expected = entry.result;
    if (expected.load_error) expected = { load_error: true };
    else if (expected.exception) expected = { ...expected, messages: [] };
    if (JSON.stringify(js) !== JSON.stringify(expected)) mismatches.push({ file: entry.file, expected, js });
  }
  assert.deepEqual(mismatches, []);
});

test('every export case matches the legacy generator after a PyYAML round trip', async () => {
  const runs = [];
  for (const c of golden.exports) {
    const messages = [];
    const confirm = async (title, text) => {
      messages.push(['confirm', title, text]);
      return c.confirm;
    };
    const r = await buildExport(normalizeModel(structuredClone(c.model)), { confirm, randomFiller });
    if (r.error) messages.push(['error', ...r.error]);
    runs.push({ c, messages, text: r.data ? dumpYaml(r.data) : null });
  }
  const loaded = pyLoadAll(runs.filter(x => x.text !== null).map(x => x.text));
  const mismatches = [];
  for (const run of runs) {
    let data = null;
    if (run.text !== null) {
      data = loaded.shift();
      const block = data.Taskipelago;
      block.item_fillers.forEach((f, i) => { if (f) block.items[i] = PLACEHOLDER; });
    }
    const js = { data, messages: run.messages };
    if (JSON.stringify(js) !== JSON.stringify(run.c.result)) {
      mismatches.push({ name: run.c.name, expected: run.c.result, js });
    }
  }
  assert.deepEqual(mismatches, []);
});
