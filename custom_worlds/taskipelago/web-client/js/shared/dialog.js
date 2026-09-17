// Generalized stackable dialogs (UNIFY 5.8), replacing the legacy client's
// messagebox and Toplevel windows. shared/modal.js stays for the play tab's
// option-list prompts.

const stack = [];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/**
 * Open a dialog. buttons: [{ label, value, primary }]. Escape and a click on the
 * backdrop resolve with `dismissValue` when `dismissable` (default true).
 * Returns { box, body, close(value), result: Promise }.
 */
export function openDialog({
  title = '', text = '', body = null, buttons = [{ label: 'OK', value: true, primary: true }],
  className = '', dismissable = true, dismissValue = null,
} = {}) {
  const overlay = el('div', 'dialog-overlay');
  overlay.style.zIndex = String(950 + stack.length);
  stack.push(overlay);
  const box = el('div', `dialog-box ${className}`.trim());
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-modal', 'true');
  if (title) box.appendChild(el('div', 'dialog-title', title));
  const content = el('div', 'dialog-body');
  if (text) content.appendChild(el('div', 'dialog-text', text));
  if (body) content.appendChild(body);
  box.appendChild(content);
  const btnRow = el('div', 'dialog-btns');
  box.appendChild(btnRow);
  overlay.appendChild(box);

  let resolve;
  const result = new Promise(r => { resolve = r; });
  let closed = false;
  const onKey = e => {
    if (e.key === 'Escape' && dismissable && stack[stack.length - 1] === overlay) {
      e.preventDefault();
      close(dismissValue);
    }
  };
  function close(value) {
    if (closed) return;
    closed = true;
    stack.splice(stack.indexOf(overlay), 1);
    document.removeEventListener('keydown', onKey);
    overlay.remove();
    resolve(value);
  }
  function setButtons(list) {
    btnRow.innerHTML = '';
    for (const b of list) {
      const btn = el('button', b.primary ? 'primary' : '', b.label);
      btn.type = 'button';
      btn.onclick = () => (b.onClick ? b.onClick(close) : close(b.value));
      btnRow.appendChild(btn);
    }
    btnRow.classList.toggle('hidden', list.length === 0);
  }
  setButtons(buttons);
  overlay.addEventListener('mousedown', e => {
    if (e.target === overlay && dismissable) close(dismissValue);
  });
  document.addEventListener('keydown', onKey);
  document.body.appendChild(overlay);
  const focusTarget = box.querySelector('input, textarea, select') || btnRow.querySelector('.primary') || btnRow.querySelector('button');
  focusTarget?.focus();
  return { box, body: content, close, setButtons, result };
}

/** messagebox.showerror / showwarning / showinfo */
export function alertDialog(kind, title, text) {
  return openDialog({
    title, text, className: `dialog-${kind}`, dismissValue: undefined,
    buttons: [{ label: 'OK', value: undefined, primary: true }],
  }).result;
}

/** messagebox.askyesno */
export async function confirmDialog(title, text) {
  return (await openDialog({
    title, text, className: 'dialog-confirm', dismissValue: false,
    buttons: [{ label: 'Yes', value: true, primary: true }, { label: 'No', value: false }],
  }).result) === true;
}
