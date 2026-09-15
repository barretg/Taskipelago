import { ap, state, els } from '../play/state.js';
import { escapeHtml } from '../shared/dom.js';

const AP_COLORS = {
  red:       '#cc4444', green:    '#55aa55', yellow: '#aaaa44',
  blue:      '#5588cc', magenta:  '#aa55aa', cyan:   '#44aaaa',
  white:     '#cccccc', black:    '#555555', slateblue: '#6d8be8',
  plum:      '#af99ef', salmon:   '#fa8072',
};

function resolveItemName(id) {
  if (state.baseItemId !== null) {
    const idx = id - state.baseItemId;
    if (idx >= 0 && idx < state.items.length) return state.items[idx];
  }
  if (state.baseTokenId !== null) {
    const idx = id - state.baseTokenId;
    if (idx >= 0 && idx < state.tasks.length) return `${state.tasks[idx]} Token`;
  }
  return String(id);
}

function resolveLocationName(id) {
  if (state.baseCompleteId !== null) {
    const idx = id - state.baseCompleteId;
    if (idx >= 0 && idx < state.tasks.length) return state.tasks[idx];
  }
  if (state.baseRewardId !== null) {
    const idx = id - state.baseRewardId;
    if (idx >= 0 && idx < state.tasks.length) return `${state.tasks[idx]} Reward`;
  }
  return String(id);
}

function printJsonToHTML(parts, senderSlot) {
  let html = '';
  for (const part of parts) {
    const type = part.type || 'text';

    let displayText = part.text || '';
    if (type === 'player_id') {
      const slot = parseInt(displayText);
      displayText = ap.resolvePlayerName(slot) || displayText;
    } else if (type === 'item_id') {
      displayText = resolveItemName(parseInt(displayText));
    } else if (type === 'location_id') {
      displayText = resolveLocationName(parseInt(displayText));
    }

    const text = escapeHtml(displayText);

    let color = null;
    let bold  = false;

    if (type === 'player_id' || type === 'player_name') {
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

function appendConsoleHTML(html) {
  const line = document.createElement('div');
  line.innerHTML = html;
  els.consoleOutput.appendChild(line);
  els.consoleOutput.scrollTop = els.consoleOutput.scrollHeight;
}

export function updateConsoleConnected(connected) {
  els.consoleInput.disabled = !connected;
  if (!connected) {
    els.consoleInput.placeholder = 'Must be connected to a multiworld';
    els.consoleInput.value = '';
  } else {
    els.consoleInput.placeholder = 'Send a message...';
  }
}

function sendConsoleMessage() {
  if (state.connState !== 'connected') return;
  const msg = els.consoleInput.value.trim();
  if (!msg) return;
  els.consoleInput.value = '';
  appendConsoleHTML(`<span style="color:var(--muted)">&gt; ${escapeHtml(msg)}</span>`);
  ap.sendSay(msg);
}

export function initConsole() {
  ap.onPrintJSON = (parts, msgType, senderSlot) => {
    appendConsoleHTML(printJsonToHTML(parts, senderSlot));
  };
  els.consoleSendBtn.addEventListener('click', sendConsoleMessage);
  els.consoleInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') sendConsoleMessage();
  });
}
