// UNIFY 3.1: per-seed state in AP data storage (manual consumptions, notify
// cursor, purchases) plus the TaskipelagoSync Bounce kept for v1.0.x clients.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  setupDom, bootApp, connect, importModule, $, FakeWS, errors, wait, sent,
} from '../helpers/env.mjs';

const KEYS = {
  manual: 'taskipelago_manual::Me::S',
  notify: 'taskipelago_notify::Me::S',
  purchases: 'taskipelago_purchases::Me::S',
  deathlink: 'taskipelago_deathlink::Me::S',
};

const SLOT_DATA = {
  tasks: ['Wash', 'Cook', 'Bake'], items: ['Key', 'Gold', 'Gem'],
  task_prereqs: ['', '', ''], item_prereqs: ['', '', ''],
  item_consumable: [false, true, true],
  task_cost_amounts: [[], [[['Gold', 1]]], [[['Gold', 1]]]],
  base_reward_location_id: 100, base_complete_location_id: 200, base_item_id: 300, base_token_id: 400,
  seed_name: 'S', lock_prereqs: false, hide_unreachable_tasks: false,
};

setupDom({
  localStorage: { 'taskipelago_manual_v1::localhost:38281::Me::S': JSON.stringify({ Gold: 1 }) },
});
await bootApp();
const { state, CLIENT_ID } = await importModule('play/state.js');
const logic = await importModule('play/logic.js');

const setsFor = key => sent.filter(m => m.cmd === 'Set' && m.key === key);

test('connect subscribes to every per-seed key in one batch', async () => {
  await connect(SLOT_DATA, {
    onSent: (m, ws) => {
      if (m.cmd === 'Connect') {
        // Items arrive before the Retrieved answer, as on a real server.
        ws.recv([{ cmd: 'ReceivedItems', index: 0, items: [
          { item: 300, location: 5, player: 2, flags: 1 },
          { item: 301, location: 6, player: 2, flags: 0 },
        ] }]);
      }
      if (m.cmd === 'Get') {
        setTimeout(() => ws.recv([{ cmd: 'Retrieved', keys: {
          [KEYS.manual]: null, [KEYS.notify]: 1, [KEYS.purchases]: { 1: { Gold: 1 }, bad: { Gold: 1 } },
          [KEYS.deathlink]: null,
        } }]), 100);
      }
    },
  });
  const get = sent.find(m => m.cmd === 'Get');
  const notify = sent.find(m => m.cmd === 'SetNotify');
  assert.deepEqual(get.keys, Object.values(KEYS));
  assert.deepEqual(notify.keys, Object.values(KEYS));
});

test('notifications wait for the server notify cursor', async () => {
  assert.match($('notif-list').textContent, /No notifications/);
  assert.match($('items-list').textContent, /Key/); // the item list does not wait
  await wait(120);
  const text = $('notif-list').textContent;
  assert.match(text, /Gold/);
  assert.doesNotMatch(text, /Key/); // index 0 is before the server cursor (1)
});

test('empty server manual key is filled from the device copy', () => {
  const sets = setsFor(KEYS.manual);
  assert.equal(sets.length, 1);
  assert.deepEqual(sets[0].operations, [{ operation: 'replace', value: { Gold: 1 } }]);
  assert.equal(sets[0].client_id, CLIENT_ID);
});

test('server purchases are applied and sanitized', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(state.taskPurchases)), { 1: { Gold: 1 } });
});

test('notify cursor is written with max, debounced', async () => {
  assert.equal(setsFor(KEYS.notify).length, 0);
  await wait(1050);
  const sets = setsFor(KEYS.notify);
  assert.equal(sets.length, 1);
  assert.deepEqual(sets[0].operations, [{ operation: 'max', value: 2 }]);
  assert.equal(localStorage.getItem('taskipelago_notify_v3::localhost:38281::Me::S'), '2');
});

test('SetReply from another client updates the device copy without a Set', async () => {
  const before = setsFor(KEYS.manual).length;
  FakeWS.last.recv([{ cmd: 'SetReply', key: KEYS.manual, value: {}, client_id: 'other' }]);
  await wait(10);
  assert.deepEqual(state.manualConsumptions, {});
  assert.equal(localStorage.getItem('taskipelago_manual_v1::localhost:38281::Me::S'), '{}');
  assert.equal(setsFor(KEYS.manual).length, before);
});

test('own SetReply echoes are ignored', async () => {
  FakeWS.last.recv([{ cmd: 'SetReply', key: KEYS.manual, value: { Gold: 5 }, client_id: CLIENT_ID }]);
  await wait(10);
  assert.deepEqual(state.manualConsumptions, {});
});

test('Bounce from a v1.0.x client is sanitized and not re-sent', async () => {
  const before = setsFor(KEYS.manual).length;
  FakeWS.last.recv([{ cmd: 'Bounced', tags: ['TaskipelagoSync'], data: {
    type: 'taskipelago_manual_sync', client_id: 'old', seed: 'S', slot_name: 'Me',
    manual_consumptions: { Gem: 2, Junk: 0, Bad: 'x' },
  } }]);
  await wait(10);
  assert.deepEqual(state.manualConsumptions, { Gem: 2 });
  assert.equal(setsFor(KEYS.manual).length, before);
  FakeWS.last.recv([{ cmd: 'SetReply', key: KEYS.manual, value: {}, client_id: 'other' }]);
  await wait(10);
});

test('manual -1 writes the server key and still sends the Bounce', async () => {
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 2, items: [{ item: 302, location: 7, player: 2, flags: 0 }] }]);
  await wait(10);
  sent.length = 0;
  const row = [...$('consumables-list').querySelectorAll('.consumable-entry')].find(r => r.textContent.includes('Gem'));
  [...row.querySelectorAll('button')].find(b => b.textContent === '-1').click();
  await wait(10);
  assert.deepEqual(setsFor(KEYS.manual)[0].operations, [{ operation: 'replace', value: { Gem: 1 } }]);
  const bounce = sent.find(m => m.cmd === 'Bounce' && m.tags.includes('TaskipelagoSync'));
  assert.deepEqual(bounce.data.manual_consumptions, { Gem: 1 });
});

test('purchase writes the choice with update', async () => {
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 3, items: [{ item: 301, location: 8, player: 2, flags: 0 }] }]);
  await wait(10);
  sent.length = 0;
  logic.attemptPurchase(2);
  const sets = setsFor(KEYS.purchases);
  assert.equal(sets.length, 1);
  assert.deepEqual(sets[0].operations, [{ operation: 'update', value: { 2: { Gold: 1 } } }]);
});

test('purchases from another client override local entries', async () => {
  FakeWS.last.recv([{ cmd: 'SetReply', key: KEYS.purchases, value: { 2: { Gold: 3 } }, client_id: 'other' }]);
  await wait(10);
  assert.deepEqual(state.taskPurchases[2], { Gold: 3 });
});

test('server restart moves the cursor back with replace', async () => {
  sent.length = 0;
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 0, items: [{ item: 302, location: 9, player: 2, flags: 0 }] }]);
  await wait(10);
  assert.deepEqual(setsFor(KEYS.notify)[0].operations, [{ operation: 'replace', value: 0 }]);
  assert.equal(localStorage.getItem('taskipelago_notify_v3::localhost:38281::Me::S'), '1');
});

test('UI toggles persist in taskipelago_ui', async () => {
  $('hide-completed-cb').checked = true;
  $('hide-completed-cb').dispatchEvent(new Event('change'));
  $('connect-btn').click(); // disconnect
  await wait(10);
  assert.equal($('hide-completed-cb').checked, true);
  assert.deepEqual(JSON.parse(localStorage.getItem('taskipelago_ui')), { hideCompleted: true });
});

test('no runtime errors', () => {
  assert.deepEqual(errors.map(e => String(e?.stack || e)), []);
});
