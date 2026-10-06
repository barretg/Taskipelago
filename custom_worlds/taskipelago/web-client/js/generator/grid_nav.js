// Excel-style data entry in the task, item, DeathLink, region and group tables:
// Enter / Shift+Enter move down / up in the same column, Tab / Shift+Tab move right /
// left along the row and wrap to the next / previous row. Buttons are skipped;
// disabled fields are passed over. Past the table edge the key falls through to its
// default. Fields that commit on blur (region / group renames) may open a dialog and
// redraw the table, so the move waits for that and re-finds its target by position.
const ROW = '.gt-task, .gt-item, .dl-row:not(.gt-head), .region-row:not(.region-head)';
const FIELD = 'input:not([type=button]):not([type=hidden]), select, textarea';

const fields = row => [...row.querySelectorAll(FIELD)];
const rowsOf = table => [...table.children].filter(r => r.matches(ROW));
const usable = el => el && !el.disabled;

const pending = new Set();

/** Register a blur-commit workflow; grid moves wait for it to finish. */
export function trackCommit(promise) {
  pending.add(promise);
  promise.finally(() => pending.delete(promise));
  return promise;
}

/** Position [row, column] of the next usable field from (r, c), or null. */
function step(rows, r, c, key, dir) {
  if (key === 'Enter') {
    for (let i = r + dir; i >= 0 && i < rows.length; i += dir) {
      if (usable(fields(rows[i])[c])) return [i, c];
    }
    return null;
  }
  let cols = fields(rows[r]);
  for (let i = r, j = c + dir; ;) {
    if (j < 0 || j >= cols.length) {
      i += dir;
      if (i < 0 || i >= rows.length) return null;
      cols = fields(rows[i]);
      j = dir > 0 ? 0 : cols.length - 1;
      continue;
    }
    if (usable(cols[j])) return [i, j];
    j += dir;
  }
}

function go(el) {
  el.focus();
  if (el.select && (el.type === 'text' || el.type === 'number')) el.select();
}

/** Keydown handler for the generator root. */
export async function gridNavKeydown(e) {
  if ((e.key !== 'Enter' && e.key !== 'Tab') || e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
  const el = e.target;
  const row = el.closest?.(ROW);
  if (!row || !el.matches(FIELD)) return;
  const table = row.parentElement;
  const rows = rowsOf(table);
  const pos = step(rows, rows.indexOf(row), fields(row).indexOf(el), e.key, e.shiftKey ? -1 : 1);
  if (!pos) return;
  e.preventDefault();
  if (document.activeElement === el) el.blur();
  if (pending.size) {
    while (pending.size) await Promise.allSettled([...pending]);
    // Something else took focus while the workflow ran; leave it there.
    if (document.activeElement && document.activeElement !== document.body) return;
  }
  const target = rowsOf(table)[pos[0]] && fields(rowsOf(table)[pos[0]])[pos[1]];
  if (usable(target)) go(target);
}
