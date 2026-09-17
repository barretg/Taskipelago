// v1.1 F4: rename and remove prompts for regions and progressive groups when
// expressions reference the name. The expression walk is shared/expr_rewrite.js.
import { alertDialog, confirmDialog, openDialog } from '../shared/dialog.js';
import { countNameRefFields, rewriteNameRefs } from './model.js';

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
