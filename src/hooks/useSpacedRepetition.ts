import { useCallback, useMemo, useRef, useState } from 'react';
import type { Question } from '@/types';
import { useApp } from '@/context/AppContext';
import {
  REQUEUE_OFFSET,
  buildSessionQueue,
  markEasyEntry,
  markHardEntry,
  newEntry,
} from '@/lib/srs';

export interface UseSpacedRepetitionReturn {
  currentCard: Question | null;
  remaining: number;
  total: number;
  reviewed: number;
  hardCount: number;
  easyCount: number;
  isEarlyReview: boolean;
  isDone: boolean;
  markEasy: () => void;
  markHard: () => void;
  restart: () => void;
}

/**
 * Flashcard modunun kalp atışı: Leitner kutularına göre oturum kuyruğu kurar,
 * "Zor" kartları aynı oturumda birkaç kart ileride yeniden gösterir,
 * "Kolay" kartları kuyruktan çıkarıp bir üst kutuya taşır.
 */
export function useSpacedRepetition(setId: string): UseSpacedRepetitionReturn {
  const { getSet, getDeckState, updateDeckEntry } = useApp();

  const set = getSet(setId);
  const questions = useMemo(() => set?.questions ?? [], [set]);

  // Kuyruk oturum başında bir kez kurulur; sonrası oturum içi durumdur.
  const initial = useRef<{ queue: Question[]; isEarlyReview: boolean } | null>(null);
  if (initial.current === null) {
    initial.current = buildSessionQueue(questions, getDeckState(setId).entries);
  }

  const [queue, setQueue] = useState<Question[]>(initial.current.queue);
  const [isEarlyReview, setIsEarlyReview] = useState(initial.current.isEarlyReview);
  const [reviewed, setReviewed] = useState(0);
  const [hardCount, setHardCount] = useState(0);
  const [easyCount, setEasyCount] = useState(0);
  const [total, setTotal] = useState(initial.current.queue.length);

  const currentCard = queue[0] ?? null;

  const entryFor = useCallback(
    (questionId: string) => getDeckState(setId).entries[questionId] ?? newEntry(questionId),
    [getDeckState, setId]
  );

  const markEasy = useCallback(() => {
    if (!currentCard) return;
    updateDeckEntry(setId, markEasyEntry(entryFor(currentCard.id)));
    setQueue((prev) => prev.slice(1));
    setReviewed((n) => n + 1);
    setEasyCount((n) => n + 1);
  }, [currentCard, entryFor, setId, updateDeckEntry]);

  const markHard = useCallback(() => {
    if (!currentCard) return;
    updateDeckEntry(setId, markHardEntry(entryFor(currentCard.id)));
    setQueue((prev) => {
      const rest = prev.slice(1);
      const insertAt = Math.min(REQUEUE_OFFSET, rest.length);
      return [...rest.slice(0, insertAt), prev[0], ...rest.slice(insertAt)];
    });
    setHardCount((n) => n + 1);
  }, [currentCard, entryFor, setId, updateDeckEntry]);

  const restart = useCallback(() => {
    const next = buildSessionQueue(questions, getDeckState(setId).entries);
    setQueue(next.queue);
    setIsEarlyReview(next.isEarlyReview);
    setTotal(next.queue.length);
    setReviewed(0);
    setHardCount(0);
    setEasyCount(0);
  }, [questions, getDeckState, setId]);

  return {
    currentCard,
    remaining: queue.length,
    total,
    reviewed,
    hardCount,
    easyCount,
    isEarlyReview,
    isDone: queue.length === 0,
    markEasy,
    markHard,
    restart,
  };
}
