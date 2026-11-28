import { useCallback, useEffect, useState } from 'react';
import { STORAGE_KEYS } from '@/lib/storageKeys';
import { isTauri } from '@/lib/updates';

// ---------------- Tema ----------------

export type ThemePref = 'system' | 'light' | 'dark';
export const THEME_LABELS: Record<ThemePref, string> = { system: 'Sistem', light: 'Açık', dark: 'Koyu' };

export function readThemePref(): ThemePref {
  try {
    const v = JSON.parse(window.localStorage.getItem(STORAGE_KEYS.theme) ?? '"system"');
    return v === 'light' || v === 'dark' ? v : 'system';
  } catch {
    return 'system';
  }
}

/** "Sistem"de data-theme yok: CSS `prefers-color-scheme` ile macOS'u izler. */
export function applyTheme(pref: ThemePref) {
  const root = document.documentElement;
  if (pref === 'system') delete root.dataset.theme;
  else root.dataset.theme = pref;
}

export function useTheme(): [ThemePref, (p: ThemePref) => void] {
  const [pref, setPref] = useState<ThemePref>(readThemePref);
  const set = useCallback((p: ThemePref) => {
    setPref(p);
    applyTheme(p);
    try {
      window.localStorage.setItem(STORAGE_KEYS.theme, JSON.stringify(p));
    } catch {
      // depolama yok — yalnız bu oturumda geçerli
    }
  }, []);
  return [pref, set];
}

// ---------------- Tam ekran ----------------
// Mac uygulamasında pencerenin kendisi tam ekrana geçer (macOS tam ekranı, ayrı Space);
// tarayıcıda Fullscreen API kullanılır. WKWebView'da öğe tam ekranı kapalı olduğu için
// uygulamada pencere API'si şart.

type WebkitDoc = Document & { webkitFullscreenElement?: Element | null; webkitExitFullscreen?: () => Promise<void> };
type WebkitEl = HTMLElement & { webkitRequestFullscreen?: () => Promise<void> };

async function tauriWindow() {
  const { getCurrentWindow } = await import('@tauri-apps/api/window');
  return getCurrentWindow();
}

export async function isFullscreen(): Promise<boolean> {
  if (isTauri()) return (await tauriWindow()).isFullscreen();
  const d = document as WebkitDoc;
  return Boolean(d.fullscreenElement ?? d.webkitFullscreenElement);
}

export async function setFullscreen(on: boolean): Promise<void> {
  if (isTauri()) {
    await (await tauriWindow()).setFullscreen(on);
    return;
  }
  const d = document as WebkitDoc;
  const el = document.documentElement as WebkitEl;
  if (on) await (el.requestFullscreen?.() ?? el.webkitRequestFullscreen?.());
  else if (d.fullscreenElement ?? d.webkitFullscreenElement) await (d.exitFullscreen?.() ?? d.webkitExitFullscreen?.());
}

export const fullscreenSupported = (): boolean =>
  isTauri() ||
  (typeof document !== 'undefined' &&
    Boolean(document.fullscreenEnabled || (document.documentElement as WebkitEl).webkitRequestFullscreen));

/** Tam ekran durumu; macOS'un yeşil düğmesi, menü (⌃⌘F) ya da Esc ile değişince de güncellenir. */
export function useFullscreen(): { on: boolean; toggle: () => void; supported: boolean } {
  const [on, setOn] = useState(false);
  useEffect(() => {
    let alive = true;
    const sync = () => {
      isFullscreen()
        .then((v) => alive && setOn(v))
        .catch(() => {});
    };
    sync();
    // Pencere tam ekrana girip çıkarken boyutu değişir; tarayıcıda ayrıca fullscreenchange.
    window.addEventListener('resize', sync);
    document.addEventListener('fullscreenchange', sync);
    document.addEventListener('webkitfullscreenchange', sync);
    return () => {
      alive = false;
      window.removeEventListener('resize', sync);
      document.removeEventListener('fullscreenchange', sync);
      document.removeEventListener('webkitfullscreenchange', sync);
    };
  }, []);
  const toggle = useCallback(() => {
    setFullscreen(!on)
      .then(() => isFullscreen())
      .then(setOn)
      .catch(() => {});
  }, [on]);
  return { on, toggle, supported: fullscreenSupported() };
}
