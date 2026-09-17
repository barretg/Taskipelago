// File open/save helpers shared by the generators. Both modes run in a browser
// window, so saving is a download and opening is a file input.

/** Resolves to { name, text } or null when the picker is cancelled. */
export function pickTextFile(accept = '.yaml,.yml') {
  return new Promise(resolve => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = accept;
    input.style.display = 'none';
    let settled = false;
    const finish = value => {
      if (settled) return;
      settled = true;
      input.remove();
      resolve(value);
    };
    input.addEventListener('change', async () => {
      const file = input.files && input.files[0];
      if (!file) return finish(null);
      try {
        finish({ name: file.name, text: await file.text() });
      } catch (e) {
        finish({ name: file.name, error: e });
      }
    });
    input.addEventListener('cancel', () => finish(null));
    document.body.appendChild(input);
    input.click();
  });
}

/** Characters Windows, macOS and Linux all accept in a file name. */
export function safeFileName(name, fallback = 'taskipelago') {
  const cleaned = String(name).replace(/[\\/:*?"<>|\x00-\x1f]/g, '_').replace(/^[ .]+|[ .]+$/g, '');
  return cleaned || fallback;
}

export function downloadText(fileName, text, type = 'application/x-yaml') {
  const blob = new Blob([text], { type: `${type};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
