// Progressive Groups panel (legacy client.py:2210-2235, 2568-2616). v1.1 F4:
// rows with inline rename (offers to update item-prereq references) and Remove.
// F6: a color swatch per group.
import { h } from '../shared/dom.js';
import { alertDialog } from '../shared/dialog.js';
import { tipMarker } from '../shared/tooltip.js';
import { TIPS } from './legacy_text.js';
import { addProgGroup, checkGroupRename, removeProgGroup, renameProgGroup } from './model.js';
import { commitNameChange, confirmNameRemoval } from './rename_refs.js';
import { openColorPicker } from './regions.js';

function groupRow(group, ctx) {
  const name = h('input', {
    type: 'text', value: group, className: 'region-name', spellcheck: false, 'aria-label': 'Group name',
  });
  let committing = false; // blur fires again when the prompt takes focus
  const commitName = async () => {
    if (committing) return;
    committing = true;
    try {
      const renamed = await commitNameChange(ctx, {
        kind: 'group', label: 'Progressive Group', oldName: group, raw: name.value,
        check: checkGroupRename, apply: renameProgGroup,
      });
      if (renamed) ctx.changed({ groups: true, items: true, tasks: true });
      else name.value = group;
    } finally {
      committing = false;
    }
  };
  name.addEventListener('keydown', e => { if (e.key === 'Enter') name.blur(); });
  name.addEventListener('blur', commitName);
  const color = ctx.model.progGroupColors?.[group] || '';
  return h('div', { className: 'region-row gen-group-row' },
    h('button', {
      type: 'button', className: 'color-swatch', style: { background: color || '#808080' },
      'aria-label': `Change color of ${group}`,
      title: 'Group color, used to color code this group in the client Items tab.',
      onclick: () => openColorPicker(`Group Color: ${group}`, color, picked => {
        ctx.model.progGroupColors[group] = picked;
        ctx.changed({ groups: true });
      }),
    }),
    name,
    h('button', {
      type: 'button', className: 'remove-btn', 'aria-label': `Remove group ${group}`,
      onclick: async () => {
        if (!(await confirmNameRemoval(ctx, { kind: 'group', label: 'Progressive Group', name: group }))) return;
        removeProgGroup(ctx.model, group);
        ctx.changed({ groups: true, items: true });
      },
    }, 'Remove'));
}

export function renderProgGroups(container, ctx) {
  const { model } = ctx;
  if (!model.progGroups.length) {
    container.replaceChildren(h('div', { className: 'muted-text empty-note' }, 'No groups defined.'));
    return;
  }
  container.replaceChildren(...model.progGroups.map(g => groupRow(g, ctx)));
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
    h('span', { className: 'muted-text hint-with-tip' }, '(no digits, spaces, quotes, parentheses or commas) ', tipMarker(TIPS.pg_hint)));
}
