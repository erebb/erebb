import { X } from 'lucide-react';
import { Progress } from '@/components/ui/progress';

export interface FeedTopBarProps {
  setName: string;
  dailyXPEarned: number;
  dailyGoalXP: number;
  onExit: () => void;
}

export function FeedTopBar({ setName, dailyXPEarned, dailyGoalXP, onExit }: FeedTopBarProps) {
  const percent = dailyGoalXP > 0 ? Math.min(100, (dailyXPEarned / dailyGoalXP) * 100) : 0;
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 z-20 bg-gradient-to-b from-black/60 to-transparent pb-8 pt-[env(safe-area-inset-top)]">
      <div className="pointer-events-auto flex items-center gap-3 px-4 pt-3">
        <button
          onClick={onExit}
          aria-label="Akıştan çık"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white/80 transition-colors hover:bg-white/15 hover:text-white"
        >
          <X className="h-5 w-5" />
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-extrabold text-white">{setName}</p>
          <Progress
            value={percent}
            className="mt-1 h-1 bg-white/20"
            indicatorClassName="bg-duo-gold"
          />
        </div>
      </div>
    </div>
  );
}
