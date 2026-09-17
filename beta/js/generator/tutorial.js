// YAML Generator tutorial (UNIFY 5.7): the legacy step text plus a step on the
// hosted page vs the launcher client. Shown as a non-blocking side panel, like
// the legacy Toplevel, so the generator stays usable while reading.
import { h } from '../shared/dom.js';
import { LEGACY_STEPS } from './legacy_text.js';

const HOSTED_VS_LAUNCHER = [
  'Hosted Page and Launcher Client',
  'The YAML Generator works the same on the hosted web page and in the client opened '
  + 'from the Archipelago Launcher.\n\n'
  + 'Your work in progress is saved automatically on this device, so closing the window '
  + 'does not lose it. Drafts are not shared between the hosted page and the launcher '
  + 'client, or between devices. Use Export YAML and Import YAML to move a design between them.\n\n'
  + 'Export YAML downloads the file through your browser. Import YAML opens a file picker.\n\n'
  + 'Playing: the hosted page can only connect to secure (wss://) servers such as '
  + 'archipelago.gg. For a local or LAN server (ws://), use the client opened from the '
  + 'Archipelago Launcher.',
];

// The web step goes before the closing "Export, Import, and Reset" summary.
export const STEPS = [...LEGACY_STEPS.slice(0, -1), HOSTED_VS_LAUNCHER, LEGACY_STEPS[LEGACY_STEPS.length - 1]];

let panel = null;

export function openTutorial() {
  if (panel) {
    panel.querySelector('.tutorial-next')?.focus();
    return;
  }
  let idx = 0;
  const title = h('div', { className: 'tutorial-title' });
  const counter = h('div', { className: 'tutorial-counter muted-text' });
  const text = h('div', { className: 'tutorial-text' });
  const prev = h('button', { type: 'button', onclick: () => show(idx - 1) }, '< Previous');
  const next = h('button', { type: 'button', className: 'tutorial-next primary' }, 'Next >');
  const close = () => {
    panel?.remove();
    panel = null;
  };
  panel = h('aside', { className: 'tutorial-panel', role: 'dialog', 'aria-label': 'YAML Generator Tutorial' },
    h('div', { className: 'tutorial-head' },
      h('div', {}, title, counter),
      h('button', { type: 'button', className: 'tutorial-x', 'aria-label': 'Close tutorial', onclick: close }, 'x')),
    text,
    h('div', { className: 'tutorial-btns' }, prev, h('span', { className: 'spacer' }), next,
      h('button', { type: 'button', onclick: close }, 'Close')));

  function show(i) {
    idx = i;
    const [t, body] = STEPS[i];
    title.textContent = t;
    counter.textContent = `Step ${i + 1} of ${STEPS.length}`;
    text.textContent = body;
    text.scrollTop = 0;
    prev.disabled = i === 0;
    const last = i === STEPS.length - 1;
    next.textContent = last ? 'Finish' : 'Next >';
    next.onclick = last ? close : () => show(idx + 1);
  }

  panel.addEventListener('keydown', e => {
    if (e.key === 'Escape') close();
  });
  document.body.appendChild(panel);
  show(0);
  next.focus();
}
