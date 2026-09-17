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
//   ['cost_group', name, count]  (cost expressions)
//
// Python details kept for parity: str.isspace()/strip() character set,
// iteration by code point, repr() text in cost errors, and the IndexError text
// ("list index out of range") when an expression ends where ')' is expected.
// Digits are ASCII only (Python also accepts other Unicode digits there).

export const RESERVED_WORDS = new Set(['prev', 'sequential']);

const INDEX_ERROR = 'list index out of range';

const PY_SPACE = new Set([
  ' ', '\t', '\n', '\r', '\x0b', '\x0c', '\x1c', '\x1d', '\x1e', '\x1f', '\x85', '\xa0',
  '\u1680', '\u2028', '\u2029', '\u202f', '\u205f', '\u3000',
]);
for (let cp = 0x2000; cp <= 0x200a; cp++) PY_SPACE.add(String.fromCodePoint(cp));

const isSpace = c => PY_SPACE.has(c);
const isDigit = c => c >= '0' && c <= '9';
const isAlpha = c => /^\p{L}$/u.test(c);

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
 * Parse a prereq expression. Returns null for an empty expression, throws Error
 * with the Python message otherwise. Integer leaves are 0-based.
 */
export function parsePrereq(text, nTasks, taskIndex, label,
                            knownGroups = null, knownRegions = null, locationLabel = null) {
  const chars = pyStrip(text);
  if (!chars.length) return null;

  const loc = locationLabel || `task ${taskIndex + 1}`;
  const groups = toSet(knownGroups);
  const regions = toSet(knownRegions);

  const tokens = tokenize(chars, taskIndex, label, locationLabel);
  if (!tokens.length) return null;

  let pos = 0;
  const peek = () => (pos < tokens.length ? tokens[pos] : null);
  const consume = (expected = null) => {
    if (pos >= tokens.length) fail(INDEX_ERROR);
    const tok = tokens[pos];
    if (expected !== null && tok !== expected) {
      fail(`Taskipelago: expected '${expected}' but got '${tok}' in ${label} on ${loc}.`);
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
    const tok = peek();
    if (tok === null) {
      fail(`Taskipelago: unexpected end of ${label} expression on ${loc}.`);
    }
    if (tok === '(') {
      consume('(');
      const node = parseExpr();
      consume(')');
      return node;
    }
    if (typeof tok === 'bigint') {
      consume();
      if (tok < 1n || tok > BigInt(nTasks)) {
        fail(`Taskipelago: ${label} index '${tok}' on ${loc} is out of range (1..${nTasks}).`);
      }
      return Number(tok) - 1;
    }
    if (typeof tok === 'string' && !['&&', '||', '(', ')', ','].includes(tok)) {
      consume();
      if (RESERVED_WORDS.has(tok)) {
        if (label !== 'task prereq') {
          fail(`Taskipelago: '${tok}' can only be used in task prereqs (used in ${label} on ${loc}).`);
        }
        if (tok === 'prev') {
          if (taskIndex < 1) {
            fail(`Taskipelago: 'prev' used on ${loc} but there is no previous task.`);
          }
          return taskIndex - 1;
        }
        return ['seq_flag'];
      }
      const mDash = /^(.+[a-zA-Z_])-(\d+)$/u.exec(tok);
      const mStar = /^(.+[a-zA-Z_])\*(\d+)$/u.exec(tok);
      let base = tok;
      let suffix = null;
      let mode = 'none';
      if (mDash) {
        [base, suffix, mode] = [mDash[1], Number(mDash[2]), 'dash'];
      } else if (mStar) {
        [base, suffix, mode] = [mStar[1], Number(mStar[2]), 'star'];
      }
      if (groups !== null && groups.has(base)) {
        return mode === 'star' ? ['group_count', base, suffix] : ['group_ref', base, suffix];
      }
      if (regions !== null && regions.has(base)) {
        return mode === 'star' ? ['region_abs', base, suffix] : ['region_ref', base, suffix];
      }
      fail(`Taskipelago: unknown name '${base}' in ${label} on ${loc}.`);
    }
    fail(`Taskipelago: unexpected token '${tok}' in ${label} on ${loc}.`);
  }

  const result = parseExpr();
  if (pos !== tokens.length) {
    fail(`Taskipelago: unexpected token '${tokens[pos]}' in ${label} on ${loc}.`);
  }
  return result;
}

// ---------------------------------------------------------------------------
// Cost expressions
// ---------------------------------------------------------------------------

function readCount(chars, j) {
  // "*N" after a name or index; returns [count, nextIndex]
  if (j < chars.length && chars[j] === '*') {
    let k = j + 1;
    while (k < chars.length && isDigit(chars[k])) k++;
    if (k > j + 1) return [Number(chars.slice(j + 1, k).join('')), k];
  }
  return [1, j];
}

function tokenizeCost(chars, itemNamesOrdered) {
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
      const [count, next] = readCount(chars, j + 1);
      tokens.push(['cost_item', name, count]);
      i = next;
      continue;
    }

    if (isDigit(c)) {
      let j = i;
      while (j < chars.length && isDigit(chars[j])) j++;
      const idx = BigInt(chars.slice(i, j).join(''));
      const [count, next] = readCount(chars, j);
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
export function parseCostExpr(text, consumableNames, itemNamesOrdered = null) {
  const chars = pyStrip(text);
  if (!chars.length) return null;

  const consumables = toSet(consumableNames) || new Set();
  const tokens = tokenizeCost(chars, itemNamesOrdered);
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
