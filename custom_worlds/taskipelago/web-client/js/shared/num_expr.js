// Port of the numeric expression sub-grammar in
// custom_worlds/taskipelago/prereq_parser.py (parse_num_expr / eval_num_expr).
// Python stays the authority for syntax errors: YAML-authored text is parsed
// there and the AST ships in slot_data, so this file mostly evaluates. It can
// still parse, for the generator tab's live preview and for the N_TASKS
// suffixes that reach the client as raw prereq text.
//
// AST (JSON, identical to the Python side):
//   {num: 1.5}  {const: 'N_TASKS'}  {op: '+', l: node, r: node}

export const NUM_CONSTANTS = ['N_TASKS', 'N_TASKS_UNLOCKED', 'N_TASKS_LOCKED', 'N_TASKS_COMPLETED'];
export const LIVE_NUM_CONSTANTS = ['N_TASKS_UNLOCKED', 'N_TASKS_LOCKED', 'N_TASKS_COMPLETED'];

const TOKEN_RE = /^(?:(\d+\.\d*|\.\d+|\d+)|([A-Za-z_][A-Za-z0-9_]*)|([-+*/()]))/;

class NumExprError extends Error {}
export { NumExprError };

function tokenize(text, label, loc) {
  const tokens = [];
  let i = 0;
  while (i < text.length) {
    if (/\s/.test(text[i])) { i++; continue; }
    const m = TOKEN_RE.exec(text.slice(i));
    if (!m) throw new NumExprError(`Taskipelago: unexpected character '${text[i]}' in ${label}${loc}.`);
    if (m[1] !== undefined) tokens.push(['num', Number(m[1])]);
    else if (m[2] !== undefined) tokens.push(['name', m[2]]);
    else tokens.push(['sym', m[3]]);
    i += m[0].length;
  }
  return tokens;
}

/** parse_num_expr. Throws NumExprError with the Python error text. */
export function parseNumExpr(text, { label = 'numeric expression', locationLabel = null, allowLive = true } = {}) {
  const loc = locationLabel ? ` on ${locationLabel}` : '';
  const src = String(text ?? '').trim();
  if (!src) throw new NumExprError(`Taskipelago: empty ${label}${loc}.`);
  const tokens = tokenize(src, label, loc);
  let pos = 0;
  const peek = () => (pos < tokens.length ? tokens[pos] : null);
  const sym = s => { const t = peek(); return !!t && t[0] === 'sym' && t[1] === s; };

  const parseExpr = () => {
    let node = parseTerm();
    while (sym('+') || sym('-')) {
      const op = tokens[pos++][1];
      node = { op, l: node, r: parseTerm() };
    }
    return node;
  };
  const parseTerm = () => {
    let node = parseUnary();
    while (sym('*') || sym('/')) {
      const op = tokens[pos++][1];
      node = { op, l: node, r: parseUnary() };
    }
    return node;
  };
  const parseUnary = () => {
    if (sym('-')) { pos++; return { op: '-', l: { num: 0 }, r: parseUnary() }; }
    if (sym('+')) { pos++; return parseUnary(); }
    return parseAtom();
  };
  const parseAtom = () => {
    const t = peek();
    if (t === null) throw new NumExprError(`Taskipelago: unexpected end of ${label}${loc}.`);
    if (t[0] === 'num') { pos++; return { num: t[1] }; }
    if (t[0] === 'name') {
      pos++;
      const name = t[1];
      if (!NUM_CONSTANTS.includes(name)) {
        throw new NumExprError(
          `Taskipelago: unknown name '${name}' in ${label}${loc} (valid constants: ${NUM_CONSTANTS.join(', ')}).`);
      }
      if (!allowLive && LIVE_NUM_CONSTANTS.includes(name)) {
        throw new NumExprError(
          `Taskipelago: '${name}' changes during play and cannot be used in ${label}${loc}; `
          + 'only N_TASKS is allowed there.');
      }
      return { const: name };
    }
    if (t[1] === '(') {
      pos++;
      const node = parseExpr();
      if (!sym(')')) throw new NumExprError(`Taskipelago: missing ')' in ${label}${loc}.`);
      pos++;
      return node;
    }
    throw new NumExprError(`Taskipelago: unexpected token '${t[1]}' in ${label}${loc}.`);
  };

  const result = parseExpr();
  if (pos !== tokens.length) {
    throw new NumExprError(`Taskipelago: unexpected token '${tokens[pos][1]}' in ${label}${loc}.`);
  }
  return result;
}

/** Every constant name the expression references. */
export function numExprConstants(node) {
  if (!node || typeof node !== 'object') return new Set();
  if ('const' in node) return new Set([node.const]);
  if ('op' in node) return new Set([...numExprConstants(node.l), ...numExprConstants(node.r)]);
  return new Set();
}

/** True when nothing in the expression changes during play. */
export function numExprIsStatic(node) {
  for (const c of numExprConstants(node)) if (LIVE_NUM_CONSTANTS.includes(c)) return false;
  return true;
}

/**
 * eval_num_expr. `node` may be a plain number (the folded form slot_data ships).
 * Returns NaN rather than throwing on malformed data, so a bad seed never
 * freezes the accrual loop.
 */
export function evalNumExpr(node, bindings = {}) {
  if (typeof node === 'number') return node;
  if (!node || typeof node !== 'object') return NaN;
  if ('num' in node) return Number(node.num);
  if ('const' in node) {
    const v = bindings[node.const];
    return typeof v === 'number' ? v : NaN;
  }
  const l = evalNumExpr(node.l, bindings);
  const r = evalNumExpr(node.r, bindings);
  switch (node.op) {
    case '+': return l + r;
    case '-': return l - r;
    case '*': return l * r;
    case '/': return r === 0 ? NaN : l / r;
    default: return NaN;
  }
}

/** Integer-required fields round up, minimum 1. */
export function numExprToInt(value) {
  if (!Number.isFinite(value)) return 1;
  return Math.max(1, Math.ceil(value - 1e-9));
}

/** Evaluate with N_TASKS only (the generation-time fold). */
export function foldNumExpr(node, nTasks) {
  return evalNumExpr(node, { N_TASKS: nTasks });
}

/** Bindings for a live tick. Completed tasks still count as unlocked. */
export function numExprBindings(nTasks, nUnlocked, nCompleted) {
  return {
    N_TASKS: nTasks,
    N_TASKS_UNLOCKED: nUnlocked,
    N_TASKS_LOCKED: nTasks - nUnlocked,
    N_TASKS_COMPLETED: nCompleted,
  };
}

/**
 * Strict evaluation, mirroring Python's eval_num_expr: a division by zero or a
 * missing binding raises instead of yielding NaN. Used where the client must
 * reproduce a generation-time error exactly (the N_TASKS suffix fold).
 */
export function evalNumExprStrict(node, bindings = {}, label = 'numeric expression', locationLabel = null) {
  const loc = locationLabel ? ` on ${locationLabel}` : '';
  if (typeof node === 'number') return node;
  if (!node || typeof node !== 'object') throw new NumExprError(`Taskipelago: malformed ${label}${loc}.`);
  if ('num' in node) return Number(node.num);
  if ('const' in node) {
    const v = bindings[node.const];
    if (typeof v !== 'number') throw new NumExprError(`Taskipelago: '${node.const}' has no value in ${label}${loc}.`);
    return v;
  }
  const l = evalNumExprStrict(node.l, bindings, label, locationLabel);
  const r = evalNumExprStrict(node.r, bindings, label, locationLabel);
  switch (node.op) {
    case '+': return l + r;
    case '-': return l - r;
    case '*': return l * r;
    case '/':
      if (r === 0) throw new NumExprError(`Taskipelago: division by zero in ${label}${loc}.`);
      return l / r;
    default: throw new NumExprError(`Taskipelago: malformed ${label}${loc}.`);
  }
}
