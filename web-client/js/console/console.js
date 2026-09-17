import { ap, state, els } from '../play/state.js';
import { escapeHtml } from '../shared/dom.js';
import { dpItemName, dpLocationName, ownGame } from '../play/datapackage.js';
import { runCommand } from './commands.js';

const AP_COLORS = {
  red:       '#cc4444', green:    '#55aa55', yellow: '#aaaa44',
  blue:      '#5588cc', magenta:  '#aa55aa', cyan:   '#44aaaa',
  white:     '#cccccc', black:    '#555555', slateblue: '#6d8be8',
  plum:      '#af99ef', salmon:   '#fa8072',
};

const HISTORY_MAX = 100;

// Names from our own slot data (YAML text), or null.
function localItemName(id) {
  if (state.baseItemId !== null) {
    const idx = id - state.baseItemId;
    if (idx >= 0 && idx < state.items.length) return state.items[idx];
  }
  if (state.baseTokenId !== null) {
    const idx = id - state.baseTokenId;
    if (idx >= 0 && idx < state.tasks.length) return `${state.tasks[idx]} Token`;
  }
  return null;
}

function localLocationName(id) {
  if (state.baseCompleteId !== null) {
    const idx = id - state.baseCompleteId;
    if (idx >= 0 && idx < state.tasks.length) return state.tasks[idx];
  }
  if (state.baseRewardId !== null) {
    const idx = id - state.baseRewardId;
    if (idx >= 0 && idx < state.tasks.length) return `${state.tasks[idx]} Reward`;
  }
  return null;
}

// `player` owns the id: the receiving player for items, the finding player for
// locations. Our own ids prefer YAML text; other games use their DataPackage.
function resolveName(id, player, local, dp) {
  const own = player == null || player === ap.ourSlot;
  if (own) {
    const name = local(id);
    if (name) return name;
  }
  const game = own ? ownGame() : ap.gameOfSlot(player);
  return (game && dp(id, game)) || String(id);
}

export function printJsonToHTML(parts) {
  let html = '';
  for (const part of parts) {
    const type = part.type || 'text';

    let displayText = part.text ?? '';
    if (type === 'player_id') {
      const slot = parseInt(displayText, 10);
      displayText = ap.resolvePlayerName(slot) || displayText;
    } else if (type === 'item_id') {
      displayText = resolveName(parseInt(displayText, 10), part.player ?? null, localItemName, dpItemName);
    } else if (type === 'location_id') {
      displayText = resolveName(parseInt(displayText, 10), part.player ?? null, localLocationName, dpLocationName);
    }

    const text = escapeHtml(String(displayText));

    let color = null;
    let bold  = false;

    if (type === 'player_id') {
      color = (parseInt(part.text, 10) === ap.ourSlot) ? AP_COLORS.magenta : AP_COLORS.yellow;
    } else if (type === 'player_name') {
      color = (part.player === ap.ourSlot) ? AP_COLORS.magenta : AP_COLORS.yellow;
    } else if (type === 'item_id') {
      const f = part.flags || 0;
      if (f & 0b001)      color = AP_COLORS.plum;
      else if (f & 0b100) color = AP_COLORS.salmon;
      else                color = AP_COLORS.cyan;
    } else if (type === 'location_id') {
      color = AP_COLORS.green;
    } else if (type === 'entrance_name') {
      color = AP_COLORS.cyan;
    } else if (type === 'color') {
      color = AP_COLORS[part.color] || null;
      bold  = part.color === 'bold';
    }

    if (color || bold) {
      const style = [
        color ? `color:${color}` : '',
        bold  ? 'font-weight:bold' : '',
      ].filter(Boolean).join(';');
      html += `<span style="${style}">${text}</span>`;
    } else {
      html += text;
    }
  }
  return html;
}

function appendLine(line) {
  line.style.whiteSpace = 'pre-wrap';
  els.consoleOutput.appendChild(line);
  els.consoleOutput.scrollTop = els.consoleOutput.scrollHeight;
}

function appendConsoleHTML(html) {
  const line = document.createElement('div');
  line.innerHTML = html;
  appendLine(line);
}

export function appendConsoleText(text) {
  const line = document.createElement('div');
  line.textContent = text;
  appendLine(line);
}

export function updateConsoleConnected(connected) {
  // Input stays enabled so /connect and /help work while disconnected.
  els.consoleInput.disabled = false;
  els.consoleInput.placeholder = connected
    ? 'Send a message...'
    : 'Type /connect <address> or /help';
}

// ---- Input history (up/down) ----
const history = [];
let historyPos = 0;
let historyDraft = '';

function pushHistory(text) {
  if (history[history.length - 1] !== text) history.push(text);
  if (history.length > HISTORY_MAX) history.shift();
  historyPos = history.length;
  historyDraft = '';
}

function browseHistory(delta) {
  if (!history.length) return;
  if (historyPos === history.length) historyDraft = els.consoleInput.value;
  historyPos = Math.min(history.length, Math.max(0, historyPos + delta));
  els.consoleInput.value = historyPos === history.length ? historyDraft : history[historyPos];
}

let actions = {};

const commandCtx = {
  output: appendConsoleText,
  printJson: parts => appendConsoleHTML(printJsonToHTML(parts)),
  connect: address => {
    if (actions.connect && !actions.connect(address) && actions.status) appendConsoleText(actions.status());
  },
  disconnect: () => actions.disconnect?.(),
  hasAddress: () => !!actions.hasAddress?.(),
};

function sendConsoleMessage() {
  const msg = els.consoleInput.value.trim();
  if (!msg) return;
  els.consoleInput.value = '';
  pushHistory(msg);
  appendConsoleHTML(`<span style="color:var(--muted)">&gt; ${escapeHtml(msg)}</span>`);
  if (runCommand(msg, commandCtx)) return;
  if (state.connState !== 'connected') {
    appendConsoleText('Not connected. Use /connect <address> to connect.');
    return;
  }
  ap.sendSay(msg);
}

/** actions: {connect(address) -> bool, disconnect(), hasAddress() -> bool, status() -> string} */
export function initConsole(consoleActions = {}) {
  actions = consoleActions;
  ap.onPrintJSON = parts => {
    appendConsoleHTML(printJsonToHTML(parts));
  };
  els.consoleSendBtn.addEventListener('click', sendConsoleMessage);
  els.consoleInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') sendConsoleMessage();
    else if (e.key === 'ArrowUp') { e.preventDefault(); browseHistory(-1); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); browseHistory(1); }
  });
  updateConsoleConnected(state.connState === 'connected');
}
