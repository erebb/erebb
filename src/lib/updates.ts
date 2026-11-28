import { isManifest, SUPPORTED_SCHEMA, syncContent } from '@/content/seed';
import { STORAGE_RELOAD_EVENT } from '@/hooks/useLocalStorage';

/**
 * Güncellemeler. CI her başarılı commit'te GitHub'da yeni bir sürüm (Release) yayımlar:
 * - İçerik: açılışta son sürümün `content/manifest.json`'u okunur; sürümü yükselen setler
 *   indirilip eşitlenir (uygulamayı yeniden kurmadan yeni sorular gelir).
 * - Uygulama (Mac): Tauri updater son sürümün imzalı paketini indirip kurar; imza anahtarı
 *   henüz yoksa yalnızca "yeni sürüm var" bildirimi gösterilir.
 * Kullanıcı verisi hiçbir yere gönderilmez; yalnızca herkese açık dosyalar okunur.
 */
export const REPO = 'erebb/erebb';
export const RELEASES_URL = `https://github.com/${REPO}/releases/latest`;

async function getJson(url: string, timeoutMs = 10000): Promise<unknown> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctrl.signal, cache: 'no-store' });
    if (!res.ok) throw new Error(`${res.status} ${url}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/** "1.2.10" > "1.2.9" — sayısal karşılaştırma. */
export function compareVersions(a: string, b: string): number {
  const pa = a.split('.').map((n) => Number(n) || 0);
  const pb = b.split('.').map((n) => Number(n) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (d !== 0) return d > 0 ? 1 : -1;
  }
  return 0;
}

export interface LatestRelease {
  tag: string;
  version: string;
  url: string;
}

/** GitHub'daki en son yayımlanmış sürüm (yoksa ya da okunamazsa null). */
export async function fetchLatestRelease(): Promise<LatestRelease | null> {
  const rel = (await getJson(`https://api.github.com/repos/${REPO}/releases/latest`)) as {
    tag_name?: unknown;
    html_url?: unknown;
  };
  const tag = typeof rel?.tag_name === 'string' ? rel.tag_name : '';
  if (!/^v\d+\.\d+\.\d+$/.test(tag)) return null;
  return { tag, version: tag.slice(1), url: typeof rel.html_url === 'string' ? rel.html_url : RELEASES_URL };
}

/** O sürümdeki içerik manifest'ine göre setleri eşitler; güncellenen set adlarını döner. */
export async function updateContentFrom(tag: string): Promise<string[]> {
  const base = `https://raw.githubusercontent.com/${REPO}/${encodeURIComponent(tag)}/content/`;
  const manifest = await getJson(`${base}manifest.json`);
  if (!isManifest(manifest) || manifest.schema > SUPPORTED_SCHEMA) return [];
  const changed = await syncContent(manifest, async (file) => (await getJson(base + file)) as never);
  if (changed.length) window.dispatchEvent(new Event(STORAGE_RELOAD_EVENT));
  return changed;
}

export const isTauri = (): boolean => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

/**
 * Mac uygulamasında yeni sürüm varsa indirip kurar ve sürüm numarasını döner (güncelse null).
 * Kurulan sürüm bir sonraki açılışta (ya da relaunchApp ile hemen) başlar.
 */
export async function installAppUpdate(onProgress?: (fraction: number | null) => void): Promise<string | null> {
  const { check } = await import('@tauri-apps/plugin-updater');
  const update = await check({ timeout: 20000 });
  if (!update) return null;
  let total = 0;
  let done = 0;
  await update.downloadAndInstall((e) => {
    if (e.event === 'Started') total = e.data.contentLength ?? 0;
    else if (e.event === 'Progress') {
      done += e.data.chunkLength;
      onProgress?.(total > 0 ? Math.min(1, done / total) : null);
    }
  });
  return update.version;
}

export async function relaunchApp(): Promise<void> {
  const { relaunch } = await import('@tauri-apps/plugin-process');
  await relaunch();
}

/** Bağlantıyı sistem tarayıcısında açar. */
export async function openExternal(url: string): Promise<void> {
  if (isTauri()) {
    const { openUrl } = await import('@tauri-apps/plugin-opener');
    await openUrl(url);
  } else {
    window.open(url, '_blank', 'noopener,noreferrer');
  }
}
