import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Check, X } from 'lucide-react';
import type { Question, QuizFeedback } from '@/types';
import { cn, fitText } from '@/lib/utils';

interface Props {
  question: Question;
  choices: string[];
  feedback: QuizFeedback | null;
  onSelect: (choice: string) => void;
}

export function MultipleChoiceQuestion({ question, choices, feedback, onSelect }: Props) {
  const [chosen, setChosen] = useState<string | null>(null);
  useEffect(() => setChosen(null), [question.id]);

  const long = choices.some((c) => c.length > 60);

  return (
    <div className="flex flex-col gap-5">
      <h2
        className={cn(
          'text-center font-extrabold leading-snug text-duo-gray-700',
          fitText(question.front, ['text-2xl', 'text-xl', 'text-lg', 'text-base'])
        )}
      >
        {question.front}
      </h2>
      <div className="grid gap-2.5">
        {choices.map((choice, i) => {
          const isCorrectAnswer = choice === question.back;
          const showState = feedback !== null;
          const isChosenWrong = showState && !isCorrectAnswer && choice === chosen;
          return (
            <motion.button
              key={`${choice}-${i}`}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              disabled={showState}
              onClick={() => {
                setChosen(choice);
                onSelect(choice);
              }}
              className={cn(
                'flex items-start gap-3 rounded-2xl border-2 bg-white text-left font-bold text-duo-gray-700 transition-colors',
                long ? 'p-3 text-sm' : 'p-4 text-base',
                !showState &&
                  'border-duo-gray-100 shadow-duo-card hover:border-duo-blue hover:bg-duo-blue-light active:translate-y-0.5 active:shadow-none',
                showState && isCorrectAnswer && 'border-duo-green bg-duo-green-light text-duo-green-dark',
                isChosenWrong && 'border-duo-red bg-duo-red-light text-duo-red-dark',
                // Opaklık değil renk: framer-motion giriş animasyonu satır içi opacity:1
                // yazdığı için opacity-50 sınıfı ezilir.
                showState && !isCorrectAnswer && !isChosenWrong && 'border-duo-gray-100 text-duo-gray-300'
              )}
            >
              <span
                className={cn(
                  'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border-2 text-sm font-extrabold',
                  showState && isCorrectAnswer
                    ? 'border-duo-green text-duo-green-dark'
                    : isChosenWrong
                      ? 'border-duo-red text-duo-red-dark'
                      : 'border-duo-gray-100 text-duo-gray-500'
                )}
              >
                {showState && isCorrectAnswer ? (
                  <Check className="h-4 w-4" />
                ) : isChosenWrong ? (
                  <X className="h-4 w-4" />
                ) : (
                  String.fromCharCode(65 + i)
                )}
              </span>
              <span className="pt-0.5">{choice}</span>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
