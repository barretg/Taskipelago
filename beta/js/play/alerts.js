// v1.1 F2: DeathLink alert extras. A WebAudio two-tone beep (no asset file), a
// flashing window title until focus returns, and a switch to the Notifications
// subtab. The sound is a device setting (taskipelago_ui.dlSound, default on).
import { els } from './state.js';
import { getUiPref, setUiPref } from '../shared/ui_prefs.js';

const ALERT_TITLE = 'DEATHLINK! - Taskipelago';
let audioCtx = null;

function audio() {
  if (audioCtx) return audioCtx;
  const Ctx = globalThis.AudioContext || globalThis.webkitAudioContext;
  if (!Ctx) return null;
  try {
    audioCtx = new Ctx();
  } catch (_) {
    audioCtx = null;
  }
  return audioCtx;
}

/**
 * Create / resume the AudioContext. Browsers only allow this after a user
 * gesture; the launcher's app window passes an autoplay flag instead.
 */
export function primeAudio() {
  const ctx = audio();
  if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {});
}

export const deathLinkSoundOn = () => getUiPref('dlSound', true) !== false;

/** Returns true when the beep was scheduled; a still-suspended context is skipped silently. */
export function playDeathLinkSound() {
  if (!deathLinkSoundOn()) return false;
  const ctx = audio();
  if (!ctx || ctx.state !== 'running') {
    primeAudio();
    return false;
  }
  const now = ctx.currentTime;
  for (const [freq, at] of [[880, 0], [587, 0.2]]) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'square';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, now + at);
    gain.gain.exponentialRampToValueAtTime(0.15, now + at + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + at + 0.18);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(now + at);
    osc.stop(now + at + 0.2);
  }
  return true;
}

let flashTimer = null;
let baseTitle = '';

function stopFlash() {
  if (!flashTimer) return;
  clearInterval(flashTimer);
  flashTimer = null;
  document.title = baseTitle;
}

/** Alternate the window title until the window regains focus. */
export function flashTitle() {
  if (flashTimer || (document.hasFocus && document.hasFocus())) return;
  baseTitle = document.title;
  let on = true;
  document.title = ALERT_TITLE;
  flashTimer = setInterval(() => {
    on = !on;
    document.title = on ? ALERT_TITLE : baseTitle;
  }, 1000);
  window.addEventListener('focus', stopFlash, { once: true });
}

/** Everything a triggered DeathLink does besides its notification card and task card. */
export function alertDeathLink() {
  playDeathLinkSound();
  flashTitle();
  document.querySelector('.sub-tabs .tab-btn[data-subtab="notifications"]')?.click();
}

export function initAlerts() {
  if (els.dlSoundCb) {
    els.dlSoundCb.checked = deathLinkSoundOn();
    els.dlSoundCb.addEventListener('change', () => {
      setUiPref('dlSound', els.dlSoundCb.checked);
      if (els.dlSoundCb.checked) primeAudio();
    });
  }
  // Hosted pages: the first gesture anywhere unlocks audio for later DeathLinks.
  const unlock = () => {
    removeEventListener('pointerdown', unlock, true);
    removeEventListener('keydown', unlock, true);
    primeAudio();
  };
  addEventListener('pointerdown', unlock, true);
  addEventListener('keydown', unlock, true);
}
