// v1.1 F10: up/down carets on task, item and region rows. The swap and reference
// update live in model.js moveRow; the toggle is taskipelago_ui.reorderUpdatesRefs.
import { h, scrollIntoViewAndFocus } from '../shared/dom.js';
import { getUiPref, setUiPref } from '../shared/ui_prefs.js';
import { moveRow } from './model.js';

const PREF = 'reorderUpdatesRefs';
export const reorderUpdatesRefs = () => getUiPref(PREF, true) !== false;
export const setReorderUpdatesRefs = on => setUiPref(PREF, !!on);

const ROW_SELECTOR = { tasks: '.gt-task', items: '.gt-item', regions: '.region-row:not(.region-head)' };
const ROW_WHAT = { tasks: 'task', items: 'item', regions: 'region' };

function move(ctx, kind, i, dir, container) {
  const j = i + dir;
  const refs = reorderUpdatesRefs();
  if (!moveRow(ctx.model, kind, i, j, refs)) return;
  // Items can be referenced from task rows; tasks from goal tasks. Region rows
  // only move, but the task table's Region column follows their order.
  ctx.changed({
    tasks: true, items: kind === 'items', goal: kind === 'tasks', regions: kind === 'regions',
  });
  const row = container.querySelectorAll(ROW_SELECTOR[kind])[j];
  const carets = row?.querySelectorAll('.caret-btn') || [];
  const same = carets[dir < 0 ? 0 : 1];
  scrollIntoViewAndFocus(same && !same.disabled ? same : carets[dir < 0 ? 1 : 0]);
}

/** The "#" cell content: up caret, down caret, row number. */
export function rowNumberCell(ctx, kind, i, container) {
  const count = ctx.model[kind].length;
  const what = ROW_WHAT[kind];
  const tip = kind === 'tasks'
    ? ' Moving a task changes which task "prev" refers to.'
    : kind === 'regions'
      ? ' Regions are referenced by name, so this only changes their order.'
      : '';
  const caret = (label, dir, disabled) => h('button', {
    type: 'button', className: 'caret-btn', disabled, 'aria-label': `Move ${what} ${i + 1} ${label}`,
    title: `Move this ${what} ${label}.${tip}`,
    onclick: () => move(ctx, kind, i, dir, container),
  }, dir < 0 ? '^' : 'v');
  return h('div', { className: 'row-num-cell' },
    caret('up', -1, i === 0), caret('down', 1, i === count - 1),
    h('span', { className: 'row-num' }, String(i + 1)));
}
