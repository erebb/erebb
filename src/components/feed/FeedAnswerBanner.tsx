import { AnimatePresence, motion } from 'framer-motion';
import { BookOpen, Check, ChevronUp, X } from 'lucide-react';
import type { FeedAnswerResult, Question } from '@/types';

interface Props {
  result?: FeedAnswerResult;
  question: Question;
}

/**
 * Cevap sonrası geri bildirim. Yanlışta doğru cevabı gösterir; açıklaması olan sorularda
 * (doğru ya da yanlış) açıklamayı ve slayt kaynağını gösterip okunması için kaydırmayı bekler.
 */
export function FeedAnswerBanner({ result, question }: Props) {
  const hasNotes = Boolean(question.explanation || question.source);
  const waitsForSwipe = result && (!result.correct || hasNotes);
  return (
    <div aria-live="polite" className="pt-3">
      <AnimatePresence>
        {result && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className={
              result.correct
                ? 'flex flex-col gap-2 rounded-2xl bg-duo-green px-4 py-3 text-white'
                : 'flex flex-col gap-2 rounded-2xl bg-duo-red px-4 py-3 text-white'
            }
          >
            <div className="flex items-start gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/25">
                {result.correct ? <Check className="h-5 w-5" /> : <X className="h-5 w-5" />}
              </span>
              <div className="min-w-0 text-left">
                <p className="font-semibold">{result.correct ? 'Doğru!' : 'Yanlış'}</p>
                {!result.correct && (
                  <p className="text-sm font-medium text-white/95">Doğru cevap: {result.correctAnswer}</p>
                )}
              </div>
            </div>
            {question.explanation && (
              <p className="text-left text-xs font-normal leading-relaxed text-white/90">{question.explanation}</p>
            )}
            {question.source && (
              <p className="flex items-center gap-1 text-left text-[0.7rem] font-medium text-white/75">
                <BookOpen className="h-3 w-3" /> {question.source}
              </p>
            )}
            {waitsForSwipe && (
              <motion.div
                animate={{ y: [0, -4, 0] }}
                transition={{ repeat: Infinity, duration: 1.4 }}
                className="flex items-center justify-center gap-1 text-xs font-semibold text-white/80"
              >
                <ChevronUp className="h-4 w-4" /> Devam etmek için yukarı kaydır
              </motion.div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Doğru cevaptan sonra otomatik geçilsin mi? Açıklaması olan sorular okunmak için bekler. */
export function autoAdvanceAfter(result: FeedAnswerResult, question: Question): boolean {
  return result.correct && !question.explanation && !question.source;
}
