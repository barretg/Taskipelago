// Task table (legacy TaskRow, client.py:951-1091, headers 2068-2175).
import { h } from '../shared/dom.js';
import { openDialog } from '../shared/dialog.js';
import { pyStrip } from '../shared/pyish.js';
import { tipHeader } from '../shared/tooltip.js';
import { MAX_TASK_DESCRIPTION_LEN, newTask } from './model.js';
import { TIPS } from './legacy_text.js';
import { rowNumberCell } from './reorder.js';

/** Code-point length and truncation for the description editor. */
const cpLen = s => Array.from(s).length;
const cpCut = (s, n) => Array.from(s).slice(0, n).join('');

function editDescription(task, onDone) {
  const area = h('textarea', { className: 'desc-editor', rows: 4, value: task.desc });
  const counter = h('div', { className: 'desc-counter muted-text' });
  const update = () => {
    if (cpLen(area.value) > MAX_TASK_DESCRIPTION_LEN) area.value = cpCut(area.value, MAX_TASK_DESCRIPTION_LEN);
    counter.textContent = `${cpLen(area.value)}/${MAX_TASK_DESCRIPTION_LEN}`;
  };
  area.addEventListener('input', update);
  update();
  const dlg = openDialog({
    title: 'Task Description',
    text: `Optional flavor text shown under the task name in-game (max ${MAX_TASK_DESCRIPTION_LEN} chars):`,
    body: h('div', {}, area, counter),
    buttons: [
      {
        label: 'OK', primary: true,
        onClick: close => {
          task.desc = cpCut(pyStrip(area.value), MAX_TASK_DESCRIPTION_LEN);
          onDone();
          close(true);
        },
      },
      { label: 'Cancel', value: false },
    ],
  });
  area.focus();
  return dlg.result;
}

const cell = (...children) => h('div', { className: 'gt-cell' }, ...children);

function textInput(obj, key, ctx, field) {
  return h('input', {
    type: 'text', value: obj[key], spellcheck: false, dataset: { field },
    oninput: e => { obj[key] = e.target.value; ctx.changed(); },
  });
}

function countInput(obj, ctx, max = 999) {
  return h('input', {
    type: 'number', min: 1, max, step: 1, value: obj.count, className: 'count-input',
    oninput: e => { obj.count = e.target.value; ctx.changed({ counter: true }); },
  });
}

export function renderTaskTable(container, ctx) {
  const { model } = ctx;
  container.replaceChildren(
    h('div', { className: 'gt-row gt-head' },
      cell('#'), cell('Task'),
      cell(tipHeader('Task prereqs', TIPS.task_prereq)),
      cell(tipHeader('Item prereqs', TIPS.item_prereq)),
      cell(tipHeader('Cost', TIPS.cost_col)),
      cell(tipHeader('Region', TIPS.region_col)),
      cell(tipHeader('Prio', TIPS.priority_col)),
      cell(tipHeader('Count', TIPS.count_task)),
      cell('')),
    h('div', { className: 'gt-row gt-hint muted-text' },
      cell(''), cell('Location'), cell('1  or  "Task Name"  or  region'),
      cell('1  or  "Item Name"'), cell('"ItemName"*N'), cell(''), cell(''), cell(''), cell('')),
  );

  model.tasks.forEach((task, i) => {
    const descBtn = h('button', { type: 'button', className: 'desc-btn', dataset: { field: `tasks.${i}.desc` } });
    const refreshDesc = () => { descBtn.textContent = pyStrip(task.desc) ? 'Description*' : 'Description'; };
    refreshDesc();
    descBtn.onclick = () => editDescription(task, () => { refreshDesc(); ctx.changed(); });

    const region = h('select', {
      onchange: e => { task.region = e.target.value; ctx.changed(); },
    }, h('option', { value: '' }, ''), model.regions.map(r => h('option', { value: r.name }, r.name)));
    region.value = task.region;

    container.appendChild(h('div', { className: 'gt-row gt-task' },
      cell(rowNumberCell(ctx, 'tasks', i, container)),
      cell(h('div', { className: 'task-name-cell' }, textInput(task, 'name', ctx, `tasks.${i}.name`), descBtn)),
      cell(textInput(task, 'prereq', ctx, `tasks.${i}.prereq`)),
      cell(textInput(task, 'itemPrereq', ctx, `tasks.${i}.itemPrereq`)),
      cell(textInput(task, 'cost', ctx, `tasks.${i}.cost`)),
      cell(region),
      cell(h('input', {
        type: 'checkbox', checked: !!task.priority, 'aria-label': 'Priority',
        onchange: e => { task.priority = e.target.checked; ctx.changed(); },
      })),
      cell(countInput(task, ctx)),
      cell(h('button', {
        type: 'button', className: 'remove-btn',
        onclick: () => { model.tasks.splice(i, 1); ctx.changed({ tasks: true, counter: true }); },
      }, 'Remove'))));
  });
}

export function addTask(ctx) {
  ctx.model.tasks.push(newTask());
  ctx.changed({ tasks: true, counter: true, focusLast: 'tasks' });
}
