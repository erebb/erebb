import { X } from 'lucide-react';
import { FullscreenButton } from '@/components/DisplayControls';

export interface FeedTopBarProps {
  title: string;
  subtitle?: string;
  onExit: () => void;
}

export function FeedTopBar({ title, subtitle, onExit }: FeedTopBarProps) {
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 z-20 bg-gradient-to-b from-ink to-transparent pb-8 pt-[env(safe-area-inset-top)]">
      <div className="pointer-events-auto flex items-center gap-3 px-4 pt-3">
        <button
          onClick={onExit}
          aria-label="Akıştan çık"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white/80 transition-colors hover:bg-white/15 hover:text-white"
        >
          <X className="h-5 w-5" />
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-white">{title}</p>
          {subtitle && <p className="truncate text-xs font-medium text-white/60">{subtitle}</p>}
        </div>
        <FullscreenButton tone="dark" />
      </div>
    </div>
  );
}
