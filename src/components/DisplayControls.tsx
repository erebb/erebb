import { Maximize2, Minimize2, Monitor, Moon, Sun } from 'lucide-react';
import { cn } from '@/lib/utils';
import { THEME_LABELS, useFullscreen, useTheme, type ThemePref } from '@/lib/display';

/**
 * Tam ekran düğmesi. Çalışma ekranlarının başlığında durur: tam ekranda Dock, menü çubuğu ve
 * diğer pencereler görünmez, yalnız çalışılan içerik kalır. `tone="dark"` Akış'ın koyu sahnesi için.
 */
export function FullscreenButton({ tone = 'default', className }: { tone?: 'default' | 'dark'; className?: string }) {
  const { on, toggle, supported } = useFullscreen();
  if (!supported) return null;
  const label = on ? 'Tam ekrandan çık' : 'Tam ekran';
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={`${label} (⌃⌘F)`}
      aria-pressed={on}
      data-fullscreen-toggle=""
      className={cn(
        'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors',
        tone === 'dark'
          ? 'text-white/70 hover:bg-white/10 hover:text-white'
          : 'text-duo-gray-500 hover:bg-duo-gray-100 hover:text-duo-gray-700',
        className
      )}
    >
      {on ? <Minimize2 className="h-[18px] w-[18px]" /> : <Maximize2 className="h-[18px] w-[18px]" />}
    </button>
  );
}

const THEME_ICONS: Record<ThemePref, typeof Sun> = { system: Monitor, light: Sun, dark: Moon };

/** Tema seçimi: Sistem (macOS'u izler) · Açık · Koyu. */
export function ThemeSwitcher() {
  const [pref, setPref] = useTheme();
  return (
    <div role="radiogroup" aria-label="Tema" className="inline-flex rounded-xl border border-duo-gray-100 bg-surface p-0.5">
      {(Object.keys(THEME_LABELS) as ThemePref[]).map((p) => {
        const Icon = THEME_ICONS[p];
        const active = pref === p;
        return (
          <button
            key={p}
            type="button"
            role="radio"
            aria-checked={active}
            data-theme-option={p}
            onClick={() => setPref(p)}
            className={cn(
              'inline-flex h-8 items-center gap-1.5 rounded-[0.6rem] px-2.5 text-xs font-medium transition-colors',
              active ? 'bg-duo-gray-100 text-duo-gray-700' : 'text-duo-gray-500 hover:text-duo-gray-700'
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {THEME_LABELS[p]}
          </button>
        );
      })}
    </div>
  );
}
