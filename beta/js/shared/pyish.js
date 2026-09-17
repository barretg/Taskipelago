// Python value semantics used by the YAML Generator ports (UNIFY 5.3).
//
// The legacy Tk generator read PyYAML documents and ran str(), int(), bool()
// and list() over whatever it found. Imports stay compatible with every YAML
// the legacy client accepted only if those conversions behave the same here,
// so this module models them over the values produced by shared/yaml11.js.

export const PY_SPACE = new Set([
  ' ', '\t', '\n', '\r', '\x0b', '\x0c', '\x1c', '\x1d', '\x1e', '\x1f', '\x85', '\xa0',
  '\u1680', '\u2028', '\u2029', '\u202f', '\u205f', '\u3000',
]);
for (let cp = 0x2000; cp <= 0x200a; cp++) PY_SPACE.add(String.fromCodePoint(cp));

export const isPySpace = c => PY_SPACE.has(c);

export class PyError extends Error {
  constructor(type, message) {
    super(message);
    this.pyType = type;
  }
}

/** A YAML float. JS numbers from the loader are always Python ints. */
export class PyFloat {
  constructor(value) { this.value = value; }
}

/** A YAML timestamp; text is Python's str() of the date/datetime. */
export class PyDate {
  constructor(text) { this.text = text; }
}

export function isDict(v) {
  if (v === null || typeof v !== 'object') return false;
  const proto = Object.getPrototypeOf(v);
  return proto === Object.prototype || proto === null;
}

/** dict.get(key, fallback): a present key with a null value returns null. */
export function pyGet(dict, key, fallback = null) {
  return Object.hasOwn(dict, key) ? dict[key] : fallback;
}

export function pyStrip(s) {
  const chars = Array.from(s);
  let a = 0;
  let b = chars.length;
  while (a < b && isPySpace(chars[a])) a++;
  while (b > a && isPySpace(chars[b - 1])) b--;
  return chars.slice(a, b).join('');
}

/** s[:n] by code point. */
export function pySlice(s, n) {
  const chars = Array.from(s);
  return chars.length <= n ? s : chars.slice(0, n).join('');
}

export function floatRepr(x) {
  if (Number.isNaN(x)) return 'nan';
  if (x === Infinity) return 'inf';
  if (x === -Infinity) return '-inf';
  if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0';
  const [mant, expText] = x.toExponential().split('e');
  const exp = Number(expText);
  if (exp >= -4 && exp < 16) {
    const neg = mant.startsWith('-');
    const digits = mant.replace('-', '').replace('.', '');
    let out;
    if (exp >= 0) {
      const intPart = digits.slice(0, exp + 1).padEnd(exp + 1, '0');
      const frac = digits.slice(exp + 1);
      out = `${intPart}.${frac || '0'}`;
    } else {
      out = `0.${'0'.repeat(-exp - 1)}${digits}`;
    }
    return (neg ? '-' : '') + out;
  }
  const sign = exp < 0 ? '-' : '+';
  return `${mant}e${sign}${String(Math.abs(exp)).padStart(2, '0')}`;
}

function reprStr(value) {
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

export function pyRepr(v) {
  if (typeof v === 'string') return reprStr(v);
  if (Array.isArray(v)) return `[${v.map(pyRepr).join(', ')}]`;
  if (isDict(v)) return `{${Object.entries(v).map(([k, x]) => `${reprStr(k)}: ${pyRepr(x)}`).join(', ')}}`;
  if (v instanceof PyDate) return `<date ${v.text}>`;
  return pyStr(v);
}

export function pyStr(v) {
  if (typeof v === 'string') return v;
  if (v === null || v === undefined) return 'None';
  if (v === true) return 'True';
  if (v === false) return 'False';
  if (typeof v === 'number') return String(v);
  if (v instanceof PyFloat) return floatRepr(v.value);
  if (v instanceof PyDate) return v.text;
  return pyRepr(v);
}

function typeName(v) {
  if (v === null || v === undefined) return 'NoneType';
  if (Array.isArray(v)) return 'list';
  if (isDict(v)) return 'dict';
  if (v instanceof PyDate) return 'datetime.date';
  return typeof v;
}

const INT_TEXT = /^[-+]?[0-9](?:_?[0-9])*$/;

/** int(v); throws PyError('TypeError' | 'ValueError' | 'OverflowError'). */
export function pyInt(v) {
  if (v === true) return 1;
  if (v === false) return 0;
  if (typeof v === 'number') return Math.trunc(v);
  if (v instanceof PyFloat) {
    if (Number.isNaN(v.value)) throw new PyError('ValueError', 'cannot convert float NaN to integer');
    if (!Number.isFinite(v.value)) throw new PyError('OverflowError', 'cannot convert float infinity to integer');
    return Math.trunc(v.value);
  }
  if (typeof v === 'string') {
    const t = pyStrip(v);
    if (!INT_TEXT.test(t)) throw new PyError('ValueError', `invalid literal for int() with base 10: ${reprStr(v)}`);
    return Number(t.replace(/_/g, ''));
  }
  throw new PyError('TypeError', `int() argument must be a string, a bytes-like object or a real number, not '${typeName(v)}'`);
}

export function pyTruthy(v) {
  if (v === null || v === undefined || v === false || v === 0 || v === '') return false;
  if (v instanceof PyFloat) return v.value !== 0;
  if (Array.isArray(v)) return v.length > 0;
  if (isDict(v)) return Object.keys(v).length > 0;
  return true;
}

/** list(v) */
export function pyList(v) {
  if (Array.isArray(v)) return [...v];
  if (typeof v === 'string') return Array.from(v);
  if (isDict(v)) return Object.keys(v);
  throw new PyError('TypeError', `'${typeName(v)}' object is not iterable`);
}

/** list(block.get(key, []) or []) */
export function pyListOr(dict, key, fallback = []) {
  const v = pyGet(dict, key, fallback);
  return pyTruthy(v) ? pyList(v) : [];
}
