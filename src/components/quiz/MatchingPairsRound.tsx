import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import type { Question } from '@/types';
import { cn, shuffle } from '@/lib/utils';

interface Props {
  pairs: Question[];
  matchedIds: string[];
  lastWrongPair: { frontId: string; backId: string } | null;
  onMatch: (frontQuestionId: string, backQuestionId: string) => void;
}

export function MatchingPairsRound({ pairs, matchedIds, lastWrongPair, onMatch }: Props) {
  // Sütun sıraları tur boyunca sabit kalsın diye bir kez karıştırılır.
  const fronts = useMemo(() => shuffle(pairs), [pairs]);
  const backs = useMemo(() => shuffle(pairs), [pairs]);

  const [selectedFront, setSelectedFront] = useState<string | null>(null);
  const [selectedBack, setSelectedBack] = useState<string | null>(null);

  // İki taraf da seçilince eşleşmeyi dene.
  useEffect(() => {
    if (selectedFront && selectedBack) {
      onMatch(selectedFront, selectedBack);
      setSelectedFront(null);
      setSelectedBack(null);
    }
  }, [selectedFront, selectedBack, onMatch]);

  const tileClass = (opts: { matched: boolean; selected: boolean; wrongFlash: boolean }) =>
    cn(
      'w-full rounded-2xl border-2 p-3 text-sm font-bold transition-all min-h-[3.5rem]',
      opts.matched &&
        'border-duo-green bg-duo-green-light text-duo-green-dark opacity-60 pointer-events-none',
      !opts.matched && opts.selected && 'border-duo-blue bg-duo-blue-light text-duo-blue-dark',
      !opts.matched &&
        !opts.selected &&
        'border-duo-gray-100 bg-white text-duo-gray-700 shadow-duo-card hover:border-duo-blue',
      opts.wrongFlash && 'animate-flash-incorrect border-duo-red'
    );

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-center text-xl font-extrabold text-duo-gray-700">Çiftleri eşleştir</h2>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-3">
          {fronts.map((q) => (
            <motion.button
              key={q.id}
              layout
              onClick={() => setSelectedFront((prev) => (prev === q.id ? null : q.id))}
              className={tileClass({
                matched: matchedIds.includes(q.id),
                selected: selectedFront === q.id,
                wrongFlash: lastWrongPair?.frontId === q.id,
              })}
            >
              {q.front}
            </motion.button>
          ))}
        </div>
        <div className="flex flex-col gap-3">
          {backs.map((q) => (
            <motion.button
              key={q.id}
              layout
              onClick={() => setSelectedBack((prev) => (prev === q.id ? null : q.id))}
              className={tileClass({
                matched: matchedIds.includes(q.id),
                selected: selectedBack === q.id,
                wrongFlash: lastWrongPair?.backId === q.id,
              })}
            >
              {q.back}
            </motion.button>
          ))}
        </div>
      </div>
    </div>
  );
}
