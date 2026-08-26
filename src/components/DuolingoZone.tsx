import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, Heart, HeartCrack, Sparkles, Trophy, X } from 'lucide-react';
import { useApp } from '@/context/AppContext';
import { useLearningEngine } from '@/hooks/useLearningEngine';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { MultipleChoiceQuestion } from '@/components/quiz/MultipleChoiceQuestion';
import { TextInputQuestion } from '@/components/quiz/TextInputQuestion';
import { MatchingPairsRound } from '@/components/quiz/MatchingPairsRound';
import { playCorrect, playIncorrect } from '@/lib/sound';
import { cn } from '@/lib/utils';

interface Props {
  setId: string;
  onExit: () => void;
}

export function DuolingoZone({ setId, onExit }: Props) {
  const { getSet } = useApp();
  const set = getSet(setId);
  const {
    session,
    currentItem,
    progressPercent,
    feedback,
    matchedPairIds,
    lastWrongPair,
    submitMultipleChoice,
    submitTextAnswer,
    submitMatchingPair,
    goToNext,
    retry,
  } = useLearningEngine(setId);

  // Geri bildirim sesleri (çoktan seçmeli / yazılı sorularda).
  useEffect(() => {
    if (!feedback) return;
    if (feedback.type === 'correct') playCorrect();
    else playIncorrect();
  }, [feedback]);

  // Eşleştirmede: yanlış çift ve doğru çift sesleri.
  useEffect(() => {
    if (lastWrongPair) playIncorrect();
  }, [lastWrongPair]);
  useEffect(() => {
    if (matchedPairIds.length > 0) playCorrect();
  }, [matchedPairIds.length]);

  if (!set || !session) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6">
        <p className="font-bold text-duo-gray-500">Soru seti bulunamadı.</p>
        <Button variant="blue" onClick={onExit}>
          Panoya Dön
        </Button>
      </div>
    );
  }

  const matchingDone =
    currentItem?.kind === 'matching-pairs' && matchedPairIds.length === currentItem.pairs.length;

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-md flex-col p-4">
      <header className="flex items-center gap-3 py-2">
        <Button variant="ghost" size="icon" onClick={onExit} aria-label="Çıkış">
          <X className="h-5 w-5" />
        </Button>
        <Progress value={progressPercent} className="flex-1" />
        <div className="flex items-center gap-1" aria-label={`${session.hearts} can kaldı`}>
          <Heart className="h-6 w-6 fill-duo-red text-duo-red" />
          <span className="text-lg font-extrabold text-duo-red">{session.hearts}</span>
        </div>
      </header>

      <main className="flex flex-1 flex-col justify-center py-6">
        <AnimatePresence mode="wait">
          {session.status === 'in-progress' && currentItem && (
            <motion.div
              key={session.currentIndex}
              initial={{ x: 60, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: -60, opacity: 0 }}
              transition={{ duration: 0.2 }}
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
                <TextInputQuestion
                  question={currentItem.question}
                  feedback={feedback}
                  onSubmit={submitTextAnswer}
                />
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
        {(feedback || matchingDone) && session.status === 'in-progress' && (
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
                <div>
                  <p className="font-extrabold text-duo-red-dark">Yanlış!</p>
                  <p className="text-sm font-bold text-duo-red-dark/80">
                    Doğru cevap: {feedback.correctAnswer}
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white">
                  <Check className="h-6 w-6 text-duo-green" />
                </span>
                <p className="font-extrabold text-duo-green-dark">Harika, doğru!</p>
              </div>
            )}
            <Button
              variant={feedback?.type === 'incorrect' ? 'danger' : 'primary'}
              size="lg"
              onClick={goToNext}
            >
              Devam Et
            </Button>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {session.status === 'game-over' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-white p-6 text-center"
          >
            <motion.div initial={{ scale: 0.5 }} animate={{ scale: 1 }}>
              <HeartCrack className="h-20 w-20 text-duo-red" />
            </motion.div>
            <h2 className="text-3xl font-extrabold text-duo-gray-700">Canların bitti!</h2>
            <p className="max-w-xs font-semibold text-duo-gray-500">
              Endişelenme — hatalar öğrenmenin bir parçası. Tekrar dene!
            </p>
            <div className="mt-4 flex w-full max-w-xs flex-col gap-3">
              <Button size="lg" onClick={retry}>
                Tekrar Dene
              </Button>
              <Button variant="outline" onClick={onExit}>
                Panoya Dön
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {session.status === 'completed' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-white p-6 text-center"
          >
            <motion.div
              initial={{ scale: 0.5, rotate: -12 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ type: 'spring', stiffness: 260, damping: 14 }}
            >
              <Trophy className="h-20 w-20 text-duo-gold" />
            </motion.div>
            <h2 className="text-3xl font-extrabold text-duo-gray-700">Ders tamamlandı!</h2>
            <div className="flex items-center gap-2 rounded-2xl bg-duo-gold-light px-4 py-2">
              <Sparkles className="h-5 w-5 text-duo-gold-dark" />
              <span className="font-extrabold text-duo-gold-dark">+{session.xpEarned} XP</span>
            </div>
            <p className="font-semibold text-duo-gray-500">
              {session.score} / {session.totalAnswerable} doğru · {session.hearts} /{' '}
              {session.maxHearts} can kaldı
            </p>
            <div className="mt-4 flex w-full max-w-xs flex-col gap-3">
              <Button size="lg" onClick={retry}>
                Tekrar Oyna
              </Button>
              <Button variant="outline" onClick={onExit}>
                Panoya Dön
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
