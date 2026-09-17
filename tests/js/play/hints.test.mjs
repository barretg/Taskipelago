// v1.1 F1: Hints tab (_read_hints_<team>_<slot>, names, colors, sorting, UpdateHint).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, bootApp, connect, $, FakeWS, errors, wait, sent, BASIC_SLOT_DATA } from '../helpers/env.mjs';

const window = setupDom();
await bootApp();

const KEY = '_read_hints_0_1';
const HINTS = [
  // Our item found by the other player: status editable.
  { receiving_player: 1, finding_player: 2, location: 9001, item: 300, found: false, entrance: '', item_flags: 1, status: 0, class: 'Hint' },
  // Other player's item in our task: not editable.
  { receiving_player: 2, finding_player: 1, location: 101, item: 77, found: false, entrance: 'Cave', item_flags: 2, status: 30 },
  // Found.
  { receiving_player: 1, finding_player: 1, location: 100, item: 300, found: true, item_flags: 4, status: 40 },
];

const rows = () => [...$('hints-root').querySelectorAll('tbody tr')].map(tr => [...tr.children].map(td => {
  const sel = td.querySelector('select');
  return sel ? `[${sel.options[sel.selectedIndex].textContent}]` : td.textContent;
}));

test('empty state before hints', async () => {
  let answered = false;
  await connect(BASIC_SLOT_DATA, {
    onSent: (m, ws) => {
      if (m.cmd === 'Get' && m.keys.includes(KEY) && !answered) {
        answered = true;
        ws.recv([{ cmd: 'Retrieved', keys: { [KEY]: [] } }]);
      }
    },
  });
  await wait(10);
  assert.ok(sent.some(m => m.cmd === 'SetNotify' && m.keys.includes(KEY)));
  assert.equal([...document.querySelectorAll('#main-tabs .tab-btn')].map(b => b.textContent)[2], 'Hints');
  assert.match($('hints-root').textContent, /No hints yet\. Use !hint <item> in the Text Console\./);
});

test('hints render names, colors and the default sort; DataPackage names fill in when they arrive', async () => {
  FakeWS.last.recv([{ cmd: 'SetReply', key: KEY, value: HINTS }]);
  await wait(10);
  assert.deepEqual(rows(), [
    ['Me', 'Key', 'Me', 'Wash', '', 'Found'],
    ['Other', '#77', 'Me', 'Cook', 'Cave', 'Priority'],
    ['Me', 'Key', 'Other', '#9001', '', '[Unspecified]'],
  ]);
  assert.match($('hints-root').textContent, /Loading item and location names/);
  FakeWS.last.recv([{ cmd: 'DataPackage', data: { games: { 'Other Game': {
    item_name_to_id: { 'Master Sword': 77 }, location_name_to_id: { 'Big Chest': 9001 }, checksum: 'x',
  } } } }]);
  await wait(10);
  assert.equal(rows()[1][1], 'Master Sword');
  assert.equal(rows()[2][3], 'Big Chest');
  assert.doesNotMatch($('hints-root').textContent, /null|Loading item and location names/);
  const tr = $('hints-root').querySelectorAll('tbody tr')[1];
  assert.equal(tr.children[0].className, 'hint-player-other');
  assert.equal(tr.children[1].className, 'hint-item-useful');
  assert.equal(tr.children[2].className, 'hint-player-own');
});

test('clicking a header sorts, clicking again reverses', () => {
  const header = label => [...$('hints-root').querySelectorAll('th button')].find(b => b.textContent.startsWith(label));
  header('Item').click();
  assert.deepEqual(rows().map(r => r[1]), ['Key', 'Key', 'Master Sword']);
  header('Item').click();
  assert.deepEqual(rows().map(r => r[1]), ['Master Sword', 'Key', 'Key']);
  header('Status').click();
  assert.deepEqual(rows().map(r => r[5]), ['[Unspecified]', 'Priority', 'Found']);
});

test('status select only on our unfound hints; UpdateHint waits for SetReply', async () => {
  const selects = $('hints-root').querySelectorAll('select');
  assert.equal(selects.length, 1);
  const select = selects[0];
  select.value = '30';
  select.dispatchEvent(new window.Event('change', { bubbles: true }));
  const update = sent.filter(m => m.cmd === 'UpdateHint').pop();
  assert.deepEqual(update, { cmd: 'UpdateHint', location: 9001, player: 2, status: 30 });
  assert.equal(rows()[0][5], '[Unspecified]', 'no optimistic write');
  FakeWS.last.recv([{ cmd: 'SetReply', key: KEY, value: HINTS.map((x, i) => (i === 0 ? { ...x, status: 30 } : x)) }]);
  await wait(10);
  assert.ok(rows().some(r => r[5] === '[Priority]'));
});

test('disconnect clears the table; reconnect repopulates it', async () => {
  $('connect-btn').click();
  await wait(10);
  assert.match($('hints-root').textContent, /Connect to a server to see hints/);
  await connect(BASIC_SLOT_DATA, {
    onSent: (m, ws) => { if (m.cmd === 'Get' && m.keys.includes(KEY)) ws.recv([{ cmd: 'Retrieved', keys: { [KEY]: HINTS } }]); },
  });
  await wait(10);
  assert.equal(rows().length, 3);
});

test('no runtime errors', () => {
  assert.deepEqual(errors.map(e => String(e?.stack || e)), []);
});
