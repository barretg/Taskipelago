// Filler Scout / Filler Hint: a received filler item reveals (and in hint mode,
// hints) the task generation assigned to it.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, bootApp, importModule } from '../helpers/env.mjs';

setupDom();
await bootApp();
const { ap, state } = await importModule('play/state.js');
const logic = await importModule('play/logic.js');
const { rewardPreview } = await importModule('play/tasks.js');

function setup(mode, received) {
  state.taskRewardPreviews = mode;
  state.baseItemId = 300;
  state.baseRewardId = 500;
  state.fillerPreviewTargets = [-1, 2, 0];
  state.sentItemNames = ['Sword', 'Shield', 'Bow'];
  state.sentPlayerNames = ['Ann', 'Bo', 'Cy'];
  state.hintRequestedIndices = new Set();
  ap.itemsReceived = received.map(i => ({ item: 300 + i }));
}

test('filler scout reveals only the assigned task, available or not', () => {
  setup(3, [1]);
  assert.equal(rewardPreview(2, false), 'Bow → Cy');
  assert.equal(rewardPreview(0, true), '');
  setup(3, [0, 1, 2]);
  assert.equal(rewardPreview(0, false), 'Sword → Ann');
});

test('filler hint sends each revealed hint once', () => {
  const sent = [];
  const orig = ap.sendLocationScouts;
  ap.sendLocationScouts = (locs, hint) => sent.push([locs, hint]);
  try {
    setup(4, [1]);
    logic.sendFillerHints();
    logic.sendFillerHints();
    assert.deepEqual(sent, [[[502], 2]]);
    ap.itemsReceived.push({ item: 302 });
    logic.sendFillerHints();
    assert.deepEqual(sent[1], [[500], 2]);
    setup(3, [1]);
    logic.sendFillerHints();
    assert.equal(sent.length, 2);
  } finally {
    ap.sendLocationScouts = orig;
  }
});
