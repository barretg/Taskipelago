// Style color pickers (v1.1 F7), shared by the YAML Generator's Style section
// and the Taskipelabingo page. The colors ride along in the YAML as
// style_colors and are applied by the play tab while the slot is connected;
// the pickers never change the editor's own colors.
import { h } from '../shared/dom.js';
import { GENERAL_THEME_COLORS, normalizeHex, normalizeStyleColors } from '../shared/theme.js';

const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

export const STYLE_SECTION_TIP = 'These colors are applied to this app while you are connected '
  + 'to the slot made from this YAML. Disconnecting restores the default color scheme.';

function styleRow(spec, colors, onChange, rerender) {
  const current = normalizeHex(colors[spec.key]) || spec.default;
  const set = color => {
    colors[spec.key] = color;
    onChange();
  };
  const native = h('input', {
    type: 'color', value: current, className: 'style-color-native', 'aria-label': spec.label,
    oninput: e => {
      hex.value = e.target.value;
      set(e.target.value);
    },
  });
  const hex = h('input', {
    type: 'text', value: current, className: 'hex-input', spellcheck: false,
    'aria-label': `${spec.label} hex code`, dataset: { field: `style.${spec.key}` },
    oninput: e => {
      let v = e.target.value.trim();
      if (v && !v.startsWith('#')) v = '#' + v;
      if (!HEX_RE.test(v)) return;
      native.value = normalizeHex(v);
      set(normalizeHex(v));
    },
  });
  return h('div', { className: 'style-row' },
    h('span', { className: 'style-row-label' }, spec.label),
    native, hex,
    h('button', {
      type: 'button', className: 'style-row-default', disabled: current === spec.default,
      title: `Back to the default ${spec.default}`,
      onclick: () => { set(spec.default); rerender(); },
    }, 'Default'));
}

/**
 * Fill `container` with one picker per spec. `get()` returns the live color map
 * (normalized in place) and `onChange()` runs after every edit.
 */
export function renderStyleColors(container, { specs = GENERAL_THEME_COLORS, get, set, onChange }) {
  const rerender = () => renderStyleColors(container, { specs, get, set, onChange });
  const colors = normalizeStyleColors(get(), specs);
  set(colors);
  container.replaceChildren(...specs.map(spec => styleRow(spec, colors, onChange, rerender)));
}

/** "Reset Colors" button target: every spec back to its stylesheet default. */
export function resetStyleColors(container, opts) {
  opts.set(normalizeStyleColors(null, opts.specs || GENERAL_THEME_COLORS));
  renderStyleColors(container, opts);
  opts.onChange();
}
