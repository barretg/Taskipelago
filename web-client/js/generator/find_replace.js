// v1.1 F5: Find and replace across the YAML Generator. Matches come from the
// editor model (not the DOM); inputs carry data-field="<section>.<row>.<key>" so
// a match can be scrolled to, focused and selected.
import { h, scrollIntoViewAndFocus } from '../shared/dom.js';
import { confirmDialog } from '../shared/dialog.js';
import { MAX_TASK_DESCRIPTION_LEN } from './model.js';

export const SCOPES = [
  ['taskNames', 'Task names'],
  ['descriptions', 'Descriptions'],
  ['taskPrereqs', 'Task prereqs'],
  ['itemPrereqs', 'Item prereqs'],
  ['costs', 'Costs'],
  ['itemNames', 'Item names'],
  ['deathLink', 'DeathLink tasks'],
  ['regionPrereqs', 'Region "depends on"'],
  ['goalTasks', 'Goal tasks'],
];

// ---------------------------------------------------------------------------
// Engine (pure)
// ---------------------------------------------------------------------------

/** Searchable fields in section order Tasks, Items, DeathLink, Regions. Filler item rows are skipped. */
export function collectTargets(model, scopes = {}) {
  const targets = [];
  const add = (scope, section, field, obj, key, label) => {
    if (scopes[scope] !== false) targets.push({ scope, section, field, obj, key, label });
  };
  add('goalTasks', 'tasks', 'goalTasks', model, 'goalTasks', 'Goal tasks');
  model.tasks.forEach((t, i) => {
    add('taskNames', 'tasks', `tasks.${i}.name`, t, 'name', `Task ${i + 1} name`);
    add('descriptions', 'tasks', `tasks.${i}.desc`, t, 'desc', `Task ${i + 1} description`);
    add('taskPrereqs', 'tasks', `tasks.${i}.prereq`, t, 'prereq', `Task ${i + 1} task prereqs`);
    add('itemPrereqs', 'tasks', `tasks.${i}.itemPrereq`, t, 'itemPrereq', `Task ${i + 1} item prereqs`);
    add('costs', 'tasks', `tasks.${i}.cost`, t, 'cost', `Task ${i + 1} cost`);
  });
  model.items.forEach((it, i) => {
    if (!it.filler) add('itemNames', 'items', `items.${i}.name`, it, 'name', `Item ${i + 1} name`);
  });
  model.deathLink.forEach((row, i) => add('deathLink', 'deathlink', `deathlink.${i}.text`, row, 'text', `DeathLink task ${i + 1}`));
  model.regions.forEach((r, i) => add('regionPrereqs', 'regions', `regions.${i}.prereq`, r, 'prereq', `Region '${r.name}' depends on`));
  return targets;
}

export const escapeRegExp = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Global RegExp for the search text, or null when empty. Whole word uses
 * letter/digit/underscore lookarounds rather than \b so words that start or end
 * with punctuation (e.g. "Quoted") still match.
 */
export function findRegExp(find, { matchCase = false, wholeWord = false } = {}) {
  if (!find) return null;
  const body = escapeRegExp(find);
  const source = wholeWord ? `(?<![\\p{L}\\p{N}_])${body}(?![\\p{L}\\p{N}_])` : body;
  return new RegExp(source, matchCase ? 'gu' : 'giu');
}

/** Every match as { ti, target, start, end } (UTF-16 offsets, as setSelectionRange takes). */
export function findMatches(targets, re) {
  const out = [];
  if (!re) return out;
  targets.forEach((target, ti) => {
    const text = String(target.obj[target.key] ?? '');
    for (const m of text.matchAll(re)) {
      if (m[0]) out.push({ ti, target, start: m.index, end: m.index + m[0].length });
    }
  });
  return out;
}

const cpCut = (s, n) => Array.from(s).slice(0, n).join('');

function store(target, text) {
  target.obj[target.key] = target.key === 'desc' ? cpCut(text, MAX_TASK_DESCRIPTION_LEN) : text;
}

/** Replace one match (as returned by findMatches) with literal text. */
export function replaceMatch(match, replacement) {
  const text = String(match.target.obj[match.target.key] ?? '');
  store(match.target, text.slice(0, match.start) + replacement + text.slice(match.end));
}

/** Replace every match with literal text. Returns { count, fields }. */
export function replaceAll(targets, re, replacement) {
  let count = 0;
  let fields = 0;
  if (!re) return { count, fields };
  for (const target of targets) {
    let n = 0;
    const text = String(target.obj[target.key] ?? '');
    const next = text.replace(re, m => (m ? (n++, replacement) : m));
    if (n) {
      store(target, next);
      count += n;
      fields++;
    }
  }
  return { count, fields };
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

const ALL_PARTS = { tasks: true, items: true, regions: true, deathlink: true, goal: true };
let panel = null;

/**
 * Open (or refocus) the panel. ctx needs model, changed(parts), root and
 * openSection(key). focus is 'find' or 'replace'.
 */
export function openFindReplace(ctx, focus = 'find') {
  if (panel?.isConnected) {
    panel.focusField(focus);
    return panel;
  }
  let cursor = null; // { ti, start } of the match last shown
  let highlighted = null;

  const find = h('input', { type: 'text', spellcheck: false, 'aria-label': 'Find', placeholder: 'Find' });
  const replace = h('input', { type: 'text', spellcheck: false, 'aria-label': 'Replace', placeholder: 'Replace with' });
  const matchCase = h('input', { type: 'checkbox' });
  const wholeWord = h('input', { type: 'checkbox' });
  const scopeBoxes = Object.fromEntries(SCOPES.map(([key]) => [key, h('input', { type: 'checkbox', checked: true, dataset: { scope: key } })]));
  const status = h('div', { className: 'find-status muted-text', role: 'status' });

  const scopes = () => Object.fromEntries(SCOPES.map(([key]) => [key, scopeBoxes[key].checked]));
  const targets = () => collectTargets(ctx.model, scopes());
  const regexp = () => findRegExp(find.value, { matchCase: matchCase.checked, wholeWord: wholeWord.checked });
  const matches = () => findMatches(targets(), regexp());
  const reset = () => { cursor = null; status.textContent = ''; };

  function show(match, index, total, prefix = '') {
    cursor = { ti: match.ti, start: match.start };
    highlighted?.classList.remove('find-highlight');
    highlighted = null;
    const where = `Match ${index + 1} of ${total}`;
    ctx.openSection(match.target.section);
    const el = ctx.root.querySelector(`[data-field="${match.target.field}"]`);
    if (match.target.key === 'desc') {
      // Descriptions are edited in a dialog: point at the row's button and show the text here.
      el?.classList.add('find-highlight');
      highlighted = el;
      el?.scrollIntoView?.({ block: 'center' });
      status.textContent = `${prefix}${where}: ${match.target.label}: ${match.target.obj.desc}`;
      return;
    }
    status.textContent = `${prefix}${where} (${match.target.label})`;
    if (el) {
      scrollIntoViewAndFocus(el);
      el.setSelectionRange?.(match.start, match.end);
    }
  }

  function step(dir, prefix = '') {
    const all = matches();
    if (!all.length) {
      reset();
      status.textContent = `${prefix}${find.value ? 'No matches' : ''}`;
      return;
    }
    let idx;
    if (!cursor) idx = dir > 0 ? 0 : all.length - 1;
    else if (dir > 0) {
      idx = all.findIndex(m => m.ti > cursor.ti || (m.ti === cursor.ti && m.start > cursor.start));
      if (idx < 0) idx = 0;
    } else {
      idx = all.findLastIndex(m => m.ti < cursor.ti || (m.ti === cursor.ti && m.start < cursor.start));
      if (idx < 0) idx = all.length - 1;
    }
    show(all[idx], idx, all.length, prefix);
  }

  function replaceOne() {
    const current = cursor && matches().find(m => m.ti === cursor.ti && m.start === cursor.start);
    if (!current) {
      step(1);
      return;
    }
    replaceMatch(current, replace.value);
    ctx.changed(ALL_PARTS);
    // Continue after the inserted text so it is not matched again.
    cursor = { ti: current.ti, start: current.start + replace.value.length - 1 };
    step(1, 'Replaced 1. ');
  }

  async function replaceEverything() {
    const all = matches();
    if (!all.length) {
      status.textContent = find.value ? 'No matches' : '';
      return;
    }
    const fields = new Set(all.map(m => m.ti)).size;
    const ok = await confirmDialog('Replace All',
      `Replace ${all.length} occurrence${all.length === 1 ? '' : 's'} in ${fields} field${fields === 1 ? '' : 's'}?`);
    if (!ok) return;
    const { count } = replaceAll(targets(), regexp(), replace.value);
    ctx.changed(ALL_PARTS);
    cursor = null;
    status.textContent = `Replaced ${count}`;
  }

  function close() {
    highlighted?.classList.remove('find-highlight');
    panel.remove();
    panel = null;
  }

  for (const el of [find, matchCase, wholeWord, ...Object.values(scopeBoxes)]) {
    el.addEventListener(el === find ? 'input' : 'change', reset);
  }
  find.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); step(e.shiftKey ? -1 : 1); } });
  replace.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); replaceOne(); } });

  const check = (box, label) => h('label', { className: 'check-label' }, box, label);
  panel = h('div', { className: 'find-panel', role: 'dialog', 'aria-label': 'Find and Replace' },
    h('div', { className: 'find-head' },
      h('span', { className: 'dialog-title' }, 'Find and Replace'),
      h('button', { type: 'button', className: 'remove-btn', 'aria-label': 'Close', onclick: () => close() }, 'x')),
    find, replace,
    h('div', { className: 'find-options' }, check(matchCase, 'Match case'), check(wholeWord, 'Whole word')),
    h('details', { className: 'find-scopes' }, h('summary', {}, 'Search in'),
      h('div', { className: 'find-scope-list' }, SCOPES.map(([key, label]) => check(scopeBoxes[key], label)))),
    h('div', { className: 'btn-row' },
      h('button', { type: 'button', onclick: () => step(-1) }, 'Find Previous'),
      h('button', { type: 'button', className: 'primary', onclick: () => step(1) }, 'Find Next')),
    h('div', { className: 'btn-row' },
      h('button', { type: 'button', onclick: replaceOne }, 'Replace'),
      h('button', { type: 'button', onclick: replaceEverything }, 'Replace All')),
    status,
    h('div', { className: 'muted-text find-hint' },
      'Renaming a task or item does not update "Quoted" references unless the prereq and cost scopes are checked.'));
  panel.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
    }
  });
  panel.focusField = which => (which === 'replace' ? replace : find).focus();
  ctx.root.appendChild(panel);
  panel.focusField(focus);
  return panel;
}
