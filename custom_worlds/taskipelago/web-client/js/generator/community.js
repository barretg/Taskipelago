// Community YAMLs (UNIFY 5.6). The list and files come from the Apps Script web
// app at cfg.communityEndpoint (yaml-library/Code.gs doGet); its page without an
// action is the submission form. The last list is cached on this device (3.2).
import { cfg } from '../shared/config.js';
import { h } from '../shared/dom.js';
import { alertDialog, openDialog } from '../shared/dialog.js';
import * as storage from '../shared/storage.js';
import { loadYaml } from '../shared/yaml11.js';

export const CACHE_KEY = 'taskipelago_community_cache';
const TIMEOUT_MS = 15000;

async function getJson(params) {
  const url = new URL(cfg.communityEndpoint);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { redirect: 'follow', signal: controller.signal, cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = await res.json();
    if (body && typeof body === 'object' && !Array.isArray(body) && body.error) throw new Error(body.error);
    return body;
  } catch (e) {
    throw e.name === 'AbortError' ? new Error('The request timed out.') : e;
  } finally {
    clearTimeout(timer);
  }
}

const str = v => (typeof v === 'string' ? v : '');

export async function fetchCommunityEntries() {
  const body = await getJson({ action: 'list' });
  if (!Array.isArray(body)) throw new Error('Unexpected response from the community YAML list.');
  const entries = body
    .map(e => ({ file_id: str(e?.file_id), filename: str(e?.filename), slot: str(e?.slot), author: str(e?.author), version: str(e?.version) }))
    .filter(e => e.file_id && e.filename);
  storage.set(CACHE_KEY, { savedAt: Date.now(), entries });
  return entries;
}

export async function downloadCommunityYaml(fileId) {
  const body = await getJson({ action: 'file', id: fileId });
  if (!body || typeof body.text !== 'string') throw new Error('Unexpected response from the community YAML download.');
  return body.text;
}

function cachedEntries() {
  const cache = storage.get(CACHE_KEY);
  return cache && Array.isArray(cache.entries) ? cache.entries : null;
}

async function importEntry(entry, listDialog, applyDoc) {
  const status = openDialog({
    title: 'Importing...', text: `Downloading ${entry.filename}...`, buttons: [], dismissable: false,
  });
  let doc;
  try {
    doc = loadYaml(await downloadCommunityYaml(entry.file_id));
  } catch (e) {
    status.close();
    await alertDialog('error', 'Error', `Failed to import community YAML:\n${e.message}`);
    return;
  }
  status.close();
  listDialog.close();
  await applyDoc(doc, `Imported YAML from community file:\n${entry.filename}`);
}

function renderList(dialog, entries, note, applyDoc) {
  const submit = h('a', { href: cfg.communityEndpoint, target: '_blank', rel: 'noopener' }, 'Submit your YAML');
  const parts = [];
  if (note) parts.push(h('div', { className: 'muted-text community-note' }, note));
  if (!entries.length) {
    parts.push(h('div', {}, 'No community YAMLs found.'));
  } else {
    parts.push(h('div', { className: 'community-table' },
      h('div', { className: 'community-row gt-head' },
        h('span', {}, 'Slot Name'), h('span', {}, 'Author'), h('span', { className: 'num' }, 'Taskipelago Version'), h('span', {})),
      entries.map(entry => h('div', { className: 'community-row' },
        h('span', {}, entry.slot), h('span', {}, entry.author), h('span', { className: 'num' }, entry.version),
        h('button', { type: 'button', onclick: () => importEntry(entry, dialog, applyDoc) }, 'Import YAML')))));
  }
  parts.push(h('div', { className: 'community-submit' }, submit));
  dialog.body.replaceChildren(...parts);
  dialog.setButtons([{ label: 'Close', value: null }]);
}

/** Open the list dialog. applyDoc(doc, successMessage) comes from generator.js. */
export async function openCommunityYamls(applyDoc) {
  if (!cfg.communityEndpoint) {
    await alertDialog('info', 'Community YAMLs', 'Community YAMLs unavailable.');
    return;
  }
  const dialog = openDialog({
    title: 'Community YAMLs', className: 'community-dialog', text: 'Loading community YAML list...',
    buttons: [{ label: 'Close', value: null }],
  });
  try {
    renderList(dialog, await fetchCommunityEntries(), '', applyDoc);
  } catch (e) {
    const cached = cachedEntries();
    if (cached) {
      renderList(dialog, cached, `Community YAMLs unavailable (${e.message}). Showing the last list loaded.`, applyDoc);
    } else {
      dialog.body.replaceChildren(h('div', { className: 'dialog-text' },
        `Community YAMLs unavailable.\n\nFailed to load community YAML list:\n${e.message}`));
    }
  }
}
