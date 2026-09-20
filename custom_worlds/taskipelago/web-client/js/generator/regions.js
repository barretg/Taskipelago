// Regions panel (legacy client.py:1955-2003, 2619-2860): add, color picker,
// inline rename (F4: offers to update references), default %, depends-on text,
// remove (F4: warns when referenced).
import { h } from '../shared/dom.js';
import { alertDialog, openDialog } from '../shared/dialog.js';
import { tipMarker } from '../shared/tooltip.js';
import { TIPS } from './legacy_text.js';
import {
  REGION_COLOR_PALETTE, addRegion, checkRegionRename, commitRegionPct, normalizeRegionParents,
  regionCanHaveParent, regionChildren, regionParentOptions, removeRegion, renameRegion,
} from './model.js';
import { regionCells } from './clicker_cells.js';
import { commitNameChange, confirmNameRemoval } from './rename_refs.js';
import { regionRandom } from './randomize_check.js';

const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

/** Color picker dialog shared by regions and progressive groups (F6). onPick(color) runs on OK. */
export function openColorPicker(title, currentColor, onPick) {
  const current = currentColor || REGION_COLOR_PALETTE[0];
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
    title,
    body: h('div', { className: 'color-picker' },
      h('div', { className: 'muted-text' }, 'Preset colors:'), swatches,
      h('div', { className: 'muted-text' }, 'Hex code:'),
      h('div', { className: 'color-hex-row' }, hex, native, preview)),
    buttons: [
      {
        label: 'OK', primary: true,
        onClick: close => { onPick(selected); close(true); },
      },
      { label: 'Cancel', value: false },
    ],
  });
}

/**
 * Parent dropdown for subregions. Blank means a top-level region. Only
 * non-randomized, non-nested regions are offered, so nesting stays one level
 * deep and a randomized region is never a parent.
 */
function parentCell(region, ctx) {
  const canNest = regionCanHaveParent(ctx.model, region);
  const options = canNest ? regionParentOptions(ctx.model, region) : [];
  const sel = h('select', {
    className: 'region-parent', disabled: !canNest,
    'aria-label': `Parent region of ${region.name}`,
    title: canNest ? '' : 'A region that already has subregions cannot itself have a parent.',
    onchange: e => {
      region.parent = e.target.value;
      ctx.changed({ regions: true });
    },
  }, [
    h('option', { value: '' }, '(none)'),
    ...options.map(n => h('option', { value: n }, n)),
  ]);
  sel.value = canNest ? region.parent || '' : '';
  return sel;
}

/** Randomize checkbox, pick field (N or N%), and shuffle-order checkbox for one region. */
function randomizeCells(region, ctx) {
  const rr = regionRandom(ctx.model, region.name);
  const isParent = regionChildren(ctx.model, region.name).length > 0;
  const pick = h('input', {
    type: 'text', value: rr.pick, placeholder: 'N or N%', className: 'count-input region-pick',
    spellcheck: false, disabled: !rr.on, 'aria-label': `Tasks kept from ${region.name}`,
    dataset: { field: `regions.${region.name}.pick` },
    oninput: e => {
      ctx.model.regionRandom[region.name] = { ...regionRandom(ctx.model, region.name), pick: e.target.value.trim() };
      ctx.changed();
    },
  });
  const orderBox = h('input', {
    type: 'checkbox', checked: rr.order, disabled: !rr.on,
    'aria-label': `Shuffle task order in ${region.name}`,
    onchange: e => {
      ctx.model.regionRandom[region.name] = { ...regionRandom(ctx.model, region.name), order: e.target.checked };
      ctx.changed();
    },
  });
  const box = h('input', {
    type: 'checkbox', checked: rr.on && !isParent, disabled: isParent,
    'aria-label': `Randomize ${region.name}`,
    title: isParent ? 'A region with subregions cannot be randomized.' : '',
    onchange: e => {
      ctx.model.regionRandom[region.name] = { ...regionRandom(ctx.model, region.name), on: e.target.checked };
      pick.disabled = !e.target.checked;
      orderBox.disabled = !e.target.checked;
      // Randomizing a region drops any child that pointed at it.
      normalizeRegionParents(ctx.model);
      ctx.changed({ regions: true });
    },
  });
  return [
    h('label', { className: 'check-label region-random' }, box, 'Randomize', tipMarker(TIPS.rg_random)),
    pick,
    h('label', { className: 'check-label region-random' }, orderBox, 'Shuffle order', tipMarker(TIPS.rg_order)),
  ];
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
      'aria-label': `Change color of ${region.name}`,
      onclick: () => openColorPicker(`Region Color: ${region.name}`, region.color, color => {
        region.color = color;
        ctx.changed({ regions: true });
      }),
    }),
    name,
    pct,
    h('input', {
      type: 'text', value: region.prereq, placeholder: 'Depends on', className: 'region-prereq', spellcheck: false,
      'aria-label': 'Depends on', dataset: { field: `regions.${i}.prereq` },
      oninput: e => { region.prereq = e.target.value.trim(); ctx.changed(); },
    }),
    parentCell(region, ctx),
    ...randomizeCells(region, ctx),
    ...(ctx.model.clickerMode ? regionCells(region, ctx) : []),
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
  normalizeRegionParents(model);
  if (!model.regions.length) {
    container.replaceChildren(h('div', { className: 'muted-text empty-note' }, 'No regions defined.'));
    return;
  }
  container.replaceChildren(
    h('div', { className: 'region-row region-head muted-text' },
      h('span', { className: 'col-color' }, 'Color'), h('span', { className: 'col-name' }, 'Name'),
      h('span', { className: 'col-pct' }, 'Default %'), h('span', { className: 'col-prereq' }, 'Depends on', tipMarker(TIPS.rg_prereq)),
      h('span', { className: 'col-parent' }, 'Parent', tipMarker(TIPS.rg_parent)),
      h('span', { className: 'col-random' }, 'Randomize'), h('span', { className: 'col-pick' }, 'Keep'),
      h('span', { className: 'col-order' }, 'Shuffle order')),
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
