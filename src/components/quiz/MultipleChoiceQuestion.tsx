import { motion } from 'framer-motion';
import type { Question, QuizFeedback } from '@/types';
import { cn } from '@/lib/utils';

interface Props {
  question: Question;
  choices: string[];
  feedback: QuizFeedback | null;
  onSelect: (choice: string) => void;
}

export function MultipleChoiceQuestion({ question, choices, feedback, onSelect }: Props) {
  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-center text-2xl font-extrabold text-duo-gray-700">{question.front}</h2>
      <div className="grid gap-3">
        {choices.map((choice, i) => {
          const isCorrectAnswer = choice === question.back;
          const showState = feedback !== null;
          return (
            <motion.button
              key={`${choice}-${i}`}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06 }}
              disabled={showState}
              onClick={() => onSelect(choice)}
              className={cn(
                'rounded-2xl border-2 bg-white p-4 text-left text-base font-bold text-duo-gray-700 transition-colors',
                !showState &&
                  'border-duo-gray-100 shadow-duo-card hover:border-duo-blue hover:bg-duo-blue-light active:translate-y-0.5 active:shadow-none',
                showState &&
                  isCorrectAnswer &&
                  'border-duo-green bg-duo-green-light text-duo-green-dark',
                showState && !isCorrectAnswer && 'border-duo-gray-100 opacity-50'
              )}
            >
              <span className="mr-3 inline-flex h-7 w-7 items-center justify-center rounded-lg border-2 border-duo-gray-100 text-sm font-extrabold text-duo-gray-500">
                {i + 1}
              </span>
              {choice}
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
