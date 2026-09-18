// Expression rewriting helpers shared by the YAML generator: import/export
// index remapping now (ports of legacy_client/client.py:347-477), rename and
// reorder reference updates later (v1.1_PLAN B0, F4, F10).
//
// indexMap[k] lists the new 1-based indices for old index k+1.
// Digits are ASCII only (Python's str.isdigit also accepts other Unicode digits).
import { isPySpace } from './pyish.js';
import { splitNameSuffix } from './prereq_parser.js';

const isDigit = c => c >= '0' && c <= '9';
const isAlpha = c => /^\p{L}$/u.test(c);

function findQuote(chars, from) {
  for (let j = from; j < chars.length; j++) if (chars[j] === '"') return j;
  return -1;
}

const pair = (chars, i) => chars[i] + (chars[i + 1] ?? '');

/**
 * Port of _remap_prereq_indices: several targets become an OR group. With
 * collapse false (one-to-one maps, F10 reorder) the legacy "(n || n)" cleanup
 * is skipped so untouched text stays exactly as typed.
 * INDEX*Y keeps its count: several targets become an AND of the first Y.
 */
export function remapPrereqIndices(text, indexMap, collapse = true) {
  if (!text) return text;
  const chars = Array.from(text);
  const n = chars.length;
  const out = [];
  let i = 0;
  while (i < n) {
    const c = chars[i];
    if (isPySpace(c)) { out.push(c); i++; continue; }
    const two = pair(chars, i);
    if (two === '&&' || two === '||') { out.push(two); i += 2; continue; }
    if (c === '(' || c === ')' || c === ',') { out.push(c); i++; continue; }
    if (c === '"') {
      const q = findQuote(chars, i + 1);
      let j = q < 0 ? n : q + 1;
      // "Name"*Y: the count is not an index
      let k = j + 1;
      while (k < n && isDigit(chars[k])) k++;
      if (chars[j] === '*' && k > j + 1) j = k;
      out.push(chars.slice(i, j).join(''));
      i = j;
      continue;
    }
    if (isAlpha(c) || c === '_') {
      let j = i;
      while (j < n) {
        const ch = chars[j];
        if (isPySpace(ch) || ch === '(' || ch === ')' || ch === ',') break;
        const p = pair(chars, j);
        if (p === '&&' || p === '||') break;
        j++;
      }
      out.push(chars.slice(i, j).join(''));
      i = j;
      continue;
    }
    if (isDigit(c)) {
      let j = i;
      while (j < n && isDigit(chars[j])) j++;
      const run = chars.slice(i, j).join('');
      const old = Number(run);
      const next = old >= 1 && old <= indexMap.length ? indexMap[old - 1] : [];
      let k = j + 1;
      while (k < n && isDigit(chars[k])) k++;
      if (chars[j] === '*' && k > j + 1) {
        const countText = chars.slice(j + 1, k).join('');
        const y = Number(countText);
        if (next.length === 1) out.push(`${next[0]}*${countText}`);
        else if (next.length > 1 && y >= 1) {
          const take = next.slice(0, y);
          out.push(take.length === 1 ? String(take[0]) : '(' + take.join(' && ') + ')');
        } else out.push(`${run}*${countText}`);
        i = k;
        continue;
      }
      if (next.length === 1) out.push(String(next[0]));
      else if (next.length > 1) out.push('(' + next.join(' || ') + ')');
      else out.push(run);
      i = j;
      continue;
    }
    out.push(c);
    i++;
  }

  // Collapse "(n || n || n)" groups left when several old indices map to one new row.
  let result = out.join('');
  if (!collapse) return result;
  let prev = null;
  while (prev !== result) {
    prev = result;
    // Counts of INDEX*Y / "Name"*Y are not indices (legacy NAME*N handling is kept as it was).
    result = result.replace(/(?<![\d"]\*)(\b\d+\b)(?!\*)(?:\s*\|\|\s*\1\b(?!\*))+/g, '$1');
  }
  return result.replace(/\(\s*(\d+)\s*\)/g, '$1');
}

/**
 * Import-side inverse of the INDEX*Y expansion: "(a && b && ...)" whose
 * indices are exactly the first m >= 2 flat entries of one row (flatToRow
 * as in remapPrereqIndices) becomes "a*m". Run before remapPrereqIndices.
 * Quoted names are left alone.
 */
export function collapseCopyGroups(text, flatToRow) {
  if (!text) return text;
  const rowFlats = new Map();
  flatToRow.forEach((rows, k) => {
    if (rows.length !== 1) return;
    if (!rowFlats.has(rows[0])) rowFlats.set(rows[0], []);
    rowFlats.get(rows[0]).push(k + 1);
  });
  return text.split(/("[^"]*")/).map((part, p) => (p % 2 ? part : part.replace(
    /\(\s*\d+(?:\s*&&\s*\d+)+\s*\)/g,
    group => {
      const nums = group.match(/\d+/g).map(Number);
      const rows = flatToRow[nums[0] - 1];
      if (!rows || rows.length !== 1) return group;
      const flats = rowFlats.get(rows[0]);
      return nums.every((v, x) => flats[x] === v) ? `${nums[0]}*${nums.length}` : group;
    },
  ))).join('');
}

/** Port of _remap_cost_indices: a digit run right after '*' is a count, not an index. */
export function remapCostIndices(text, indexMap) {
  if (!text) return text;
  const chars = Array.from(text);
  const n = chars.length;
  const out = [];
  let i = 0;
  while (i < n) {
    const c = chars[i];
    if (c === '"') {
      const q = findQuote(chars, i + 1);
      const j = q < 0 ? n : q + 1;
      out.push(chars.slice(i, j).join(''));
      i = j;
      continue;
    }
    if (isDigit(c)) {
      let j = i;
      while (j < n && isDigit(chars[j])) j++;
      const run = chars.slice(i, j).join('');
      let k = out.length - 1;
      while (k >= 0 && out[k] !== '' && [...out[k]].every(isPySpace)) k--;
      if (k >= 0 && out[k].endsWith('*')) {
        out.push(run);
      } else {
        const old = Number(run);
        const next = old >= 1 && old <= indexMap.length ? indexMap[old - 1] : [];
        out.push(next.length ? String(next[0]) : run);
      }
      i = j;
      continue;
    }
    out.push(c);
    i++;
  }
  return out.join('');
}

/**
 * v1.1 B0: rename region / group name tokens (the same token walk as
 * remapPrereqIndices). Quoted strings and integers are copied verbatim; a name
 * token whose base (splitNameSuffix) equals oldName keeps its -N / *N suffix.
 * Returns { text, count } with the number of tokens changed.
 */
export function renameNameRefs(text, oldName, newName) {
  if (!text) return { text, count: 0 };
  const chars = Array.from(text);
  const n = chars.length;
  const out = [];
  let count = 0;
  let i = 0;
  while (i < n) {
    const c = chars[i];
    if (c === '"') {
      const q = findQuote(chars, i + 1);
      const j = q < 0 ? n : q + 1;
      out.push(chars.slice(i, j).join(''));
      i = j;
      continue;
    }
    if (isAlpha(c) || c === '_') {
      let j = i;
      while (j < n) {
        const ch = chars[j];
        if (isPySpace(ch) || ch === '(' || ch === ')' || ch === ',') break;
        const p = pair(chars, j);
        if (p === '&&' || p === '||') break;
        j++;
      }
      const tok = chars.slice(i, j).join('');
      const [base] = splitNameSuffix(tok);
      if (base === oldName) {
        out.push(newName + tok.slice(base.length));
        count++;
      } else {
        out.push(tok);
      }
      i = j;
      continue;
    }
    if (isDigit(c)) {
      let j = i;
      while (j < n && isDigit(chars[j])) j++;
      out.push(chars.slice(i, j).join(''));
      i = j;
      continue;
    }
    out.push(c);
    i++;
  }
  return { text: out.join(''), count };
}

/** Number of name tokens in text that reference name (with or without a suffix). */
export const countNameRefs = (text, name) => renameNameRefs(text, name, name).count;
