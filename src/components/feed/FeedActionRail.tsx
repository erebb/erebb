import { CheckCircle2, Eye } from 'lucide-react';
import type { FeedSessionStats, LeitnerBox } from '@/types';
import { MasteryDots } from '@/components/feed/MasteryDots';
import { cn } from '@/lib/utils';

export interface FeedActionRailProps {
  stats: FeedSessionStats;
  box?: LeitnerBox;
  onReveal: () => void;
  /** Anlatım kartında "Göster" anlamsız — devre dışı. */
  revealDisabled: boolean;
}

export function FeedActionRail({ stats, box, onReveal, revealDisabled }: FeedActionRailProps) {
  return (
    <div className="pointer-events-none absolute bottom-28 right-3 z-20 flex flex-col items-center gap-5">
      <div className="flex flex-col items-center gap-0.5" aria-label={`${stats.correct} doğru, ${stats.answered} cevap`}>
        <div className="flex h-10 w-10 items-center justify-center text-duo-green">
          <CheckCircle2 className="h-7 w-7" />
        </div>
        <span className="text-sm font-extrabold leading-none text-white">
          {stats.correct}/{stats.answered}
        </span>
        <span className="text-[0.65rem] font-bold text-white/60">doğru</span>
      </div>

      {box !== undefined && (
        <div className="flex flex-col items-center gap-1">
          <MasteryDots box={box} className="flex-col gap-0.5" />
          <span className="text-[0.65rem] font-bold text-white/60">Seviye</span>
        </div>
      )}

      <button
        onClick={onReveal}
        disabled={revealDisabled}
        aria-label="Cevabı göster"
        className={cn(
          'pointer-events-auto flex flex-col items-center gap-0.5 transition-opacity',
          revealDisabled && 'pointer-events-none opacity-25'
        )}
      >
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/15 text-white">
          <Eye className="h-5 w-5" />
        </span>
        <span className="text-[0.65rem] font-bold text-white/60">Göster</span>
      </button>
    </div>
  );
}
