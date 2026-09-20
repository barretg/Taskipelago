// Port of custom_worlds/taskipelago/prereq_parser.py: parse_prereq,
// parse_cost_expr and RESERVED_WORDS (UNIFY 5.4), with identical error text.
//
// prereq_parser.py stays the generation authority. Any parser change lands in
// both files and must pass the parity corpus (python tests/run_tests.py; see
// tests/parity/README.md).
//
// AST (Python tuples become arrays):
//   int                          0-based task/item index
//   ['and', [node, ...]]  ['or', [node, ...]]
//   ['group_ref', name, n|null]  ['group_count', name, n]
//   ['region_ref', name, pct|null]  ['region_abs', name, n]
//   ['seq_flag']
//   ['item_copies', idx, y]      first y copies of item idx (INDEX*Y, item prereqs only)
//   ['scoped_task', [node]]      task(...) wrapper (region prereqs only)
//   ['scoped_item', [node]]      item(...) wrapper (region prereqs only)
//   ['cost_group', name, count]  (cost expressions)
//
// Python details kept for parity: str.isspace()/strip() character set,
// iteration by code point, repr() text in cost errors, and the IndexError text
// ("list index out of range") when an expression ends where ')' is expected.
// Digits are ASCII only (Python also accepts other Unicode digits there).

import {
  LIVE_NUM_CONSTANTS, NumExprError, evalNumExprStrict, numExprConstants, numExprToInt, parseNumExpr,
} from './num_expr.js';

export const RESERVED_WORDS = new Set(['prev', 'sequential']);

/** Names the numeric-expression grammar reserves; unusable as region/group/item names. */
export const RESERVED_NAMES = new Set([
  ...RESERVED_WORDS, 'n_tasks', 'n_tasks_unlocked', 'n_tasks_locked', 'n_tasks_completed',
]);

const INDEX_ERROR = 'list index out of range';

const PY_SPACE = new Set([
  ' ', '\t', '\n', '\r', '\x0b', '\x0c', '\x1c', '\x1d', '\x1e', '\x1f', '\x85', '\xa0',
  '\u1680', '\u2028', '\u2029', '\u202f', '\u205f', '\u3000',
]);
for (let cp = 0x2000; cp <= 0x200a; cp++) PY_SPACE.add(String.fromCodePoint(cp));

const isSpace = c => PY_SPACE.has(c);
const isDigit = c => c >= '0' && c <= '9';
const isAlpha = c => /^\p{L}$/u.test(c);

// Port of prereq_parser.py NAME_DASH_RE / NAME_STAR_RE / split_name_suffix (v1.1 F8).
// Names never contain digits, so the trailing -N / *N split is unambiguous.
const NAME_DASH_RE = /^(\P{Nd}+)-(\d+)$/u;
const NAME_STAR_RE = /^(\P{Nd}+)\*(\d+)$/u;

/**
 * Returns [base, n, mode]; mode is 'dash', 'star' or 'none'.
 * A suffix that mentions N_TASKS ("chores-N_TASKS") is folded with `nTasks`;
 * every suffix that parsed before still takes the plain-integer path.
 * knownNames, when given, restricts which prefixes may be split off, which
 * disambiguates names that themselves contain '-'.
 */
export function splitNameSuffix(tok, knownNames = null, nTasks = 0, errCtx = null) {
  const dash = NAME_DASH_RE.exec(tok);
  if (dash && (!knownNames || knownNames.has(dash[1]))) return [dash[1], Number(dash[2]), 'dash'];
  const star = NAME_STAR_RE.exec(tok);
  if (star && (!knownNames || knownNames.has(star[1]))) return [star[1], Number(star[2]), 'star'];
  if (tok.includes('N')) {
    for (let i = 1; i < tok.length; i++) {
      const ch = tok[i];
      if (ch !== '-' && ch !== '*') continue;
      const base = tok.slice(0, i);
      const rest = tok.slice(i + 1);
      if (!rest) continue;
      if (knownNames && !knownNames.has(base)) continue;
      let ast;
      try {
        ast = parseNumExpr(rest, { allowLive: true });
      } catch (_) {
        continue;
      }
      const consts = numExprConstants(ast);
      if (!consts.size) continue;
      for (const live of LIVE_NUM_CONSTANTS) {
        if (consts.has(live)) {
          fail(`Taskipelago: '${live}' changes during play and cannot be used in '${tok}'; `
            + 'only N_TASKS is allowed in a prereq, goal or cost suffix.');
        }
      }
      let value;
      try {
        value = evalNumExprStrict(
          ast, { N_TASKS: nTasks },
          errCtx ? errCtx.label : 'numeric expression', errCtx ? errCtx.loc : null);
      } catch (e) {
        if (!(e instanceof NumExprError)) throw e;
        fail(e.message);
      }
      return [base, numExprToInt(value), ch === '-' ? 'dash' : 'star'];
    }
  }
  if (dash) return [dash[1], Number(dash[2]), 'dash'];
  if (star) return [star[1], Number(star[2]), 'star'];
  return [tok, null, 'none'];
}

/**
 * Unified region / progressive group name rule (v1.1 F8). Returns null when
 * valid, else the reason as a predicate phrase ("must not contain digits").
 * Rejects exactly what the tokenizer cannot carry inside one name token.
 */
export function validateRefName(name) {
  const chars = Array.from(name);
  if (!chars.length) return 'must not be empty';
  if (/\p{Nd}/u.test(name)) return 'must not contain digits';
  if (chars.some(isSpace)) return 'must not contain spaces';
  if (!(isAlpha(chars[0]) || chars[0] === '_')) return 'must start with a letter or underscore';
  if (/["(),]/.test(name)) return 'must not contain quotes, parentheses or commas';
  if (name.includes('&&') || name.includes('||')) return 'must not contain && or ||';
  if (RESERVED_WORDS.has(name.toLowerCase())) return 'is a reserved word';
  return null;
}

function fail(message) {
  throw new Error(message);
}

function pyStrip(text) {
  const chars = Array.from(text);
  let a = 0;
  let b = chars.length;
  while (a < b && isSpace(chars[a])) a++;
  while (b > a && isSpace(chars[b - 1])) b--;
  return chars.slice(a, b);
}

function toSet(names) {
  if (names === null || names === undefined) return null;
  return names instanceof Set ? names : new Set(names);
}

/** Python repr() of a token: str, int, or tuple (array). */
export function pyRepr(value) {
  if (Array.isArray(value)) return `(${value.map(pyRepr).join(', ')})`;
  if (typeof value !== 'string') return String(value);
  const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
  let out = '';
  for (const ch of value) {
    const cp = ch.codePointAt(0);
    if (ch === '\\') out += '\\\\';
    else if (ch === quote) out += '\\' + quote;
    else if (ch === '\n') out += '\\n';
    else if (ch === '\r') out += '\\r';
    else if (ch === '\t') out += '\\t';
    else if (ch !== ' ' && /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Z}]/u.test(ch)) {
      if (cp <= 0xff) out += '\\x' + cp.toString(16).padStart(2, '0');
      else if (cp <= 0xffff) out += '\\u' + cp.toString(16).padStart(4, '0');
      else out += '\\U' + cp.toString(16).padStart(8, '0');
    } else out += ch;
  }
  return quote + out + quote;
}

function simplify(op, nodes) {
  return nodes.length === 1 ? nodes[0] : [op, nodes];
}

// ---------------------------------------------------------------------------
// Prereq expressions
// ---------------------------------------------------------------------------

// Token as written, for error messages (copies tokens back to INDEX*Y).
const tokText = tok => (Array.isArray(tok) && tok[0] === 'copies' ? `${tok[1]}*${tok[2]}` : String(tok));

function tokenize(chars, taskIndex, label, locationLabel) {
  const loc = locationLabel || `task ${taskIndex + 1}`;
  const tokens = [];
  let i = 0;
  while (i < chars.length) {
    const c = chars[i];
    const two = c + (chars[i + 1] ?? '');

    if (isSpace(c)) { i++; continue; }

    if (isDigit(c)) {
      let j = i;
      while (j < chars.length && isDigit(chars[j])) j++;
      // INDEX*Y copy count (no spaces around '*')
      if (chars[j] === '*') {
        let k = j + 1;
        while (k < chars.length && isDigit(chars[k])) k++;
        if (k > j + 1) {
          tokens.push(['copies', BigInt(chars.slice(i, j).join('')), BigInt(chars.slice(j + 1, k).join(''))]);
          i = k;
          continue;
        }
      }
      tokens.push(BigInt(chars.slice(i, j).join(''))); // ints are bigint, names are strings
      i = j;
      continue;
    }

    if (two === '&&' || two === '||') { tokens.push(two); i += 2; continue; }

    if (c === '(' || c === ')' || c === ',') { tokens.push(c); i++; continue; }

    if (isAlpha(c) || c === '_') {
      let j = i;
      while (j < chars.length) {
        const ch = chars[j];
        if (isSpace(ch) || ch === '(' || ch === ')' || ch === ',') break;
        const pair = ch + (chars[j + 1] ?? '');
        if (pair === '&&' || pair === '||') break;
        j++;
      }
      tokens.push(chars.slice(i, j).join(''));
      i = j;
      continue;
    }

    fail(`Taskipelago: unexpected character '${c}' in ${label} on ${loc}.`);
  }
  return tokens;
}

/**
 * Port of prereq_parser.py map_scoped_text. Rewrites the contents of the
 * task(...) / item(...) wrappers in a region prereq; text outside a wrapper is
 * left exactly as written and quoted names are skipped over.
 */
export function mapScopedText(text, taskFn = null, itemFn = null) {
  if (!text) return text;
  const chars = Array.from(text);
  const n = chars.length;
  const findQuote = from => {
    for (let k = from; k < n; k++) if (chars[k] === '"') return k;
    return -1;
  };
  const out = [];
  let i = 0;
  while (i < n) {
    const c = chars[i];
    if (c === '"') {
      const q = findQuote(i + 1);
      const j = q < 0 ? n : q + 1;
      out.push(chars.slice(i, j).join(''));
      i = j;
      continue;
    }
    if (isAlpha(c) || c === '_') {
      let j = i;
      while (j < n && (isAlpha(chars[j]) || isDigit(chars[j]) || chars[j] === '_')) j++;
      const word = chars.slice(i, j).join('');
      if ((word === 'task' || word === 'item') && chars[j] === '(') {
        let depth = 0;
        let k = j;
        while (k < n) {
          const ch = chars[k];
          if (ch === '"') {
            const q = findQuote(k + 1);
            k = q < 0 ? n : q + 1;
            continue;
          }
          if (ch === '(') depth++;
          else if (ch === ')') {
            depth--;
            if (depth === 0) break;
          }
          k++;
        }
        if (k < n) {
          const inner = chars.slice(j + 1, k).join('');
          const fn = word === 'task' ? taskFn : itemFn;
          out.push(`${word}(${fn ? fn(inner) : inner})`);
          i = k + 1;
          continue;
        }
      }
      out.push(word);
      i = j;
      continue;
    }
    out.push(c);
    i++;
  }
  return out.join('');
}

/**
 * Parse a prereq expression. Returns null for an empty expression, throws Error
 * with the Python message otherwise. Integer leaves are 0-based.
 */
export function parsePrereq(text, nTasks, taskIndex, label,
                            knownGroups = null, knownRegions = null, locationLabel = null,
                            nTasksConst = null, scopedDomains = null) {
  const chars = pyStrip(text);
  if (!chars.length) return null;

  const loc = locationLabel || `task ${taskIndex + 1}`;
  const groups = toSet(knownGroups);
  const regions = toSet(knownRegions);

  const tokens = tokenize(chars, taskIndex, label, locationLabel);
  if (!tokens.length) return null;

  // Parsing context; task(...) / item(...) push a scoped copy onto the stack.
  const ctx = [{
    n: nTasks,
    groups,
    regions,
    const: nTasksConst === null ? nTasks : nTasksConst,
    label,
  }];

  let pos = 0;
  const peek = () => (pos < tokens.length ? tokens[pos] : null);
  const consume = (expected = null) => {
    if (pos >= tokens.length) fail(INDEX_ERROR);
    const tok = tokens[pos];
    if (expected !== null && tok !== expected) {
      fail(`Taskipelago: expected '${expected}' but got '${tokText(tok)}' in ${ctx[ctx.length - 1].label} on ${loc}.`);
    }
    pos++;
    return tok;
  };

  const parseExpr = () => parseOr();

  function parseOr() {
    const nodes = [parseAnd()];
    while (peek() === '||') {
      consume('||');
      nodes.push(parseAnd());
    }
    return simplify('or', nodes);
  }

  function parseAnd() {
    const nodes = [parseAtom()];
    while (peek() === '&&' || peek() === ',') {
      consume();
      nodes.push(parseAtom());
    }
    return simplify('and', nodes);
  }

  function parseAtom() {
    const c = ctx[ctx.length - 1];
    const cLabel = c.label;
    const cN = c.n;
    const cGroups = c.groups;
    const cRegions = c.regions;
    const tok = peek();
    if (tok === null) {
      fail(`Taskipelago: unexpected end of ${cLabel} expression on ${loc}.`);
    }
    if (tok === '(') {
      consume('(');
      const node = parseExpr();
      consume(')');
      return node;
    }
    if (scopedDomains && typeof tok === 'string' && Object.hasOwn(scopedDomains, tok)
        && tokens[pos + 1] === '(') {
      consume();
      consume('(');
      const spec = scopedDomains[tok];
      ctx.push({
        n: spec.n ?? 0,
        groups: toSet(spec.groups ?? null),
        regions: toSet(spec.regions ?? null),
        const: spec.const ?? spec.n ?? 0,
        label: spec.label ?? cLabel,
      });
      let node;
      try {
        node = parseExpr();
        consume(')');
      } finally {
        ctx.pop();
      }
      return [`scoped_${tok}`, [node]];
    }
    if (typeof tok === 'bigint') {
      consume();
      if (tok < 1n || tok > BigInt(cN)) {
        fail(`Taskipelago: ${cLabel} index '${tok}' on ${loc} is out of range (1..${cN}).`);
      }
      return Number(tok) - 1;
    }
    if (Array.isArray(tok) && tok[0] === 'copies') {
      consume();
      const [, idx, y] = tok;
      if (cLabel !== 'item prereq') {
        fail(`Taskipelago: '${idx}*${y}' copy counts can only be used in item prereqs (used in ${cLabel} on ${loc}).`);
      }
      if (idx < 1n || idx > BigInt(cN)) {
        fail(`Taskipelago: ${cLabel} index '${idx}' on ${loc} is out of range (1..${cN}).`);
      }
      if (y < 1n) fail(`Taskipelago: copy count in '${idx}*${y}' on ${loc} must be at least 1.`);
      return ['item_copies', Number(idx) - 1, Number(y)];
    }
    if (typeof tok === 'string' && !['&&', '||', '(', ')', ','].includes(tok)) {
      consume();
      if (RESERVED_WORDS.has(tok)) {
        if (cLabel !== 'task prereq') {
          fail(`Taskipelago: '${tok}' can only be used in task prereqs (used in ${cLabel} on ${loc}).`);
        }
        if (tok === 'prev') {
          if (taskIndex < 1) {
            fail(`Taskipelago: 'prev' used on ${loc} but there is no previous task.`);
          }
          return taskIndex - 1;
        }
        return ['seq_flag'];
      }
      const known = new Set([...(cGroups || []), ...(cRegions || [])]);
      const [base, suffix, mode] = splitNameSuffix(
        tok, known.size ? known : null, c.const, { label: cLabel, loc });
      if (cGroups !== null && cGroups.has(base)) {
        return mode === 'star' ? ['group_count', base, suffix] : ['group_ref', base, suffix];
      }
      if (cRegions !== null && cRegions.has(base)) {
        return mode === 'star' ? ['region_abs', base, suffix] : ['region_ref', base, suffix];
      }
      fail(`Taskipelago: unknown name '${base}' in ${cLabel} on ${loc}.`);
    }
    fail(`Taskipelago: unexpected token '${tok}' in ${cLabel} on ${loc}.`);
  }

  const result = parseExpr();
  if (pos !== tokens.length) {
    fail(`Taskipelago: unexpected token '${tokText(tokens[pos])}' in ${label} on ${loc}.`);
  }
  return result;
}

// ---------------------------------------------------------------------------
// Cost expressions
// ---------------------------------------------------------------------------

const COST_SUFFIX_CHARS = new Set('0123456789._+-*/ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz');

function readCount(chars, j, nTasks = 0) {
  // "*N" after a name or index, where N is an integer or an N_TASKS expression;
  // returns [count, nextIndex]
  if (j >= chars.length || chars[j] !== '*') return [1, j];
  let digitsEnd = j + 1;
  while (digitsEnd < chars.length && isDigit(chars[digitsEnd])) digitsEnd++;
  let k = j + 1;
  while (k < chars.length && COST_SUFFIX_CHARS.has(chars[k])) k++;
  const rest = chars.slice(j + 1, k).join('');
  if (k > digitsEnd && rest.includes('N')) {
    let ast = null;
    try {
      ast = parseNumExpr(rest, { label: 'cost count', allowLive: true });
    } catch (_) { /* fall through to the digits-only reading */ }
    const consts = ast ? numExprConstants(ast) : new Set();
    if (consts.size) {
      for (const live of LIVE_NUM_CONSTANTS) {
        if (consts.has(live)) {
          fail(`Taskipelago: '${live}' changes during play and cannot be used in a cost `
            + 'expression; only N_TASKS is allowed there.');
        }
      }
      let value;
      try {
        value = evalNumExprStrict(ast, { N_TASKS: nTasks }, 'cost count');
      } catch (e) {
        if (!(e instanceof NumExprError)) throw e;
        fail(e.message);
      }
      return [numExprToInt(value), k];
    }
  }
  if (digitsEnd > j + 1) return [Number(chars.slice(j + 1, digitsEnd).join('')), digitsEnd];
  return [1, j];
}

function tokenizeCost(chars, itemNamesOrdered, nTasks = 0) {
  const tokens = [];
  let i = 0;
  while (i < chars.length) {
    const c = chars[i];
    const two = c + (chars[i + 1] ?? '');

    if (isSpace(c)) { i++; continue; }

    if (two === '&&' || two === '||') { tokens.push(two); i += 2; continue; }

    if (c === '(' || c === ')' || c === ',') { tokens.push(c); i++; continue; }

    if (c === '"') {
      let j = i + 1;
      while (j < chars.length && chars[j] !== '"') j++;
      if (j >= chars.length) fail('Taskipelago: unclosed quote in cost expression.');
      const name = chars.slice(i + 1, j).join('');
      const [count, next] = readCount(chars, j + 1, nTasks);
      tokens.push(['cost_item', name, count]);
      i = next;
      continue;
    }

    if (isDigit(c)) {
      let j = i;
      while (j < chars.length && isDigit(chars[j])) j++;
      const idx = BigInt(chars.slice(i, j).join(''));
      const [count, next] = readCount(chars, j, nTasks);
      const name = itemNamesOrdered && itemNamesOrdered.length && idx >= 1n && idx <= BigInt(itemNamesOrdered.length)
        ? itemNamesOrdered[Number(idx) - 1]
        : String(idx); // left as the index; the name check reports it
      tokens.push(['cost_item', name, count]);
      i = next;
      continue;
    }

    fail(`Taskipelago: unexpected character '${c}' in cost expression.`);
  }
  return tokens;
}

/**
 * Parse a task cost expression. consumableNames: valid consumable names.
 * itemNamesOrdered: all item names (index 0 = item 1) for numeric references.
 */
export function parseCostExpr(text, consumableNames, itemNamesOrdered = null, nTasks = 0) {
  const chars = pyStrip(text);
  if (!chars.length) return null;

  const consumables = toSet(consumableNames) || new Set();
  const tokens = tokenizeCost(chars, itemNamesOrdered, nTasks);
  if (!tokens.length) return null;

  let pos = 0;
  const peek = () => (pos < tokens.length ? tokens[pos] : null);
  const consume = (expected = null) => {
    if (pos >= tokens.length) fail(INDEX_ERROR);
    const tok = tokens[pos];
    if (expected !== null && tok !== expected) {
      fail(`Taskipelago: cost expression expected '${expected}' but got '${pyRepr(tok)}'.`);
    }
    pos++;
    return tok;
  };

  function parseOr() {
    const nodes = [parseAnd()];
    while (peek() === '||') {
      consume('||');
      nodes.push(parseAnd());
    }
    return simplify('or', nodes);
  }

  function parseAnd() {
    const nodes = [parseAtom()];
    while (peek() === '&&' || peek() === ',') {
      consume();
      nodes.push(parseAtom());
    }
    return simplify('and', nodes);
  }

  function parseAtom() {
    const tok = peek();
    if (tok === null) fail('Taskipelago: unexpected end of cost expression.');
    if (tok === '(') {
      consume('(');
      const node = parseOr();
      consume(')');
      return node;
    }
    if (Array.isArray(tok) && tok[0] === 'cost_item') {
      consume();
      const [, name, count] = tok;
      if (!consumables.has(name)) {
        fail(`Taskipelago: '${name}' in cost expression is not a known consumable item name.`);
      }
      if (count < 1) fail(`Taskipelago: cost count for '${name}' must be at least 1.`);
      return ['cost_group', name, count];
    }
    fail(`Taskipelago: unexpected token ${pyRepr(tok)} in cost expression.`);
  }

  const result = parseOr();
  if (pos !== tokens.length) {
    fail(`Taskipelago: unexpected trailing token ${pyRepr(tokens[pos])} in cost expression.`);
  }
  return result;
}
