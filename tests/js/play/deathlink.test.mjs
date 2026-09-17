// v1.1 F2 (alert color and sound) and F3 (DeathLink task cards, queue sync, optional lock).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  setupDom, bootApp, connect, importModule, $, FakeWS, errors, wait, sent, fakeDataStorage,
} from '../helpers/env.mjs';

const window = setupDom();

// WebAudio stub: records scheduled oscillators.
const beeps = [];
class FakeAudioContext {
  constructor() { this.state = 'running'; this.currentTime = 0; this.destination = {}; }
  resume() { this.state = 'running'; return Promise.resolve(); }
  createOscillator() {
    return { frequency: {}, connect() {}, start: () => beeps.push(Date.now()), stop() {} };
  }
  createGain() {
    return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} };
  }
}
globalThis.AudioContext = FakeAudioContext;

await bootApp();
const { state } = await importModule('play/state.js');
const logic = await importModule('play/logic.js');

const KEY = 'taskipelago_deathlink::Me::S';
const DEVICE_KEY = 'taskipelago_deathlink_v1::localhost:38281::Me::S';
const SLOT_DATA = {
  tasks: ['Wash', 'Cook'], items: ['Key', 'Gold'], task_prereqs: ['', ''], item_prereqs: ['', ''],
  item_consumable: [false, true], task_cost_amounts: [[], [[['Gold', 1]]]],
  base_reward_location_id: 100, base_complete_location_id: 200, base_item_id: 300, base_token_id: 400,
  seed_name: 'S', lock_prereqs: false, hide_unreachable_tasks: false,
  death_link_enabled: true, death_link_pool: ['Pushups'], death_link_amnesty: 0, death_link_lock_tasks: true,
};

const storage = fakeDataStorage();
const dl = (time, source = 'Other', cause = '') => FakeWS.last.recv([{ cmd: 'Bounced', tags: ['DeathLink'], data: { time, source, cause } }]);
const cards = () => [...$('deathlink-cards').querySelectorAll('.dl-task-card')];
const taskButtons = () => [...$('tasks-list').querySelectorAll('button')];
const dlNotifs = () => $('notif-list').querySelectorAll('.notif-card.notif-deathlink');
const locationChecks = () => sent.filter(m => m.cmd === 'LocationChecks').length;

test('connect with lock on and an empty queue', async () => {
  await connect(SLOT_DATA, { onSent: storage });
  await wait(10);
  assert.equal($('connect-status').textContent, 'Connected.');
  assert.ok($('deathlink-cards').classList.contains('hidden'));
  assert.equal(taskButtons().every(b => !b.disabled), true);
});

test('three DeathLinks stack three red cards, lock everything else, then unlock after the last', async () => {
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 0, items: [{ item: 301, location: 1, player: 2, flags: 0 }] }]);
  dl(10, 'Other', 'fell');
  dl(11);
  dl(12);
  await wait(10);
  assert.equal(cards().length, 3);
  assert.deepEqual(cards().map(c => c.dataset.id), ['10|Other', '11|Other', '12|Other']);
  assert.match(cards()[0].textContent, /DeathLink: Pushups/);
  assert.match(cards()[0].textContent, /From Other: fell/);
  assert.match($('deathlink-cards').textContent, /Locked until your DeathLink task\(s\) are done/);
  assert.ok($('tasks-list').classList.contains('locked-dl'));
  assert.ok(taskButtons().length > 0 && taskButtons().every(b => b.disabled));
  assert.equal($('deathlink-send-btn').disabled, false);
  assert.equal(Object.keys(storage.store[KEY]).length, 3);
  assert.equal(Object.keys(JSON.parse(localStorage.getItem(DEVICE_KEY))).length, 3);

  const before = locationChecks();
  logic.completeTask(0);
  logic.attemptPurchase(1);
  assert.equal(locationChecks(), before, 'entry points no-op while locked');
  assert.equal(state.taskPurchases[1], undefined);

  // View toggles still work while locked.
  $('hide-completed-cb').click();
  $('hide-completed-cb').click();

  cards()[0].querySelector('button').click();
  cards()[0].querySelector('button').click();
  await wait(10);
  assert.equal(cards().length, 1);
  assert.ok(taskButtons().every(b => b.disabled));
  cards()[0].querySelector('button').click();
  await wait(10);
  assert.equal(cards().length, 0);
  assert.ok(!$('tasks-list').classList.contains('locked-dl'));
  assert.ok(taskButtons().some(b => !b.disabled));
  assert.deepEqual(storage.store[KEY], {});
});

test('F2: DeathLink notifications are red, beep, and switch to the Notifications subtab', async () => {
  [...document.querySelectorAll('.sub-tabs .tab-btn')].find(b => b.dataset.subtab === 'items').click();
  const n = beeps.length;
  dl(20);
  await wait(10);
  assert.ok(dlNotifs().length >= 1);
  assert.equal(beeps.length, n + 2, 'two-tone beep');
  assert.ok($('subtab-notifications').classList.contains('active'));
  assert.equal(document.querySelectorAll('.notif-card.notif-reward.notif-deathlink').length, 0);
  assert.equal(document.title, 'DEATHLINK! - Taskipelago', 'title flashes while the window is unfocused');
  window.dispatchEvent(new window.Event('focus'));
  assert.notEqual(document.title, 'DEATHLINK! - Taskipelago');

  $('dl-sound-cb').click(); // off
  assert.equal(JSON.parse(localStorage.getItem('taskipelago_ui')).dlSound, false);
  dl(21);
  await wait(10);
  assert.equal(beeps.length, n + 2, 'no sound when the setting is off');
  $('dl-sound-cb').click();
  for (const c of cards()) c.querySelector('button').click();
  await wait(10);
  assert.equal(cards().length, 0);
});

test('amnesty absorbs a DeathLink without a card', async () => {
  state.deathLinkAmnestyLeft = 1;
  dl(30);
  await wait(10);
  assert.equal(cards().length, 0);
  assert.equal(storage.store[KEY]['30|Other'], undefined);
});

test('another client of the slot adds and completes an entry through SetNotify', async () => {
  const notifs = dlNotifs().length;
  storage.externalSet(KEY, { '40|Other': { id: '40|Other', task: 'Plank', source: 'Other', cause: '', time: 40 } });
  await wait(10);
  assert.equal(cards().length, 1);
  assert.match(cards()[0].textContent, /Plank/);
  // The same bounce arriving here afterwards is already queued: no new task, sound or notification.
  dl(40);
  await wait(10);
  assert.equal(cards().length, 1);
  assert.equal(dlNotifs().length, notifs);
  storage.externalSet(KEY, {});
  await wait(10);
  assert.equal(cards().length, 0);
});

test('pending cards survive a reconnect with the server key unreachable, then merge into an absent key', async () => {
  dl(50);
  await wait(10);
  assert.equal(cards().length, 1);
  $('connect-btn').click(); // disconnect
  await wait(10);
  assert.equal(Object.keys(state.deathLinkQueue).length, 0, 'disconnect clears only memory');
  assert.ok(JSON.parse(localStorage.getItem(DEVICE_KEY))['50|Other']);

  delete storage.store[KEY]; // e.g. a fresh server data store
  storage.unreachable = true;
  await connect(SLOT_DATA, { onSent: storage });
  await wait(10);
  assert.equal(cards().length, 1, 'device copy renders before the server answers');

  storage.unreachable = false;
  const retrieved = keys => FakeWS.last.recv([{ cmd: 'Retrieved', keys }]);
  retrieved({ [KEY]: null });
  await wait(10);
  assert.ok(storage.store[KEY]['50|Other'], 'device entries pushed when the server key is absent');

  storage.store[KEY] = {};
  retrieved({ [KEY]: {} });
  await wait(10);
  assert.equal(cards().length, 0, 'an existing server dict wins');
  assert.deepEqual(JSON.parse(localStorage.getItem(DEVICE_KEY)), {});
});

test('a seed without death_link_lock_tasks shows cards but never locks', async () => {
  $('connect-btn').click();
  await wait(10);
  const { death_link_lock_tasks: _unused, ...oldSeed } = SLOT_DATA;
  await connect(oldSeed, { onSent: storage });
  await wait(10);
  dl(60);
  await wait(10);
  assert.equal(cards().length, 1);
  assert.doesNotMatch($('deathlink-cards').textContent, /Locked until/);
  assert.ok(!$('tasks-list').classList.contains('locked-dl'));
  assert.ok(taskButtons().some(b => !b.disabled));
});

test('no runtime errors', () => {
  window.dispatchEvent(new window.Event('focus')); // stop any title flash timer
  assert.deepEqual(errors.map(e => String(e?.stack || e)), []);
});
