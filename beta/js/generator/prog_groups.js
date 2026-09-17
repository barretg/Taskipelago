// Progressive Groups panel (legacy client.py:2210-2235, 2568-2616).
import { h } from '../shared/dom.js';
import { alertDialog } from '../shared/dialog.js';
import { tipMarker } from '../shared/tooltip.js';
import { TIPS } from './legacy_text.js';
import { addProgGroup, removeProgGroup } from './model.js';

export function renderProgGroups(container, ctx) {
  const { model } = ctx;
  if (!model.progGroups.length) {
    container.replaceChildren(h('span', { className: 'muted-text' }, 'No groups defined.'));
    return;
  }
  container.replaceChildren(...model.progGroups.map(g => h('span', { className: 'chip' },
    h('span', {}, g),
    h('button', {
      type: 'button', className: 'chip-x', 'aria-label': `Remove group ${g}`,
      onclick: () => { removeProgGroup(model, g); ctx.changed({ groups: true, items: true }); },
    }, 'x'))));
}

export function buildGroupAddRow(ctx) {
  const name = h('input', { type: 'text', spellcheck: false, className: 'region-name' });
  const add = async () => {
    const error = addProgGroup(ctx.model, name.value);
    if (error) {
      await alertDialog('error', ...error);
      return;
    }
    name.value = '';
    ctx.changed({ groups: true, items: true });
  };
  name.addEventListener('keydown', e => { if (e.key === 'Enter') add(); });
  return h('div', { className: 'add-row' },
    h('label', { className: 'inline-label' }, 'New group name:', name),
    h('button', { type: 'button', onclick: add }, 'Add Group'),
    h('span', { className: 'muted-text hint-with-tip' }, '(letters, underscores, hyphens - no digits) ', tipMarker(TIPS.pg_hint)));
}
