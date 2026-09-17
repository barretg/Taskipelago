// YAML 1.1 (PyYAML safe_load) scalar resolution for js-yaml 4 (UNIFY 5.3).
//
// js-yaml implements YAML 1.2, where yes/no/on/off, 017, 0x1F, 1_000 and 1:30
// are plain strings. The apworld and the legacy generator read YAML with
// PyYAML, so the web generator loads and dumps through this schema instead:
//   - loading gives the values PyYAML gives (floats as PyFloat, timestamps as PyDate)
//   - dumping quotes every string PyYAML would otherwise resolve to another type
// Known gap: mapping keys are always strings in JS, so an unquoted `true:` key
// reads as "true" here but as the bool True in PyYAML.
import * as vendored from '../../vendor/js-yaml.min.js';
import { PyFloat, PyDate, floatRepr } from './pyish.js';

const jsyaml = globalThis.jsyaml || vendored.default || vendored;
const { Type, FAILSAFE_SCHEMA } = jsyaml;

const NULL_RE = /^(?:~|null|Null|NULL|)$/;
const BOOL_RE = /^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$/;
const TRUE_WORDS = new Set(['yes', 'Yes', 'YES', 'true', 'True', 'TRUE', 'on', 'On', 'ON']);
const INT_RE = /^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$/;
const FLOAT_RE = /^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$/;
const TIMESTAMP_RE = /^(?:([0-9]{4})-([0-9]{2})-([0-9]{2})|([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})(?:[Tt]|[ \t]+)([0-9]{1,2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]*))?(?:[ \t]*(Z|([-+])([0-9]{1,2})(?::([0-9]{2}))?))?)$/;

function sexagesimal(text) {
  let base = 1;
  let value = 0;
  for (const part of text.split(':').reverse()) {
    value += Number(part) * base;
    base *= 60;
  }
  return value;
}

function constructInt(data) {
  let value = data.replace(/_/g, '');
  let sign = 1;
  if (value[0] === '-' || value[0] === '+') {
    if (value[0] === '-') sign = -1;
    value = value.slice(1);
  }
  const parse = (digits, base) => {
    const n = parseInt(digits, base);
    if (digits === '' || Number.isNaN(n)) throw new Error(`invalid int literal ${JSON.stringify(data)}`);
    return n;
  };
  if (value === '0') return 0;
  if (value.startsWith('0b')) return sign * parse(value.slice(2), 2);
  if (value.startsWith('0x')) return sign * parse(value.slice(2), 16);
  if (value[0] === '0') return sign * parse(value, 8);
  if (value.includes(':')) return sign * sexagesimal(value);
  return sign * parse(value, 10);
}

function constructFloat(data) {
  let value = data.replace(/_/g, '').toLowerCase();
  let sign = 1;
  if (value[0] === '-' || value[0] === '+') {
    if (value[0] === '-') sign = -1;
    value = value.slice(1);
  }
  if (value === '.inf') return new PyFloat(sign * Infinity);
  if (value === '.nan') return new PyFloat(NaN);
  if (value.includes(':')) return new PyFloat(sign * sexagesimal(value));
  return new PyFloat(sign * Number(value));
}

const pad = (n, w = 2) => String(n).padStart(w, '0');

function constructTimestamp(data) {
  const m = TIMESTAMP_RE.exec(data);
  const dateOnly = m[1] !== undefined;
  const year = Number(dateOnly ? m[1] : m[4]);
  const month = Number(dateOnly ? m[2] : m[5]);
  const day = Number(dateOnly ? m[3] : m[6]);
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  if (month < 1 || month > 12 || day < 1 || day > daysInMonth || year < 1) {
    throw new Error(`invalid date ${JSON.stringify(data)}`);
  }
  const date = `${pad(year, 4)}-${pad(month)}-${pad(day)}`;
  if (dateOnly) return new PyDate(date);
  const [hour, minute, second] = [m[7], m[8], m[9]].map(Number);
  if (hour > 23 || minute > 59 || second > 59) throw new Error(`invalid time ${JSON.stringify(data)}`);
  let text = `${date} ${pad(hour)}:${pad(minute)}:${pad(second)}`;
  if (m[10]) {
    const micro = Number(m[10].slice(0, 6).padEnd(6, '0'));
    if (micro) text += `.${pad(micro, 6)}`;
  }
  if (m[12]) {
    const h = Number(m[13]);
    const mm = Number(m[14] || 0);
    text += `${m[12]}${pad(h)}:${pad(mm)}`;
  } else if (m[11]) {
    text += '+00:00';
  }
  return new PyDate(text);
}

const nullType = new Type('tag:yaml.org,2002:null', {
  kind: 'scalar',
  resolve: data => NULL_RE.test(data),
  construct: () => null,
  predicate: v => v === null,
  represent: () => 'null',
});

const boolType = new Type('tag:yaml.org,2002:bool', {
  kind: 'scalar',
  resolve: data => BOOL_RE.test(data),
  construct: data => TRUE_WORDS.has(data),
  predicate: v => typeof v === 'boolean',
  represent: v => (v ? 'true' : 'false'),
});

const intType = new Type('tag:yaml.org,2002:int', {
  kind: 'scalar',
  resolve: data => INT_RE.test(data),
  construct: constructInt,
  predicate: v => typeof v === 'number' && Number.isInteger(v),
  represent: v => String(v),
});

const floatType = new Type('tag:yaml.org,2002:float', {
  kind: 'scalar',
  resolve: data => FLOAT_RE.test(data),
  construct: constructFloat,
  instanceOf: PyFloat,
  represent: v => {
    if (Number.isNaN(v.value)) return '.nan';
    if (!Number.isFinite(v.value)) return v.value > 0 ? '.inf' : '-.inf';
    return floatRepr(v.value);
  },
});

const timestampType = new Type('tag:yaml.org,2002:timestamp', {
  kind: 'scalar',
  resolve: data => TIMESTAMP_RE.test(data),
  construct: constructTimestamp,
  instanceOf: PyDate,
  represent: v => v.text,
});

// PyYAML resolves a bare `=` to tag:yaml.org,2002:value, which safe_load cannot construct.
const valueType = new Type('tag:yaml.org,2002:value', {
  kind: 'scalar',
  resolve: data => data === '=',
  construct: () => {
    throw new Error("could not determine a constructor for the tag 'tag:yaml.org,2002:value'");
  },
});

// Same order PyYAML registers its implicit resolvers in.
export const YAML11_SCHEMA = FAILSAFE_SCHEMA.extend({
  implicit: [boolType, floatType, intType, jsyaml.types.merge, nullType, timestampType, valueType],
});

export const YAMLException = jsyaml.YAMLException;

/** yaml.safe_load: duplicate keys keep the last value, like PyYAML. */
export function loadYaml(text) {
  return jsyaml.load(text, { schema: YAML11_SCHEMA, json: true });
}

/** yaml.dump(data, sort_keys=False, allow_unicode=True), read back identically by PyYAML. */
export function dumpYaml(data) {
  return jsyaml.dump(data, { schema: YAML11_SCHEMA, sortKeys: false, lineWidth: -1, noRefs: true });
}
