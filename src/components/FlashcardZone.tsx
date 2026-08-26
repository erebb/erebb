import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowLeft, Check, PartyPopper, RotateCcw, X } from 'lucide-react';
import { useApp } from '@/context/AppContext';
import { useSpacedRepetition } from '@/hooks/useSpacedRepetition';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';

interface Props {
  setId: string;
  onExit: () => void;
}

export function FlashcardZone({ setId, onExit }: Props) {
  const { getSet } = useApp();
  const set = getSet(setId);
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
  } = useSpacedRepetition(setId);

  const [isFlipped, setIsFlipped] = useState(false);

  if (!set) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6">
        <p className="font-bold text-duo-gray-500">Soru seti bulunamadı.</p>
        <Button variant="blue" onClick={onExit}>
          Panoya Dön
        </Button>
      </div>
    );
  }

  const answer = (fn: () => void) => {
    setIsFlipped(false);
    fn();
  };

  const progressPercent = total > 0 ? (reviewed / total) * 100 : 0;

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-md flex-col p-4">
      <header className="flex items-center gap-3 py-2">
        <Button variant="ghost" size="icon" onClick={onExit} aria-label="Geri">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <Progress value={progressPercent} className="flex-1" />
        <Badge variant="blue">{remaining} kart</Badge>
      </header>

      {isEarlyReview && !isDone && (
        <p className="py-1 text-center text-xs font-bold text-duo-gray-300">
          Bugün vadesi gelen kart yok — erken tekrar yapıyorsun. 💪
        </p>
      )}

      {isDone ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-1 flex-col items-center justify-center gap-4 text-center"
        >
          <PartyPopper className="h-16 w-16 text-duo-gold" />
          <h2 className="text-2xl font-extrabold">Oturum tamamlandı!</h2>
          <p className="font-semibold text-duo-gray-500">
            {reviewed} kart öğrenildi · {easyCount} kolay · {hardCount} zor işaretleme
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
              Panoya Dön
            </Button>
          </div>
        </motion.div>
      ) : (
        <>
          <div className="flex flex-1 items-center justify-center py-6">
            <div className="perspective-1000 w-full">
              <AnimatePresence mode="wait">
                {currentCard && (
                  <motion.div
                    key={currentCard.id}
                    initial={{ x: 60, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    exit={{ x: -60, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <motion.div
                      className="preserve-3d relative h-72 w-full cursor-pointer select-none"
                      onClick={() => setIsFlipped((f) => !f)}
                      animate={{ rotateY: isFlipped ? 180 : 0 }}
                      transition={{ duration: 0.5, ease: [0.4, 0.2, 0.2, 1] }}
                    >
                      {/* Ön yüz: soru */}
                      <div className="backface-hidden absolute inset-0 flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-duo-gray-100 bg-white p-6 text-center shadow-duo-card">
                        <Badge variant="gray">SORU</Badge>
                        <p className="text-2xl font-extrabold text-duo-gray-700">
                          {currentCard.front}
                        </p>
                        <p className="text-xs font-bold text-duo-gray-300">Çevirmek için dokun</p>
                      </div>
                      {/* Arka yüz: cevap */}
                      <div
                        className="backface-hidden absolute inset-0 flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-duo-blue bg-duo-blue-light p-6 text-center"
                        style={{ transform: 'rotateY(180deg)' }}
                      >
                        <Badge variant="blue">CEVAP</Badge>
                        <p className="text-2xl font-extrabold text-duo-gray-700">
                          {currentCard.back}
                        </p>
                        <p className="text-xs font-bold text-duo-gray-300">Çevirmek için dokun</p>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 pb-4">
            <Button variant="danger" size="lg" onClick={() => answer(markHard)}>
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
