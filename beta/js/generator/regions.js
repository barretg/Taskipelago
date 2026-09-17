// Regions panel (legacy client.py:1955-2003, 2619-2860): add, color picker,
// inline rename (F4: offers to update references), default %, depends-on text,
// remove (F4: warns when referenced).
import { h } from '../shared/dom.js';
import { alertDialog, openDialog } from '../shared/dialog.js';
import { tipMarker } from '../shared/tooltip.js';
import { TIPS } from './legacy_text.js';
import {
  REGION_COLOR_PALETTE, addRegion, checkRegionRename, commitRegionPct, removeRegion, renameRegion,
} from './model.js';
import { commitNameChange, confirmNameRemoval } from './rename_refs.js';

const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

function pickColor(region, ctx) {
  const current = region.color || REGION_COLOR_PALETTE[0];
  let selected = current;
  const hex = h('input', { type: 'text', value: current, className: 'hex-input', spellcheck: false });
  const preview = h('div', { className: 'color-preview' });
  const native = h('input', { type: 'color', 'aria-label': 'Pick any color' });
  const apply = color => {
    selected = color;
    preview.style.background = color;
    if (/^#[0-9a-fA-F]{6}$/.test(color)) native.value = color.toLowerCase();
  };
  apply(current);
  hex.addEventListener('input', () => {
    let v = hex.value.trim();
    if (!v.startsWith('#')) v = '#' + v;
    if (HEX_RE.test(v)) apply(v);
  });
  native.addEventListener('input', () => {
    hex.value = native.value;
    apply(native.value);
  });
  const swatches = h('div', { className: 'color-grid' }, REGION_COLOR_PALETTE.map(color => h('button', {
    type: 'button', className: `color-swatch${color === current ? ' current' : ''}`,
    style: { background: color }, 'aria-label': color,
    onclick: () => { hex.value = color; apply(color); },
  })));
  openDialog({
    title: `Region Color: ${region.name}`,
    body: h('div', { className: 'color-picker' },
      h('div', { className: 'muted-text' }, 'Preset colors:'), swatches,
      h('div', { className: 'muted-text' }, 'Hex code:'),
      h('div', { className: 'color-hex-row' }, hex, native, preview)),
    buttons: [
      {
        label: 'OK', primary: true,
        onClick: close => { region.color = selected; ctx.changed({ regions: true }); close(true); },
      },
      { label: 'Cancel', value: false },
    ],
  });
}

function regionRow(region, i, ctx) {
  const name = h('input', { type: 'text', value: region.name, className: 'region-name', spellcheck: false });
  let committing = false; // blur fires again when the prompt takes focus
  const commitName = async () => {
    if (committing) return;
    committing = true;
    try {
      const renamed = await commitNameChange(ctx, {
        kind: 'region', label: 'Region', oldName: region.name, raw: name.value,
        check: checkRegionRename, apply: renameRegion,
      });
      name.value = region.name;
      if (renamed) ctx.changed({ regions: true, tasks: true, goal: true });
    } finally {
      committing = false;
    }
  };
  name.addEventListener('keydown', e => { if (e.key === 'Enter') name.blur(); });
  name.addEventListener('blur', commitName);

  const pct = h('input', {
    type: 'number', min: 0, max: 100, value: region.pct, className: 'count-input region-pct', 'aria-label': 'Default %',
  });
  const commitPct = () => {
    pct.value = commitRegionPct(region, pct.value);
    ctx.changed();
  };
  pct.addEventListener('keydown', e => { if (e.key === 'Enter') pct.blur(); });
  pct.addEventListener('blur', commitPct);

  return h('div', { className: 'region-row' },
    h('button', {
      type: 'button', className: 'color-swatch', style: { background: region.color || '#808080' },
      'aria-label': `Change color of ${region.name}`, onclick: () => pickColor(region, ctx),
    }),
    name,
    pct,
    h('input', {
      type: 'text', value: region.prereq, placeholder: 'Depends on', className: 'region-prereq', spellcheck: false,
      'aria-label': 'Depends on', dataset: { field: `regions.${i}.prereq` },
      oninput: e => { region.prereq = e.target.value.trim(); ctx.changed(); },
    }),
    h('button', {
      type: 'button', className: 'remove-btn',
      onclick: async () => {
        if (!(await confirmNameRemoval(ctx, { kind: 'region', label: 'Region', name: region.name }))) return;
        removeRegion(ctx.model, region.name);
        ctx.changed({ regions: true, tasks: true });
      },
    }, 'Remove'));
}

export function renderRegions(container, ctx) {
  const { model } = ctx;
  if (!model.regions.length) {
    container.replaceChildren(h('div', { className: 'muted-text empty-note' }, 'No regions defined.'));
    return;
  }
  container.replaceChildren(
    h('div', { className: 'region-row region-head muted-text' },
      h('span', { className: 'col-color' }, 'Color'), h('span', { className: 'col-name' }, 'Name'),
      h('span', { className: 'col-pct' }, 'Default %'), h('span', { className: 'col-prereq' }, 'Depends on')),
    ...model.regions.map((r, i) => regionRow(r, i, ctx)),
  );
}

export function buildRegionAddRow(ctx) {
  const name = h('input', { type: 'text', spellcheck: false, className: 'region-name' });
  const pct = h('input', { type: 'number', min: 0, max: 100, value: 100, className: 'count-input' });
  const add = async () => {
    let error;
    try {
      error = addRegion(ctx.model, name.value, pct.value);
    } catch (_) {
      error = ['Error', 'Default % must be a whole number.'];
    }
    if (error) {
      await alertDialog('error', ...error);
      return;
    }
    name.value = '';
    pct.value = 100;
    ctx.changed({ regions: true, tasks: true });
  };
  name.addEventListener('keydown', e => { if (e.key === 'Enter') add(); });
  return h('div', { className: 'add-row' },
    h('label', { className: 'inline-label' }, 'New region name:', name),
    h('label', { className: 'inline-label' }, 'Default %:', pct),
    h('button', { type: 'button', onclick: add }, 'Add Region'),
    h('span', { className: 'muted-text hint-with-tip' }, '(no digits, spaces, quotes, parentheses or commas) ', tipMarker(TIPS.rg_hint)));
}
