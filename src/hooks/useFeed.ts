import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FeedAnswerResult, FeedCard, FeedCardKind, FeedSessionStats, Question } from '@/types';
import { isMcq } from '@/types';
import { useApp } from '@/context/AppContext';
import { markEasyEntry, markHardEntry, newEntry, touchEntry } from '@/lib/srs';
import {
  FEED_BATCH_SIZE,
  FEED_MAX_CARDS,
  FEED_PREFETCH_WITHIN,
  FEED_TRIM_CHUNK,
  buildFeedCard,
} from '@/lib/feed';
import { normalizeAnswer, shuffle } from '@/lib/utils';

export interface UseFeedResult {
  cards: FeedCard[];
  currentIndex: number;
  setCurrentIndex: (i: number) => void;
  /** FeedCard.id ile anahtarlı — aynı soru tekrar belirdiğinde sonuçlar bağımsız kalır. */
  answers: Record<string, FeedAnswerResult>;
  submitAnswer: (card: FeedCard, raw: string) => FeedAnswerResult;
  /** "Göster" ile bakıldığını işaretler (sonraki doğru cevap kutuyu terfi ettirmez). */
  markPeeked: (cardId: string) => void;
  stats: FeedSessionStats;
  isEmpty: boolean;
  /** Baştan kalıcı olarak atılan kart sayısı; FeedZone scrollTop telafisi yapar. */
  headOffset: number;
}

export function useFeed(questions: Question[]): UseFeedResult {
  const { srsEntries, updateSrsEntry, recordResult } = useApp();
  const isEmpty = questions.length === 0;
  const cardPool = useMemo(() => questions.filter((q) => !isMcq(q)), [questions]);

  // --- Üretim durumu (render'ı tetiklemeyen referanslar) ---
  const poolRef = useRef<Question[]>([]);
  const lastQidRef = useRef<string | null>(null);
  const recentKindsRef = useRef<FeedCardKind[]>([]);
  const taughtRef = useRef<Set<string>>(new Set());
  const seenCountRef = useRef<Map<string, number>>(new Map());

  // Güncel değerler ref'ten okunur; böylece generateBatch stabil kalır ve
  // her cevapta (SRS yazımı bağlamı yeniler) prefetch effect'i döngüye girmez.
  const entriesRef = useRef(srsEntries);
  entriesRef.current = srsEntries;
  const questionsRef = useRef(questions);
  questionsRef.current = questions;
  const cardPoolRef = useRef(cardPool);
  cardPoolRef.current = cardPool;

  const nextQuestion = useCallback((all: Question[]): Question => {
    if (poolRef.current.length === 0) {
      const next = shuffle(all);
      // Döngü sınırında arka arkaya aynı soru gelmesin.
      if (next.length > 1 && next[next.length - 1].id === lastQidRef.current) {
        [next[0], next[next.length - 1]] = [next[next.length - 1], next[0]];
      }
      poolRef.current = next;
    }
    const q = poolRef.current.pop()!;
    lastQidRef.current = q.id;
    return q;
  }, []);

  const generateBatch = useCallback(
    (n: number, opts?: { firstIsExplainer?: boolean }): FeedCard[] => {
      const all = questionsRef.current;
      if (all.length === 0) return [];
      const out: FeedCard[] = [];
      const entries = entriesRef.current;

      for (let i = 0; i < n; i++) {
        const q = nextQuestion(all);
        const seen = (seenCountRef.current.get(q.id) ?? 0) + 1;
        seenCountRef.current.set(q.id, seen);

        const card = buildFeedCard({
          question: q,
          cardPool: cardPoolRef.current,
          entry: entries[q.id],
          taught: taughtRef.current,
          recentKinds: recentKindsRef.current,
          sessionSeenCount: seen,
          forceKind: opts?.firstIsExplainer && i === 0 ? 'explainer' : undefined,
        });

        if (card.kind === 'explainer') taughtRef.current.add(q.id);
        recentKindsRef.current = [...recentKindsRef.current, card.kind].slice(-2);
        out.push(card);
      }
      return out;
    },
    [nextQuestion]
  );

  const [cards, setCards] = useState<FeedCard[]>(() =>
    generateBatch(FEED_BATCH_SIZE, { firstIsExplainer: true })
  );
  const [currentIndex, setCurrentIndex] = useState(0);
  const [headOffset, setHeadOffset] = useState(0);
  const [answers, setAnswers] = useState<Record<string, FeedAnswerResult>>({});
  const [peekedIds, setPeekedIds] = useState<Set<string>>(new Set());
  const [stats, setStats] = useState<FeedSessionStats>({ correct: 0, answered: 0 });

  // --- Sonsuz üretim: sona yaklaşınca yeni parti ekle ---
  useEffect(() => {
    if (isEmpty) return;
    if (cards.length - currentIndex - 1 <= FEED_PREFETCH_WITHIN) {
      setCards((prev) => {
        const grown = [...prev, ...generateBatch(FEED_BATCH_SIZE)];
        if (grown.length > FEED_MAX_CARDS) {
          setHeadOffset((h) => h + FEED_TRIM_CHUNK);
          setCurrentIndex((i) => i - FEED_TRIM_CHUNK);
          return grown.slice(FEED_TRIM_CHUNK);
        }
        return grown;
      });
    }
  }, [currentIndex, cards.length, isEmpty, generateBatch]);

  const markPeeked = useCallback((cardId: string) => {
    setPeekedIds((prev) => {
      if (prev.has(cardId)) return prev;
      const next = new Set(prev);
      next.add(cardId);
      return next;
    });
  }, []);

  const submitAnswer = useCallback(
    (card: FeedCard, raw: string): FeedAnswerResult => {
      const existing = answers[card.id];
      if (existing) return existing;

      const correct = normalizeAnswer(raw) === normalizeAnswer(card.question.back);
      const peeked = peekedIds.has(card.id);

      // --- Tekrar kaydı: anında, kart başına bir yazma ---
      const entry = entriesRef.current[card.question.id] ?? newEntry(card.question.id);
      if (correct) {
        // Çoktan seçmeli tanımadır, hatırlama değil: 1/4 şans bir öğeyi 14 günlük
        // aralığa taşımasın. Bakılarak verilen cevap da terfi ettirmez.
        const promote = !peeked && (card.kind === 'text-input' || entry.box <= 3);
        updateSrsEntry(promote ? markEasyEntry(entry) : touchEntry(entry));
      } else {
        updateSrsEntry(markHardEntry(entry));
      }

      // İlerleme: cevaba bakılarak verilen doğru cevap "bildim" sayılmaz.
      recordResult(card.question.id, correct && !peeked);

      const result: FeedAnswerResult = { correct, correctAnswer: card.question.back, userAnswer: raw, peeked };
      setAnswers((prev) => ({ ...prev, [card.id]: result }));
      setStats((prev) => ({ correct: prev.correct + (correct ? 1 : 0), answered: prev.answered + 1 }));
      return result;
    },
    [answers, peekedIds, updateSrsEntry, recordResult]
  );

  return {
    cards,
    currentIndex,
    setCurrentIndex,
    answers,
    submitAnswer,
    markPeeked,
    stats,
    isEmpty,
    headOffset,
  };
}
