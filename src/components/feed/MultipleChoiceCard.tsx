import { motion, useReducedMotion } from 'framer-motion';
import { Check, X } from 'lucide-react';
import type { FeedAnswerResult, MultipleChoiceFeedCard } from '@/types';
import { isMcq } from '@/types';
import { cn, fitText, normalizeAnswer } from '@/lib/utils';
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
  const longOptions = card.choices.some((c) => c.length > 60);

  return (
    // pr-20: sağdaki eylem rayının (w-10 + right-3) üstüne binmesini önler.
    <div className="no-scrollbar flex h-full w-full flex-col overflow-y-auto bg-duo-gray-900 pb-24 pl-6 pr-20 pt-20">
      <motion.div
        initial={isActive && !reduced ? { opacity: 0, y: 16 } : false}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-1 flex-col items-center justify-center gap-3 py-4 text-center"
      >
        <span className="text-xs font-extrabold tracking-[0.2em] text-white/50">
          {isMcq(card.question) ? 'SORU' : 'CEVABI SEÇ'}
        </span>
        <h2
          className={cn(
            'break-words font-extrabold leading-tight text-white',
            fitText(card.question.front, ['text-4xl sm:text-5xl', 'text-2xl', 'text-xl', 'text-lg'])
          )}
        >
          {card.question.front}
        </h2>
      </motion.div>

      <div className="flex flex-col gap-2.5">
        {card.choices.map((choice, i) => {
          const isCorrectChoice = normalizeAnswer(choice) === correctNorm;
          const showCorrect = locked && isCorrectChoice;
          const chosenWrong =
            locked && !isCorrectChoice && normalizeAnswer(choice) === normalizeAnswer(result.userAnswer);
          const showWrong = locked && !isCorrectChoice && !chosenWrong;
          return (
            <motion.button
              key={`${choice}-${i}`}
              initial={isActive && !reduced ? { opacity: 0, y: 14 } : false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 * i }}
              disabled={locked}
              onClick={() => onAnswer(choice)}
              className={cn(
                'flex w-full items-center gap-3 rounded-2xl border-2 text-left font-bold transition-colors',
                longOptions ? 'p-3 text-sm' : 'p-4 text-base',
                !locked &&
                  'border-white/20 bg-white/10 text-white hover:border-white/50 hover:bg-white/20 active:translate-y-0.5',
                showCorrect && 'border-duo-green bg-duo-green text-white',
                chosenWrong && 'border-duo-red bg-duo-red/80 text-white',
                showWrong && 'border-white/10 bg-white/5 text-white/40'
              )}
            >
              <span
                className={cn(
                  'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border-2 text-sm font-extrabold',
                  showCorrect || chosenWrong ? 'border-white/60 text-white' : 'border-white/25 text-white/60'
                )}
              >
                {showCorrect ? (
                  <Check className="h-4 w-4" />
                ) : chosenWrong ? (
                  <X className="h-4 w-4" />
                ) : (
                  String.fromCharCode(65 + i)
                )}
              </span>
              <span className="flex-1">{choice}</span>
            </motion.button>
          );
        })}
      </div>

      <FeedAnswerBanner result={result} question={card.question} />
    </div>
  );
}
