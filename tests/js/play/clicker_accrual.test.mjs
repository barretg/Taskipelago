// Tasclickpelago phase 4: accrual math on a fixed clock. Rate stacking, the two
// multiplier channels, distributed production, the locked-task rule, offline
// catch-up and completion at threshold.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, bootApp, connect, importModule, sent, wait } from '../helpers/env.mjs';

const BASE_SD = {
  tasks: ['Wash', 'Cook', 'Bake', 'Sweep'],
  items: ['Sponge', 'Oven', 'Foreman', 'Glove', 'NightShift'],
  task_prereqs: ['', '', '', ''],
  item_prereqs: ['', '', '', ''],
  regions: ['Kitchen', 'House'],
  region_colors: ['', ''],
  task_region: ['House', 'Kitchen', 'Kitchen', 'House'],
  base_reward_location_id: 100, base_complete_location_id: 200,
  base_item_id: 300, base_token_id: 400,
  seed_name: 'S', lock_prereqs: true, hide_unreachable_tasks: false,
  clicker_mode: true,
  task_activations: [10, 10, 10, 10],
  item_production: [[], [], [], [], []],
  item_click_power: [0, 0, 0, 0, 0],
  item_production_mult: [null, null, null, null, null],
  item_click_mult: [null, null, null, null, null],
  item_offline_mult: [[], [], [], [], []],
  region_distributed_production: {},
  clicker_distribute_global: false,
  clicker_offline_progress: true,
  clicker_offline_rate: 1,
  region_offline_rate: {},
  clicker_offline_cap_hours: 8,
};

setupDom();
await bootApp();
const { state, ap } = await importModule('play/state.js');
const board = await importModule('play/clicker_board.js');
const conn = await importModule('play/connection.js');

const ITEM = { Sponge: 300, Oven: 301, Foreman: 302, Glove: 303, NightShift: 304 };

async function boot(sd = {}) {
  if (state.connState === 'connected') { conn.startDisconnect(); await wait(10); }
  await connect({ ...BASE_SD, ...sd });
  board.stopClickerLoop();          // drive the clock by hand
  state.clickerProgress = {};
  state.clickerLastTick = 0;
  sent.length = 0;
}

function give(...names) {
  ap.itemsReceived.push(...names.map(n => ({ item: ITEM[n], location: 1, player: 2, flags: 0 })));
}

test('per-task rates stack per received copy', async () => {
  await boot({ item_production: [[{ kind: 'task', ref: 0, rate: 1.5 }], [], [], [], []] });
  give('Sponge', 'Sponge');
  const m = board.clickerModel();
  assert.equal(m.rate[0], 3);
  assert.equal(m.rate[1], 0);
});

test('production multipliers stack multiplicatively and values below 1 slow the game', async () => {
  await boot({
    item_production: [[{ kind: 'task', ref: 0, rate: 1 }], [], [], [], []],
    item_production_mult: [null, 2, 0.5, null, null],
  });
  give('Sponge');
  give('Oven', 'Oven');       // x2 twice = x4
  assert.equal(board.clickerModel().globalMult, 4);
  give('Foreman');            // x0.5
  const m = board.clickerModel();
  assert.equal(m.globalMult, 2);
  assert.equal(m.rate[0], 2);
});

test('the two multiplier channels stay independent', async () => {
  await boot({
    item_production: [[{ kind: 'task', ref: 0, rate: 1 }], [], [], [], []],
    item_production_mult: [null, 3, null, null, null],
    item_click_power: [0, 0, 2, 0, 0],
    item_click_mult: [null, null, null, 5, null],
  });
  give('Sponge', 'Oven', 'Foreman', 'Glove');
  const m = board.clickerModel();
  assert.equal(m.rate[0], 3);          // production multiplier only
  assert.equal(m.clickValue, (1 + 2) * 5); // click channel only
});

test('a region rate applies in full, or splits when the region is distributed', async () => {
  await boot({ item_production: [[{ kind: 'region', ref: 'Kitchen', rate: 0.5 }], [], [], [], []] });
  give('Sponge');
  let m = board.clickerModel();
  assert.deepEqual([m.rate[1], m.rate[2]], [0.5, 0.5]);

  await boot({
    item_production: [[{ kind: 'region', ref: 'Kitchen', rate: 0.5 }], [], [], [], []],
    region_distributed_production: { Kitchen: true },
  });
  give('Sponge');
  m = board.clickerModel();
  assert.deepEqual([m.rate[1], m.rate[2]], [0.25, 0.25]);

  // The share rises as a sibling completes: the region's throughput is constant.
  state.pendingLocations.add(state.baseCompleteId + 1);
  m = board.clickerModel();
  assert.equal(m.rate[1], 0);
  assert.equal(m.rate[2], 0.5);
  state.pendingLocations.clear();
});

test('a locked target contributes nothing and banks nothing', async () => {
  await boot({
    task_prereqs: ['', '', '', '1'],   // Sweep needs Wash
    item_production: [[{ kind: 'all', ref: null, rate: 1 }], [], [], [], []],
  });
  give('Sponge');
  const m = board.clickerModel();
  assert.equal(m.rate[3], 0);
  board.settle(5);
  assert.equal(board.taskProgress(3), 0);
  assert.equal(board.taskProgress(0), 5);
  // Unlocking it later starts from zero, not from a banked 5.
  state.pendingLocations.add(state.baseCompleteId + 0);
  board.settle(1);
  assert.equal(board.taskProgress(3), 1);
  state.pendingLocations.clear();
});

test('a distributed global rate divides by the eligible tasks only', async () => {
  await boot({
    task_prereqs: ['', '', '', '1'],
    item_production: [[{ kind: 'all', ref: null, rate: 1 }], [], [], [], []],
    clicker_distribute_global: true,
  });
  give('Sponge');
  const m = board.clickerModel();
  assert.equal(m.eligible.length, 3);           // Sweep is locked
  assert.equal(m.rate[0], 1 / 3);
  assert.equal(m.rate[3], 0);
});

test('completion happens at the threshold and overflow is discarded', async () => {
  await boot({ item_production: [[{ kind: 'task', ref: 0, rate: 4 }], [], [], [], []] });
  give('Sponge');
  board.settle(100);                     // far past 10 activations
  assert.equal(board.taskProgress(0), 10);
  const checks = sent.filter(m => m.cmd === 'LocationChecks');
  assert.ok(checks.some(c => c.locations.includes(state.baseCompleteId + 0)));
});

test('the settle loop re-binds the constants as tasks complete', async () => {
  // Rate scales with how much is done, so a one-shot pass would undercount.
  await boot({
    task_activations: [1, 1, 1, 1],
    item_production: [[{ kind: 'all', ref: null, rate: { op: '+', l: { num: 1 }, r: { const: 'N_TASKS_COMPLETED' } } }], [], [], [], []],
  });
  give('Sponge');
  assert.equal(board.clickerModel().rate[0], 1);
  board.settle(1);                       // every task hits 1 activation at once
  assert.equal(board.clickerModel().nCompleted, 4);
});

test('a click adds the click value and never overflows', async () => {
  await boot({ item_click_power: [3, 0, 0, 0, 0] });
  give('Sponge');
  assert.equal(board.clickerModel().clickValue, 4);
  board.clickTask(0);
  assert.equal(board.taskProgress(0), 4);
  board.clickTask(0);
  board.clickTask(0);
  assert.equal(board.taskProgress(0), 10);  // clamped at the requirement
});

test('offline catch-up: rate x region override x item multiplier, bounded by the cap', async () => {
  await boot({
    item_production: [[{ kind: 'task', ref: 1, rate: 1 }, { kind: 'task', ref: 0, rate: 1 }], [], [], [], []],
    clicker_offline_rate: 0.5,
    region_offline_rate: { Kitchen: 0.25 },
    item_offline_mult: [[], [], [], [], [{ kind: 'region', ref: 'Kitchen', rate: 2 }]],
    task_activations: [4000, 4000, 4000, 4000],
    clicker_offline_cap_hours: 1,
  });
  give('Sponge', 'NightShift');
  const now = Date.now();
  state.clickerLastTick = now - 5 * 3600 * 1000;   // five hours, capped to one
  board.applyOfflineCatchUp(now);
  // Wash is in House: 1/s * 0.5 global = 0.5/s for 3600s.
  assert.equal(board.taskProgress(0), 1800);
  // Cook is in Kitchen: 1/s * 0.25 region * 2 NightShift = 0.5/s.
  assert.equal(board.taskProgress(1), 1800);
});

test('offline production off means no catch-up at all', async () => {
  await boot({
    item_production: [[{ kind: 'all', ref: null, rate: 1 }], [], [], [], []],
    clicker_offline_progress: false,
    task_activations: [1000, 1000, 1000, 1000],
  });
  give('Sponge');
  const now = Date.now();
  state.clickerLastTick = now - 3600 * 1000;
  assert.equal(board.applyOfflineCatchUp(now), 0);
  assert.equal(board.taskProgress(0), 0);
});

test('an offline cap of 0 disables catch-up while the rest stays configured', async () => {
  await boot({
    item_production: [[{ kind: 'all', ref: null, rate: 1 }], [], [], [], []],
    clicker_offline_cap_hours: 0,
    task_activations: [1000, 1000, 1000, 1000],
  });
  give('Sponge');
  const now = Date.now();
  state.clickerLastTick = now - 3600 * 1000;
  assert.equal(board.applyOfflineCatchUp(now), 0);
  assert.equal(board.taskProgress(0), 0);
});

test('clicker mode renders the board instead of the task list', async () => {
  const { els } = await importModule('play/state.js');
  const { renderTasks } = await importModule('play/tasks.js');
  await boot({
    item_production: [[{ kind: 'task', ref: 0, rate: 2 }], [], [], [], []],
    item_click_power: [1, 0, 0, 0, 0],
  });
  give('Sponge');
  renderTasks();
  assert.ok(els.clickerSection.classList.contains('hidden') === false);
  assert.ok(els.tasksList.classList.contains('hidden'));
  const cards = els.clickerGrid.querySelectorAll('.clicker-card');
  assert.equal(cards.length, 4);
  assert.match(cards[0].textContent, /1\. Wash/);
  assert.match(cards[0].textContent, /0 \/ 10/);
  assert.match(cards[0].textContent, /\+2\/s/);
  assert.match(els.clickerHeader.textContent, /N_TASKS 4/);
  assert.match(els.clickerHeader.textContent, /Click: 2 per click/);

  // The Click button drives the same path as clickTask().
  cards[0].querySelector('.clicker-click-btn').click();
  assert.equal(board.taskProgress(0), 2);
});

test('/clicker and /click drive the board from the console', async () => {
  const { runCommand } = await importModule('console/commands.js');
  await boot({
    item_production: [[{ kind: 'task', ref: 1, rate: 2 }], [], [], [], []],
    item_click_power: [0, 4, 0, 0, 0],
  });
  give('Sponge', 'Oven');
  const lines = [];
  const ctx = { output: t => lines.push(t), printJson: () => {}, connect: () => {}, disconnect: () => {}, hasAddress: () => true };

  await runCommand('/clicker', ctx);
  await wait(5);
  assert.ok(lines.some(l => /Production: 2\/s across 4 eligible/.test(l)));
  assert.ok(lines.some(l => /Click value: 5/.test(l)));
  assert.ok(lines.some(l => /N_TASKS 4, N_TASKS_UNLOCKED 4/.test(l)));

  lines.length = 0;
  await runCommand('/click Cook', ctx);
  await wait(5);
  assert.equal(board.taskProgress(1), 5);
  assert.match(lines[0], /2\. Cook: 5 \/ 10/);

  lines.length = 0;
  await runCommand('/click 99', ctx);
  await wait(5);
  assert.match(lines[0], /No task named 99/);
});

test('the clicker commands say so on a non-clicker slot', async () => {
  const { runCommand } = await importModule('console/commands.js');
  await boot({ clicker_mode: false });
  const lines = [];
  const ctx = { output: t => lines.push(t), printJson: () => {}, connect: () => {}, disconnect: () => {}, hasAddress: () => true };
  await runCommand('/clicker', ctx);
  await wait(5);
  await runCommand('/click 1', ctx);
  await wait(5);
  assert.deepEqual(lines, ['This slot is not in clicker mode.', 'This slot is not in clicker mode.']);
});

test('the header attributes rates per task, so completing one never moves the base', async () => {
  await boot({
    item_production: [
      [{ kind: 'region', ref: 'Kitchen', rate: 0.2 }],
      [{ kind: 'region', ref: 'House', rate: 0.5 }],
      [], [], [],
    ],
    item_production_mult: [null, null, 2, null, null],
  });
  give('Sponge', 'Oven', 'Foreman');
  const { els } = await importModule('play/state.js');
  const header = () => [...els.clickerHeader.children].map(el => el.textContent);

  board.renderClicker();
  assert.deepEqual(header().slice(0, 2), [
    '2.8/s total across 4 tasks',
    'Per task: 1/s on 2 tasks (0.5 base × 2), 0.4/s on 2 tasks (0.2 base × 2)',
  ]);

  // Completing a task drops it from the total and the count, and leaves every
  // per-task figure exactly where it was.
  ap.checkedLocations.add(200);     // Wash complete
  board.renderClicker();
  assert.deepEqual(header().slice(0, 2), [
    '1.8/s total across 3 tasks',
    'Per task: 1/s on 1 task (0.5 base × 2), 0.4/s on 2 tasks (0.2 base × 2)',
  ]);
});

test('CPS binds to the live click value and drives production from it', async () => {
  await boot({
    item_production: [[{ kind: 'task', ref: 0, rate: { op: '*', l: { num: 0.5 }, r: { const: 'CPS' } } }], [], [], [], []],
    item_click_power: [0, 0, 2, 0, 0],
    item_click_mult: [null, null, null, 3, null],
  });
  give('Sponge');
  // No click items yet: CPS is the base click value of 1.
  assert.equal(board.clickerModel().rate[0], 0.5);

  give('Foreman');            // +2 click power -> CPS 3
  assert.equal(board.clickerModel().clickValue, 3);
  assert.equal(board.clickerModel().rate[0], 1.5);

  give('Glove');              // x3 click multiplier -> CPS 9
  const m = board.clickerModel();
  assert.equal(m.clickValue, 9);
  assert.equal(m.rate[0], 4.5);
  assert.equal(m.bindings.CPS, 9);
});

test('manual tasks take no production and leave the clicker grid', async () => {
  await boot({
    task_manual: [false, true, false, false],
    item_production: [[{ kind: 'all', ref: null, rate: 1 }], [], [], [], []],
  });
  give('Sponge');
  const m = board.clickerModel();
  assert.equal(board.isManualTask(1), true);
  assert.deepEqual(m.eligible, [0, 2, 3]);
  assert.equal(m.rate[1], 0);

  // A directly targeted manual task is skipped too, and its rate is not banked.
  await boot({
    task_manual: [false, true, false, false],
    item_production: [[{ kind: 'task', ref: 1, rate: 5 }], [], [], [], []],
  });
  give('Sponge');
  assert.equal(board.clickerModel().rate[1], 0);

  board.settle(60);
  assert.equal(board.taskProgress(1), 0);
  assert.equal(board.clickTask(1), false);
  assert.equal(board.taskProgress(1), 0);

  // The grid holds only the clicker tasks; the manual one renders as a task row.
  board.renderClicker();
  const names = [...document.querySelectorAll('#clicker-grid .clicker-name')].map(e => e.textContent);
  assert.equal(names.length, 3);
  assert.ok(!names.some(t => t.includes('Cook')));
  const manual = [...document.querySelectorAll('#clicker-manual-list .task-name')].map(e => e.textContent);
  assert.deepEqual(manual, ['2. Cook']);
  assert.equal(document.getElementById('clicker-manual').classList.contains('hidden'), false);
});

test('with no manual tasks the manual section stays hidden', async () => {
  await boot({ item_production: [[{ kind: 'all', ref: null, rate: 1 }], [], [], [], []] });
  assert.equal(document.getElementById('clicker-manual').classList.contains('hidden'), true);
  assert.equal(document.querySelectorAll('#clicker-manual-list .task-card').length, 0);
});

// ---------------------------------------------------------------------------
// Targeted grants: every kind but "unlock only" carries a target.
// ---------------------------------------------------------------------------

test('click power and the click multiplier are per target', async () => {
  await boot({
    // Foreman: +4 click power on Kitchen (Cook, Bake). Glove: x3 clicks on Wash.
    item_click_power: [[], [], [{ kind: 'region', ref: 'Kitchen', rate: 4 }], [], []],
    item_click_mult: [[], [], [], [{ kind: 'task', ref: 0, rate: 3 }], []],
  });
  give('Foreman', 'Glove');
  const m = board.clickerModel();
  assert.deepEqual(m.taskClickValue, [3, 5, 5, 1]);
  assert.equal(m.clickValue, 1);          // nothing is aimed at '*'

  // A click is worth the clicked task's own value.
  board.clickTask(0);
  assert.equal(board.taskProgress(0), 3);
  board.clickTask(1);
  assert.equal(board.taskProgress(1), 5);
  board.clickTask(3);
  assert.equal(board.taskProgress(3), 1);
});

test('a production multiplier only scales the tasks it targets', async () => {
  await boot({
    item_production: [[{ kind: 'all', ref: null, rate: 1 }], [], [], [], []],
    item_production_mult: [[], [{ kind: 'region', ref: 'Kitchen', rate: 2 }], [], [], []],
  });
  give('Sponge', 'Oven');
  const m = board.clickerModel();
  assert.deepEqual(m.rate, [1, 2, 2, 1]);
  assert.equal(m.globalMult, 1);
  assert.deepEqual(m.prodMult, [1, 2, 2, 1]);
});

test('CPS in a production rate is the target task click value', async () => {
  await boot({
    item_production: [[{ kind: 'all', ref: null, rate: { op: '*', l: { num: 1 }, r: { const: 'CPS' } } }], [], [], [], []],
    item_click_power: [[], [], [{ kind: 'task', ref: 2, rate: 9 }], [], []],
  });
  give('Sponge', 'Foreman');
  const m = board.clickerModel();
  assert.deepEqual(m.rate, [1, 1, 10, 1]);
});

test('an offline multiplier aimed at one region only speeds that region up', async () => {
  await boot({
    item_production: [[{ kind: 'all', ref: null, rate: 1 }], [], [], [], []],
    item_offline_mult: [[], [], [], [], [{ kind: 'region', ref: 'Kitchen', rate: 2 }]],
  });
  give('Sponge', 'NightShift');
  const m = board.clickerModel({ offline: true });
  assert.deepEqual(m.rate, [1, 2, 2, 1]);
});

test('the header and the cards name every grant and its target', async () => {
  const { els } = await importModule('play/state.js');
  await boot({
    item_production: [[{ kind: 'region', ref: 'Kitchen', rate: 0.5 }], [], [], [], []],
    item_click_power: [[], [], [{ kind: 'task', ref: 0, rate: 4 }], [], []],
  });
  give('Sponge', 'Foreman');
  board.renderClicker();
  const header = [...els.clickerHeader.children].map(el => el.textContent);
  assert.ok(header.some(l => l === 'Production: Sponge +0.5/s → Kitchen'), header.join('\n'));
  assert.ok(header.some(l => l === 'Click power: Foreman +4/click → 1. Wash'), header.join('\n'));
  assert.ok(header.some(l => l.startsWith('Click: 5 per click on 1 task')), header.join('\n'));

  const detail = [...document.querySelectorAll('#clicker-grid .clicker-detail')].map(e => e.textContent);
  assert.equal(detail[0], 'Foreman +4/click');
  assert.equal(detail[1], 'Sponge +0.5/s');
  assert.equal(detail[3], '');
  const clicks = [...document.querySelectorAll('#clicker-grid .clicker-click-value')].map(e => e.textContent);
  assert.deepEqual(clicks, ['click +5', 'click +1', 'click +1', 'click +1']);
});

test('a manual task is outside every grant pool, even a region or * one', async () => {
  await boot({
    task_manual: [false, true, false, false],     // Cook is an ordinary task
    item_production: [[{ kind: 'all', ref: null, rate: 1 }], [], [], [], []],
    // Kitchen holds Cook (manual) and Bake; '*' reaches every clicker task.
    item_click_power: [[], [{ kind: 'region', ref: 'Kitchen', rate: 4 }], [{ kind: 'all', ref: null, rate: 1 }], [], []],
    item_production_mult: [[], [], [], [{ kind: 'region', ref: 'Kitchen', rate: 3 }], []],
  });
  give('Oven', 'Foreman', 'Glove', 'Sponge');
  const m = board.clickerModel();
  assert.deepEqual(m.clickerTasks, [0, 2, 3]);
  // Cook keeps the base click value of 1 and gets no rate or multiplier.
  assert.deepEqual(m.taskClickValue, [2, 1, 6, 2]);
  assert.equal(m.rate[1], 0);
  assert.equal(m.prodMult[1], 1);
  assert.deepEqual(m.rate, [1, 0, 3, 1]);
  // A distributed '*' rate divides by the clicker tasks only.
  assert.equal(m.eligible.includes(1), false);
});
