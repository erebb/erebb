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
    <div data-feed-kind="mc" className="no-scrollbar flex h-full w-full flex-col overflow-y-auto bg-ink pb-24 pl-6 pr-20 pt-20">
      <motion.div
        initial={isActive && !reduced ? { opacity: 0 } : false}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.15 }}
        className="flex flex-1 flex-col justify-center gap-3 py-4"
      >
        <span className="text-xs font-medium text-white/50">{isMcq(card.question) ? 'Soru' : 'Cevabı seç'}</span>
        <h2
          className={cn(
            'break-words font-semibold leading-tight text-white',
            fitText(card.question.front, ['text-3xl', 'text-2xl', 'text-xl', 'text-lg'])
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
              initial={false}
              disabled={locked}
              onClick={() => onAnswer(choice)}
              className={cn(
                'flex w-full items-center gap-3 rounded-2xl border text-left font-medium transition-colors',
                longOptions ? 'p-3 text-sm' : 'p-4 text-base',
                !locked &&
                  'border-white/15 bg-white/[0.06] text-white/90 hover:border-white/40 hover:bg-white/10',
                showCorrect && 'border-duo-green bg-duo-green text-white',
                chosenWrong && 'border-duo-red bg-duo-red/80 text-white',
                showWrong && 'border-white/10 bg-transparent text-white/40'
              )}
            >
              <span
                className={cn(
                  'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border text-sm font-semibold',
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
