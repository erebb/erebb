import { motion, useReducedMotion } from 'framer-motion';
import { BookOpen, Lightbulb } from 'lucide-react';
import type { ExplainerFeedCard, LeitnerBox, Question } from '@/types';
import { isMcq } from '@/types';
import { Badge } from '@/components/ui/badge';
import { MasteryDots } from '@/components/feed/MasteryDots';
import { cn, daysSince, fitText } from '@/lib/utils';

/**
 * ÖNEMLİ: Bu kartta gösterilen her metin ya kullanıcının kendi verisidir
 * (front / back / açıklama / kaynak / ipucu) ya da yerel tekrar durumundan hesaplanır
 * (kutu, son çalışma, oturum içi görülme sayısı). Hiçbir bilgi uydurulmaz; ağ isteği,
 * API veya LLM çağrısı yapılmaz.
 */

interface BoxPresentation {
  label: string;
  variant: 'green' | 'blue' | 'gold' | 'red';
  note?: string;
}

// Renk yalnız küçük etikette: kartın tamamını boyamak (doygun gradyan) dikkati içerikten alır.
function presentationFor(box: LeitnerBox | undefined, hasEntry: boolean, mcq: boolean): BoxPresentation {
  if (box === undefined) {
    return {
      label: mcq ? 'Soru · cevap' : 'Yeni bilgi',
      variant: 'blue',
      note: mcq ? undefined : 'Bunu ilk kez görüyorsun',
    };
  }
  switch (box) {
    case 1:
      return { label: 'Tekrar zamanı', variant: 'red', note: hasEntry ? 'Bunu daha önce zorlanmıştın' : undefined };
    case 2:
      return { label: 'Öğreniyorsun', variant: 'gold' };
    case 3:
      return { label: 'İlerliyorsun', variant: 'gold' };
    case 4:
      return { label: 'Neredeyse hazır', variant: 'green' };
    case 5:
      return { label: 'Ustalaştın', variant: 'green' };
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

/** Anlatım içeriği — hem tam ekran kartta hem "Göster" alt sayfasında kullanılır. */
export function ExplainerBody({
  question,
  box,
  sessionSeenCount,
  lastSeenAt,
  animate = true,
  compact = false,
}: ExplainerBodyProps) {
  const reduced = useReducedMotion();
  const mcq = isMcq(question);
  const p = presentationFor(box, Boolean(lastSeenAt), mcq);
  const on = animate && !reduced;

  // Tek, kısa solma; parça parça kayarak gelen içerik gözü her parçaya ayrı çeker.
  const rise = (_delay: number) =>
    on ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: 0.15 } } : { initial: false as const };

  const seenDays = lastSeenAt ? daysSince(lastSeenAt) : null;
  const muted = compact ? 'text-duo-gray-500' : 'text-white/70';
  const faint = compact ? 'text-duo-gray-300' : 'text-white/50';

  const frontSize = compact
    ? fitText(question.front, ['text-3xl', 'text-2xl', 'text-lg', 'text-base'])
    : fitText(question.front, ['text-4xl', 'text-2xl', 'text-xl', 'text-lg']);
  const backSize = compact
    ? fitText(question.back, ['text-xl', 'text-lg', 'text-base', 'text-sm'])
    : fitText(question.back, ['text-2xl', 'text-xl', 'text-lg', 'text-base']);

  return (
    <div
      className={cn('flex flex-col items-center gap-4 text-center', compact ? 'text-duo-gray-700' : 'text-white')}
    >
      <motion.div {...rise(0)}>
        <Badge variant={p.variant} className="px-3 py-1">
          {p.label}
        </Badge>
      </motion.div>

      <motion.div {...rise(0.12)} className="flex flex-col gap-1">
        {mcq && <span className={cn('text-xs font-medium', faint)}>Soru</span>}
        <h2 className={cn('break-words font-semibold leading-tight', frontSize)}>{question.front}</h2>
      </motion.div>

      <div className={cn('h-px w-24 shrink-0', compact ? 'bg-duo-gray-100' : 'bg-white/20')} />

      <motion.div {...rise(0.28)} className="flex flex-col gap-1">
        <span className={cn('text-xs font-medium', faint)}>{mcq ? 'Cevap' : 'Anlam'}</span>
        <p className={cn('font-semibold leading-snug', compact ? 'text-duo-green-dark' : 'text-[#9FDCC9]', backSize)}>
          {question.back}
        </p>
      </motion.div>

      {question.explanation && (
        <motion.p {...rise(0.34)} className={cn('max-w-prose text-sm font-normal leading-relaxed', muted)}>
          {question.explanation}
        </motion.p>
      )}

      {question.hint && (
        <motion.div
          {...rise(0.38)}
          className={cn(
            'flex items-start gap-2 rounded-xl px-4 py-3 text-left text-sm font-normal',
            compact ? 'bg-duo-gold-light text-duo-gold-dark' : 'bg-white/10 text-white/90'
          )}
        >
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0" />
          <span>İpucu: {question.hint}</span>
        </motion.div>
      )}

      <motion.div {...rise(0.46)} className="flex flex-col items-center gap-1.5">
        <MasteryDots box={box} />
        <span className={cn('text-xs font-medium', muted)}>Seviye {box ?? 0}/5</span>
        {p.note && <span className={cn('text-xs font-medium', muted)}>{p.note}</span>}
        {sessionSeenCount > 1 && (
          <span className={cn('text-xs font-medium', faint)}>Bu oturumda {sessionSeenCount}. kez</span>
        )}
        {seenDays !== null && seenDays > 0 && (
          <span className={cn('text-xs font-medium', faint)}>Son çalışma: {seenDays} gün önce</span>
        )}
        {question.source && (
          <span className={cn('mt-1 inline-flex items-center gap-1 text-xs font-medium', faint)}>
            <BookOpen className="h-3.5 w-3.5" /> {question.source}
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
  return (
    <div
      data-feed-kind="explainer"
      // pr-20: uzun metinler sağdaki eylem rayının altına girmesin.
      className="no-scrollbar flex h-full w-full items-center justify-center overflow-y-auto bg-ink pb-24 pl-6 pr-20 pt-24"
    >
      <div className="my-auto w-full">
        <ExplainerBody
          question={card.question}
          box={card.box}
          sessionSeenCount={card.sessionSeenCount}
          lastSeenAt={card.lastSeenAt}
          animate={isActive}
        />
      </div>
    </div>
  );
}
