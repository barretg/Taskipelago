// v1.1 F4: rename and remove prompts for regions and progressive groups when
// expressions reference the name, and for task / item rows with "Quoted" references. The expression walk is shared/expr_rewrite.js.
import { alertDialog, confirmDialog, openDialog } from '../shared/dialog.js';
import { countNameRefFields, countRowRenameRefs, rewriteNameRefs, rewriteRowRenameRefs } from './model.js';
import { reorderUpdatesRefs } from './reorder.js';
import { trackCommit } from './grid_nav.js';

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/**
 * Commit an inline rename. check(model, old, raw) -> { newName, error };
 * apply(model, old, newName) renames. Resolves true when the model changed.
 */
export async function commitNameChange(ctx, { kind, label, oldName, raw, check, apply }) {
  const { newName, error } = check(ctx.model, oldName, raw);
  if (error) {
    await alertDialog('error', ...error);
    return false;
  }
  if (!newName) return false;
  const refs = countNameRefFields(ctx.model, kind, oldName);
  let update = false;
  if (refs > 0) {
    const choice = await openDialog({
      title: `Rename ${label}`,
      text: `${plural(refs, 'expression references', 'expressions reference')} '${oldName}'. `
        + `Update ${refs === 1 ? 'it' : 'them'} to '${newName}'?`,
      className: 'dialog-confirm', dismissValue: 'cancel',
      buttons: [
        { label: 'Update', value: 'update', primary: true },
        { label: 'Rename only', value: 'rename' },
        { label: 'Cancel', value: 'cancel' },
      ],
    }).result;
    if (choice === 'cancel') return false;
    update = choice === 'update';
  }
  // Validate again: the model may have changed while the prompt was open.
  if (!check(ctx.model, oldName, newName).newName) return false;
  if (update) rewriteNameRefs(ctx.model, kind, oldName, newName);
  apply(ctx.model, oldName, newName);
  return true;
}

/** Confirm removing a name that expressions still reference. Resolves true to remove. */
export async function confirmNameRemoval(ctx, { kind, label, name }) {
  const refs = countNameRefFields(ctx.model, kind, name);
  if (!refs) return true;
  return confirmDialog(`Remove ${label}`,
    `${plural(refs, 'expression still references', 'expressions still reference')} '${name}' `
    + 'and will fail to export. Remove anyway?');
}

/**
 * Task / item row i was renamed from oldRaw in its name field. With the
 * reference toggle on and quoted references to the old name, offer to update
 * them. Cancel restores the old name through revert(oldRaw). Resolves true
 * when expressions were rewritten (the caller redraws).
 */
export async function commitRowRename(ctx, kind, i, oldRaw, revert) {
  if (!reorderUpdatesRefs()) return false;
  const refs = countRowRenameRefs(ctx.model, kind, i, oldRaw);
  if (!refs) return false;
  const what = kind === 'tasks' ? 'Task' : 'Item';
  const row = ctx.model[kind][i];
  const newRaw = row.name;
  const choice = await openDialog({
    title: `Rename ${what}`,
    text: `${plural(refs, 'expression references', 'expressions reference')} "${oldRaw.trim()}". `
      + `Update ${refs === 1 ? 'it' : 'them'} to "${newRaw.trim()}"?`,
    className: 'dialog-confirm', dismissValue: 'cancel',
    buttons: [
      { label: 'Update', value: 'update', primary: true },
      { label: 'Rename only', value: 'rename' },
      { label: 'Cancel', value: 'cancel' },
    ],
  }).result;
  // The model may have changed while the prompt was open.
  if (ctx.model[kind][i] !== row || row.name !== newRaw) return false;
  if (choice === 'cancel') {
    row.name = oldRaw;
    revert(oldRaw);
    ctx.changed();
    return false;
  }
  return choice === 'update' && rewriteRowRenameRefs(ctx.model, kind, i, oldRaw) > 0;
}

/** Wire a task / item name input so leaving it runs commitRowRename. */
export function watchRowRename(input, ctx, kind, i) {
  let before = null;
  let committing = false;
  input.addEventListener('focus', () => { if (!committing) before = ctx.model[kind][i].name; });
  input.addEventListener('blur', () => {
    if (committing || before === null) return;
    const oldRaw = before;
    before = null;
    committing = true;
    trackCommit((async () => {
      try {
        if (await commitRowRename(ctx, kind, i, oldRaw, v => { input.value = v; })) {
          ctx.changed({ tasks: true, items: kind === 'tasks' && !!ctx.model.clickerMode, regions: true, goal: true });
        }
      } finally {
        committing = false;
      }
    })());
  });
}
