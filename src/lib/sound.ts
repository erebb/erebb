import { STORAGE_KEYS } from '@/lib/storageKeys';

let ctx: AudioContext | null = null;

/** Sesler varsayılan olarak kapalı: beklenmedik ses dikkati dağıtır. Ana ekrandan açılır. */
export function soundEnabled(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEYS.sound) === 'true';
  } catch {
    return false;
  }
}

export function setSoundEnabled(on: boolean) {
  try {
    window.localStorage.setItem(STORAGE_KEYS.sound, on ? 'true' : 'false');
  } catch {
    // depolama yok
  }
}

function getCtx(): AudioContext | null {
  try {
    if (!ctx) ctx = new AudioContext();
    if (ctx.state === 'suspended') void ctx.resume();
    return ctx;
  } catch {
    return null;
  }
}

function tone(frequency: number, startAt: number, duration: number, volume = 0.08) {
  if (!soundEnabled()) return;
  const ac = getCtx();
  if (!ac) return;
  const osc = ac.createOscillator();
  const gain = ac.createGain();
  osc.type = 'sine';
  osc.frequency.value = frequency;
  gain.gain.setValueAtTime(volume, ac.currentTime + startAt);
  gain.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + startAt + duration);
  osc.connect(gain).connect(ac.destination);
  osc.start(ac.currentTime + startAt);
  osc.stop(ac.currentTime + startAt + duration);
}

/** Doğru cevap: yükselen iki nota. */
export function playCorrect() {
  tone(660, 0, 0.15);
  tone(880, 0.12, 0.2);
}

/** Yanlış cevap: alçalan iki nota. */
export function playIncorrect() {
  tone(330, 0, 0.18);
  tone(220, 0.15, 0.25);
}
