import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { BookOpen, Check, ClipboardCheck, RotateCcw, Target, X } from 'lucide-react';
import type { StudyTarget } from '@/types';
import { useLearningEngine } from '@/hooks/useLearningEngine';
import { useApp } from '@/context/AppContext';
import { useLocalStorage } from '@/hooks/useLocalStorage';
import { STORAGE_KEYS } from '@/lib/storageKeys';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { MultipleChoiceQuestion } from '@/components/quiz/MultipleChoiceQuestion';
import { TextInputQuestion } from '@/components/quiz/TextInputQuestion';
import { MatchingPairsRound } from '@/components/quiz/MatchingPairsRound';
import { playCorrect, playIncorrect } from '@/lib/sound';
import { cn } from '@/lib/utils';

interface Props {
  target: StudyTarget;
  onExit: () => void;
}

const COUNT_OPTIONS = [10, 20, 40];

/** Soru çözme: canı, puanı, serisi yok — yalnızca sorular, cevaplar ve açıklamalar. */
type PoolFilter = 'all' | 'new' | 'wrong';

export function DuolingoZone({ target, onExit }: Props) {
  const { progress, recordResult } = useApp();
  const engine = useLearningEngine(target.questions, recordResult);
  const {
    session,
    currentItem,
    progressPercent,
    feedback,
    matchedPairIds,
    lastWrongPair,
    source,
    quizPool,
    correctCount,
    wrongQuestions,
    start,
    submitMultipleChoice,
    submitTextAnswer,
    submitMatchingPair,
    goToNext,
    reset,
  } = engine;

  // 0 = tümü
  const [count, setCount] = useLocalStorage<number>(STORAGE_KEYS.quizCount, 20);
  // Havuz: hepsi / hiç çözülmemiş / son cevabı yanlış olan. Liste oturum başında sabitlenir.
  const [poolFilter, setPoolFilter] = useState<PoolFilter>('all');
  const pools: Record<PoolFilter, typeof quizPool> = {
    all: quizPool,
    new: quizPool.filter((q) => !progress[q.id]),
    wrong: quizPool.filter((q) => progress[q.id]?.last === 'wrong'),
  };
  const activePool = pools[poolFilter].length > 0 ? pools[poolFilter] : quizPool;
  const availableCount = activePool.length;

  // Geri bildirim sesleri
  useEffect(() => {
    if (!feedback) return;
    if (feedback.type === 'correct') playCorrect();
    else playIncorrect();
  }, [feedback]);
  useEffect(() => {
    if (lastWrongPair) playIncorrect();
  }, [lastWrongPair]);
  useEffect(() => {
    if (matchedPairIds.length > 0) playCorrect();
  }, [matchedPairIds.length]);

  const matchingDone =
    currentItem?.kind === 'matching-pairs' && matchedPairIds.length === currentItem.pairs.length;
  const canContinue = Boolean(feedback || matchingDone) && session?.status === 'in-progress';

  // Masaüstü kısayolları: 1–6 / A–F şık seçer, Enter ya da Boşluk devam ettirir.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
      if (canContinue && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault();
        goToNext();
        return;
      }
      if (currentItem?.kind === 'multiple-choice' && !feedback) {
        const k = e.key.toLowerCase();
        const idx = /^[1-6]$/.test(k) ? Number(k) - 1 : /^[a-f]$/.test(k) ? k.charCodeAt(0) - 97 : -1;
        const choice = currentItem.choices[idx];
        if (choice !== undefined) {
          e.preventDefault();
          // Tıklamayla aynı yoldan geçsin ki seçilen şık da işaretlensin.
          const buttons = document.querySelectorAll<HTMLButtonElement>('[data-quiz-choices] button');
          if (buttons[idx]) buttons[idx].click();
          else submitMultipleChoice(choice);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [canContinue, currentItem, feedback, goToNext, submitMultipleChoice]);

  // ---------------- Başlangıç ----------------
  if (!session) {
    const options = COUNT_OPTIONS.filter((n) => n < availableCount);
    const chosen = count > 0 && count < availableCount ? count : 0;
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-md flex-col p-4">
        <header className="flex items-center gap-3 py-2">
          <Button variant="ghost" size="icon" onClick={onExit} aria-label="Geri">
            <X className="h-5 w-5" />
          </Button>
          <div className="min-w-0">
            <p className="truncate text-sm font-extrabold text-duo-gray-700">{target.title}</p>
            {target.subtitle && <p className="truncate text-xs font-bold text-duo-gray-300">{target.subtitle}</p>}
          </div>
        </header>

        <main className="flex flex-1 flex-col justify-center gap-6 py-6">
          <div className="flex flex-col items-center gap-3 text-center">
            <ClipboardCheck className="h-14 w-14 text-duo-green" />
            <h2 className="text-2xl font-extrabold text-duo-gray-700">Soru çöz</h2>
            <p className="max-w-xs text-sm font-semibold text-duo-gray-500">
              {availableCount === 0
                ? 'Burada çözülecek soru yok.'
                : source === 'mcq'
                  ? `${availableCount} sınav sorusu. Her cevaptan sonra doğru şık, açıklama ve slayt kaynağı gösterilir.`
                  : `${availableCount} karttan soru üretilecek (çoktan seçmeli, yazılı ve eşleştirme).`}
            </p>
          </div>

          {availableCount > 0 && (
            <>
              <div className="flex flex-col gap-2">
                <span className="text-center text-xs font-extrabold tracking-widest text-duo-gray-300">
                  HANGİ SORULAR
                </span>
                <div className="flex flex-wrap justify-center gap-2" data-pool-filter>
                  {(
                    [
                      ['all', 'Hepsi'],
                      ['new', 'Çözülmemiş'],
                      ['wrong', 'Yanlışlarım'],
                    ] as const
                  ).map(([key, label]) => (
                    <button
                      key={key}
                      disabled={pools[key].length === 0}
                      onClick={() => setPoolFilter(key)}
                      className={cn(
                        'h-11 rounded-xl border-2 px-4 text-sm font-extrabold transition-colors disabled:opacity-40',
                        poolFilter === key && pools[key].length > 0
                          ? 'border-duo-blue bg-duo-blue-light text-duo-blue-dark'
                          : 'border-duo-gray-100 bg-white text-duo-gray-500 hover:border-duo-blue'
                      )}
                    >
                      {label} ({pools[key].length})
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex flex-col gap-2">
                <span className="text-center text-xs font-extrabold tracking-widest text-duo-gray-300">
                  SORU SAYISI
                </span>
                <div className="flex flex-wrap justify-center gap-2">
                  {options.map((n) => (
                    <button
                      key={n}
                      onClick={() => setCount(n)}
                      className={cn(
                        'h-11 min-w-[4rem] rounded-xl border-2 px-4 text-sm font-extrabold transition-colors',
                        chosen === n
                          ? 'border-duo-blue bg-duo-blue-light text-duo-blue-dark'
                          : 'border-duo-gray-100 bg-white text-duo-gray-500 hover:border-duo-blue'
                      )}
                    >
                      {n}
                    </button>
                  ))}
                  <button
                    onClick={() => setCount(0)}
                    className={cn(
                      'h-11 min-w-[4rem] rounded-xl border-2 px-4 text-sm font-extrabold transition-colors',
                      chosen === 0
                        ? 'border-duo-blue bg-duo-blue-light text-duo-blue-dark'
                        : 'border-duo-gray-100 bg-white text-duo-gray-500 hover:border-duo-blue'
                    )}
                  >
                    Tümü ({availableCount})
                  </button>
                </div>
              </div>
              <Button size="lg" onClick={() => start(chosen || undefined, activePool)}>
                Başla
              </Button>
            </>
          )}
        </main>
      </div>
    );
  }

  // ---------------- Sonuç ----------------
  if (session.status === 'completed') {
    const total = session.totalAnswerable;
    const percent = total > 0 ? Math.round((correctCount / total) * 100) : 0;
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-md flex-col gap-5 p-4 pb-10">
        <header className="flex items-center gap-3 py-2">
          <Button variant="ghost" size="icon" onClick={onExit} aria-label="Geri">
            <X className="h-5 w-5" />
          </Button>
          <p className="truncate text-sm font-extrabold text-duo-gray-700">{target.title}</p>
        </header>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-2 text-center"
        >
          <Target className="h-14 w-14 text-duo-blue" />
          <h2 className="text-3xl font-extrabold text-duo-gray-700" data-quiz-score="">
            {correctCount} / {total}
          </h2>
          <p className="font-bold text-duo-gray-500">doğru · %{percent}</p>
        </motion.div>

        <div className="flex flex-col gap-2.5">
          {wrongQuestions.length > 0 && (
            <Button size="lg" onClick={() => start(undefined, wrongQuestions)}>
              <RotateCcw className="h-4 w-4" /> Yanlışları tekrar çöz ({wrongQuestions.length})
            </Button>
          )}
          <Button variant={wrongQuestions.length > 0 ? 'outline' : 'primary'} onClick={reset}>
            Yeni tur
          </Button>
          <Button variant="ghost" onClick={onExit}>
            Geri dön
          </Button>
        </div>

        {wrongQuestions.length > 0 && (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-extrabold tracking-wide text-duo-gray-500">YANLIŞ YAPTIKLARIN</h3>
            {wrongQuestions.map((q) => (
              <Card key={q.id}>
                <CardContent className="flex flex-col gap-1.5 p-4">
                  <p className="text-sm font-bold text-duo-gray-700">{q.front}</p>
                  <p className="flex items-start gap-1.5 text-sm font-extrabold text-duo-green-dark">
                    <Check className="mt-0.5 h-4 w-4 shrink-0" /> {q.back}
                  </p>
                  {q.explanation && (
                    <p className="text-xs font-semibold leading-relaxed text-duo-gray-500">{q.explanation}</p>
                  )}
                  {q.source && (
                    <p className="inline-flex items-center gap-1 text-[0.7rem] font-bold text-duo-gray-300">
                      <BookOpen className="h-3 w-3" /> {q.source}
                    </p>
                  )}
                </CardContent>
              </Card>
            ))}
          </section>
        )}
      </div>
    );
  }

  // ---------------- Soru ----------------
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-md flex-col p-4">
      <header className="flex items-center gap-3 py-2">
        <Button variant="ghost" size="icon" onClick={onExit} aria-label="Çıkış">
          <X className="h-5 w-5" />
        </Button>
        <Progress value={progressPercent} className="flex-1" />
        <span className="text-sm font-extrabold tabular-nums text-duo-gray-500" data-quiz-position="">
          {session.currentIndex + 1}/{session.items.length}
        </span>
      </header>

      <main className="flex flex-1 flex-col justify-center py-6">
        <AnimatePresence mode="wait">
          {currentItem && (
            <motion.div
              key={session.currentIndex}
              initial={{ x: 60, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: -60, opacity: 0 }}
              transition={{ duration: 0.2 }}
              data-quiz-choices=""
            >
              {currentItem.kind === 'multiple-choice' && (
                <MultipleChoiceQuestion
                  question={currentItem.question}
                  choices={currentItem.choices}
                  feedback={feedback}
                  onSelect={submitMultipleChoice}
                />
              )}
              {currentItem.kind === 'text-input' && (
                <TextInputQuestion question={currentItem.question} feedback={feedback} onSubmit={submitTextAnswer} />
              )}
              {currentItem.kind === 'matching-pairs' && (
                <MatchingPairsRound
                  pairs={currentItem.pairs}
                  matchedIds={matchedPairIds}
                  lastWrongPair={lastWrongPair}
                  onMatch={submitMatchingPair}
                />
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      <AnimatePresence>
        {canContinue && (
          <motion.div
            initial={{ y: 100, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 100, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className={cn(
              'sticky bottom-0 -mx-4 flex flex-col gap-3 rounded-t-2xl p-4 pb-6',
              feedback?.type === 'incorrect' ? 'bg-duo-red-light' : 'bg-duo-green-light'
            )}
          >
            {feedback?.type === 'incorrect' ? (
              <div className="flex items-start gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white">
                  <X className="h-6 w-6 text-duo-red" />
                </span>
                <div className="min-w-0">
                  <p className="font-extrabold text-duo-red-dark">Yanlış</p>
                  <p className="text-sm font-bold text-duo-red-dark/90">Doğru cevap: {feedback.correctAnswer}</p>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white">
                  <Check className="h-6 w-6 text-duo-green" />
                </span>
                <p className="font-extrabold text-duo-green-dark">Doğru!</p>
              </div>
            )}
            {feedback?.explanation && (
              <p
                className={cn(
                  'text-sm font-semibold leading-relaxed',
                  feedback.type === 'incorrect' ? 'text-duo-red-dark/80' : 'text-duo-green-dark/80'
                )}
              >
                {feedback.explanation}
              </p>
            )}
            {feedback?.source && (
              <p className="inline-flex items-center gap-1 text-xs font-bold text-duo-gray-500">
                <BookOpen className="h-3.5 w-3.5" /> {feedback.source}
              </p>
            )}
            <Button variant={feedback?.type === 'incorrect' ? 'danger' : 'primary'} size="lg" onClick={goToNext}>
              Devam Et
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
