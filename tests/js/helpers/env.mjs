// jsdom environment for booting the web client in Node. Each *.test.mjs file
// runs in its own process, so every file gets a fresh copy of the app modules.
import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const WEB_CLIENT = fileURLToPath(new URL('../../../custom_worlds/taskipelago/web-client/', import.meta.url));

export const errors = [];
export const sent = [];
export const wait = ms => new Promise(r => setTimeout(r, ms));

let dom;

// options.config: object served as config.json (default: the committed file)
// options.url:    page URL (default http://127.0.0.1:8000/)
// options.fetch:  async (url, opts) => response-like, for non-config requests
// options.localStorage: initial {key: string} contents
export function setupDom(options = {}) {
  const html = readFileSync(join(WEB_CLIENT, 'index.html'), 'utf8');
  dom = new JSDOM(html, { url: options.url || 'http://127.0.0.1:8000/', pretendToBeVisual: true });
  const { window } = dom;
  window.addEventListener('error', e => errors.push(e.error || e.message));
  process.on('unhandledRejection', e => errors.push(e));

  for (const [k, v] of Object.entries(options.localStorage || {})) window.localStorage.setItem(k, v);

  for (const k of ['document', 'window', 'location', 'localStorage', 'sessionStorage', 'navigator',
                   'HTMLElement', 'Node', 'Event', 'KeyboardEvent', 'CustomEvent', 'getComputedStyle',
                   'addEventListener', 'removeEventListener', 'dispatchEvent']) {
    const value = typeof window[k] === 'function' && /^[a-z]/.test(k) ? window[k].bind(window) : window[k];
    Object.defineProperty(globalThis, k, { value, configurable: true, writable: true });
  }
  globalThis.requestAnimationFrame = cb => setTimeout(cb, 0);
  globalThis.WebSocket = FakeWS;
  window.WebSocket = FakeWS;

  const config = options.config ?? JSON.parse(readFileSync(join(WEB_CLIENT, 'config.json'), 'utf8'));
  globalThis.fetch = async (url, opts) => {
    const u = String(url);
    if (u.endsWith('config.json')) return jsonResponse(config);
    if (options.fetch) return options.fetch(u, opts);
    return { ok: false, status: 404, json: async () => ({}), text: async () => '' };
  };
  return window;
}

export function jsonResponse(body, status = 200) {
  return { ok: status < 400, status, json: async () => body, text: async () => JSON.stringify(body) };
}

export async function bootApp() {
  await import(pathToFileURL(join(WEB_CLIENT, 'js/app.js')).href);
  await wait(20);
}

export async function importModule(rel) {
  return import(pathToFileURL(join(WEB_CLIENT, 'js', rel)).href);
}

export const $ = id => dom.window.document.getElementById(id);

// Fake WebSocket speaking just enough of the AP protocol. Tests react to
// outgoing packets through FakeWS.onSent and push packets with ws.recv().
export class FakeWS {
  static OPEN = 1;
  static instances = [];
  static onSent = null;
  static failUrls = new Set();
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    FakeWS.instances.push(this);
    setTimeout(() => {
      if (FakeWS.failUrls.has(url)) { this.onerror?.(); this.onclose?.(); return; }
      this.readyState = 1;
      this.onopen?.();
      this.recv([{ cmd: 'RoomInfo', seed_name: 'S' }]);
    }, 0);
  }
  static get last() { return FakeWS.instances[FakeWS.instances.length - 1]; }
  send(s) { for (const m of JSON.parse(s)) { sent.push(m); FakeWS.onSent?.(m, this); } }
  close() { this.readyState = 3; }
  recv(msgs) { this.onmessage?.({ data: JSON.stringify(msgs) }); }
}

export function connectedPacket(slotData, extra = {}) {
  return {
    cmd: 'Connected', slot: 1, team: 0,
    players: [{ slot: 1, team: 0, name: 'Me', alias: 'Me' }, { slot: 2, team: 0, name: 'Other', alias: 'Other' }],
    checked_locations: [], missing_locations: [], slot_info: {
      1: { name: 'Me', game: 'Taskipelago', type: 1 },
      2: { name: 'Other', game: 'Other Game', type: 1 },
    },
    slot_data: slotData,
    ...extra,
  };
}

export const BASIC_SLOT_DATA = {
  tasks: ['Wash', 'Cook'], items: ['Key', ''], task_prereqs: ['', '1'], item_prereqs: ['', ''],
  base_reward_location_id: 100, base_complete_location_id: 200, base_item_id: 300, base_token_id: 400,
  seed_name: 'S', lock_prereqs: true, hide_unreachable_tasks: false,
};

// Connect through the UI against the fake server.
export async function connect(slotData = BASIC_SLOT_DATA, { server = 'localhost:38281', slot = 'Me', onSent } = {}) {
  $('server-input').value = server;
  $('slot-input').value = slot;
  FakeWS.onSent = (m, ws) => {
    if (m.cmd === 'Connect') ws.recv([connectedPacket(slotData)]);
    onSent?.(m, ws);
  };
  $('connect-btn').click();
  await wait(40);
}
