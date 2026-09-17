// Port of legacy_client/client.py:286-312 (FILLER_ITEMS, LEGACY_FILLER_TOKEN,
// _is_filler, _random_filler). Must match items.py FILLER_ITEMS.
export const FILLER_ITEMS = [
  'Several pats on the back',
  'A big thumbs up',
  'Free dopamine',
  'One (1) sense of accomplishment',
  'Mildly increased self-esteem',
  'A crisp high five',
  'A firm handshake',
  'A tiny mental victory parade',
  'Temporary immunity to self-criticism',
  'An imaginary star sticker',
  'A nod of respect',
];
export const LEGACY_FILLER_TOKEN = 'nothing here, get pranked nerd';

const FILLER_SET = new Set([...FILLER_ITEMS, LEGACY_FILLER_TOKEN]);

// Play-tab check: tolerant of surrounding whitespace.
export function isFiller(s) { return FILLER_SET.has((s || '').trim()); }

// Exact-match check, identical to legacy _is_filler (generator import/export).
export function isFillerExact(s) { return FILLER_SET.has(s); }

export function randomFiller() {
  return FILLER_ITEMS[Math.floor(Math.random() * FILLER_ITEMS.length)];
}
