// Purchases are gated by the apworld's cumulative cost thresholds
// (slot_data task_cost_reqs), so spending out of logic cannot strand an
// in-logic purchase. Older seeds without thresholds stay ungated.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, bootApp, importModule } from '../helpers/env.mjs';

setupDom();
await bootApp();
const { ap, state } = await importModule('play/state.js');
const logic = await importModule('play/logic.js');

function setup(coins, reqs) {
  state.baseItemId = 300;
  state.items = ['Coin', 'Wood'];
  state.itemConsumable = [true, true];
  ap.itemsReceived = Array.from({ length: coins }, () => ({ item: 300 }));
  state.taskCostReqs = reqs;
}

test('a cost is in logic once its cumulative threshold is received', () => {
  setup(4, [[[{ consumable: 'Coin', threshold: 3 }]], [[{ consumable: 'Coin', threshold: 11 }]]]);
  assert.equal(logic.costLogicReason(0), '');
  assert.equal(logic.costLogicReason(1), 'Needs 11 Coin received (out of logic)');
  assert.equal(logic.costBranchInLogic(1, 0), false);
});

test('any in-logic OR branch clears the reason; the closest branch is reported', () => {
  setup(4, [[
    [{ consumable: 'Coin', threshold: 8 }, { consumable: 'Wood', threshold: 3 }],
    [{ consumable: 'Coin', threshold: 9 }],
  ]]);
  assert.equal(logic.costLogicReason(0), 'Needs 9 Coin received (out of logic)');
  setup(9, state.taskCostReqs);
  assert.equal(logic.costLogicReason(0), '');
  assert.equal(logic.costBranchInLogic(0, 0), false);
  assert.equal(logic.costBranchInLogic(0, 1), true);
});

test('seeds without thresholds are never gated', () => {
  setup(0, []);
  assert.equal(logic.costLogicReason(0), '');
  assert.equal(logic.costBranchInLogic(0, 0), true);
});
