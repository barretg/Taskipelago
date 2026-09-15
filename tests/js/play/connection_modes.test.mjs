// UNIFY 1.3 candidate order and 2.6 launcher autoconnect.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, importModule, FakeWS, wait } from '../helpers/env.mjs';

setupDom({
  url: 'https://barretg.github.io/Taskipelago/web-client/',
  config: { mode: 'hosted', features: { insecureWs: false, localStorageService: false }, launch: null, token: null },
});
const { loadConfig } = await importModule('shared/config.js');
await loadConfig();
const { ArchipelagoClient } = await importModule('archipelago.js');

test('hosted https: wss only, with the launcher hint on failure', async () => {
  const ap = new ArchipelagoClient();
  let reason = null;
  ap.onDisconnected = r => { reason = r; };
  FakeWS.instances.length = 0;
  FakeWS.failUrls = new Set(['wss://localhost:38281']);
  ap.connect('localhost:38281', 'Me', null);
  await wait(20);
  assert.deepEqual(FakeWS.instances.map(w => w.url), ['wss://localhost:38281']);
  assert.match(reason, /Taskipelago Client from the Archipelago launcher/);
});

test('explicit scheme is used as-is', async () => {
  const ap = new ArchipelagoClient();
  FakeWS.instances.length = 0;
  FakeWS.failUrls = new Set();
  ap.connect('ws://example:1', 'Me', null);
  await wait(10);
  assert.deepEqual(FakeWS.instances.map(w => w.url), ['ws://example:1']);
  ap.disconnect();
});
