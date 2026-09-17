// YAML Generator tutorial (UNIFY 5.7): the legacy step text plus a step on the
// hosted page vs the launcher client and the v1.1 feature steps. Shown as a non-blocking side panel, like
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
  + 'Playing: the hosted page connects to secure (wss://) servers such as archipelago.gg. '
  + 'Insecure (ws://) servers, such as most local or LAN servers, only work there if you allow '
  + 'insecure content for the site in your browser settings. Otherwise use the client opened '
  + 'from the Archipelago Launcher.',
];

// v1.1 steps, each inserted after the legacy step with the given title.
const V11_STEPS = [
  ['Progressive Groups', [
    'Group Colors and Renaming',
    'Each progressive group gets a color from the same palette as regions. Click the swatch on a '
    + "group's row to change it. In the client's Items tab, received items are grouped under their "
    + 'progressive group and marked with its color.\n\n'
    + 'Region and group names can be edited inline. Names must start with a letter or underscore and '
    + 'cannot contain digits, spaces, quotes, parentheses, commas, && or ||.\n\n'
    + 'When you rename a region or group that expressions already use (Task Prereqs, Item Prereqs, '
    + 'region "Depends on" or Goal Tasks), you are asked what to do:\n'
    + '  Update        rename and rewrite every reference, keeping -N and *N suffixes\n'
    + '  Rename only   rename without touching the expressions\n'
    + '  Cancel        keep the old name\n\n'
    + 'Removing a region or group that is still referenced asks first, because those expressions '
    + 'will fail to export.',
  ]],
  ['Item Count and Item Settings', [
    'Reordering Tasks and Items',
    'Use the ^ and v buttons next to a row number to move a task or item up or down.\n\n'
    + 'With "Reordering updates references" checked (in the bar at the top of the generator), '
    + 'numbered references follow the moved row: task numbers in Task Prereqs and Goal Tasks, and '
    + 'item numbers in Item Prereqs and Cost. Quoted names never need updating. Uncheck it to move '
    + 'rows without touching any expression.\n\n'
    + "'prev' always means the task directly above, so moving a task changes what 'prev' refers to.",
  ]],
  ['Item Count and Item Settings', [
    'Find and Replace',
    'Click Find/Replace at the top of the generator, or press Ctrl+F (find) or Ctrl+H (replace) '
    + 'while the YAML Generator tab is open.\n\n'
    + 'Choose which fields to search (task names, descriptions, prereqs, costs, item names, DeathLink '
    + 'tasks, region dependencies and goal tasks), and optionally Match case or Whole word.\n\n'
    + 'Find Next and Find Previous jump to each match, opening collapsed sections as needed. Replace '
    + 'changes the current match; Replace All asks before changing every match. Filler items are '
    + 'never searched.\n\n'
    + 'Renaming a task or item this way does not update "Quoted" references unless the prereq and '
    + 'cost fields are included in the search.',
  ]],
  ['DeathLink (Optional Challenge)', [
    'DeathLink Task Cards and Lock',
    'Each DeathLink that gets past amnesty adds a red DeathLink task card to the top of the task '
    + 'list (or above the bingo board). Click Complete on the card when you have done it. Cards are '
    + 'saved on your device and shared with every client connected to your slot, so they survive '
    + 'closing the client.\n\n'
    + 'Check "Lock other tasks until DeathLink tasks are done" to make pending cards block everything '
    + 'else: other tasks, purchases and consumable adjustments are disabled until every card is '
    + 'completed. The same checkbox is on the Taskipelabingo tab.\n\n'
    + 'The client also highlights DeathLink notifications in red and can play a short sound '
    + '("Sound on DeathLink" in the Notifications tab).',
  ]],
  [null, [
    'While Playing: Hints and Item Filters',
    'The Hints tab lists every hint for your slot, like the Archipelago text client: who receives '
    + 'the item, who finds it, where, and its status. Click a column header to sort. For hints on '
    + 'items you receive, set the status to Priority, No Priority or Avoid. Use !hint <item> in the '
    + 'Text Console to request a hint.\n\n'
    + 'In the Items tab, Filter hides items by type (Progression, Useful, Junk, Trap, Filler, '
    + 'Consumable) and by progressive group. The last line shows how many received items are hidden.',
  ]],
];

function withV11Steps(steps) {
  const out = [...steps];
  for (const [after, step] of V11_STEPS) {
    if (!after) continue;
    // Insert after the last step already placed behind `after`, so order in V11_STEPS is kept.
    let i = out.findIndex(s => s[0] === after);
    while (i + 1 < out.length && V11_STEPS.some(([a, s]) => a === after && s === out[i + 1])) i++;
    out.splice(i + 1, 0, step);
  }
  return out;
}

const PLAYING_STEP = V11_STEPS.find(([after]) => after === null)[1];

// The web steps go before the closing "Export, Import, and Reset" summary.
const BODY = withV11Steps(LEGACY_STEPS.slice(0, -1));
export const STEPS = [...BODY, PLAYING_STEP, HOSTED_VS_LAUNCHER, LEGACY_STEPS[LEGACY_STEPS.length - 1]];

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
