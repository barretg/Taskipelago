import { $ } from './dom.js';

// Option-list modal: callback(index) or callback(null) on Cancel.
export function showModal(title, desc, options, callback) {
  const overlay = $('modal-overlay');
  $('modal-title').textContent = title;
  $('modal-desc').textContent = desc;
  const btns = $('modal-btns');
  btns.innerHTML = '';

  const close = idx => {
    overlay.classList.add('hidden');
    callback(idx);
  };

  for (let i = 0; i < options.length; i++) {
    const btn = document.createElement('button');
    btn.textContent = options[i];
    btn.onclick = () => close(i);
    btns.appendChild(btn);
  }

  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = 'Cancel';
  cancelBtn.className = 'modal-cancel';
  cancelBtn.onclick = () => close(null);
  btns.appendChild(cancelBtn);

  overlay.classList.remove('hidden');
}

export function initModal() {
  const overlay = $('modal-overlay');
  overlay.addEventListener('click', e => {
    if (e.target === overlay) overlay.classList.add('hidden');
  });
}
