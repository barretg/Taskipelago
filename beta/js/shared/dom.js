export const $ = id => document.getElementById(id);

export function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Element builder: h('button', { className: 'x', onclick }, 'Label', child).
 * Keys starting with "on" become listeners; `dataset` and `style` objects merge;
 * other keys are set as properties when the element has them, else attributes.
 * null, undefined and false children are skipped.
 */
export function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null) continue;
    if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else if (k === 'dataset' || k === 'style') Object.assign(node[k], v);
    else if (k in node) node[k] = v;
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}
