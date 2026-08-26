import { motion, useReducedMotion } from 'framer-motion';
import { Lightbulb, Sparkles } from 'lucide-react';
import type { ExplainerFeedCard, LeitnerBox, Question } from '@/types';
import { Badge } from '@/components/ui/badge';
import { MasteryDots } from '@/components/feed/MasteryDots';
import { cn, daysSince } from '@/lib/utils';

/**
 * ÖNEMLİ: Bu kartta gösterilen her metin ya kullanıcının kendi verisidir
 * (front / back / hint) ya da yerel SRS durumundan hesaplanır (kutu, son çalışma,
 * oturum içi görülme sayısı). Etimoloji, örnek cümle, kelime türü gibi hiçbir bilgi
 * uydurulmaz — veri kümesinde yoktur. Ağ isteği, API veya LLM çağrısı yapılmaz.
 */

interface BoxPresentation {
  label: string;
  variant: 'green' | 'blue' | 'gold' | 'red';
  gradient: string;
  note?: string;
}

function presentationFor(box: LeitnerBox | undefined, hasEntry: boolean): BoxPresentation {
  if (box === undefined) {
    return {
      label: 'YENİ KELİME',
      variant: 'blue',
      gradient: 'from-duo-blue-dark via-duo-blue to-duo-blue-dark',
      note: 'Bu kelimeyi ilk kez görüyorsun',
    };
  }
  switch (box) {
    case 1:
      return {
        label: 'TEKRAR ZAMANI',
        variant: 'red',
        gradient: 'from-duo-red-dark via-duo-red to-duo-red-dark',
        note: hasEntry ? 'Bunu daha önce zorlanmıştın' : undefined,
      };
    case 2:
      return {
        label: 'ÖĞRENİYORSUN',
        variant: 'gold',
        gradient: 'from-duo-gold-dark via-duo-gold to-duo-gold-dark',
      };
    case 3:
      return {
        label: 'İLERLİYORSUN',
        variant: 'gold',
        gradient: 'from-[#B98A00] via-duo-gold to-[#B98A00]',
      };
    case 4:
      return {
        label: 'NEREDEYSE HAZIR',
        variant: 'green',
        gradient: 'from-duo-green-dark via-duo-green to-duo-green-dark',
      };
    case 5:
      return {
        label: 'USTALAŞTIN',
        variant: 'green',
        gradient: 'from-[#2E6B01] via-duo-green-dark to-[#2E6B01]',
      };
  }
}

export interface ExplainerBodyProps {
  question: Question;
  box?: LeitnerBox;
  sessionSeenCount: number;
  lastSeenAt?: string | null;
  animate?: boolean;
  /** Alt sayfada (Dialog) kullanılırken koyu zemin yerine açık zemin. */
  compact?: boolean;
}

/** Anlatım içeriği — hem tam ekran kartta hem "Kelimeyi göster" alt sayfasında kullanılır. */
export function ExplainerBody({
  question,
  box,
  sessionSeenCount,
  lastSeenAt,
  animate = true,
  compact = false,
}: ExplainerBodyProps) {
  const reduced = useReducedMotion();
  const p = presentationFor(box, Boolean(lastSeenAt));
  const on = animate && !reduced;

  const rise = (delay: number) =>
    on
      ? { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 }, transition: { delay } }
      : { initial: false as const };

  const seenDays = lastSeenAt ? daysSince(lastSeenAt) : null;

  return (
    <div
      className={cn(
        'flex flex-col items-center gap-5 text-center',
        compact ? 'text-duo-gray-700' : 'text-white'
      )}
    >
      <motion.div {...rise(0)}>
        <Badge variant={p.variant} className="px-3 py-1 text-[0.7rem] tracking-widest">
          {p.label}
        </Badge>
      </motion.div>

      <motion.div
        {...(on
          ? {
              initial: { opacity: 0, scale: 0.9 },
              animate: { opacity: 1, scale: 1 },
              transition: { delay: 0.08 },
            }
          : { initial: false as const })}
      >
        <Sparkles className={cn('h-8 w-8', compact ? 'text-duo-gold-dark' : 'text-white/70')} />
      </motion.div>

      <motion.h2
        {...(on
          ? {
              initial: { opacity: 0, scale: 0.9 },
              animate: { opacity: 1, scale: 1 },
              transition: { delay: 0.14 },
            }
          : { initial: false as const })}
        className={cn(
          'break-words font-extrabold leading-tight',
          compact ? 'text-3xl' : 'text-5xl sm:text-6xl'
        )}
      >
        {question.front}
      </motion.h2>

      <motion.div
        {...(on
          ? {
              initial: { scaleX: 0 },
              animate: { scaleX: 1 },
              transition: { delay: 0.2 },
            }
          : { initial: false as const })}
        className={cn('h-1 w-24 rounded-full', compact ? 'bg-duo-gray-100' : 'bg-white/30')}
      />

      <motion.div {...rise(0.28)} className="flex flex-col gap-1">
        <span
          className={cn(
            'text-xs font-extrabold tracking-[0.2em]',
            compact ? 'text-duo-gray-300' : 'text-white/60'
          )}
        >
          ANLAM
        </span>
        <p className={cn('font-bold leading-snug', compact ? 'text-lg' : 'text-2xl')}>
          {question.back}
        </p>
      </motion.div>

      {question.hint && (
        <motion.div
          {...rise(0.38)}
          className={cn(
            'flex items-start gap-2 rounded-xl px-4 py-3 text-left text-sm font-semibold',
            compact ? 'bg-duo-gold-light text-duo-gold-dark' : 'bg-white/15 text-white'
          )}
        >
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0" />
          <span>İpucu: {question.hint}</span>
        </motion.div>
      )}

      <motion.div {...rise(0.46)} className="flex flex-col items-center gap-2">
        <MasteryDots box={box} />
        <span
          className={cn(
            'text-xs font-bold',
            compact ? 'text-duo-gray-500' : 'text-white/70'
          )}
        >
          Seviye {box ?? 0}/5
        </span>
        {p.note && (
          <span className={cn('text-xs font-bold', compact ? 'text-duo-gray-500' : 'text-white/70')}>
            {p.note}
          </span>
        )}
        {sessionSeenCount > 1 && (
          <span className={cn('text-xs font-bold', compact ? 'text-duo-gray-300' : 'text-white/50')}>
            Bu oturumda {sessionSeenCount}. kez
          </span>
        )}
        {seenDays !== null && seenDays > 0 && (
          <span className={cn('text-xs font-bold', compact ? 'text-duo-gray-300' : 'text-white/50')}>
            Son çalışma: {seenDays} gün önce
          </span>
        )}
      </motion.div>
    </div>
  );
}

export interface ExplainerCardProps {
  card: ExplainerFeedCard;
  isActive: boolean;
}

export function ExplainerCard({ card, isActive }: ExplainerCardProps) {
  const p = presentationFor(card.box, Boolean(card.lastSeenAt));
  return (
    <div
      className={cn(
        'flex h-full w-full items-center justify-center bg-gradient-to-br px-8 py-24',
        p.gradient
      )}
    >
      <ExplainerBody
        question={card.question}
        box={card.box}
        sessionSeenCount={card.sessionSeenCount}
        lastSeenAt={card.lastSeenAt}
        animate={isActive}
      />
    </div>
  );
}
