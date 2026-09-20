// Local slash commands, ported from Archipelago CommonClient.ClientCommandProcessor
// (UNIFY 5.2). Help, error and result text match Archipelago's CommandProcessor.
// Not ported: /exit and /license (no meaning in a page), /item_groups and
// /location_groups (groups are not in the DataPackage). Added: /checked, and
// /click and /clicker for Tasclickpelago slots.
import { ap, state } from '../play/state.js';
import { ClientStatus } from '../archipelago.js';
import { dpEntries, ownGame } from '../play/datapackage.js';

const MARKER = '/';

// [name, args with "" defaults, docstring]
const COMMANDS = [
  ['help', [], 'Returns the help listing'],
  ['connect', ['address'], 'Connect to a MultiWorld Server'],
  ['disconnect', [], 'Disconnect from a MultiWorld Server'],
  ['received', [], 'List all received items'],
  ['missing', ['filter_text'],
    'List all missing location checks, from your local game state.\nCan be given text, which will be used as filter.'],
  ['checked', ['filter_text'],
    'List all checked location checks, from your local game state.\nCan be given text, which will be used as filter.'],
  ['items', [], 'List all item names for the currently running game.'],
  ['locations', [], 'List all location names for the currently running game.'],
  ['ready', [], 'Send ready status to server.'],
  ['click', ['task'],
    'Clicker mode: click a task once, by number or by name.\nWith no argument, lists the tasks you can click.'],
  ['clicker', [], 'Clicker mode: print the current rates, multipliers and task-count constants.'],
];

export function helpText() {
  let s = '';
  for (const [name, args, doc] of COMMANDS) {
    const argtext = args.map(a => `[${a}] `).join('');
    s += `${MARKER}${name} ${argtext}\n    ${doc.split('\n').join('\n    ')}\n`;
  }
  return s;
}

/** shlex-style split; falls back to whitespace split on unbalanced quotes. */
export function splitCommand(raw) {
  const out = [];
  let cur = '';
  let quote = null;
  let started = false;
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (quote) {
      if (ch === quote) quote = null;
      else if (ch === '\\' && quote === '"' && i + 1 < raw.length) cur += raw[++i];
      else cur += ch;
    } else if (ch === '"' || ch === "'") {
      quote = ch;
      started = true;
    } else if (ch === '\\' && i + 1 < raw.length) {
      cur += raw[++i];
      started = true;
    } else if (/\s/.test(ch)) {
      if (started) { out.push(cur); cur = ''; started = false; }
    } else {
      cur += ch;
      started = true;
    }
  }
  if (quote) return raw.split(/\s+/).filter(Boolean);
  if (started) out.push(cur);
  return out;
}

function listLocations(ctx, filterText, wantChecked) {
  if (!ap.ourSlot && ap.ourSlot !== 0) {
    ctx.output(`No game set, cannot determine ${wantChecked ? 'checked' : 'missing'} checks.`);
    return false;
  }
  const entries = dpEntries(ownGame(), 'locations');
  if (!entries) {
    ctx.output('datapackage not yet loaded, try again');
    return false;
  }
  let count = 0;
  let checkedCount = 0;
  for (const [id, name] of entries) {
    if (filterText && !name.includes(filterText)) continue;
    if (id < 0) continue;
    if (wantChecked) {
      if (ap.checkedLocations.has(id)) {
        ctx.output('Checked: ' + name);
        count++;
      }
    } else if (!ap.sentLocations.has(id)) {
      if (ap.missingLocations.has(id)) {
        ctx.output('Missing: ' + name);
        count++;
      } else if (ap.checkedLocations.has(id)) {
        ctx.output('Checked: ' + name);
        count++;
        checkedCount++;
      }
    }
  }
  if (wantChecked) {
    ctx.output(count ? `Found ${count} checked location checks` : 'No checked location checks found.');
  } else if (count) {
    ctx.output(`Found ${count} missing location checks${checkedCount ? `. ${checkedCount} location checks previously visited.` : ''}`);
  } else {
    ctx.output('No missing location checks found.');
  }
  return true;
}

function listNames(ctx, kind) {
  const label = kind === 'items' ? 'Item Names' : 'Location Names';
  if (!ap.ourSlot && ap.ourSlot !== 0) {
    ctx.output(`No game set, cannot determine ${label}.`);
    return false;
  }
  const game = ownGame();
  const entries = dpEntries(game, kind);
  if (!entries) {
    ctx.output('datapackage not yet loaded, try again');
    return false;
  }
  ctx.output(`${label} for ${game}`);
  for (const [, name] of entries) ctx.output(name);
  return true;
}

/** Resolve a /click argument: a 1-based task number or a task name. */
function findTask(arg) {
  const s = String(arg ?? '').trim();
  if (!s) return -1;
  if (/^\d+$/.test(s)) {
    const n = Number(s) - 1;
    return n >= 0 && n < state.tasks.length ? n : -1;
  }
  const exact = state.tasks.indexOf(s);
  if (exact >= 0) return exact;
  const lower = s.toLowerCase();
  return state.tasks.findIndex(t => String(t).toLowerCase() === lower);
}

function clickerGuard(ctx) {
  if (!state.clickerMode) {
    ctx.output('This slot is not in clicker mode.');
    return false;
  }
  return true;
}

const HANDLERS = {
  help: ctx => { ctx.output(helpText()); return true; },
  connect: (ctx, address = '') => {
    if (!address && !ctx.hasAddress()) {
      ctx.output('Please specify an address.');
      return false;
    }
    ctx.connect(address);
    return true;
  },
  disconnect: ctx => { ctx.disconnect(); return true; },
  received: ctx => {
    const items = ap.itemsReceived.filter(Boolean);
    ctx.output(`${items.length} received items, sorted by time:`);
    for (const it of items) {
      ctx.printJson([
        { type: 'item_id', text: String(it.item), player: ap.ourSlot, flags: it.flags },
        { type: 'text', text: ' from ' },
        { type: 'location_id', text: String(it.location), player: it.player },
        { type: 'text', text: ' by ' },
        { type: 'player_id', text: String(it.player) },
      ]);
    }
    return true;
  },
  missing: (ctx, filterText = '') => listLocations(ctx, filterText, false),
  checked: (ctx, filterText = '') => listLocations(ctx, filterText, true),
  items: ctx => listNames(ctx, 'items'),
  locations: ctx => listNames(ctx, 'locations'),
  click: async (ctx, task = '') => {
    if (!clickerGuard(ctx)) return false;
    const board = await import('../play/clicker_board.js');
    const model = board.clickerModel();
    if (!String(task).trim()) {
      ctx.output(model.eligible.length ? 'Clickable tasks:' : 'No task is clickable right now.');
      for (const i of model.eligible) {
        ctx.output(`  ${i + 1}. ${state.tasks[i]} - ${board.taskProgress(i)} / ${board.requiredActivations(i)}`);
      }
      return true;
    }
    const idx = findTask(task);
    if (idx < 0) {
      ctx.output(`No task named ${task}.`);
      return false;
    }
    if (!model.eligible.includes(idx)) {
      const ready = !board.isManualTask(idx) && board.isReadyTask(idx)
        && model.avail[idx].unlocked && !model.avail[idx].completed;
      ctx.output(ready
        ? `${idx + 1}. ${state.tasks[idx]} is full; press its Complete button.`
        : `${idx + 1}. ${state.tasks[idx]} is locked or already complete.`);
      return false;
    }
    const done = board.clickTask(idx);
    ctx.output(`${idx + 1}. ${state.tasks[idx]}: ${board.taskProgress(idx)} / ${board.requiredActivations(idx)}`
      + (done ? ' - complete!' : ''));
    return true;
  },
  clicker: async ctx => {
    if (!clickerGuard(ctx)) return false;
    const board = await import('../play/clicker_board.js');
    const m = board.clickerModel();
    let total = 0;
    for (const i of m.eligible) total += m.rate[i];
    ctx.output(`Production: ${total}/s across ${m.eligible.length} eligible task(s), slot-wide multiplier x${m.globalMult}`);
    ctx.output(`Click value: ${m.clickValue} slot-wide (per task below; click power is per target)`);
    for (const g of m.grants) {
      ctx.output(`  ${g.name}: ${g.kind} ${g.rate ?? g.power ?? g.mult}`
        + `${g.copies > 1 ? ` x${g.copies}` : ''} -> ${board.targetLabel(g.spec)}`);
    }
    ctx.output(`N_TASKS ${m.nTasks}, N_TASKS_UNLOCKED ${m.nUnlocked}, N_TASKS_LOCKED ${m.nLocked}, `
      + `N_TASKS_COMPLETED ${m.nCompleted}, CPS ${m.clickValue}`);
    ctx.output(state.clickerOffline
      ? `Offline production on, capped at ${state.clickerOfflineCapHours}h`
      : 'Offline production off');
    for (const i of m.eligible) {
      ctx.output(`  ${i + 1}. ${state.tasks[i]} - ${board.taskProgress(i)} / ${board.requiredActivations(i)}`
        + ` (+${m.rate[i]}/s, click +${m.taskClickValue[i]}, x${m.prodMult[i]} production)`);
    }
    return true;
  },
  ready: ctx => {
    ap.ready = !ap.ready;
    ctx.output(ap.ready ? 'Readied up.' : 'Unreadied.');
    ap.sendStatusUpdate(ap.ready ? ClientStatus.READY : ClientStatus.CONNECTED);
    return true;
  },
};

/**
 * Run console input as a local command.
 * ctx: {output(text), printJson(parts), connect(address), disconnect(), hasAddress()}
 * Returns false when the input is not a slash command (the caller sends it as Say).
 */
export function runCommand(raw, ctx) {
  const command = splitCommand(raw);
  if (!command.length || !command[0].startsWith(MARKER)) return false;
  const name = command[0].slice(1).toLowerCase();
  const handler = HANDLERS[name];
  if (!handler) {
    ctx.output(`Could not find command ${command[0].slice(1)}. Known commands: ${COMMANDS.map(c => c[0]).join(', ')}`);
    return true;
  }
  handler(ctx, ...command.slice(1));
  return true;
}
