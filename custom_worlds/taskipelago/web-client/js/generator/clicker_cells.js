// The clicker-only cells the shared task, item and region tables grow when
// clicker mode is on. Kept apart from the row files so those stay readable and
// the normal generator keeps working with clicker mode off.
import { h } from '../shared/dom.js';
import { tipHeader } from '../shared/tooltip.js';
import { KIND_LABELS, TARGETED_KINDS, UPGRADE_KINDS, previewValue } from './clicker_fields.js';
import { rowCount } from './model.js';

export const TIPS = {
  activations: 'Activations needed to finish this task. Blank means 1.\n\n'
    + 'Accepts a number or an expression over N_TASKS. The other constants are live values, so '
    + 'they are not allowed here: the requirement is fixed when the seed is generated.',
  grants: 'What this item does when you receive it.\n\n'
    + 'Production adds activations per second. Click power adds to the value of one click. The two '
    + 'multiplier channels are separate: a production multiplier never touches clicks and a click '
    + 'multiplier never touches production. Copies of a multiplier stack multiplicatively.\n\n'
    + 'Every kind but Unlock only applies to its Target, so the same item can be a general upgrade '
    + '(*) or a boost for one task or region.\n\n'
    + 'Unlock only grants nothing, for an item that exists purely to be named in a task\'s item '
    + 'prereqs.',
  target: 'Who the value applies to, in the usual Taskipelago reference syntax:\n'
    + '  *              ->  every clicker task\n'
    + '  myregion       ->  every task in that region\n'
    + '  "Task Name"    ->  one task, by quoted name\n'
    + '  3              ->  one task, by 1-based number\n\n'
    + 'Join several with &&. Every kind but Unlock only takes a target, so click power and both '
    + 'multipliers can be aimed at one task or one region instead of the whole slot. A task\'s '
    + 'click value is (1 + the click power aimed at it) x the click multipliers aimed at it.\n\n'
    + 'A manual task is not a clicker task, so nothing may be aimed at it: exporting refuses a '
    + 'target that names a manual task, or a region in which every task is manual. A region that '
    + 'still has clicker tasks is fine; the manual ones inside it are skipped.',
  value: 'A number or an expression over N_TASKS, N_TASKS_UNLOCKED, N_TASKS_LOCKED, '
    + 'N_TASKS_COMPLETED and CPS (the current click value). CPS cannot be used in a click '
    + 'field, since that is what defines it. In a production rate CPS is the click value of the '
    + 'task the rate is aimed at. The preview shows the value at both ends of the '
    + 'curve, with CPS at its base value of 1.',
  manual: 'On: this task is a normal Taskipelago task even in clicker mode. It is never clickable, never receives production, and the client shows it with a Complete button below the clicker cards.\n\n'
    + 'A task is also manual when its region is marked manual.',
  autoComplete: 'On: this task completes itself the moment it reaches its activations.\n\n'
    + 'Off (the default): a full task stops accruing and waits for you to press its Complete button.',
  regionManual: 'On: every task in this region is a normal (non-clicker) task, as if each were marked Manual in the task table.',
  distributed: 'Off: the rate applies in full to each eligible task in the region.\n\n'
    + 'On: the rate is split evenly among them, so the region\'s total throughput stays constant '
    + 'and each share rises as siblings complete.',
  offlineRate: 'The fraction of live production that accrues while away, for tasks in this region. '
    + 'Blank inherits the global away rate.',
};

/** Live task count, for the expression previews. Counts expand with Count > 1. */
export function taskTotal(model) {
  return model.tasks.reduce((n, t) => n + (t.name.trim() ? rowCount(t.count) : 0), 0);
}

/**
 * A numeric input plus a preview of both ends of the curve, so an expression
 * like `0.1 * N_TASKS_UNLOCKED` is not opaque before export.
 */
export function exprInput(obj, key, ctx, field, placeholder = '') {
  const input = h('input', {
    type: 'text', value: obj[key] ?? '', spellcheck: false, placeholder, dataset: { field },
  });
  const preview = h('span', { className: 'clicker-preview' });
  const refresh = () => {
    const r = previewValue(input.value, taskTotal(ctx.model));
    if (r.blank) preview.textContent = '';
    else if (!r.ok) preview.textContent = r.error;
    else preview.textContent = r.low === r.high ? `= ${r.low}` : `${r.low} -> ${r.high}`;
    preview.classList.toggle('warning-text', !r.ok);
  };
  input.addEventListener('input', () => {
    obj[key] = input.value;
    refresh();
    ctx.changed();
  });
  refresh();
  return h('div', { className: 'clicker-expr' }, input, preview);
}

/** Header cells appended to the task table in clicker mode. */
export const taskHeadCells = () => [
  tipHeader('Activations', TIPS.activations), tipHeader('Manual', TIPS.manual),
  tipHeader('Auto', TIPS.autoComplete),
];

/** Body cells appended to a task row in clicker mode. */
export function taskCells(task, i, ctx) {
  const activations = exprInput(task, 'activations', ctx, `tasks.${i}.activations`, '1');
  const manual = h('input', {
    type: 'checkbox', 'aria-label': 'Manual task',
    dataset: { field: `tasks.${i}.manual` },
    onchange: e => {
      task.manual = e.target.checked;
      // A manual task never accrues, so its activations and auto-complete are moot.
      activations.querySelector('input').disabled = e.target.checked;
      auto.disabled = e.target.checked;
      ctx.changed();
    },
  });
  const auto = h('input', {
    type: 'checkbox', 'aria-label': 'Auto-complete',
    dataset: { field: `tasks.${i}.autoComplete` },
    onchange: e => { task.autoComplete = e.target.checked; ctx.changed(); },
  });
  manual.checked = !!task.manual;
  auto.checked = !!task.autoComplete;
  activations.querySelector('input').disabled = !!task.manual;
  auto.disabled = !!task.manual;
  return [activations, manual, auto];
}

/** Header cells appended to the item table in clicker mode. */
export const itemHeadCells = () => [
  tipHeader('Grants', TIPS.grants), tipHeader('Target', TIPS.target), tipHeader('Value', TIPS.value),
];

/** Body cells appended to an item row in clicker mode. */
export function itemCells(it, i, ctx) {
  const kind = h('select', {},
    UPGRADE_KINDS.map(k => h('option', { value: k }, KIND_LABELS[k])));
  kind.value = UPGRADE_KINDS.includes(it.clickerKind) ? it.clickerKind : 'none';
  const target = h('input', {
    type: 'text', value: it.clickerTarget ?? '*', spellcheck: false, placeholder: '*',
    dataset: { field: `items.${i}.clickerTarget` },
    oninput: e => { it.clickerTarget = e.target.value; ctx.changed(); },
  });
  const value = exprInput(it, 'clickerValue', ctx, `items.${i}.clickerValue`, '1');

  // A filler row has no item to grant anything, and 'Unlock only' grants
  // nothing, so neither has a target or a value to set.
  const sync = () => {
    const off = !!it.filler || !it.name;
    kind.disabled = off;
    target.disabled = off || !TARGETED_KINDS.has(kind.value);
    value.querySelector('input').disabled = off || kind.value === 'none';
  };
  kind.addEventListener('change', () => {
    it.clickerKind = kind.value;
    sync();
    ctx.changed();
  });
  sync();
  return [kind, target, value];
}

/** The region controls appended to a region row in clicker mode. */
export function regionCells(region, ctx) {
  const distributed = h('input', {
    type: 'checkbox', 'aria-label': 'Distributed production',
    onchange: e => { region.distributed = e.target.checked; ctx.changed(); },
  });
  distributed.checked = !!region.distributed;
  const rate = h('input', {
    type: 'text', className: 'region-offline', value: region.offlineRate ?? '',
    spellcheck: false, placeholder: 'inherit', 'aria-label': 'Offline rate',
    oninput: e => { region.offlineRate = e.target.value; ctx.changed(); },
  });
  const manual = h('input', {
    type: 'checkbox', 'aria-label': 'Manual region',
    onchange: e => { region.manual = e.target.checked; ctx.changed(); },
  });
  manual.checked = !!region.manual;
  return [
    h('label', { className: 'check-label' }, distributed, tipHeader('Distributed', TIPS.distributed)),
    h('label', { className: 'check-label' }, manual, tipHeader('Manual', TIPS.regionManual)),
    h('label', { className: 'inline-label' }, tipHeader('Offline rate:', TIPS.offlineRate), rate),
  ];
}
