// UNIFY 1.3 candidate order and 2.6 launcher autoconnect. Secure (hosted) pages
// still try ws:// so browsers that allow mixed content can connect.
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

async function attempt(server, { fail = [], throws = [] } = {}) {
  const ap = new ArchipelagoClient();
  let reason = null;
  ap.onDisconnected = r => { reason = r; };
  FakeWS.instances.length = 0;
  FakeWS.failUrls = new Set(fail);
  FakeWS.throwUrls = new Set(throws);
  ap.connect(server, 'Me', null);
  await wait(20);
  return { ap, reason, urls: FakeWS.instances.map(w => w.url) };
}

test('hosted https: wss first, then ws; a failed ws attempt explains mixed content', async () => {
  const { reason, urls } = await attempt('localhost:38281', { fail: ['wss://localhost:38281', 'ws://localhost:38281'] });
  assert.deepEqual(urls, ['wss://localhost:38281', 'ws://localhost:38281']);
  assert.match(reason, /allow insecure content for this site in your browser settings/);
  assert.match(reason, /Taskipelago Client from the Archipelago launcher/);
});

test('hosted https: ws connects when the browser allows mixed content', async () => {
  const { ap, reason, urls } = await attempt('localhost:38281', { fail: ['wss://localhost:38281'] });
  assert.deepEqual(urls, ['wss://localhost:38281', 'ws://localhost:38281']);
  assert.equal(reason, null);
  ap.disconnect();
});

test('hosted https: a browser SecurityError says the connection was blocked', async () => {
  const { reason } = await attempt('ws://lan-host:38281', { throws: ['ws://lan-host:38281'] });
  assert.match(reason, /^Your browser blocked the insecure \(ws:\/\/\) connection\./);
  assert.match(reason, /Taskipelago Client from the Archipelago launcher/);
});

test('hosted https: archipelago.gg stays wss only', async () => {
  const { reason, urls } = await attempt('archipelago.gg:38281', { fail: ['wss://archipelago.gg:38281'] });
  assert.deepEqual(urls, ['wss://archipelago.gg:38281']);
  assert.equal(reason, 'Could not connect to server.');
});

test('explicit scheme is used as-is', async () => {
  const { ap, urls } = await attempt('ws://example:1');
  assert.deepEqual(urls, ['ws://example:1']);
  ap.disconnect();
});
