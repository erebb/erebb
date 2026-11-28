import { useCallback, useRef, useState } from 'react';
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
 * Kart modunun kalbi: Leitner kutularına göre oturum kuyruğu kurar,
 * "Zor" kartları aynı oturumda birkaç kart ileride yeniden gösterir,
 * "Kolay" kartları kuyruktan çıkarıp bir üst kutuya taşır.
 */
export function useSpacedRepetition(questions: Question[]): UseSpacedRepetitionReturn {
  const { srsEntries, updateSrsEntry, recordResult } = useApp();

  // Güncel kayıtları ref'ten oku: her işaretleme bağlamı yeniler, ama kuyruk
  // yalnızca oturum başında kurulmalı.
  const entriesRef = useRef(srsEntries);
  entriesRef.current = srsEntries;

  const initial = useRef<{ queue: Question[]; isEarlyReview: boolean } | null>(null);
  if (initial.current === null) {
    initial.current = buildSessionQueue(questions, srsEntries);
  }

  const [queue, setQueue] = useState<Question[]>(initial.current.queue);
  const [isEarlyReview, setIsEarlyReview] = useState(initial.current.isEarlyReview);
  const [reviewed, setReviewed] = useState(0);
  const [hardCount, setHardCount] = useState(0);
  const [easyCount, setEasyCount] = useState(0);
  const [total, setTotal] = useState(initial.current.queue.length);

  const currentCard = queue[0] ?? null;

  const entryFor = (questionId: string) => entriesRef.current[questionId] ?? newEntry(questionId);

  const markEasy = useCallback(() => {
    if (!currentCard) return;
    updateSrsEntry(markEasyEntry(entryFor(currentCard.id)));
    recordResult(currentCard.id, true);
    setQueue((prev) => prev.slice(1));
    setReviewed((n) => n + 1);
    setEasyCount((n) => n + 1);
  }, [currentCard, updateSrsEntry, recordResult]);

  const markHard = useCallback(() => {
    if (!currentCard) return;
    updateSrsEntry(markHardEntry(entryFor(currentCard.id)));
    recordResult(currentCard.id, false);
    setQueue((prev) => {
      const rest = prev.slice(1);
      const insertAt = Math.min(REQUEUE_OFFSET, rest.length);
      return [...rest.slice(0, insertAt), prev[0], ...rest.slice(insertAt)];
    });
    setHardCount((n) => n + 1);
  }, [currentCard, updateSrsEntry, recordResult]);

  const restart = useCallback(() => {
    const next = buildSessionQueue(questions, entriesRef.current);
    setQueue(next.queue);
    setIsEarlyReview(next.isEarlyReview);
    setTotal(next.queue.length);
    setReviewed(0);
    setHardCount(0);
    setEasyCount(0);
  }, [questions]);

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
