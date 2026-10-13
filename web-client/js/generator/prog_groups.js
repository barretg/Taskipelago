// Item Groups panel (formerly Progressive Groups) (legacy client.py:2210-2235, 2568-2616). v1.1 F4:
// rows with inline rename (offers to update item-prereq references) and Remove.
// F6: a color swatch per group.
import { h } from '../shared/dom.js';
import { alertDialog } from '../shared/dialog.js';
import { tipMarker } from '../shared/tooltip.js';
import { TIPS } from './legacy_text.js';
import {
  addProgGroup, checkGroupRename, groupCanHaveParent, groupChildren, groupParentOptions, normalizeGroupParents,
  refreshItemGroupLocks, removeProgGroup, renameProgGroup,
} from './model.js';
import { commitNameChange, confirmNameRemoval } from './rename_refs.js';
import { trackCommit } from './grid_nav.js';
import { openColorPicker } from './regions.js';
import { GROUP_TYPES, groupSetting, isGroupDisabled } from './randomize_check.js';

/**
 * Parent dropdown for subgroups. Blank means a top-level group. Only
 * non-random-choice, non-nested groups are offered, so nesting stays one level
 * deep and a random-choice group is never a parent.
 */
function parentCell(group, ctx) {
  const canNest = groupCanHaveParent(ctx.model, group);
  const options = canNest ? groupParentOptions(ctx.model, group) : [];
  const sel = h('select', {
    className: 'region-parent', disabled: !canNest,
    'aria-label': `Parent group of ${group}`,
    title: canNest ? 'Parent group' : 'A group that already has subgroups cannot itself have a parent.',
    onchange: e => {
      ctx.model.groupSettings[group] = { ...groupSetting(ctx.model, group), parent: e.target.value };
      ctx.changed({ groups: true, items: true });
    },
  }, [
    h('option', { value: '' }, '(no parent)'),
    ...options.map(n => h('option', { value: n }, n)),
  ]);
  sel.value = canNest ? groupSetting(ctx.model, group).parent : '';
  return h('span', { className: 'hint-with-tip' }, sel, tipMarker(TIPS.group_parent));
}

/** Type dropdown, random-choice pick field and default % field for one group. */
function settingCells(group, ctx) {
  const s = groupSetting(ctx.model, group);
  const isParent = groupChildren(ctx.model, group).length > 0;
  const update = patch => {
    ctx.model.groupSettings[group] = { ...groupSetting(ctx.model, group), ...patch };
    ctx.changed();
  };
  const pick = h('input', {
    type: 'text', value: s.pick, placeholder: 'N or N%', className: 'count-input group-pick', spellcheck: false,
    disabled: s.type !== 'random-choice', 'aria-label': `Items kept from ${group}`,
    oninput: e => update({ pick: e.target.value.trim() }),
  });
  const pct = h('input', {
    type: 'text', value: s.pct, className: 'count-input group-pct', spellcheck: false,
    placeholder: s.type === 'progressive' ? 'auto' : '100', 'aria-label': `Default % for ${group}`,
    oninput: e => update({ pct: e.target.value.trim() }),
  });
  const type = h('select', {
    className: 'group-type', 'aria-label': `Type of ${group}`,
    onchange: e => {
      ctx.model.groupSettings[group] = { ...groupSetting(ctx.model, group), type: e.target.value };
      // Only progressive groups force their items to Progression.
      refreshItemGroupLocks(ctx.model);
      // A random-choice group cannot be a parent; its subgroups drop the link.
      normalizeGroupParents(ctx.model);
      ctx.changed({ groups: true, items: true });
    },
  }, GROUP_TYPES.map(t => h('option', {
    value: t,
    // A group with subgroups cannot become random-choice.
    disabled: t === 'random-choice' && isParent,
  }, t)));
  type.value = s.type;
  // A subgroup inherits Early and Disabled when its parent sets them; the box is
  // then locked on. The subgroup's own value is kept for when the parent clears it.
  const ps = s.parent ? groupSetting(ctx.model, s.parent) : null;
  const inherit = (key, box, label, tip) => {
    const on = !!(ps && ps[key]);
    if (on) {
      box.checked = true;
      box.disabled = true;
    }
    return h('span', { className: `hint-with-tip${key === 'disabled' ? ' disabled-toggle' : ''}${on ? ' inherited' : ''}` },
      h('label', {
        className: 'check-label',
        title: on ? `Inherited: parent group '${s.parent}' has ${label} on.` : '',
      }, box, label), tipMarker(tip));
  };
  const disabled = h('input', {
    type: 'checkbox', checked: s.disabled, 'aria-label': `Disable ${group}`,
    onchange: e => {
      ctx.model.groupSettings[group] = { ...groupSetting(ctx.model, group), disabled: e.target.checked };
      ctx.changed({ groups: true, items: true });
    },
  });
  const early = h('input', {
    type: 'checkbox', checked: s.early, 'aria-label': `Place ${group} items early`,
    onchange: e => update({ early: e.target.checked }),
  });
  return [
    h('span', { className: 'hint-with-tip' }, type, tipMarker(TIPS.group_type)),
    h('span', { className: 'hint-with-tip' }, pick, tipMarker(TIPS.group_pick)),
    h('span', { className: 'hint-with-tip' }, pct, tipMarker(TIPS.group_pct)),
    inherit('early', early, 'Early', TIPS.group_early),
    inherit('disabled', disabled, 'Disabled', TIPS.group_disabled),
  ];
}

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
  name.addEventListener('blur', () => trackCommit(commitName()));
  const color = ctx.model.progGroupColors?.[group] || '';
  const off = isGroupDisabled(ctx.model, group);
  return h('div', { className: `region-row gen-group-row${off ? ' row-disabled' : ''}` },
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
    parentCell(group, ctx),
    ...settingCells(group, ctx),
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
  normalizeGroupParents(model);
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
