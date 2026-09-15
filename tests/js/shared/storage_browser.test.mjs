// storage.js with the browser localStorage backend (hosted), including values
// written by the v1.0.x web client, which must still read back.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, importModule } from '../helpers/env.mjs';

setupDom({
  url: 'https://barretg.github.io/Taskipelago/web-client/',
  localStorage: {
    'taskipelago_last_conn': JSON.stringify({ server: 'archipelago.gg:1', slot: 'me' }),
    'taskipelago_notify_v3::archipelago.gg:1::me::S': '12',
    'taskipelago_manual_v1::archipelago.gg:1::me::S': JSON.stringify({ Gold: 2 }),
  },
});

const { loadConfig, hasFeature } = await importModule('shared/config.js');
const storage = await importModule('shared/storage.js');
await loadConfig();
await storage.initStorage();

test('hosted defaults', () => {
  assert.equal(hasFeature('insecureWs'), false);
  assert.equal(hasFeature('localStorageService'), false);
});

test('reads v1.0.x values', () => {
  assert.deepEqual(storage.get('taskipelago_last_conn'), { server: 'archipelago.gg:1', slot: 'me' });
  assert.equal(parseInt(storage.get('taskipelago_notify_v3::archipelago.gg:1::me::S'), 10), 12);
  assert.deepEqual(storage.get('taskipelago_manual_v1::archipelago.gg:1::me::S'), { Gold: 2 });
});

test('writes stay readable by v1.0.x', () => {
  storage.set('taskipelago_notify_v3::x', 15);
  assert.equal(localStorage.getItem('taskipelago_notify_v3::x'), '15');
  storage.set('taskipelago_last_conn', { server: 's', slot: 't' });
  assert.deepEqual(JSON.parse(localStorage.getItem('taskipelago_last_conn')), { server: 's', slot: 't' });
  storage.remove('taskipelago_notify_v3::x');
  assert.equal(localStorage.getItem('taskipelago_notify_v3::x'), null);
});
