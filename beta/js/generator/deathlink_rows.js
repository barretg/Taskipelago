// DeathLink task pool (legacy DeathLinkRow, client.py:1263-1291, 2315-2348).
import { h } from '../shared/dom.js';
import { newDeathLink } from './model.js';

export function renderDeathLinkTable(container, ctx) {
  const { model } = ctx;
  container.replaceChildren(
    h('div', { className: 'dl-row gt-head' }, h('span', {}, 'DeathLink Task'), h('span', {}, 'Weight'), h('span', {})),
    ...model.deathLink.map((row, i) => h('div', { className: 'dl-row' },
      h('input', {
        type: 'text', value: row.text, spellcheck: false, 'aria-label': 'DeathLink task',
        oninput: e => { row.text = e.target.value; ctx.changed(); },
      }),
      h('input', {
        type: 'text', value: row.weight, className: 'weight-input', 'aria-label': 'Weight',
        oninput: e => { row.weight = e.target.value; ctx.changed(); },
      }),
      h('button', {
        type: 'button', className: 'remove-btn',
        onclick: () => { model.deathLink.splice(i, 1); ctx.changed({ deathlink: true }); },
      }, 'Remove'))),
  );
}

export function addDeathLink(ctx) {
  ctx.model.deathLink.push(newDeathLink());
  ctx.changed({ deathlink: true, focusLast: 'deathlink' });
}
