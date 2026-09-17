import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupDom, bootApp, connect, $, FakeWS, errors, wait, sent } from '../helpers/env.mjs';

setupDom();
await bootApp();

test('boot renders disconnected placeholders', () => {
  assert.match($('tasks-list').textContent, /Connect to a server/);
  assert.match($('notif-list').textContent, /No notifications/);
  assert.equal($('console-input').disabled, false); // /connect and /help work while disconnected
});

test('connect renders tasks with prereq lock hints', async () => {
  await connect();
  assert.equal($('connect-status').textContent, 'Connected.');
  assert.match($('tasks-list').textContent, /1\. Wash/);
  assert.match($('tasks-list').textContent, /Locked behind task\(s\): 1/);
  assert.equal($('console-input').disabled, false);
  assert.ok(sent.some(m => m.cmd === 'Connect' && m.game === 'Taskipelago'));
});

test('received items show in the Items tab', async () => {
  FakeWS.last.recv([{ cmd: 'ReceivedItems', index: 0, items: [{ item: 300, location: 5, player: 1, flags: 1 }] }]);
  await wait(10);
  assert.match($('items-list').textContent, /Key/);
});

test('completing a task sends both location checks', async () => {
  sent.length = 0;
  const btn = [...$('tasks-list').querySelectorAll('button')].find(b => b.textContent === 'Complete' && !b.disabled);
  btn.click();
  await wait(10);
  assert.ok(sent.some(m => m.cmd === 'LocationChecks' && m.locations.includes(200) && m.locations.includes(100)));
});

test('no runtime errors', () => {
  assert.deepEqual(errors.map(e => String(e?.stack || e)), []);
});
