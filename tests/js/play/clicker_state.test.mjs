// Tasclickpelago phase 2: slot_data application, the data-storage key and the
// max-merge rule that keeps two open clients from rolling each other back.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, bootApp, connect, importModule, sent, wait } from '../helpers/env.mjs';

const CLICKER_KEY = 'taskipelago_clicker::Me::S';

const BASE = {
  tasks: ['Wash', 'Cook', 'Bake'], items: ['Key', 'Gold', 'Gem'],
  task_prereqs: ['', '', ''], item_prereqs: ['', '', ''],
  base_reward_location_id: 100, base_complete_location_id: 200,
  base_item_id: 300, base_token_id: 400,
  seed_name: 'S', lock_prereqs: false, hide_unreachable_tasks: false,
};

const CLICKER_SD = {
  ...BASE,
  clicker_mode: true,
  task_activations: [10, 20, 30],
  item_production: [[{ kind: 'all', ref: null, rate: 1 }], [], []],
  item_click_power: [0, 2, 0],
  item_production_mult: [null, null, 1.5],
  item_click_mult: [null, null, null],
  item_offline_mult: [[], [], []],
  region_distributed_production: { Chores: true },
  clicker_distribute_global: true,
  clicker_offline_progress: false,
  clicker_offline_rate: 0.5,
  region_offline_rate: { Chores: 0.25 },
  clicker_offline_cap_hours: 12,
};

setupDom();
await bootApp();
const { state } = await importModule('play/state.js');
const ss = await importModule('shared/server_state.js');
const board = await importModule('play/clicker_board.js');

test('sanitizeClickerProgress keeps only integer keys and finite non-negative numbers', () => {
  assert.deepEqual(ss.sanitizeClickerProgress(null), { p: {}, t: 0 });
  assert.deepEqual(ss.sanitizeClickerProgress([1, 2]), { p: {}, t: 0 });
  assert.deepEqual(ss.sanitizeClickerProgress({
    p: { 0: 3.5, 1: -1, 2: 'x', bad: 4, 3: Infinity, 4: 0 }, t: 99,
  }), { p: { 0: 3.5, 4: 0 }, t: 99 });
  assert.deepEqual(ss.sanitizeClickerProgress({ p: { 0: 1 }, t: -5 }), { p: { 0: 1 }, t: 0 });
});

test('mergeClickerProgress takes the max per task and the max timestamp', () => {
  const merged = ss.mergeClickerProgress(
    { p: { 0: 10, 1: 4 }, t: 500 },
    { p: { 0: 3, 1: 9, 2: 7 }, t: 100 },
  );
  assert.deepEqual(merged, { p: { 0: 10, 1: 9, 2: 7 }, t: 500 });
});

test('a remote value never rolls local progress back', () => {
  state.clickerProgress = { 0: 12 };
  state.clickerLastTick = 1000;
  board.applyServerClickerProgress({ p: { 0: 5, 1: 2 }, t: 900 });
  assert.deepEqual(state.clickerProgress, { 0: 12, 1: 2 });
  assert.equal(state.clickerLastTick, 1000);
  state.clickerProgress = {};
  state.clickerLastTick = 0;
});

test('old slot_data leaves clicker mode off with today\'s defaults', async () => {
  await connect(BASE);
  assert.equal(state.clickerMode, false);
  assert.deepEqual(state.taskActivations, []);
  assert.deepEqual(state.regionDistributed, {});
  assert.equal(state.clickerOffline, true);
  assert.equal(state.clickerOfflineRate, 1);
  assert.equal(state.clickerOfflineCapHours, 8);
  assert.equal(board.clickerLoopRunning(), false);
  (await importModule('play/connection.js')).startDisconnect();
  await wait(10);
});

test('clicker slot_data lands on state and the loop starts', async () => {
  await connect(CLICKER_SD, {
    onSent: (m, ws) => {
      if (m.cmd === 'Get' && m.keys.includes(CLICKER_KEY)) {
        ws.recv([{ cmd: 'Retrieved', keys: { [CLICKER_KEY]: { p: { 1: 4 }, t: 1234 } } }]);
      }
    },
  });
  assert.equal(state.clickerMode, true);
  assert.deepEqual(state.taskActivations, [10, 20, 30]);
  assert.deepEqual(state.itemClickPower, [0, 2, 0]);
  assert.deepEqual(state.itemProductionMult, [null, null, 1.5]);
  assert.deepEqual(state.regionDistributed, { Chores: true });
  assert.equal(state.clickerDistributeGlobal, true);
  assert.equal(state.clickerOffline, false);
  assert.equal(state.clickerOfflineRate, 0.5);
  assert.deepEqual(state.regionOfflineRate, { Chores: 0.25 });
  assert.equal(state.clickerOfflineCapHours, 12);
  assert.equal(board.clickerLoopRunning(), true);
  // The connect-time Retrieved seeds progress and runs offline catch-up, which
  // moves the clock to now (this seed has offline production off).
  assert.deepEqual(state.clickerProgress, { 1: 4 });
  assert.ok(state.clickerLastTick > 1234);
});

test('a SetReply from another client merges live', async () => {
  const { ap } = await importModule('play/state.js');
  ap.onSetReply(CLICKER_KEY, { p: { 1: 2, 2: 9 }, t: 2000 },
    { cmd: 'SetReply', key: CLICKER_KEY, client_id: 'someone-else' });
  assert.deepEqual(state.clickerProgress, { 1: 4, 2: 9 });
});

test('the clicker write is debounced and replaces the whole value', async () => {
  sent.length = 0;
  board.saveClickerProgress(5000);
  board.saveClickerProgress(5100);
  assert.equal(sent.filter(m => m.cmd === 'Set').length, 0);
  ss.flushClickerProgress();
  const sets = sent.filter(m => m.cmd === 'Set' && m.key === CLICKER_KEY);
  assert.equal(sets.length, 1);
  assert.deepEqual(sets[0].operations, [
    { operation: 'replace', value: { p: { 1: 4, 2: 9 }, t: 5100 } },
  ]);
});

test('disconnect clears every clicker field and stops the loop', async () => {
  const conn = await importModule('play/connection.js');
  conn.startDisconnect();
  await wait(10);
  assert.equal(state.clickerMode, false);
  assert.deepEqual(state.clickerProgress, {});
  assert.equal(state.clickerLastTick, 0);
  assert.deepEqual(state.taskActivations, []);
  assert.equal(state.clickerOfflineCapHours, 8);
  assert.equal(board.clickerLoopRunning(), false);
});
