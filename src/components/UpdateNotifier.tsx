import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Download, RefreshCw, Sparkles, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  compareVersions,
  fetchLatestRelease,
  installAppUpdate,
  isTauri,
  openExternal,
  relaunchApp,
  updateContentFrom,
  type LatestRelease,
} from '@/lib/updates';

type AppNotice =
  | { kind: 'downloading'; fraction: number | null }
  | { kind: 'ready'; version: string }
  | { kind: 'available'; version: string; url: string };

// StrictMode efektleri iki kez çalıştırır; denetim uygulama ömründe bir kez yapılsın.
let started = false;

/**
 * Açılışta güncelleme denetimi: önce içerik (yeni/düzeltilmiş setler), sonra Mac uygulaması.
 * Hata ya da çevrimdışı durumda sessiz kalır — uygulama her zaman gömülü içerikle çalışır.
 */
export function UpdateNotifier() {
  const [contentNames, setContentNames] = useState<string[] | null>(null);
  const [app, setApp] = useState<AppNotice | null>(null);

  useEffect(() => {
    if (started) return;
    started = true;
    if (typeof navigator !== 'undefined' && navigator.onLine === false) return;
    void (async () => {
      let latest: LatestRelease | null = null;
      try {
        latest = await fetchLatestRelease();
      } catch {
        // ağ yok / GitHub erişilemez
      }
      if (latest) {
        try {
          const changed = await updateContentFrom(latest.tag);
          if (changed.length) setContentNames(changed);
        } catch {
          // içerik okunamadı — bir sonraki açılışta yeniden denenir
        }
      }
      if (!isTauri()) return;
      try {
        const version = await installAppUpdate((fraction) => setApp({ kind: 'downloading', fraction }));
        setApp(version ? { kind: 'ready', version } : null);
      } catch {
        // İmzalı güncelleme yoksa ya da kurulamadıysa: daha yeni sürüm varsa bağlantı göster.
        setApp(
          latest && compareVersions(latest.version, __APP_VERSION__) > 0
            ? { kind: 'available', version: latest.version, url: latest.url }
            : null
        );
      }
    })();
  }, []);

  // İçerik bildirimi kendiliğinden kapanır.
  useEffect(() => {
    if (!contentNames) return;
    const t = window.setTimeout(() => setContentNames(null), 12000);
    return () => window.clearTimeout(t);
  }, [contentNames]);

  const shown = contentNames
    ? contentNames.length > 3
      ? `${contentNames.slice(0, 3).join(', ')} ve ${contentNames.length - 3} set daha`
      : contentNames.join(', ')
    : '';

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4">
      <AnimatePresence>
        {contentNames && (
          <Toast key="content" onClose={() => setContentNames(null)} kind="content">
            <Sparkles className="h-5 w-5 shrink-0 text-duo-green" />
            <p className="min-w-0 flex-1">
              <span className="font-extrabold">Yeni içerik yüklendi:</span> {shown}
            </p>
          </Toast>
        )}
        {app?.kind === 'downloading' && (
          <Toast key="downloading" kind="downloading">
            <Download className="h-5 w-5 shrink-0 animate-pulse text-duo-blue" />
            <p className="min-w-0 flex-1 font-bold">
              Yeni sürüm indiriliyor{app.fraction !== null ? ` · %${Math.round(app.fraction * 100)}` : '…'}
            </p>
          </Toast>
        )}
        {app?.kind === 'ready' && (
          <Toast key="ready" onClose={() => setApp(null)} kind="ready">
            <RefreshCw className="h-5 w-5 shrink-0 text-duo-green" />
            <p className="min-w-0 flex-1">
              <span className="font-extrabold">Sürüm {app.version} yüklendi.</span> Bir sonraki açılışta başlar.
            </p>
            <Button size="sm" onClick={() => void relaunchApp()}>
              Şimdi başlat
            </Button>
          </Toast>
        )}
        {app?.kind === 'available' && (
          <Toast key="available" onClose={() => setApp(null)} kind="available">
            <Download className="h-5 w-5 shrink-0 text-duo-blue" />
            <p className="min-w-0 flex-1">
              <span className="font-extrabold">Yeni sürüm var: {app.version}</span>
            </p>
            <Button size="sm" variant="blue" onClick={() => void openExternal(app.url)}>
              İndir
            </Button>
          </Toast>
        )}
      </AnimatePresence>
    </div>
  );
}

function Toast({
  children,
  onClose,
  kind,
}: {
  children: React.ReactNode;
  onClose?: () => void;
  kind: string;
}) {
  return (
    <motion.div
      role="status"
      aria-live="polite"
      data-update-toast={kind}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 16 }}
      className="pointer-events-auto flex w-full max-w-md items-center gap-3 rounded-2xl border-2 border-duo-gray-100 bg-white p-3 text-sm text-duo-gray-700 shadow-lg"
    >
      {children}
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Bildirimi kapat"
          className="rounded-lg p-1 text-duo-gray-300 hover:bg-duo-gray-50 hover:text-duo-gray-500"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </motion.div>
  );
}
