import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  FeedAnswerResult,
  FeedCard,
  FeedCardKind,
  FeedSessionStats,
  Question,
} from '@/types';
import { useApp } from '@/context/AppContext';
import { XP_TABLE } from '@/hooks/useLearningEngine';
import { markEasyEntry, markHardEntry, newEntry, touchEntry } from '@/lib/srs';
import {
  FEED_BATCH_SIZE,
  FEED_MAX_CARDS,
  FEED_PREFETCH_WITHIN,
  FEED_TRIM_CHUNK,
  buildFeedCard,
} from '@/lib/feed';
import { normalizeAnswer, shuffle } from '@/lib/utils';

const FLUSH_EVERY_CORRECT = 3;

export interface UseFeedResult {
  cards: FeedCard[];
  currentIndex: number;
  setCurrentIndex: (i: number) => void;
  /** FeedCard.id ile anahtarlı — aynı soru tekrar belirdiğinde sonuçlar bağımsız kalır. */
  answers: Record<string, FeedAnswerResult>;
  submitAnswer: (card: FeedCard, raw: string) => FeedAnswerResult;
  /** "Kelimeyi göster" ile bakıldığını işaretler (sonraki doğru cevap kutuyu terfi ettirmez). */
  markPeeked: (cardId: string) => void;
  peekedIds: Set<string>;
  stats: FeedSessionStats;
  isEmpty: boolean;
  /** Baştan kalıcı olarak atılan kart sayısı; FeedZone scrollTop telafisi yapar. */
  headOffset: number;
  flushXP: () => void;
}

export function useFeed(setId: string): UseFeedResult {
  const { getSet, getDeckState, updateDeckEntry, recordSessionResult } = useApp();
  const set = getSet(setId);
  const questions = useMemo(() => set?.questions ?? [], [set]);
  const isEmpty = questions.length === 0;

  // --- Üretim durumu (render'ı tetiklemeyen referanslar) ---
  const poolRef = useRef<Question[]>([]);
  const lastQidRef = useRef<string | null>(null);
  const recentKindsRef = useRef<FeedCardKind[]>([]);
  const taughtRef = useRef<Set<string>>(new Set());
  const seenCountRef = useRef<Map<string, number>>(new Map());

  // getDeckState her render'da yeni kimlik alabildiği için ref üzerinden okunur;
  // böylece generateBatch stabil kalır ve prefetch effect'i döngüye girmez.
  const deckRef = useRef(getDeckState);
  useEffect(() => {
    deckRef.current = getDeckState;
  }, [getDeckState]);

  const questionsRef = useRef(questions);
  useEffect(() => {
    questionsRef.current = questions;
  }, [questions]);

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
      const entries = deckRef.current(setId).entries;

      for (let i = 0; i < n; i++) {
        const q = nextQuestion(all);
        const seen = (seenCountRef.current.get(q.id) ?? 0) + 1;
        seenCountRef.current.set(q.id, seen);

        const card = buildFeedCard({
          question: q,
          allQuestions: all,
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
    [nextQuestion, setId]
  );

  const [cards, setCards] = useState<FeedCard[]>(() =>
    generateBatch(FEED_BATCH_SIZE, { firstIsExplainer: true })
  );
  const [currentIndex, setCurrentIndex] = useState(0);
  const [headOffset, setHeadOffset] = useState(0);
  const [answers, setAnswers] = useState<Record<string, FeedAnswerResult>>({});
  const [peekedIds, setPeekedIds] = useState<Set<string>>(new Set());
  const [stats, setStats] = useState<FeedSessionStats>({ xpEarned: 0, correct: 0, answered: 0 });

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

  // --- XP toplu yazımı ---
  const pendingXpRef = useRef(0);
  const pendingCorrectRef = useRef(0);

  const flushXP = useCallback(() => {
    const xp = pendingXpRef.current;
    // recordSessionResult'tan ÖNCE sıfırla: StrictMode çift unmount'unda
    // ikinci çağrı 0 yazar, XP iki kez sayılmaz.
    pendingXpRef.current = 0;
    pendingCorrectRef.current = 0;
    if (xp > 0) recordSessionResult(xp);
  }, [recordSessionResult]);

  // Cleanup [] bağımlılıklı ama güncel flush'ı çağırmalı.
  const flushRef = useRef(flushXP);
  useEffect(() => {
    flushRef.current = flushXP;
  }, [flushXP]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') flushRef.current();
    };
    // Sabit sarmalayıcı: flushRef.current doğrudan verilirse removeEventListener eşleşmez.
    const onPageHide = () => flushRef.current();
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', onPageHide);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pagehide', onPageHide);
      flushRef.current();
    };
  }, []);

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

      const mode = card.kind === 'explainer' ? 'text-input' : card.kind;
      const correct = normalizeAnswer(raw) === normalizeAnswer(card.question.back);
      const peeked = peekedIds.has(card.id);
      const xpEarned = correct && !peeked ? XP_TABLE[mode] : 0;

      // --- SRS geri yazımı: anında, kart başına bir yazma ---
      const entries = deckRef.current(setId).entries;
      const entry = entries[card.question.id] ?? newEntry(card.question.id);
      if (correct) {
        // Çoktan seçmeli tanımadır, hatırlama değil: 1/4 şans kelimeyi
        // 14 günlük aralığa taşımasın. Bakılan cevap da terfi ettirmez.
        const promote = !peeked && (card.kind === 'text-input' || entry.box <= 3);
        updateDeckEntry(setId, promote ? markEasyEntry(entry) : touchEntry(entry));
      } else {
        updateDeckEntry(setId, markHardEntry(entry));
      }

      const result: FeedAnswerResult = {
        correct,
        correctAnswer: card.question.back,
        xpEarned,
        peeked,
      };
      setAnswers((prev) => ({ ...prev, [card.id]: result }));
      setStats((prev) => ({
        xpEarned: prev.xpEarned + xpEarned,
        correct: prev.correct + (correct ? 1 : 0),
        answered: prev.answered + 1,
      }));

      if (xpEarned > 0) {
        pendingXpRef.current += xpEarned;
        pendingCorrectRef.current += 1;
        if (pendingCorrectRef.current >= FLUSH_EVERY_CORRECT) flushXP();
      }

      return result;
    },
    [answers, peekedIds, setId, updateDeckEntry, flushXP]
  );

  return {
    cards,
    currentIndex,
    setCurrentIndex,
    answers,
    submitAnswer,
    markPeeked,
    peekedIds,
    stats,
    isEmpty,
    headOffset,
    flushXP,
  };
}
