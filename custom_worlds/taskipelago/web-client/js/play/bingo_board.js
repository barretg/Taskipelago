import { ap, state, els } from './state.js';
import { allChecked, receivedItemIds, bingoLines, completeTask } from './logic.js';
import { isDeathLinkLocked } from './deathlink_queue.js';

export function renderBingo() {
  const X = state.bingoDimX;
  const Y = state.bingoDimY;
  const nSpaces = X * Y;

  if (state.tasks.length < nSpaces) {
    els.bingoGrid.innerHTML = '<div style="color:var(--muted);padding:8px">Waiting for task data...</div>';
    return;
  }

  els.bingoGrid.style.gridTemplateColumns = `repeat(${X}, 1fr)`;

  const checked   = allChecked();
  const received  = receivedItemIds();
  const base      = state.baseCompleteId;
  const baseItem  = state.baseItemId;
  const baseRew   = state.baseRewardId;

  const middle    = Math.floor(nSpaces / 2);
  const spDone    = Array.from({length: nSpaces}, (_, i) => checked.has(base + i));
  const spUnlocked = Array.from({length: nSpaces}, (_, i) =>
    (typeof baseItem === 'number' && received.has(baseItem + i)) || i === middle
  );

  const lines      = bingoLines(X, Y);
  const lineDone   = lines.map(line => line.every(s => spDone[s]));
  const nBingos    = lineDone.filter(Boolean).length;
  const needed     = Math.max(0, state.bingoal - nBingos);
  els.bingoCounter.textContent = `${nBingos} of ${lines.length} bingos complete (need ${needed} more)`;

  const inBingo = new Array(nSpaces).fill(false);
  lines.forEach((line, li) => {
    if (lineDone[li]) line.forEach(s => { inBingo[s] = true; });
  });

  // Auto-complete bingo lines
  lines.forEach((line, li) => {
    if (!lineDone[li]) return;
    const lineTaskIdx  = nSpaces + li;
    const lineCplId    = base + lineTaskIdx;
    const lineRewId    = baseRew + lineTaskIdx;
    if (!checked.has(lineCplId) && !state.pendingLocations.has(lineCplId)) {
      state.pendingLocations.add(lineCplId);
      ap.sendLocationChecks([lineCplId, lineRewId]);
    }
  });

  const frag = document.createDocumentFragment();
  for (let i = 0; i < nSpaces; i++) {
    const cell = document.createElement('div');
    cell.className = 'bingo-cell' +
      (inBingo[i] ? ' has-bingo' : spDone[i] ? ' is-done' : '');

    const txt = document.createElement('div');
    txt.className = 'cell-text';

    if (!spUnlocked[i]) {
      txt.textContent = 'Locked';
      txt.style.color = 'var(--muted)';
    } else if (spDone[i]) {
      txt.textContent = `✔ ${state.tasks[i]}`;
      txt.style.color = 'var(--muted)';
    } else {
      txt.textContent = state.tasks[i];
    }

    cell.appendChild(txt);

    if (spUnlocked[i] && !spDone[i]) {
      const btn = document.createElement('button');
      btn.textContent = 'Complete';
      btn.disabled = isDeathLinkLocked(); // F3
      btn.onclick = () => completeTask(i);
      cell.appendChild(btn);
    }

    frag.appendChild(cell);
  }

  els.bingoGrid.innerHTML = '';
  els.bingoGrid.appendChild(frag);
}
