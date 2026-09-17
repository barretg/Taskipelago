import { splitNameSuffix } from './prereq_parser.js';

// Client-side prereq evaluator (port of legacy_client/client.py _eval_prereq_expr).
// Unknown input evaluates to true so a bad expression never locks the UI.
export function evalPrereqExpr(text, leafFn, nameFn) {
  text = (text || '').trim();
  if (!text) return true;

  const tokens = [];
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (c === ' ' || c === '\t') { i++; continue; }
    if (/\d/.test(c)) {
      let j = i;
      while (j < text.length && /\d/.test(text[j])) j++;
      tokens.push(parseInt(text.slice(i, j), 10));
      i = j;
    } else if (text.slice(i, i + 2) === '&&') { tokens.push('&&'); i += 2; }
    else if (text.slice(i, i + 2) === '||') { tokens.push('||'); i += 2; }
    else if (c === '(' || c === ')' || c === ',') { tokens.push(c); i++; }
    else if (/[\p{L}_]/u.test(c)) {
      let j = i;
      while (j < text.length) {
        const ch = text[j];
        if (ch === ' ' || ch === '\t' || ch === '(' || ch === ')' || ch === ',') break;
        if (text.slice(j, j + 2) === '&&' || text.slice(j, j + 2) === '||') break;
        j++;
      }
      tokens.push(text.slice(i, j)); // raw name token e.g. "Infamy*5"
      i = j;
    } else { i++; } // skip unknown chars
  }

  let pos = 0;
  const peek = () => (pos < tokens.length ? tokens[pos] : null);
  const consume = () => tokens[pos++];

  const parseOr = () => {
    const results = [parseAnd()];
    while (peek() === '||') { consume(); results.push(parseAnd()); }
    return results.some(Boolean);
  };
  const parseAnd = () => {
    const results = [parseAtom()];
    while (peek() === '&&' || peek() === ',') { consume(); results.push(parseAtom()); }
    return results.every(Boolean);
  };
  const parseAtom = () => {
    const tok = peek();
    if (tok === '(') { consume(); const v = parseOr(); consume(); return v; }
    if (typeof tok === 'number') { consume(); return leafFn(tok); }
    if (typeof tok === 'string' && tok !== '&&' && tok !== '||' && tok !== '(' && tok !== ')' && tok !== ',') {
      consume();
      if (nameFn) {
        const [base, n, mode] = splitNameSuffix(tok);
        return nameFn(base, mode === 'star' ? n : null);
      }
      return true;
    }
    if (tok !== null) consume();
    return true;
  };

  try { return parseOr(); } catch (_) { return true; }
}
