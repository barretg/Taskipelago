// Per-seed game state in Archipelago data storage (UNIFY 3.1). Shared by every
// client of the slot (hosted page, local client, other devices) and synced live
// through SetNotify.
//
//   taskipelago_manual::<slot>::<seed>     {name: count}            replace
//   taskipelago_notify::<slot>::<seed>     int item index           max; replace on server-restart reset
//   taskipelago_purchases::<slot>::<seed>  {taskIdx: {name: amt}}   update
//   taskipelago_deathlink::<slot>::<seed>  {id: entry}              update to add, pop to remove (v1.1 F3)
//   taskipelago_clicker::<slot>::<seed>    {p:{taskIdx: n}, t: ms}  replace (clicker mode)
import { ap, state, CLIENT_ID } from '../play/state.js';

const NOTIFY_DEBOUNCE_MS = 1000;
// Clicker progress moves every tick; writing at tick rate would hammer data storage.
const CLICKER_DEBOUNCE_MS = 5000;

export function serverKeys(slot = state.slotName, seed = state.seedName) {
  const id = `${slot || ''}::${seed || ''}`;
  return {
    manual: `taskipelago_manual::${id}`,
    notify: `taskipelago_notify::${id}`,
    purchases: `taskipelago_purchases::${id}`,
    deathlink: `taskipelago_deathlink::${id}`,
    clicker: `taskipelago_clicker::${id}`,
  };
}

/** On connect: Get every per-seed key and subscribe to changes in one batch. */
export function subscribeServerState() {
  const keys = Object.values(serverKeys());
  ap.sendGet(keys);
  ap.sendSetNotify(keys);
}

/** True for a SetReply caused by this client's own Set (the server echoes client_id). */
export function isOwnWrite(msg) {
  return !!msg && msg.client_id === CLIENT_ID;
}

// ---- Validation of values read from the server or other clients ----

function isCount(v) {
  return Number.isInteger(v) && v > 0;
}

/** Accept only {string: int > 0} (legacy client.py:1475, 1490). */
export function sanitizeCounts(obj) {
  const out = {};
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return out;
  for (const [k, v] of Object.entries(obj)) if (isCount(v)) out[k] = v;
  return out;
}

/**
 * Clicker progress read back from the server: {"p": {taskIdx: activations}, "t": ms}.
 * Task indices are non-negative integers and activations finite non-negative
 * numbers; anything else is dropped rather than trusted.
 */
export function sanitizeClickerProgress(obj) {
  const out = { p: {}, t: 0 };
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return out;
  const p = obj.p;
  if (p && typeof p === 'object' && !Array.isArray(p)) {
    for (const [k, v] of Object.entries(p)) {
      if (!/^\d+$/.test(k)) continue;
      const n = typeof v === 'number' ? v : NaN;
      if (Number.isFinite(n) && n >= 0) out.p[Number(k)] = n;
    }
  }
  const t = obj.t;
  if (typeof t === 'number' && Number.isFinite(t) && t > 0) out.t = t;
  return out;
}

/**
 * Merge a remote clicker value into a local one, taking the max per task so two
 * open clients cannot roll each other back. The timestamp takes the max too.
 */
export function mergeClickerProgress(local, remote) {
  const a = sanitizeClickerProgress(local);
  const b = sanitizeClickerProgress(remote);
  const p = { ...a.p };
  for (const [k, v] of Object.entries(b.p)) p[k] = Math.max(p[k] ?? 0, v);
  return { p, t: Math.max(a.t, b.t) };
}

/** {taskIdx: {name: amount}} with non-negative integer task indices. */
export function sanitizePurchases(obj) {
  const out = {};
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return out;
  for (const [k, v] of Object.entries(obj)) {
    if (!/^\d+$/.test(k)) continue;
    const deduction = sanitizeCounts(v);
    if (Object.keys(deduction).length) out[Number(k)] = deduction;
  }
  return out;
}

// ---- Writers ----

const OWN = { client_id: CLIENT_ID };

export function writeManualConsumptions(consumptions) {
  ap.sendSetOps(serverKeys().manual, {}, [
    { operation: 'replace', value: sanitizeCounts(consumptions) },
  ], false, OWN);
}

export function writePurchase(taskIdx, deduction) {
  ap.sendSetOps(serverKeys().purchases, {}, [
    { operation: 'update', value: { [String(taskIdx)]: sanitizeCounts(deduction) } },
  ], false, OWN);
}

/** v1.1 F3: add one DeathLink queue entry. */
export function writeDeathLinkAdd(entry) {
  ap.sendSetOps(serverKeys().deathlink, {}, [{ operation: 'update', value: { [entry.id]: entry } }], false, OWN);
}

/** v1.1 F3: push device entries when the server key did not exist yet. */
export function writeDeathLinkMerge(queue) {
  ap.sendSetOps(serverKeys().deathlink, {}, [{ operation: 'update', value: queue }], false, OWN);
}

/** v1.1 F3: remove a completed entry. */
export function writeDeathLinkRemove(id) {
  ap.sendSetOps(serverKeys().deathlink, {}, [{ operation: 'pop', value: id }], false, OWN);
}

let clickerTimer = null;
let clickerPending = null; // {key, value}

/**
 * Queue a clicker progress write. Debounced, and flushed by
 * flushClickerProgress() on visibilitychange / pagehide so a closing tab does
 * not lose the last few seconds.
 */
export function writeClickerProgress(progress, tickMs) {
  const key = serverKeys().clicker;
  if (clickerPending && clickerPending.key !== key) flushClickerProgress();
  clickerPending = { key, value: sanitizeClickerProgress({ p: progress, t: tickMs }) };
  if (!clickerTimer) clickerTimer = setTimeout(flushClickerProgress, CLICKER_DEBOUNCE_MS);
}

export function flushClickerProgress() {
  if (clickerTimer) { clearTimeout(clickerTimer); clickerTimer = null; }
  if (!clickerPending) return;
  const { key, value } = clickerPending;
  clickerPending = null;
  ap.sendSetOps(key, { p: {}, t: 0 }, [{ operation: 'replace', value }], false, OWN);
}

let notifyTimer = null;
let notifyPending = null; // {key, value}

/** Forward-only cursor write, debounced (a small int per item packet). */
export function writeNotifyCursor(index) {
  const key = serverKeys().notify;
  if (notifyPending && notifyPending.key !== key) flushNotifyCursor();
  notifyPending = { key, value: Math.max(notifyPending ? notifyPending.value : 0, index) };
  if (!notifyTimer) notifyTimer = setTimeout(flushNotifyCursor, NOTIFY_DEBOUNCE_MS);
}

export function flushNotifyCursor() {
  if (notifyTimer) { clearTimeout(notifyTimer); notifyTimer = null; }
  if (!notifyPending) return;
  const { key, value } = notifyPending;
  notifyPending = null;
  ap.sendSetOps(key, 0, [{ operation: 'max', value }], false, OWN);
}

/** Server restart detected: move the cursor back. */
export function resetNotifyCursor(index) {
  if (notifyTimer) { clearTimeout(notifyTimer); notifyTimer = null; }
  notifyPending = null;
  ap.sendSetOps(serverKeys().notify, 0, [{ operation: 'replace', value: index }], false, OWN);
}
