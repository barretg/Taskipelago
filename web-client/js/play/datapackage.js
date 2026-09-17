// DataPackage name resolution (UNIFY 5.1). Packages are requested per game and
// cached in device storage by checksum (UNIFY 3.2); older checksums of the same
// game are pruned when a new one is stored.
import { ap } from './state.js';
import * as storage from '../shared/storage.js';

const PREFIX = 'taskipelago_dp::';
const packages = new Map(); // game -> {items: Map(id -> name), locations: Map(id -> name), checksum}

function cacheKey(game, checksum) {
  return `${PREFIX}${game}::${checksum}`;
}

function invert(nameToId) {
  const out = new Map();
  if (!nameToId || typeof nameToId !== 'object') return out;
  for (const [name, id] of Object.entries(nameToId)) {
    if (Number.isInteger(id)) out.set(id, name);
  }
  return out;
}

function load(game, data, checksum) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return false;
  packages.set(game, {
    items: invert(data.item_name_to_id),
    locations: invert(data.location_name_to_id),
    checksum: checksum || null,
  });
  return true;
}

/** Game played by our slot. */
export function ownGame() {
  return ap.gameOfSlot(ap.ourSlot) || 'Taskipelago';
}

/** After Connected: load cached packages and request the rest. */
export function requestDataPackages(roomInfo = ap.roomInfo) {
  const checksums = (roomInfo && roomInfo.datapackage_checksums) || {};
  const wanted = new Set(['Archipelago', ownGame()]);
  for (const info of Object.values(ap.slotInfo || {})) {
    if (info && info.game) wanted.add(info.game);
  }

  const missing = [];
  for (const game of wanted) {
    const checksum = checksums[game];
    if (checksum) {
      const mem = packages.get(game);
      if (mem && mem.checksum === checksum) continue;
      if (load(game, storage.get(cacheKey(game, checksum)), checksum)) continue;
    }
    missing.push(game);
  }
  if (missing.length) ap.sendGetDataPackage(missing);
}

/** DataPackage packet: remember, cache by checksum, prune older checksums. */
export function handleDataPackage(games) {
  const roomChecksums = (ap.roomInfo && ap.roomInfo.datapackage_checksums) || {};
  for (const [game, data] of Object.entries(games || {})) {
    if (!data || typeof data !== 'object') continue;
    const checksum = data.checksum || roomChecksums[game] || null;
    load(game, data, checksum);
    if (!checksum) continue;
    const key = cacheKey(game, checksum);
    for (const k of storage.keys()) {
      if (k.startsWith(`${PREFIX}${game}::`) && k !== key) storage.remove(k);
    }
    storage.set(key, {
      item_name_to_id: data.item_name_to_id || {},
      location_name_to_id: data.location_name_to_id || {},
    });
  }
}

export function hasDataPackage(game) {
  return packages.has(game);
}

export function dpItemName(id, game) {
  const pkg = packages.get(game);
  return (pkg && pkg.items.get(id)) || null;
}

export function dpLocationName(id, game) {
  const pkg = packages.get(game);
  return (pkg && pkg.locations.get(id)) || null;
}

/** [id, name] pairs in DataPackage order, or null when not loaded. */
export function dpEntries(game, kind) {
  const pkg = packages.get(game);
  if (!pkg) return null;
  return [...(kind === 'items' ? pkg.items : pkg.locations).entries()];
}
