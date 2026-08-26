import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Question, QuizFeedback, QuizItem, QuizMode, QuizSession } from '@/types';
import { useApp } from '@/context/AppContext';
import { dedupeBy, normalizeAnswer, shuffle } from '@/lib/utils';

export const MAX_HEARTS = 5;

export const XP_TABLE: Record<QuizMode, number> = {
  'multiple-choice': 10,
  'text-input': 15,
  'matching-pairs': 5, // eşleşen çift başına
};

const MATCHING_ROUND_SIZE = 4;

/** Doğru cevap + veri setinden rastgele 3 çeldirici; küçük setlerde azalarak bozulur. */
export function buildChoices(
  correct: Question,
  allQuestions: Question[],
  numDistractors = 3
): string[] {
  const correctNorm = normalizeAnswer(correct.back);
  const pool = allQuestions.filter(
    (q) => q.id !== correct.id && normalizeAnswer(q.back) !== correctNorm
  );
  const unique = dedupeBy(pool, (q) => normalizeAnswer(q.back));
  const distractors = shuffle(unique).slice(0, Math.min(numDistractors, unique.length));
  return shuffle([correct.back, ...distractors.map((q) => q.back)]);
}

/** Modları sırayla dönerek oturum sorularını üretir; küçük setlerde zarifçe geriler. */
function buildQuizItems(questions: Question[]): QuizItem[] {
  const shuffled = shuffle(questions);
  const items: QuizItem[] = [];
  const modes: QuizMode[] = ['multiple-choice', 'text-input', 'matching-pairs'];
  let i = 0;
  let modeIdx = 0;

  while (i < shuffled.length) {
    const mode = modes[modeIdx % modes.length];
    if (mode === 'matching-pairs' && shuffled.length - i >= MATCHING_ROUND_SIZE) {
      items.push({ kind: 'matching-pairs', pairs: shuffled.slice(i, i + MATCHING_ROUND_SIZE) });
      i += MATCHING_ROUND_SIZE;
    } else if (mode === 'matching-pairs') {
      // Eşleştirme için yeterli kart kalmadı — bu turu atla, diğer modlara devam.
      modeIdx++;
      continue;
    } else {
      const q = shuffled[i];
      i += 1;
      if (mode === 'multiple-choice') {
        const choices = buildChoices(q, questions);
        items.push(
          choices.length >= 2
            ? { kind: 'multiple-choice', question: q, choices }
            : { kind: 'text-input', question: q }
        );
      } else {
        items.push({ kind: 'text-input', question: q });
      }
    }
    modeIdx++;
  }

  return items;
}

function countAnswerable(items: QuizItem[]): number {
  return items.reduce(
    (sum, item) => sum + (item.kind === 'matching-pairs' ? item.pairs.length : 1),
    0
  );
}

export interface UseLearningEngineReturn {
  session: QuizSession | null;
  currentItem: QuizItem | null;
  progressPercent: number;
  feedback: QuizFeedback | null;
  /** Mevcut eşleştirme turunda tamamlanan çiftlerin soru id'leri. */
  matchedPairIds: string[];
  /** Eşleştirmede son yanlış denemenin çifti (kısa süreli görsel geri bildirim için). */
  lastWrongPair: { frontId: string; backId: string } | null;
  startSession: () => void;
  submitMultipleChoice: (choice: string) => void;
  submitTextAnswer: (text: string) => void;
  submitMatchingPair: (frontQuestionId: string, backQuestionId: string) => void;
  goToNext: () => void;
  retry: () => void;
}

export function useLearningEngine(setId: string): UseLearningEngineReturn {
  const { getSet, recordSessionResult } = useApp();
  const set = getSet(setId);
  const questions = useMemo(() => set?.questions ?? [], [set]);

  const [session, setSession] = useState<QuizSession | null>(null);
  const [feedback, setFeedback] = useState<QuizFeedback | null>(null);
  const [matchedPairIds, setMatchedPairIds] = useState<string[]>([]);
  const [lastWrongPair, setLastWrongPair] = useState<{ frontId: string; backId: string } | null>(
    null
  );
  const committedRef = useRef(false);

  const startSession = useCallback(() => {
    const items = buildQuizItems(questions);
    setSession({
      setId,
      items,
      currentIndex: 0,
      hearts: MAX_HEARTS,
      maxHearts: MAX_HEARTS,
      score: 0,
      totalAnswerable: countAnswerable(items),
      xpEarned: 0,
      answers: [],
      status: items.length > 0 ? 'in-progress' : 'completed',
    });
    setFeedback(null);
    setMatchedPairIds([]);
    setLastWrongPair(null);
    committedRef.current = false;
  }, [questions, setId]);

  useEffect(() => {
    startSession();
  }, [startSession]);

  // Oturum tamamlandığında XP/seriyi bir kez kalıcı ilerlemeye işle.
  useEffect(() => {
    if (session?.status === 'completed' && !committedRef.current) {
      committedRef.current = true;
      if (session.xpEarned > 0) recordSessionResult(session.xpEarned);
    }
  }, [session, recordSessionResult]);

  const currentItem = session ? (session.items[session.currentIndex] ?? null) : null;

  const applyAnswer = useCallback(
    (mode: QuizMode, questionId: string, userAnswer: string, correct: boolean) => {
      setSession((prev) => {
        if (!prev || prev.status !== 'in-progress') return prev;
        const hearts = correct ? prev.hearts : prev.hearts - 1;
        return {
          ...prev,
          hearts,
          score: correct ? prev.score + 1 : prev.score,
          xpEarned: correct ? prev.xpEarned + XP_TABLE[mode] : prev.xpEarned,
          answers: [...prev.answers, { questionId, userAnswer, correct, mode }],
          status: hearts <= 0 ? 'game-over' : prev.status,
        };
      });
    },
    []
  );

  const submitMultipleChoice = useCallback(
    (choice: string) => {
      if (!currentItem || currentItem.kind !== 'multiple-choice' || feedback) return;
      const correct = choice === currentItem.question.back;
      applyAnswer('multiple-choice', currentItem.question.id, choice, correct);
      setFeedback(
        correct ? { type: 'correct' } : { type: 'incorrect', correctAnswer: currentItem.question.back }
      );
    },
    [currentItem, feedback, applyAnswer]
  );

  const submitTextAnswer = useCallback(
    (text: string) => {
      if (!currentItem || currentItem.kind !== 'text-input' || feedback) return;
      const correct = normalizeAnswer(text) === normalizeAnswer(currentItem.question.back);
      applyAnswer('text-input', currentItem.question.id, text, correct);
      setFeedback(
        correct ? { type: 'correct' } : { type: 'incorrect', correctAnswer: currentItem.question.back }
      );
    },
    [currentItem, feedback, applyAnswer]
  );

  const submitMatchingPair = useCallback(
    (frontQuestionId: string, backQuestionId: string) => {
      if (!currentItem || currentItem.kind !== 'matching-pairs') return;
      const correct = frontQuestionId === backQuestionId;
      applyAnswer('matching-pairs', frontQuestionId, backQuestionId, correct);
      if (correct) {
        setMatchedPairIds((prev) => [...prev, frontQuestionId]);
        setLastWrongPair(null);
      } else {
        setLastWrongPair({ frontId: frontQuestionId, backId: backQuestionId });
      }
    },
    [currentItem, applyAnswer]
  );

  const goToNext = useCallback(() => {
    setFeedback(null);
    setMatchedPairIds([]);
    setLastWrongPair(null);
    setSession((prev) => {
      if (!prev || prev.status !== 'in-progress') return prev;
      const nextIndex = prev.currentIndex + 1;
      return {
        ...prev,
        currentIndex: nextIndex,
        status: nextIndex >= prev.items.length ? 'completed' : prev.status,
      };
    });
  }, []);

  const progressPercent = session
    ? Math.min(100, (session.currentIndex / Math.max(1, session.items.length)) * 100)
    : 0;

  return {
    session,
    currentItem,
    progressPercent,
    feedback,
    matchedPairIds,
    lastWrongPair,
    startSession,
    submitMultipleChoice,
    submitTextAnswer,
    submitMatchingPair,
    goToNext,
    retry: startSession,
  };
}
