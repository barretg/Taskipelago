// v1.1 F3: pending DeathLink task queue. Every DeathLink that gets past amnesty
// adds an entry, rendered as a red task card; completing a card removes it.
// With slot_data death_link_lock_tasks, a non-empty queue locks every other task.
//
// Persistence (UNIFY 3 layers):
//   device  taskipelago_deathlink_v1::<server>::<slot>::<seed>  written on every change, loaded on connect
//   server  taskipelago_deathlink::<slot>::<seed>               update {id: entry} / pop id, synced by SetNotify
// Merge on connect: the server dict wins; the device copy is pushed only when the
// server key is absent (first run or migration).
import { state } from './state.js';
import * as storage from '../shared/storage.js';
import { writeDeathLinkAdd, writeDeathLinkRemove, writeDeathLinkMerge } from '../shared/server_state.js';
import { renderAll } from './render.js';

function deviceKey() {
  return `taskipelago_deathlink_v1::${state.serverAddr.toLowerCase()}::${state.slotName}::${state.seedName}`;
}

/** Keep only well-formed entries; the dict key is the id. */
export function sanitizeDeathLinkQueue(obj) {
  const out = {};
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return out;
  for (const [id, e] of Object.entries(obj)) {
    if (!e || typeof e !== 'object' || Array.isArray(e)) continue;
    out[id] = {
      id,
      task: typeof e.task === 'string' ? e.task : String(e.task ?? ''),
      source: typeof e.source === 'string' ? e.source : 'Unknown',
      cause: typeof e.cause === 'string' ? e.cause : '',
      time: Number.isFinite(e.time) ? e.time : 0,
    };
  }
  return out;
}

/** The same id on every client of the slot for one bounce. */
export const deathLinkId = (time, source) => `${time}|${source}`;

function saveDevice() {
  storage.set(deviceKey(), state.deathLinkQueue);
}

/** On connect, before the first render. */
export function loadDeviceDeathLinkQueue() {
  state.deathLinkQueue = sanitizeDeathLinkQueue(storage.get(deviceKey()));
}

/** Pending entries, oldest first. */
export function pendingDeathLinks() {
  return Object.values(state.deathLinkQueue).sort((a, b) => (a.time - b.time) || (a.id < b.id ? -1 : 1));
}

export function hasDeathLinkEntry(id) {
  return Object.hasOwn(state.deathLinkQueue, id);
}

export function isDeathLinkLocked() {
  return !!state.deathLinkLockTasks && state.connState === 'connected' && pendingDeathLinks().length > 0;
}

export function addDeathLinkEntry(entry) {
  const clean = sanitizeDeathLinkQueue({ [entry.id]: entry })[entry.id];
  state.deathLinkQueue[clean.id] = clean;
  saveDevice();
  writeDeathLinkAdd(clean);
}

export function completeDeathLinkEntry(id) {
  if (!hasDeathLinkEntry(id)) return;
  delete state.deathLinkQueue[id];
  saveDevice();
  writeDeathLinkRemove(id);
  renderAll();
}

/** Retrieved (fromGet) or another client's SetReply. */
export function applyServerDeathLinkQueue(value, fromGet) {
  if (fromGet && (value === null || value === undefined)) {
    if (Object.keys(state.deathLinkQueue).length) writeDeathLinkMerge(state.deathLinkQueue);
    return;
  }
  state.deathLinkQueue = sanitizeDeathLinkQueue(value);
  saveDevice();
}
