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

const GROUPS_TITLE = 'Item Groups (Progressive, Random-Choice, Aesthetic)';

// v1.1 steps, each inserted after the legacy step with the given title.
const V11_STEPS = [
  ['Regions', [
    'Region Dependencies',
    "Each region row has a 'Depends on' field: an expression that gates every task in that "
    + 'region. It is added to each of the region\'s tasks on top of that task\'s own Task Prereqs, '
    + 'so none of them unlock until it is met.\n\n'
    + 'Only whole regions may be named:\n'
    + '  intro             intro\'s default % of its tasks done\n'
    + '  intro-75          75% of intro\'s tasks done\n'
    + '  intro*5           5 tasks in intro done\n'
    + 'Combine them with &&, || and parentheses: intro && (caves || cliffs).\n\n'
    + 'To gate the region on one specific task or item, wrap it in task( ... ) or item( ... ). '
    + 'Whatever goes inside the parentheses is an ordinary Task Prereq or Item Prereq '
    + 'expression:\n'
    + '  task(3)                   task 3 completed\n'
    + '  task("Do the dishes")     that named task completed\n'
    + '  task(1 || 2)              task 1 or task 2 completed\n'
    + '  task(caves-50)            region refs work inside task( ... ) too\n'
    + '  item(4)                   item 4 received\n'
    + '  item("Blue Key")          that named item received\n'
    + '  item(keys*3)              3 items from progressive group keys\n'
    + 'Mix the two freely with the rest of the expression: '
    + 'task(3) && (item("Blue Key") || caves-50).\n\n'
    + 'Inside task( ... ) you may use task numbers, quoted task names and region refs. '
    + 'Inside item( ... ) you may use item numbers, quoted item names and group counts '
    + '(keys*3). A progressive group must use count mode here, never ordering mode '
    + '(keys or keys-2), because an ordering position belongs to a single task. '
    + "'prev' and 'sequential' are never allowed in a region dependency. "
    + 'A consumable currency item cannot be named at all, since it is spent on task '
    + 'costs and so cannot stably gate a region.\n\n'
    + 'A region cannot depend on itself or on a task inside itself, the region it names must '
    + 'have at least one task assigned, and cycles between regions (a depends on b, b depends '
    + 'on a) are an error. Leave the field blank for a region with no gate.\n\n'
    + 'Renaming or removing a region that other regions depend on asks what to do with those '
    + 'expressions, the same as for Task Prereqs.',
  ]],
  ['Regions', [
    'Randomized Regions and Dependencies',
    'A randomized region keeps only some of its tasks in each seed, so references into it '
    + 'follow stricter rules.\n\n'
    + 'Allowed:\n'
    + '  chores            default % of the kept tasks done\n'
    + '  chores-75         75% of the kept tasks done\n'
    + '  chores*5          5 of the kept tasks done (at most the Keep value)\n'
    + 'Tasks inside a randomized region may depend on tasks in normal regions.\n\n'
    + 'Not allowed: referencing an individual task in or from inside a randomized region, by '
    + "number, quoted name, 'prev' or 'sequential'. Reference the region as a whole instead. "
    + "That includes a region dependency's task( ... ), and item( ... ) may not name an "
    + 'individual item inside a random-choice group.\n\n'
    + 'Goal Tasks may name individual tasks in a randomized region. Generation guarantees at least '
    + 'one way to meet the goal: with 4 || 10, at least one of tasks 4 and 10 is kept. Export '
    + 'fails if no way to meet the goal fits within the Keep values.\n\n'
    + 'Task numbers are renumbered in the final seed, so the numbers seen while playing differ '
    + 'from the generator.\n\n'
    + 'Shuffle order (per region, off by default): with it off, the kept tasks stay in the order '
    + 'they have in the task list. Check it to shuffle the order of that region\'s kept tasks in '
    + 'each seed. It only applies to regions with Randomize checked.',
  ]],
  [GROUPS_TITLE, [
    'Group Types, Keep and Default %',
    'Each group row has a Type:\n'
    + '  progressive     items are interchangeable; power-2 is the 2nd position, power*2 is any\n'
    + '                  2 items (the original behavior)\n'
    + '  random-choice   each seed keeps only some of the items; the rest are removed\n'
    + '  aesthetic       color and inventory grouping only\n'
    + 'Items in random-choice and aesthetic groups are normal, distinct items.\n\n'
    + 'Keep (random-choice only): N or N% of the items to keep per seed. Percent rounds up, with '
    + 'a minimum of 1. Blank keeps every item.\n\n'
    + 'Default %: the share of the group required by a bare group reference. Blank on a '
    + 'progressive group keeps the original behavior (fills the lowest unused position). Blank on '
    + 'other types means 100%.\n\n'
    + 'Item Prereqs for random-choice and aesthetic groups:\n'
    + '  gems              default % of the group\n'
    + '  gems-50           any 50% of the group\n'
    + '  gems*2            any 2 items from the group\n'
    + 'For random-choice groups these count only the kept items, and items inside the group '
    + 'cannot be referenced individually.\n\n'
    + 'Progressive group items are always Progression. Random-choice and aesthetic items are '
    + 'Progression only when an Item Prereq references them or their group.',
  ]],
  [GROUPS_TITLE, [
    'Group Colors and Renaming',
    'Each item group gets a color from the same palette as regions. Click the swatch on a '
    + "group's row to change it. In the client's Items tab, received items are grouped under their "
    + 'item group and marked with its color.\n\n'
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
    'Reordering Rows',
    'Use the ^ and v buttons next to a row number to move a task, item or region up or down.\n\n'
    + 'With "Reordering updates references" checked (in the bar at the top of the generator), '
    + 'numbered references follow the moved row: task numbers in Task Prereqs and Goal Tasks, and '
    + 'item numbers in Item Prereqs and Cost. Quoted names never need updating. Uncheck it to move '
    + 'rows without touching any expression.\n\n'
    + "'prev' always means the task directly above, so moving a task changes what 'prev' refers to.\n\n"
    + 'Regions are only ever referenced by name, so moving a region row just changes the order '
    + 'they are listed in.',
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
  ['DeathLink (Optional Challenge)', [
    'Slot Colors',
    'The Style section sets the colors this client uses while it is connected to the slot made '
    + 'from this YAML. Pick a color with the swatch or type a hex code; Default puts one row back, '
    + 'and Reset Colors puts them all back.\n\n'
    + 'Nothing changes until you connect: disconnecting restores the standard color scheme, and '
    + 'slots exported without color changes leave it alone. The Taskipelabingo tab has its own '
    + 'Style panel, including the two bingo board colors.',
  ]],
  ['DeathLink (Optional Challenge)', [
    'Clicker Mode (Tasclickpelago)',
    'Tick "Enable Tasclickpelago" in the bar at the top of the generator to turn this slot into an '
    + 'idle/clicker game. Nothing else changes: the same regions, item groups, prereqs, DeathLink '
    + 'and Style panels all still apply, and a slot stays a normal Taskipelago YAML until the '
    + 'toggle is on.\n\n'
    + 'The toggle adds columns to the tables you already have:\n'
    + '  Tasks   Activations - how many activations finish the task (blank means 1)\n'
    + '  Items   Grants, Target and Value - what an item does when you receive it\n'
    + '  Regions Distributed and Offline rate\n\n'
    + 'Activations come from clicking and from production granted by items. Grants can be:\n'
    + '  Production (/s)              activations per second\n'
    + '  Click power (+)              added to the value of one click\n'
    + '  Production multiplier (x)    scales production only\n'
    + '  Click multiplier (x)         scales clicks only\n'
    + '  Offline multiplier (x)       scales what accrues while you are away\n'
    + '  Unlock only (no effect)      grants nothing; use it as an Item Prereq\n'
    + 'The two multiplier channels never touch each other, and copies of a multiplier stack '
    + 'multiplicatively.\n\n'
    + 'Target applies to every kind but Unlock only, in the usual reference syntax: '
    + '* for every task, a bare region name, a quoted "Task Name" or a task number, joined with &&. '
    + 'Click power and both multipliers are per target too, so one item can be a slot-wide upgrade '
    + '(*) and another a boost for a single task or region. A task\'s click value is '
    + '(1 + the click power aimed at it) x the click multipliers aimed at it, and the board shows '
    + 'each card\'s own click value and rate. Nothing can be aimed at a manual task, which is an '
    + 'ordinary task: export refuses it.\n\n'
    + 'Distributed (per region) splits that region\'s rate evenly among its eligible tasks instead '
    + 'of giving each one the full rate, so the region\'s throughput stays constant as tasks '
    + 'complete. The Clicker section has the same switch for the whole slot, plus offline '
    + 'production: the away rate, the cap in hours and a worked example.',
  ]],
  ['DeathLink (Optional Challenge)', [
    'Clicker Values and Constants',
    'Every clicker number can be an expression instead of a plain number: integers, decimals, '
    + '+ - * / and parentheses over five constants:\n'
    + '  N_TASKS             total tasks in the slot (fixed when the seed is made)\n'
    + '  N_TASKS_UNLOCKED    tasks unlocked so far, including completed ones\n'
    + '  N_TASKS_LOCKED      N_TASKS - N_TASKS_UNLOCKED\n'
    + '  N_TASKS_COMPLETED   tasks completed so far\n'
    + '  CPS                 the current click value, after click power and the click multiplier\n\n'
    + 'The preview beside each cell shows the value at both ends of the curve, with CPS at its base '
    + 'value of 1. Examples: 0.1 * N_TASKS_UNLOCKED, 1 + 0.02 * N_TASKS, 0.25 * CPS.\n\n'
    + 'Two rules follow from when each value is decided. Activations are fixed when the seed is '
    + 'generated, so only N_TASKS is allowed there. CPS is the click value itself, so it cannot be '
    + 'used in Click power or Click multiplier, which are what define it; use it to price '
    + 'production in clicks instead.\n\n'
    + 'Curve Fill in the Clicker section writes the whole Activations column from a first cost and '
    + 'a growth factor, the usual idle-game pacing. The values stay editable afterwards.',
  ]],
  [null, [
    'While Playing: Hints and Item Filters',
    'The Hints tab lists every hint for your slot, like the Archipelago text client: who receives '
    + 'the item, who finds it, where, and its status. Click a column header to sort. For hints on '
    + 'items you receive, set the status to Priority, No Priority or Avoid. Use !hint <item> in the '
    + 'Text Console to request a hint.\n\n'
    + 'In the Items tab, Filter hides items by type (Progression, Useful, Junk, Trap, Filler, '
    + 'Consumable) and by item group. The last line shows how many received items are hidden.',
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
