// Local slash commands, ported from Archipelago CommonClient.ClientCommandProcessor
// (UNIFY 5.2). Help, error and result text match Archipelago's CommandProcessor.
// Not ported: /exit and /license (no meaning in a page), /item_groups and
// /location_groups (groups are not in the DataPackage). Added: /checked.
import { ap } from '../play/state.js';
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
