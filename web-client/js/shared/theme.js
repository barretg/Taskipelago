// Slot-supplied color theme (v1.1 F7). The generator's Style section picks a
// color per CSS variable; the apworld passes them through slot_data as
// "key:#rrggbb" strings, and the play tab applies them for the length of the
// connection only. Disconnecting removes the inline overrides, so the
// stylesheet's own :root values come back.

/** Themable CSS variables shared by every slot, in Style-section order. */
export const GENERAL_THEME_COLORS = [
  { key: 'bg', cssVar: '--bg', label: 'Page Background', default: '#1e1e1e' },
  { key: 'panel', cssVar: '--panel', label: 'Panel Background', default: '#252526' },
  { key: 'field', cssVar: '--field', label: 'Text Box Background', default: '#2d2d30' },
  { key: 'fg', cssVar: '--fg', label: 'Main Text', default: '#e6e6e6' },
  { key: 'muted', cssVar: '--muted', label: 'Dimmed Text', default: '#bdbdbd' },
  { key: 'desc', cssVar: '--desc', label: 'Task Description Text', default: '#d4d4d4' },
  { key: 'border', cssVar: '--border', label: 'Borders and Dividers', default: '#3a3a3a' },
  { key: 'tab-bg', cssVar: '--tab-bg', label: 'Tab Bar', default: '#3a3a3a' },
  { key: 'tab-active', cssVar: '--tab-active', label: 'Selected Tab', default: '#4a4a4a' },
  { key: 'btn-bg', cssVar: '--btn-bg', label: 'Buttons', default: '#3a3a3a' },
  { key: 'btn-hover', cssVar: '--btn-hover', label: 'Buttons (Mouse Over)', default: '#484848' },
  { key: 'warning', cssVar: '--warning', label: 'Warning Text', default: '#e07070' },
];

/** Board colors that only a Taskipelabingo slot shows; configured on that page. */
export const BINGO_THEME_COLORS = [
  { key: 'bingo-line', cssVar: '--bingo-line', label: 'Bingo Line Highlight', default: '#1a4a1a' },
  { key: 'bingo-done', cssVar: '--bingo-done', label: 'Bingo Completed Square', default: '#4a3a00' },
];

/** Every themable variable. Decoding and applying accept the whole set. */
export const THEME_COLORS = [...GENERAL_THEME_COLORS, ...BINGO_THEME_COLORS];

const BY_KEY = new Map(THEME_COLORS.map(c => [c.key, c]));

/** Defaults for one set of specs (defaults to the shared, non-bingo set). */
export const defaultThemeColors = (specs = GENERAL_THEME_COLORS) =>
  Object.fromEntries(specs.map(c => [c.key, c.default]));

/** '#abc' / '#aabbcc' -> normalized 6-digit lowercase hex; '' when unusable. */
export function normalizeHex(value) {
  const text = String(value ?? '').trim();
  const short = /^#?([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(text);
  if (short) return `#${short[1]}${short[1]}${short[2]}${short[2]}${short[3]}${short[3]}`.toLowerCase();
  const full = /^#?([0-9a-f]{6})$/i.exec(text);
  return full ? `#${full[1].toLowerCase()}` : '';
}

/** Fill in every key of a spec set, keeping valid saved colors, defaulting the rest. */
export function normalizeStyleColors(raw, specs = GENERAL_THEME_COLORS) {
  const saved = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  return Object.fromEntries(specs.map(c => [c.key, normalizeHex(saved[c.key]) || c.default]));
}

/** Model map -> the "key:#rrggbb" list carried by YAML and slot_data. */
export function encodeThemeColors(colors, specs = GENERAL_THEME_COLORS) {
  const out = [];
  for (const { key, default: def } of specs) {
    const hex = normalizeHex(colors?.[key]);
    if (hex && hex !== def) out.push(`${key}:${hex}`);
  }
  return out;
}

/** "key:#rrggbb" list -> map of known keys; unknown keys and bad colors drop. */
export function decodeThemeColors(list) {
  const out = {};
  if (!Array.isArray(list)) return out;
  for (const entry of list) {
    const text = String(entry ?? '');
    const at = text.indexOf(':');
    if (at < 0) continue;
    const key = text.slice(0, at).trim();
    const hex = normalizeHex(text.slice(at + 1));
    if (hex && BY_KEY.has(key)) out[key] = hex;
  }
  return out;
}

/** Apply a decoded map as inline :root overrides, replacing any earlier set. */
export function applyTheme(colors, root = document.documentElement) {
  if (!root) return;
  clearTheme(root);
  for (const { key, cssVar } of THEME_COLORS) {
    const hex = normalizeHex(colors?.[key]);
    if (hex) root.style.setProperty(cssVar, hex);
  }
}

/** Drop the overrides so the stylesheet's default scheme applies again. */
export function clearTheme(root = document.documentElement) {
  if (!root) return;
  for (const { cssVar } of THEME_COLORS) root.style.removeProperty(cssVar);
}
