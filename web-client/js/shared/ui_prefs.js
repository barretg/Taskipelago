// Per-device UI preferences in the taskipelago_ui device-storage object
// (UNIFY 3.2). Unknown fields are preserved so later features can add their own.
import * as storage from './storage.js';

const KEY = 'taskipelago_ui';

export function getUiPrefs() {
  const v = storage.get(KEY);
  return v && typeof v === 'object' && !Array.isArray(v) ? v : {};
}

export function getUiPref(name, fallback) {
  const v = getUiPrefs()[name];
  return v === undefined ? fallback : v;
}

export function setUiPref(name, value) {
  const prefs = getUiPrefs();
  prefs[name] = value;
  storage.set(KEY, prefs);
}
