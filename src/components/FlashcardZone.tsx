import { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowLeft, BookOpen, Check, PartyPopper, RotateCcw, X } from 'lucide-react';
import type { Question, StudyTarget } from '@/types';
import { isMcq } from '@/types';
import { useSpacedRepetition } from '@/hooks/useSpacedRepetition';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn, fitText } from '@/lib/utils';
import { FullscreenButton } from '@/components/DisplayControls';

interface Props {
  target: StudyTarget;
  onExit: () => void;
}

type Deck = 'cards' | 'mcq' | 'all';

/**
 * Hangi öğelerle çalışılacağını seçtirir: bilgi kartları (varsayılan), sorular
 * (soru → cevap) ya da hepsi. Seçim değişince tekrar oturumu sıfırdan kurulur.
 */
export function FlashcardZone({ target, onExit }: Props) {
  const cards = useMemo(() => target.questions.filter((q) => !isMcq(q)), [target.questions]);
  const mcqs = useMemo(() => target.questions.filter(isMcq), [target.questions]);
  const [deck, setDeck] = useState<Deck>(cards.length > 0 ? 'cards' : 'all');
  const questions = deck === 'cards' ? cards : deck === 'mcq' ? mcqs : target.questions;
  const showPicker = cards.length > 0 && mcqs.length > 0;

  return (
    <FlashcardSession
      key={deck}
      target={target}
      questions={questions}
      onExit={onExit}
      picker={
        showPicker ? (
          <div className="flex justify-center gap-1.5 pb-1" role="tablist" aria-label="Kart destesi">
            {(
              [
                ['cards', `Bilgi kartları (${cards.length})`],
                ['mcq', `Sorular (${mcqs.length})`],
                ['all', `Hepsi (${target.questions.length})`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                role="tab"
                aria-selected={deck === key}
                onClick={() => setDeck(key)}
                className={cn(
                  'h-8 rounded-lg border px-2.5 text-xs font-semibold transition-colors',
                  deck === key
                    ? 'border-duo-blue bg-duo-blue-light text-duo-blue-dark'
                    : 'border-duo-gray-100 bg-surface text-duo-gray-500 hover:border-duo-blue'
                )}
              >
                {label}
              </button>
            ))}
          </div>
        ) : null
      }
    />
  );
}

interface SessionProps extends Props {
  questions: Question[];
  picker: React.ReactNode;
}

function FlashcardSession({ target, questions, onExit, picker }: SessionProps) {
  const {
    currentCard,
    remaining,
    total,
    reviewed,
    hardCount,
    easyCount,
    isEarlyReview,
    isDone,
    markEasy,
    markHard,
    restart,
  } = useSpacedRepetition(questions);

  const [isFlipped, setIsFlipped] = useState(false);

  const answer = (fn: () => void) => {
    setIsFlipped(false);
    fn();
  };

  const progressPercent = total > 0 ? (reviewed / total) * 100 : 0;
  const mcq = currentCard ? isMcq(currentCard) : false;

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-md flex-col p-4">
      <header className="flex items-center gap-3 py-2">
        <Button variant="ghost" size="icon" onClick={onExit} aria-label="Geri">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-duo-gray-500">{target.title}</p>
          <Progress value={progressPercent} className="mt-1 h-3" />
        </div>
        <Badge variant="blue">{remaining} kart</Badge>
        <FullscreenButton />
      </header>

      {picker}

      {isEarlyReview && !isDone && (
        <p className="py-1 text-center text-xs font-medium text-duo-gray-300">
          Bugün vadesi gelen kart yok — erken tekrar yapıyorsun.
        </p>
      )}

      {isDone ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-1 flex-col items-center justify-center gap-4 text-center"
        >
          <PartyPopper className="h-16 w-16 text-duo-gold" />
          <h2 className="text-2xl font-semibold">Tekrar tamamlandı</h2>
          <p className="font-normal text-duo-gray-500">
            {reviewed} kart · {easyCount} kolay · {hardCount} kez zor işaretlendi
          </p>
          <div className="mt-4 flex w-full flex-col gap-3">
            <Button
              onClick={() => {
                setIsFlipped(false);
                restart();
              }}
            >
              <RotateCcw className="h-4 w-4" /> Tekrar Çalış
            </Button>
            <Button variant="outline" onClick={onExit}>
              Geri dön
            </Button>
          </div>
        </motion.div>
      ) : (
        <>
          <div className="flex flex-1 items-center justify-center py-4">
            <div className="perspective-1000 w-full">
              <AnimatePresence mode="wait">
                {currentCard && (
                  <motion.div
                    key={currentCard.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.12 }}
                  >
                    <motion.div
                      className="preserve-3d relative h-[26rem] w-full cursor-pointer select-none"
                      onClick={() => setIsFlipped((f) => !f)}
                      animate={{ rotateY: isFlipped ? 180 : 0 }}
                      transition={{ duration: 0.35, ease: [0.4, 0.2, 0.2, 1] }}
                    >
                      {/* Ön yüz */}
                      <div className="backface-hidden absolute inset-0 flex flex-col items-center gap-3 overflow-y-auto rounded-2xl border border-duo-gray-100 bg-surface p-6 text-center shadow-duo-card">
                        <div className="my-auto flex flex-col items-center gap-3">
                          <Badge variant="gray">{mcq ? 'Soru' : 'Kart'}</Badge>
                          <p
                            data-card-front=""
                            className={cn(
                              'font-semibold text-duo-gray-700',
                              fitText(currentCard.front, ['text-3xl', 'text-2xl', 'text-lg', 'text-base'])
                            )}
                          >
                            {currentCard.front}
                          </p>
                          <p className="text-xs font-medium text-duo-gray-300">Çevirmek için dokun</p>
                        </div>
                      </div>
                      {/* Arka yüz */}
                      <div
                        className="backface-hidden absolute inset-0 flex flex-col items-center gap-3 overflow-y-auto rounded-2xl border border-duo-blue bg-duo-blue-light p-6 text-center"
                        style={{ transform: 'rotateY(180deg)' }}
                      >
                        <div className="my-auto flex flex-col items-center gap-3">
                          <Badge variant="blue">Cevap</Badge>
                          <p
                            className={cn(
                              'font-semibold text-duo-gray-700',
                              fitText(currentCard.back, ['text-3xl', 'text-2xl', 'text-lg', 'text-base'])
                            )}
                          >
                            {currentCard.back}
                          </p>
                          {currentCard.explanation && (
                            <p className="text-sm font-normal leading-relaxed text-duo-gray-500">
                              {currentCard.explanation}
                            </p>
                          )}
                          {currentCard.source && (
                            <p className="inline-flex items-center gap-1 text-xs font-medium text-duo-blue-dark">
                              <BookOpen className="h-3.5 w-3.5" /> {currentCard.source}
                            </p>
                          )}
                        </div>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 pb-4">
            {/* Öz değerlendirme: "Zor" bir hata değil, kırmızı alarm rengi gerekmez. */}
            <Button variant="outline" size="lg" onClick={() => answer(markHard)}>
              <X className="h-5 w-5" /> Zor
            </Button>
            <Button size="lg" onClick={() => answer(markEasy)}>
              <Check className="h-5 w-5" /> Kolay
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
