// UNIFY 5.1: notification dedupe and DeathLink amnesty.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, bootApp, connect, $, FakeWS, errors, wait, BASIC_SLOT_DATA } from '../helpers/env.mjs';

setupDom();
await bootApp();

const cards = kind => [...$('notif-list').querySelectorAll('.notif-card')]
  .filter(c => c.querySelector('.notif-meta').textContent.startsWith(kind.toUpperCase()));

test('setup', async () => {
  await connect({
    ...BASIC_SLOT_DATA, death_link_enabled: true, death_link_pool: ['Pushups'], death_link_amnesty: 1,
  }, {
    onSent: (m, ws) => {
      if (m.cmd === 'Get') {
        setTimeout(() => ws.recv([{ cmd: 'Retrieved', keys: Object.fromEntries(m.keys.map(k => [k, k.includes('notify') ? 0 : null])) }]), 0);
      }
    },
  });
  await wait(10);
  assert.equal($('connect-status').textContent, 'Connected.');
});

test('DeathLink: amnesty, 2s dedupe, then trigger', async () => {
  const dl = data => FakeWS.last.recv([{ cmd: 'Bounced', tags: ['DeathLink'], data }]);
  dl({ time: 1, source: 'Other', cause: 'fell' }); // absorbed by amnesty
  dl({ time: 1, source: 'Other', cause: 'fell' }); // duplicate: ignored, amnesty untouched
  await wait(10);
  assert.equal(cards('deathlink').length, 0);
  dl({ time: 2, source: 'Other', cause: 'fell' });
  await wait(10);
  assert.equal(cards('deathlink').length, 1);
  assert.match(cards('deathlink')[0].textContent, /Task: Pushups/);
});

test('DeathLink: own bounces are ignored', async () => {
  FakeWS.last.recv([{ cmd: 'Bounced', tags: ['DeathLink'], data: { time: 3, source: 'Me' } }]);
  await wait(10);
  assert.equal(cards('deathlink').length, 1);
});

test('DeathLink: amnesty is not reset by network updates', async () => {
  FakeWS.last.recv([{ cmd: 'RoomUpdate', checked_locations: [] }]);
  FakeWS.last.recv([{ cmd: 'Bounced', tags: ['DeathLink'], data: { time: 4, source: 'Other' } }]); // amnesty
  FakeWS.last.recv([{ cmd: 'RoomUpdate', checked_locations: [] }]);
  FakeWS.last.recv([{ cmd: 'Bounced', tags: ['DeathLink'], data: { time: 5, source: 'Other' } }]); // triggers
  await wait(10);
  assert.equal(cards('deathlink').length, 2);
});

test('reward: same (item, player, location) within 1.5s is deduped', async () => {
  const item = { item: 300, location: 5, player: 2, flags: 1 };
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 0, items: [item] }]);
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 1, items: [item] }]);
  await wait(10);
  assert.equal(cards('reward').length, 1);
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 2, items: [{ ...item, location: 6 }] }]);
  await wait(10);
  assert.equal(cards('reward').length, 2);
});

test('no runtime errors', () => {
  assert.deepEqual(errors.map(e => String(e?.stack || e)), []);
});
