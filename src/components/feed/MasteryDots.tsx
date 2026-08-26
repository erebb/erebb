import type { LeitnerBox } from '@/types';
import { cn } from '@/lib/utils';

export interface MasteryDotsProps {
  box?: LeitnerBox;
  className?: string;
}

/** Beş nokta: Leitner kutusuna göre dolu/boş. Kutu yoksa hepsi boş. */
export function MasteryDots({ box, className }: MasteryDotsProps) {
  const filled = box ?? 0;
  return (
    <div className={cn('flex items-center gap-1', className)} aria-label={`Seviye ${filled}/5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span
          key={i}
          className={cn(
            'h-2 w-2 rounded-full transition-colors',
            i <= filled ? 'bg-duo-gold' : 'bg-white/25'
          )}
        />
      ))}
    </div>
  );
}
