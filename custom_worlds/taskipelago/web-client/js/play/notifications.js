import { ap, state, els, MAX_NOTIFICATIONS } from './state.js';
import { isFiller } from '../shared/filler.js';

export function enqueueNotification({ kind, title, body }) {
  state.notifications.push({ kind, title, body, createdAt: Date.now() });
  if (state.notifications.length > MAX_NOTIFICATIONS) {
    state.notifications = state.notifications.slice(-MAX_NOTIFICATIONS);
  }
  renderNotifications();
}

export function renderNotifications() {
  const frag = document.createDocumentFragment();
  const list = [...state.notifications].reverse();

  for (let i = 0; i < list.length; i++) {
    const realIdx = state.notifications.length - 1 - i;
    const n = list[i];

    const card = document.createElement('div');
    card.className = 'notif-card';

    const hdr = document.createElement('div');
    hdr.className = 'notif-header';

    const title = document.createElement('div');
    title.className = 'notif-title';
    title.textContent = n.title;
    hdr.appendChild(title);

    const dismissBtn = document.createElement('button');
    dismissBtn.className = 'notif-dismiss';
    dismissBtn.textContent = 'Dismiss';
    dismissBtn.onclick = () => {
      state.notifications.splice(realIdx, 1);
      renderNotifications();
    };
    hdr.appendChild(dismissBtn);
    card.appendChild(hdr);

    const meta = document.createElement('div');
    meta.className = 'notif-meta';
    const ts = new Date(n.createdAt).toLocaleTimeString();
    meta.textContent = `${n.kind.toUpperCase()} • ${ts}`;
    card.appendChild(meta);

    const body = document.createElement('div');
    body.className = 'notif-body';
    body.textContent = n.body;
    card.appendChild(body);

    frag.appendChild(card);
  }

  els.notifList.innerHTML = '';
  if (!list.length) {
    els.notifList.innerHTML = '<div style="padding:8px;color:var(--muted);font-size:12px">No notifications.</div>';
  } else {
    els.notifList.appendChild(frag);
  }
}

export function showItemNotification(it) {
  if (!it || typeof it.item !== 'number') return;

  // Skip completion tokens
  const baseToken = state.baseTokenId;
  const nTasks    = state.tasks.length;
  if (typeof baseToken === 'number' && nTasks > 0) {
    const off = it.item - baseToken;
    if (off >= 0 && off < nTasks) return;
  }

  // Resolve name
  const base = state.baseItemId;
  let name = null;
  if (typeof base === 'number') {
    const idx = it.item - base;
    if (idx >= 0 && idx < state.items.length && state.items[idx]) {
      name = state.items[idx];
    }
  }
  if (!name || !name.trim() || isFiller(name)) return;
  if (name.startsWith('Task Complete ')) return;

  // Sender
  let sender = '';
  if (it.player != null) sender = ap.resolvePlayerName(it.player);

  enqueueNotification({
    kind:  'reward',
    title: 'Reward Received!',
    body:  `${name.trim()}${sender ? `\n(from ${sender})` : ''}`,
  });
}

export function handleDeathLinkBounce(tags, data) {
  if (!tags.includes('DeathLink')) return;

  // Ignore self-sent bounces
  const ownSlot = (els.slotInput.value || '').trim() || 'Taskipelago';
  if ((data.source || '') === ownSlot) return;

  // Amnesty
  if (state.deathLinkAmnestyLeft > 0) {
    state.deathLinkAmnestyLeft--;
    return;
  }
  state.deathLinkAmnestyLeft = state.deathLinkAmnesty;

  const pool    = state.deathLinkPool;
  const weights = state.deathLinkWeights;

  let task;
  if (pool.length) {
    const w = pool.map((_, i) => Math.max(0, parseFloat(weights[i]) || 1));
    const total = w.reduce((a, b) => a + b, 0);
    if (total > 0) {
      let r = Math.random() * total;
      task = pool[pool.findIndex((_, i) => { r -= w[i]; return r <= 0; })];
    } else {
      task = pool[Math.floor(Math.random() * pool.length)];
    }
  } else {
    task = 'No pool entries configured. Make something up, I guess';
  }

  const source = data.source || 'Unknown';
  const cause  = data.cause  || '';
  enqueueNotification({
    kind:  'deathlink',
    title: 'DEATHLINK!',
    body:  `From: ${source}${cause ? '\n' + cause : ''}\n\nTask: ${task}`,
  });
}

export function initNotifications() {
  els.clearNotifsBtn.addEventListener('click', () => {
    state.notifications = [];
    renderNotifications();
  });
}
