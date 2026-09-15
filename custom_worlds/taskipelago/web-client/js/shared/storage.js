// Device storage (UNIFY 3.2). One interface, backend chosen by flag:
//   localStorageService on:  whole object loaded once from /api/storage, writes
//                            debounced into PATCH requests (webhost JSON file)
//   off:                     browser localStorage, in-memory fallback
// get() returns the value directly; awaiting it is also fine.
import { cfg, hasFeature } from './config.js';

const DEBOUNCE_MS = 300;
const HEARTBEAT_MS = 5000;

let service = false;
let mem = {};
let pendingSet = {};
let pendingRemove = new Set();
let timer = null;

function clone(v) {
  return v === undefined ? undefined : JSON.parse(JSON.stringify(v));
}

function apiHeaders(extra = {}) {
  return { 'X-Taskipelago-Token': cfg.token || '', ...extra };
}

export async function initStorage() {
  service = hasFeature('localStorageService');
  if (!service) return;
  try {
    const res = await fetch('/api/storage', { headers: apiHeaders(), cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (data && typeof data === 'object') mem = data;
    }
  } catch (_) { /* keep empty */ }
  const beat = () => {
    fetch('/api/heartbeat', {
      method: 'POST', headers: apiHeaders({ 'Content-Type': 'application/json' }), body: '{}',
    }).catch(() => {});
  };
  beat();
  setInterval(beat, HEARTBEAT_MS);
  addEventListener('pagehide', () => flush(true));
}

export function get(key, fallback = null) {
  if (service) return key in mem ? clone(mem[key]) : fallback;
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return key in mem ? clone(mem[key]) : fallback;
    try { return JSON.parse(raw); } catch (_) { return raw; }
  } catch (_) {
    return key in mem ? clone(mem[key]) : fallback;
  }
}

export function set(key, value) {
  mem[key] = clone(value);
  if (service) {
    pendingSet[key] = mem[key];
    pendingRemove.delete(key);
    schedule();
    return;
  }
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
}

export function remove(key) {
  delete mem[key];
  if (service) {
    delete pendingSet[key];
    pendingRemove.add(key);
    schedule();
    return;
  }
  try { localStorage.removeItem(key); } catch (_) {}
}

function schedule() {
  if (timer) return;
  timer = setTimeout(() => flush(false), DEBOUNCE_MS);
}

export function flush(keepalive = false) {
  if (timer) { clearTimeout(timer); timer = null; }
  if (!service) return;
  const setVals = pendingSet;
  const removeKeys = [...pendingRemove];
  if (!Object.keys(setVals).length && !removeKeys.length) return;
  pendingSet = {};
  pendingRemove = new Set();
  fetch('/api/storage', {
    method: 'PATCH',
    keepalive,
    headers: apiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ set: setVals, remove: removeKeys }),
  }).catch(() => {
    // Requeue anything not superseded since, and retry later.
    for (const [k, v] of Object.entries(setVals)) if (!(k in pendingSet) && !pendingRemove.has(k)) pendingSet[k] = v;
    for (const k of removeKeys) if (!(k in pendingSet)) pendingRemove.add(k);
    schedule();
  });
}
