import { AnimatePresence, motion } from 'framer-motion';
import { Check, ChevronUp, X } from 'lucide-react';
import type { FeedAnswerResult } from '@/types';

/** Cevap sonrası geri bildirim; yanlışta doğru cevabı gösterir ve kaydırmaya davet eder. */
export function FeedAnswerBanner({ result }: { result?: FeedAnswerResult }) {
  return (
    <div aria-live="polite" className="min-h-[4.5rem] pt-4">
      <AnimatePresence>
        {result && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className={
              result.correct
                ? 'flex items-center gap-3 rounded-2xl bg-duo-green px-4 py-3 text-white'
                : 'flex flex-col gap-2 rounded-2xl bg-duo-red px-4 py-3 text-white'
            }
          >
            {result.correct ? (
              <>
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/25">
                  <Check className="h-5 w-5" />
                </span>
                <span className="font-extrabold">Doğru!</span>
                {result.xpEarned > 0 && (
                  <span className="ml-auto font-extrabold">+{result.xpEarned} XP</span>
                )}
              </>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/25">
                    <X className="h-5 w-5" />
                  </span>
                  <div className="text-left">
                    <p className="font-extrabold">Yanlış</p>
                    <p className="text-sm font-bold text-white/90">
                      Doğru cevap: {result.correctAnswer}
                    </p>
                  </div>
                </div>
                <motion.div
                  animate={{ y: [0, -4, 0] }}
                  transition={{ repeat: Infinity, duration: 1.4 }}
                  className="flex items-center justify-center gap-1 text-xs font-extrabold text-white/80"
                >
                  <ChevronUp className="h-4 w-4" /> Devam etmek için yukarı kaydır
                </motion.div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
