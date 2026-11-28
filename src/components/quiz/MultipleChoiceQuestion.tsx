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
          // Sola hizalı: ortalanmış çok satırlı metinde göz her satırın başını arar.
          'font-semibold leading-snug text-duo-gray-700',
          fitText(question.front, ['text-2xl', 'text-xl', 'text-xl', 'text-lg'])
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
              initial={false}
              disabled={showState}
              onClick={() => {
                setChosen(choice);
                onSelect(choice);
              }}
              className={cn(
                'flex items-start gap-3 rounded-xl border bg-surface text-left text-duo-gray-700 transition-colors',
                long ? 'p-3.5 text-[15px] leading-relaxed' : 'p-4 text-base leading-relaxed',
                !showState && 'border-duo-gray-100 shadow-duo-card hover:border-duo-blue/50 hover:bg-duo-blue-light/60',
                showState && isCorrectAnswer && 'border-duo-green bg-duo-green-light text-duo-green-dark',
                isChosenWrong && 'border-duo-red bg-duo-red-light text-duo-red-dark',
                showState && !isCorrectAnswer && !isChosenWrong && 'border-duo-gray-100 text-duo-gray-300'
              )}
            >
              <span
                className={cn(
                  'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-sm font-medium',
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
              <span className="pt-0.5 font-medium">{choice}</span>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
