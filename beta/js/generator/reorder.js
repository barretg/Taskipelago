// v1.1 F10: up/down carets on task and item rows. The swap and reference
// update live in model.js moveRow; the toggle is taskipelago_ui.reorderUpdatesRefs.
import { h, scrollIntoViewAndFocus } from '../shared/dom.js';
import { getUiPref, setUiPref } from '../shared/ui_prefs.js';
import { moveRow } from './model.js';

const PREF = 'reorderUpdatesRefs';
export const reorderUpdatesRefs = () => getUiPref(PREF, true) !== false;
export const setReorderUpdatesRefs = on => setUiPref(PREF, !!on);

const ROW_SELECTOR = { tasks: '.gt-task', items: '.gt-item' };

function move(ctx, kind, i, dir, container) {
  const j = i + dir;
  const refs = reorderUpdatesRefs();
  if (!moveRow(ctx.model, kind, i, j, refs)) return;
  // Items can be referenced from task rows; tasks from goal tasks.
  ctx.changed({ tasks: true, items: kind === 'items', goal: kind === 'tasks' });
  const row = container.querySelectorAll(ROW_SELECTOR[kind])[j];
  const carets = row?.querySelectorAll('.caret-btn') || [];
  const same = carets[dir < 0 ? 0 : 1];
  scrollIntoViewAndFocus(same && !same.disabled ? same : carets[dir < 0 ? 1 : 0]);
}

/** The "#" cell content: up caret, down caret, row number. */
export function rowNumberCell(ctx, kind, i, container) {
  const count = ctx.model[kind].length;
  const what = kind === 'tasks' ? 'task' : 'item';
  const tip = kind === 'tasks'
    ? ' Moving a task changes which task "prev" refers to.'
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
