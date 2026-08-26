import { motion } from 'framer-motion';
import { Eye, Flame, Target, Zap } from 'lucide-react';
import type { FeedSessionStats, LeitnerBox } from '@/types';
import { MasteryDots } from '@/components/feed/MasteryDots';
import { cn } from '@/lib/utils';

export interface FeedActionRailProps {
  stats: FeedSessionStats;
  streak: number;
  dailyXPEarned: number;
  dailyGoalXP: number;
  box?: LeitnerBox;
  onReveal: () => void;
  /** Anlatım kartında "Kelimeyi göster" anlamsız — devre dışı. */
  revealDisabled: boolean;
}

function RailItem({
  icon,
  value,
  label,
  tone,
}: {
  icon: React.ReactNode;
  value: string | number;
  label: string;
  tone?: string;
}) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <div className={cn('flex h-10 w-10 items-center justify-center', tone ?? 'text-white')}>
        {icon}
      </div>
      <span className="text-sm font-extrabold leading-none text-white">{value}</span>
      <span className="text-[0.65rem] font-bold text-white/60">{label}</span>
    </div>
  );
}

export function FeedActionRail({
  stats,
  streak,
  dailyXPEarned,
  dailyGoalXP,
  box,
  onReveal,
  revealDisabled,
}: FeedActionRailProps) {
  const goalPercent = dailyGoalXP > 0 ? Math.min(100, (dailyXPEarned / dailyGoalXP) * 100) : 0;
  const goalReached = goalPercent >= 100;

  return (
    <div className="pointer-events-none absolute bottom-28 right-3 z-20 flex flex-col items-center gap-5">
      <motion.div
        key={stats.xpEarned}
        initial={{ scale: 1 }}
        animate={{ scale: [1, 1.35, 1] }}
        transition={{ duration: 0.35 }}
      >
        <RailItem
          icon={<Zap className="h-7 w-7 fill-duo-gold text-duo-gold" />}
          value={stats.xpEarned}
          label="XP"
        />
      </motion.div>

      <RailItem
        icon={
          <Flame
            className={cn(
              'h-7 w-7',
              streak > 0 ? 'fill-duo-gold text-duo-gold' : 'text-white/40'
            )}
          />
        }
        value={streak}
        label="gün"
      />

      <div className="flex flex-col items-center gap-0.5">
        <div className="relative flex h-10 w-10 items-center justify-center">
          <svg viewBox="0 0 36 36" className="absolute h-10 w-10 -rotate-90">
            <circle cx="18" cy="18" r="15" className="fill-none stroke-white/20" strokeWidth="3" />
            <circle
              cx="18"
              cy="18"
              r="15"
              className={cn('fill-none', goalReached ? 'stroke-duo-gold' : 'stroke-duo-green')}
              strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray={`${(goalPercent / 100) * 94.2} 94.2`}
            />
          </svg>
          <Target
            className={cn('h-4 w-4', goalReached ? 'text-duo-gold animate-pop-in' : 'text-white')}
          />
        </div>
        <span className="text-sm font-extrabold leading-none text-white">
          {Math.round(goalPercent)}%
        </span>
        <span className="text-[0.65rem] font-bold text-white/60">Hedef</span>
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
        aria-label="Kelimeyi göster"
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
