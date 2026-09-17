// v1.1 F6 (progressive group color coding) and F7 (Items tab filters, hidden footer).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, bootApp, connect, $, FakeWS, errors, wait } from '../helpers/env.mjs';

const window = setupDom();
await bootApp();

const SLOT_DATA = {
  tasks: ['a', 'b', 'c', 'd', 'e', 'f'], items: ['Sword', 'Shield', 'Key', 'Gold', 'Several pats on the back', 'Trap Card'],
  task_prereqs: Array(6).fill(''), item_prereqs: Array(6).fill(''),
  base_reward_location_id: 100, base_complete_location_id: 200, base_item_id: 300, base_token_id: 400,
  seed_name: 'S', lock_prereqs: false, hide_unreachable_tasks: false,
  progressive_groups: ['weapons', 'keys'], progressive_group_colors: ['#ff0000', ''],
  item_progressive_group: ['weapons', 'weapons', 'keys', '', '', ''],
  item_consumable: [false, false, false, true, false, false],
  item_fillers: [false, false, false, false, true, false],
  task_cost_amounts: [],
};

const list = () => $('items-list');
const headers = () => [...list().querySelectorAll('.item-group-header')].map(e => e.textContent);
const entries = () => [...list().querySelectorAll('.item-entry')].map(e => e.textContent.split('  (from')[0]);
const footer = () => list().querySelector('.items-hidden-footer')?.textContent;
const popover = () => document.querySelector('.items-filter-popover');
const box = key => popover().querySelector(`input[data-filter="${key}"]`);
const toggle = (el, checked) => {
  el.checked = checked;
  el.dispatchEvent(new window.Event('change', { bubbles: true }));
};

test('received items are grouped per progressive group in seed order, colored, with Other last', async () => {
  await connect(SLOT_DATA);
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 0, items: [
    { item: 305, location: 1, player: 2, flags: 0b100 }, // Trap Card
    { item: 302, location: 2, player: 2, flags: 0b001 }, // Key (keys)
    { item: 300, location: 3, player: 2, flags: 0b001 }, // Sword (weapons)
    { item: 303, location: 4, player: 2, flags: 0b001 }, // Gold (consumable)
    { item: 304, location: 5, player: 2, flags: 0 },     // filler
    { item: 401, location: 6, player: 2, flags: 0 },     // completion token: excluded
    { item: 301, location: 7, player: 2, flags: 0b010 }, // Shield (weapons)
  ] }]);
  await wait(10);
  assert.deepEqual(headers(), ['weapons  2/2', 'keys  1/1', 'Other']);
  assert.deepEqual(entries(), ['Sword', 'Shield', 'Key', 'Trap Card', 'Gold', 'Several pats on the back']);
  const rows = [...list().querySelectorAll('.item-entry')];
  assert.equal(rows[0].style.borderLeft, '4px solid rgb(255, 0, 0)');
  assert.equal(rows[2].style.borderLeft, '4px solid var(--border)', 'uncolored group uses the neutral border');
  assert.equal(list().querySelector('.item-group-header').style.color, 'rgb(255, 0, 0)');
  assert.equal(list().querySelector('.group-row .group-swatch').style.background, 'rgb(255, 0, 0)');
  assert.equal(footer(), '+0 Hidden Items');
  assert.equal(list().lastElementChild.className, 'items-hidden-footer muted-text');
  assert.equal($('items-filter-btn').textContent, 'Filter');
});

test('filters hide by category and group, count hidden items, and persist per device', async () => {
  $('items-filter-btn').click();
  assert.ok(popover());
  toggle(box('hiddenCategories:filler'), false);
  assert.deepEqual(entries(), ['Sword', 'Shield', 'Key', 'Trap Card', 'Gold']);
  assert.equal(footer(), '+1 Hidden Items');
  assert.equal($('items-filter-btn').textContent, 'Filter (1)');

  toggle(box('hiddenGroups:weapons'), false);
  toggle(box('hiddenCategories:trap'), false);
  assert.deepEqual(entries(), ['Key', 'Gold']);
  assert.deepEqual(headers(), ['keys  1/1', 'Other']);
  assert.equal(footer(), '+4 Hidden Items');
  assert.equal($('items-filter-btn').textContent, 'Filter (3)');
  assert.deepEqual(JSON.parse(localStorage.getItem('taskipelago_ui')).itemFilters,
    { hiddenCategories: ['filler', 'trap'], hiddenGroups: ['weapons'] });
  assert.equal([...list().querySelectorAll('.group-row')].length, 3, 'group summary rows (2 groups + currency) are never filtered');

  toggle(box('hiddenGroups:'), false); // (No group)
  assert.deepEqual(entries(), ['Key']);

  [...popover().querySelectorAll('button')].find(b => b.textContent === 'Hide all').click();
  assert.deepEqual(entries(), []);
  assert.equal(footer(), '+6 Hidden Items');
  assert.equal(box('hiddenCategories:useful').checked, false);
  [...popover().querySelectorAll('button')].find(b => b.textContent === 'Show all').click();
  assert.equal(entries().length, 6);
  assert.equal($('items-filter-btn').textContent, 'Filter');
});

test('the popover closes on Escape and on an outside click', () => {
  document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  assert.equal(popover(), null);
  $('items-filter-btn').click();
  assert.ok(popover());
  document.body.dispatchEvent(new window.MouseEvent('mousedown', { bubbles: true }));
  assert.equal(popover(), null);
});

test('a seed without groups or item_fillers looks like before: flat list, filler by name', async () => {
  $('connect-btn').click();
  await wait(10);
  const { progressive_groups: _g, progressive_group_colors: _c, item_progressive_group: _i, item_fillers: _f, ...old } = SLOT_DATA;
  await connect(old);
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 0, items: [
    { item: 300, location: 1, player: 2, flags: 1 }, { item: 304, location: 2, player: 2, flags: 0 },
  ] }]);
  await wait(10);
  assert.deepEqual(headers(), []);
  assert.deepEqual(entries(), ['Sword', 'Several pats on the back']);
  $('items-filter-btn').click();
  toggle(box('hiddenCategories:filler'), false);
  assert.deepEqual(entries(), ['Sword']);
  assert.ok(box('hiddenGroups:'), '(No group) is still offered');
  toggle(box('hiddenCategories:filler'), true);
  document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
});

test('no runtime errors', () => {
  assert.deepEqual(errors.map(e => String(e?.stack || e)), []);
});
