// UNIFY 5.2 console commands and history; UNIFY 5.1 DataPackage names and cache.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  setupDom, bootApp, connectedPacket, $, FakeWS, errors, wait, sent, BASIC_SLOT_DATA,
} from '../helpers/env.mjs';

const PACKAGES = {
  Archipelago: { item_name_to_id: { Nothing: -1 }, location_name_to_id: { 'Cheat Console': -1 }, checksum: 'c0' },
  Taskipelago: {
    item_name_to_id: { Key: 300, Mystery: 999 },
    location_name_to_id: { Wash: 200, Cook: 201, 'Wash Reward': 100, 'Cook Reward': 101 },
    checksum: 'c1',
  },
  'Other Game': { item_name_to_id: { Sword: 5 }, location_name_to_id: { Cave: 7 }, checksum: 'c2' },
};

setupDom({ localStorage: { 'taskipelago_dp::Taskipelago::old': '{}' } });
FakeWS.roomInfo = {
  cmd: 'RoomInfo', seed_name: 'S', datapackage_checksums: { Archipelago: 'c0', Taskipelago: 'c1', 'Other Game': 'c2' },
};
FakeWS.onSent = (m, ws) => {
  if (m.cmd === 'Connect') {
    ws.recv([connectedPacket(BASIC_SLOT_DATA, { missing_locations: [200, 201, 100, 101] })]);
  } else if (m.cmd === 'Get') {
    setTimeout(() => ws.recv([{ cmd: 'Retrieved', keys: Object.fromEntries(m.keys.map(k => [k, k.includes('notify') ? 0 : null])) }]), 0);
  } else if (m.cmd === 'GetDataPackage') {
    setTimeout(() => ws.recv([{ cmd: 'DataPackage', data: { games: Object.fromEntries(m.games.map(g => [g, PACKAGES[g]])) } }]), 0);
  }
};
await bootApp();

const lines = () => [...$('console-output').children].map(d => d.textContent);
async function type(text) {
  $('console-input').value = text;
  $('console-input').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
  await wait(30);
}
const key = k => $('console-input').dispatchEvent(new KeyboardEvent('keydown', { key: k }));

test('input works while disconnected; /help uses the AP help format', async () => {
  assert.equal($('console-input').disabled, false);
  await type('/help');
  const help = lines().at(-1);
  assert.ok(help.startsWith('/help \n    Returns the help listing\n/connect [address] \n    Connect to a MultiWorld Server\n'));
  assert.ok(help.includes('/missing [filter_text] \n    List all missing location checks, from your local game state.\n    Can be given text, which will be used as filter.\n'));
});

test('unknown command lists known commands', async () => {
  await type('/nope');
  assert.equal(lines().at(-1), 'Could not find command nope. Known commands: help, connect, disconnect, received, missing, checked, items, locations, ready, click, clicker');
});

test('chat while disconnected is not sent', async () => {
  await type('hello');
  assert.match(lines().at(-1), /Not connected/);
  assert.ok(!sent.some(m => m.cmd === 'Say'));
});

test('/connect without an address or a saved one asks for it', async () => {
  $('server-input').value = '';
  await type('/connect');
  assert.equal(lines().at(-1), 'Please specify an address.');
});

test('history browses with up/down and restores the draft', () => {
  $('console-input').value = 'draft';
  key('ArrowUp');
  assert.equal($('console-input').value, '/connect');
  key('ArrowUp');
  assert.equal($('console-input').value, 'hello');
  key('ArrowDown');
  key('ArrowDown');
  assert.equal($('console-input').value, 'draft');
  $('console-input').value = '';
});

test('/connect <address> connects and loads DataPackages', async () => {
  $('slot-input').value = 'Me';
  await type('/connect localhost:38281');
  assert.equal($('connect-status').textContent, 'Connected.');
  const reqs = sent.filter(m => m.cmd === 'GetDataPackage');
  assert.equal(reqs.length, 1);
  assert.deepEqual([...reqs[0].games].sort(), ['Archipelago', 'Other Game', 'Taskipelago']);
  assert.ok(localStorage.getItem('taskipelago_dp::Taskipelago::c1'));
  assert.equal(localStorage.getItem('taskipelago_dp::Taskipelago::old'), null); // pruned
});

test('/missing and /checked use the DataPackage', async () => {
  await type('/missing');
  assert.deepEqual(lines().slice(-5), [
    'Missing: Wash', 'Missing: Cook', 'Missing: Wash Reward', 'Missing: Cook Reward', 'Found 4 missing location checks',
  ]);
  await type('/missing Cook');
  assert.equal(lines().at(-1), 'Found 2 missing location checks');
  await type('/checked');
  assert.equal(lines().at(-1), 'No checked location checks found.');
});

test('/received prints items with names from both games', async () => {
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 0, items: [{ item: 300, location: 7, player: 2, flags: 1 }] }]);
  await wait(10);
  await type('/received');
  assert.deepEqual(lines().slice(-2), ['1 received items, sorted by time:', 'Key from Cave by Other']);
});

test('DataPackage names fill in items the YAML does not name', async () => {
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 1, items: [{ item: 999, location: 7, player: 2, flags: 0 }] }]);
  await wait(10);
  assert.match($('items-list').textContent, /Mystery/);
  assert.match($('notif-list').textContent, /Mystery/);
  FakeWS.last.recv([{ cmd: 'PrintJSON', data: [
    { type: 'player_id', text: '1' }, { type: 'text', text: ' found ' },
    { type: 'item_id', text: '5', player: 2, flags: 0 }, { type: 'text', text: ' at ' },
    { type: 'location_id', text: '200', player: 1 },
  ] }]);
  await wait(10);
  assert.equal(lines().at(-1), 'Me found Sword at Wash');
});

test('/items and /ready', async () => {
  await type('/items');
  assert.ok(lines().slice(-3).join('|').startsWith('Item Names for Taskipelago|Key|Mystery'));
  sent.length = 0;
  await type('/ready');
  assert.equal(lines().at(-1), 'Readied up.');
  assert.ok(sent.some(m => m.cmd === 'StatusUpdate' && m.status === 10));
});

test('reconnect uses cached DataPackages', async () => {
  await type('/disconnect');
  assert.equal($('connect-status').textContent, 'Disconnected.');
  sent.length = 0;
  await type('/connect');
  assert.equal($('connect-status').textContent, 'Connected.');
  assert.equal(sent.filter(m => m.cmd === 'GetDataPackage').length, 0);
});

test('no runtime errors', () => {
  assert.deepEqual(errors.map(e => String(e?.stack || e)), []);
});
