// Item table (legacy ItemRow, client.py:1094-1260, headers 2237-2313). The
// enable/disable rules live in model.js so they match the Tk variable traces.
import { h } from '../shared/dom.js';
import { tipHeader } from '../shared/tooltip.js';
import { TIPS } from './legacy_text.js';
import {
  REWARD_TYPE_VALUES, newItem, onConsumableToggle, onFillerToggle, setItemProgGroup,
} from './model.js';

const cell = (...children) => h('div', { className: 'gt-cell' }, ...children);

function itemRow(it, i, ctx) {
  const { model } = ctx;
  const name = h('input', {
    type: 'text', spellcheck: false,
    oninput: e => { it.name = e.target.value; ctx.changed(); },
  });
  const type = h('select', { onchange: e => { it.type = e.target.value; ctx.changed(); } });
  const filler = h('input', { type: 'checkbox', 'aria-label': 'Filler' });
  const consumable = h('input', { type: 'checkbox', 'aria-label': 'Consumable' });
  const group = h('select', {});

  const sync = () => {
    name.value = it.name;
    name.disabled = it.ui.nameDisabled;
    const types = REWARD_TYPE_VALUES.includes(it.type) ? REWARD_TYPE_VALUES : [...REWARD_TYPE_VALUES, it.type];
    type.replaceChildren(...types.map(t => h('option', { value: t }, t)));
    type.value = it.type;
    type.disabled = it.ui.typeDisabled;
    filler.checked = !!it.filler;
    filler.disabled = it.ui.fillerDisabled;
    consumable.checked = !!it.consumable;
    consumable.disabled = it.ui.consumableDisabled;
    group.replaceChildren(h('option', { value: '' }, ''), ...model.progGroups.map(g => h('option', { value: g }, g)));
    group.value = it.progGroup;
    group.disabled = it.ui.groupDisabled;
  };

  filler.addEventListener('change', () => {
    it.filler = filler.checked;
    onFillerToggle(it);
    sync();
    ctx.changed();
  });
  consumable.addEventListener('change', () => {
    it.consumable = consumable.checked;
    onConsumableToggle(it);
    sync();
    ctx.changed();
  });
  group.addEventListener('change', () => {
    setItemProgGroup(it, group.value);
    sync();
    ctx.changed();
  });
  sync();

  return h('div', { className: 'gt-row gt-item' },
    cell(h('span', { className: 'row-num' }, String(i + 1))),
    cell(name), cell(type),
    cell(h('label', { className: 'check-label' }, filler, 'Filler')),
    cell(h('label', { className: 'check-label' }, consumable, 'Consumable')),
    cell(group),
    cell(h('input', {
      type: 'number', min: 1, max: 999, step: 1, value: it.count, className: 'count-input',
      oninput: e => { it.count = e.target.value; ctx.changed({ counter: true }); },
    })),
    cell(h('button', {
      type: 'button', className: 'remove-btn',
      onclick: () => { model.items.splice(i, 1); ctx.changed({ items: true, counter: true }); },
    }, 'Remove')));
}

export function renderItemTable(container, ctx) {
  container.replaceChildren(
    h('div', { className: 'gt-row gt-head' },
      cell('#'), cell('Item'),
      cell(tipHeader('Type', TIPS.type)),
      cell(tipHeader('Filler', TIPS.filler)),
      cell(tipHeader('Consumable', TIPS.consumable)),
      cell(tipHeader('Prog. Group', TIPS.prog_group)),
      cell(tipHeader('Count', TIPS.count_item)),
      cell('')),
    h('div', { className: 'gt-row gt-hint muted-text' },
      cell(''), cell('Multiworld item name (blank = filler)'), cell(''), cell(''), cell(''), cell(''), cell(''), cell('')),
    ...ctx.model.items.map((it, i) => itemRow(it, i, ctx)),
  );
}

export function addItem(ctx) {
  ctx.model.items.push(newItem());
  ctx.changed({ items: true, counter: true, focusLast: 'items' });
}
