// Local mode: ws fallback order and launcher prefill + autoconnect.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, bootApp, $, FakeWS, connectedPacket, BASIC_SLOT_DATA, jsonResponse, wait } from '../helpers/env.mjs';

FakeWS.failUrls = new Set(['ws://archipelago.gg:38281-never']);
FakeWS.onSent = (m, ws) => { if (m.cmd === 'Connect') ws.recv([connectedPacket(BASIC_SLOT_DATA)]); };

setupDom({
  config: {
    mode: 'local', features: { insecureWs: true, localStorageService: true }, token: 't',
    launch: { server: 'archipelago.gg:38281', slot: 'Me', password: 'pw', autoconnect: true },
  },
  fetch: async (url) => (url === '/api/storage' ? jsonResponse({}) : { ok: true, status: 204, json: async () => ({}) }),
});
await bootApp();
await wait(40);

test('prefills from launch info and connects once', () => {
  assert.equal($('server-input').value, 'archipelago.gg:38281');
  assert.equal($('slot-input').value, 'Me');
  assert.equal($('pass-input').value, 'pw');
  assert.equal(FakeWS.instances.length, 1);
  assert.equal(FakeWS.instances[0].url, 'wss://archipelago.gg:38281');
  assert.equal($('connect-status').textContent, 'Connected.');
});
