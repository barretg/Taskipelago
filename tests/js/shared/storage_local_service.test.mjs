// storage.js with the webhost backend (localStorageService on).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, importModule, jsonResponse, wait } from '../helpers/env.mjs';

const calls = [];
const server = { taskipelago_last_conn: { server: 'h:1', slot: 'me' }, n: 5 };

setupDom({
  config: {
    mode: 'local', features: { insecureWs: true, localStorageService: true },
    launch: null, token: 'tok',
  },
  fetch: async (url, opts = {}) => {
    calls.push({ url, method: opts.method || 'GET', headers: opts.headers || {}, body: opts.body });
    if (url === '/api/storage' && (opts.method || 'GET') === 'GET') return jsonResponse(server);
    return { ok: true, status: 204, json: async () => ({}), text: async () => '' };
  },
});

const { loadConfig } = await importModule('shared/config.js');
const storage = await importModule('shared/storage.js');
await loadConfig();
await storage.initStorage();

test('loads the whole object once with the token header', () => {
  const gets = calls.filter(c => c.url === '/api/storage' && c.method === 'GET');
  assert.equal(gets.length, 1);
  assert.equal(gets[0].headers['X-Taskipelago-Token'], 'tok');
  assert.deepEqual(storage.get('taskipelago_last_conn'), { server: 'h:1', slot: 'me' });
  assert.equal(storage.get('missing', 'dflt'), 'dflt');
});

test('sends a heartbeat', () => {
  assert.ok(calls.some(c => c.url === '/api/heartbeat' && c.method === 'POST'));
});

test('writes are debounced into one PATCH', async () => {
  storage.set('a', 1);
  storage.set('b', { x: [1] });
  storage.remove('n');
  storage.set('a', 2);
  assert.equal(calls.filter(c => c.method === 'PATCH').length, 0);
  await wait(400);
  const patches = calls.filter(c => c.method === 'PATCH');
  assert.equal(patches.length, 1);
  assert.deepEqual(JSON.parse(patches[0].body), { set: { a: 2, b: { x: [1] } }, remove: ['n'] });
  assert.equal(storage.get('a'), 2);
  assert.equal(storage.get('n'), null);
});

test('returned values are copies', () => {
  const v = storage.get('b');
  v.x.push(2);
  assert.deepEqual(storage.get('b'), { x: [1] });
});
