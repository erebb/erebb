import { motion, useReducedMotion } from 'framer-motion';
import { Check, X } from 'lucide-react';
import type { FeedAnswerResult, MultipleChoiceFeedCard } from '@/types';
import { cn, normalizeAnswer } from '@/lib/utils';
import { FeedAnswerBanner } from '@/components/feed/FeedAnswerBanner';

export interface MultipleChoiceCardProps {
  card: MultipleChoiceFeedCard;
  isActive: boolean;
  result?: FeedAnswerResult;
  onAnswer: (raw: string) => void;
}

export function MultipleChoiceCard({ card, isActive, result, onAnswer }: MultipleChoiceCardProps) {
  const reduced = useReducedMotion();
  const locked = result !== undefined;
  const correctNorm = normalizeAnswer(card.question.back);

  return (
    <div className="flex h-full w-full flex-col justify-between bg-duo-gray-900 px-6 pb-28 pt-24">
      <motion.div
        initial={isActive && !reduced ? { opacity: 0, y: 16 } : false}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-1 flex-col items-center justify-center gap-3 text-center"
      >
        <span className="text-xs font-extrabold tracking-[0.2em] text-white/50">BU NE DEMEK?</span>
        <h2 className="break-words text-4xl font-extrabold leading-tight text-white sm:text-5xl">
          {card.question.front}
        </h2>
      </motion.div>

      <div className="flex flex-col gap-3">
        {card.choices.map((choice, i) => {
          const isCorrectChoice = normalizeAnswer(choice) === correctNorm;
          const isChosen = locked && result?.correct === isCorrectChoice && isCorrectChoice;
          // Kilitliyken: doğru şık daima yeşil; kullanıcı yanlış seçtiyse yanlışlar soluk.
          const showCorrect = locked && isCorrectChoice;
          const showWrong = locked && !isCorrectChoice;
          return (
            <motion.button
              key={`${choice}-${i}`}
              initial={isActive && !reduced ? { opacity: 0, y: 14 } : false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.06 * i }}
              disabled={locked}
              onClick={() => onAnswer(choice)}
              className={cn(
                'flex w-full items-center gap-3 rounded-2xl border-2 p-4 text-left text-base font-bold transition-colors',
                !locked &&
                  'border-white/20 bg-white/10 text-white hover:border-white/50 hover:bg-white/20 active:translate-y-0.5',
                showCorrect && 'border-duo-green bg-duo-green text-white',
                showWrong && 'border-white/10 bg-white/5 text-white/40'
              )}
            >
              <span
                className={cn(
                  'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border-2 text-sm font-extrabold',
                  showCorrect ? 'border-white/60 text-white' : 'border-white/25 text-white/60'
                )}
              >
                {showCorrect ? <Check className="h-4 w-4" /> : i + 1}
              </span>
              <span className="flex-1">{choice}</span>
              {showWrong && isChosen && <X className="h-5 w-5" />}
            </motion.button>
          );
        })}
      </div>

      <FeedAnswerBanner result={result} />
    </div>
  );
}
