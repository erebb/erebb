import { useCallback, useMemo, useState } from 'react';
import type { Question, QuizFeedback, QuizItem, QuizMode, QuizSession } from '@/types';
import { isMcq } from '@/types';
import { dedupeBy, normalizeAnswer, shuffle } from '@/lib/utils';

const MATCHING_ROUND_SIZE = 4;
/** Bundan uzun cevaplar yazarak cevaplanmaz (bir tanımı harfi harfine yazmak ölçüm değil). */
const TEXT_INPUT_MAX_LEN = 30;
/** Eşleştirme kutucuklarına sığmayacak kadar uzun cevaplar eşleştirmeye girmez. */
const MATCHING_MAX_LEN = 80;

/** Doğru cevap + havuzdan rastgele 3 çeldirici; küçük havuzlarda azalarak bozulur. */
export function buildChoices(correct: Question, pool: Question[], numDistractors = 3): string[] {
  const correctNorm = normalizeAnswer(correct.back);
  const candidates = pool.filter(
    (q) => q.id !== correct.id && normalizeAnswer(q.back) !== correctNorm
  );
  const unique = dedupeBy(candidates, (q) => normalizeAnswer(q.back));
  const distractors = shuffle(unique).slice(0, Math.min(numDistractors, unique.length));
  return shuffle([correct.back, ...distractors.map((q) => q.back)]);
}

/** Yazılı (şıklı) soru: kendi şıkları karıştırılarak sorulur. */
function mcqItem(q: Question): QuizItem {
  return { kind: 'multiple-choice', question: q, choices: shuffle(q.options ?? [q.back]) };
}

/**
 * Yalnızca kartlardan soru üretir (şıklı sorusu olmayan setler için): çoktan seçmeli,
 * yazılı ve eşleştirme sırayla döner. Çeldiriciler tüm kart havuzundan gelir.
 */
function buildCardItems(selected: Question[], cardPool: Question[]): QuizItem[] {
  const items: QuizItem[] = [];
  const modes: QuizMode[] = ['multiple-choice', 'text-input', 'matching-pairs'];
  let i = 0;
  let modeIdx = 0;

  while (i < selected.length) {
    const mode = modes[modeIdx % modes.length];
    modeIdx++;

    if (mode === 'matching-pairs') {
      const group = selected.slice(i, i + MATCHING_ROUND_SIZE);
      const fits =
        group.length === MATCHING_ROUND_SIZE &&
        group.every((q) => q.back.length <= MATCHING_MAX_LEN && q.front.length <= MATCHING_MAX_LEN);
      if (fits) {
        items.push({ kind: 'matching-pairs', pairs: group });
        i += MATCHING_ROUND_SIZE;
      }
      continue;
    }

    const q = selected[i];
    i += 1;
    if (mode === 'text-input' && q.back.length <= TEXT_INPUT_MAX_LEN) {
      items.push({ kind: 'text-input', question: q });
      continue;
    }
    const choices = buildChoices(q, cardPool);
    items.push(
      choices.length >= 2
        ? { kind: 'multiple-choice', question: q, choices }
        : { kind: 'text-input', question: q }
    );
  }
  return items;
}

function countAnswerable(items: QuizItem[]): number {
  return items.reduce((sum, item) => sum + (item.kind === 'matching-pairs' ? item.pairs.length : 1), 0);
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
  /** Bu hedefte sorulabilecek soru sayısı (şıklı soru varsa yalnız onlar). */
  availableCount: number;
  /** Şıklı soru mu soruluyor, yoksa kartlardan mı üretiliyor. */
  source: 'mcq' | 'cards';
  correctCount: number;
  wrongQuestions: Question[];
  /** `pool` verilmezse hedefin tüm sorularından; `limit` kadarı rastgele seçilir. */
  start: (limit?: number, pool?: Question[]) => void;
  submitMultipleChoice: (choice: string) => void;
  submitTextAnswer: (text: string) => void;
  submitMatchingPair: (frontQuestionId: string, backQuestionId: string) => void;
  goToNext: () => void;
  reset: () => void;
}

export function useLearningEngine(questions: Question[]): UseLearningEngineReturn {
  const mcqs = useMemo(() => questions.filter(isMcq), [questions]);
  const cards = useMemo(() => questions.filter((q) => !isMcq(q)), [questions]);
  const source: 'mcq' | 'cards' = mcqs.length > 0 ? 'mcq' : 'cards';
  const quizPool = source === 'mcq' ? mcqs : cards;

  const [session, setSession] = useState<QuizSession | null>(null);
  const [feedback, setFeedback] = useState<QuizFeedback | null>(null);
  const [matchedPairIds, setMatchedPairIds] = useState<string[]>([]);
  const [lastWrongPair, setLastWrongPair] = useState<{ frontId: string; backId: string } | null>(null);

  const start = useCallback(
    (limit?: number, pool?: Question[]) => {
      const base = pool ?? quizPool;
      const selected = shuffle(base).slice(0, limit && limit > 0 ? limit : base.length);
      const items =
        source === 'mcq' ? selected.map(mcqItem) : buildCardItems(selected, cards.length ? cards : selected);
      setSession({
        items,
        currentIndex: 0,
        answers: [],
        status: items.length > 0 ? 'in-progress' : 'completed',
        totalAnswerable: countAnswerable(items),
      });
      setFeedback(null);
      setMatchedPairIds([]);
      setLastWrongPair(null);
    },
    [quizPool, source, cards]
  );

  const reset = useCallback(() => {
    setSession(null);
    setFeedback(null);
    setMatchedPairIds([]);
    setLastWrongPair(null);
  }, []);

  const currentItem = session ? (session.items[session.currentIndex] ?? null) : null;

  const record = useCallback((mode: QuizMode, questionId: string, userAnswer: string, correct: boolean) => {
    setSession((prev) =>
      prev && prev.status === 'in-progress'
        ? { ...prev, answers: [...prev.answers, { questionId, userAnswer, correct, mode }] }
        : prev
    );
  }, []);

  const feedbackFor = (q: Question, correct: boolean): QuizFeedback => ({
    type: correct ? 'correct' : 'incorrect',
    correctAnswer: q.back,
    explanation: q.explanation,
    source: q.source,
  });

  const submitMultipleChoice = useCallback(
    (choice: string) => {
      if (!currentItem || currentItem.kind !== 'multiple-choice' || feedback) return;
      const correct = choice === currentItem.question.back;
      record('multiple-choice', currentItem.question.id, choice, correct);
      setFeedback(feedbackFor(currentItem.question, correct));
    },
    [currentItem, feedback, record]
  );

  const submitTextAnswer = useCallback(
    (text: string) => {
      if (!currentItem || currentItem.kind !== 'text-input' || feedback) return;
      const correct = normalizeAnswer(text) === normalizeAnswer(currentItem.question.back);
      record('text-input', currentItem.question.id, text, correct);
      setFeedback(feedbackFor(currentItem.question, correct));
    },
    [currentItem, feedback, record]
  );

  const submitMatchingPair = useCallback(
    (frontQuestionId: string, backQuestionId: string) => {
      if (!currentItem || currentItem.kind !== 'matching-pairs') return;
      const correct = frontQuestionId === backQuestionId;
      record('matching-pairs', frontQuestionId, backQuestionId, correct);
      if (correct) {
        setMatchedPairIds((prev) => [...prev, frontQuestionId]);
        setLastWrongPair(null);
      } else {
        setLastWrongPair({ frontId: frontQuestionId, backId: backQuestionId });
      }
    },
    [currentItem, record]
  );

  const goToNext = useCallback(() => {
    setFeedback(null);
    setMatchedPairIds([]);
    setLastWrongPair(null);
    setSession((prev) => {
      if (!prev || prev.status !== 'in-progress') return prev;
      const nextIndex = prev.currentIndex + 1;
      return { ...prev, currentIndex: nextIndex, status: nextIndex >= prev.items.length ? 'completed' : prev.status };
    });
  }, []);

  // Doğru sayısı: soru başına ilk deneme sayılır (eşleştirmede yanlış deneme o çifti "yanlış" yapar).
  const { correctCount, wrongQuestions } = useMemo(() => {
    if (!session) return { correctCount: 0, wrongQuestions: [] as Question[] };
    const byId = new Map<string, Question>();
    for (const item of session.items) {
      if (item.kind === 'matching-pairs') item.pairs.forEach((p) => byId.set(p.id, p));
      else byId.set(item.question.id, item.question);
    }
    const firstResult = new Map<string, boolean>();
    for (const a of session.answers) {
      if (!firstResult.has(a.questionId)) firstResult.set(a.questionId, a.correct);
      else if (!a.correct) firstResult.set(a.questionId, false);
    }
    let correct = 0;
    const wrong: Question[] = [];
    for (const [id, ok] of firstResult) {
      if (ok) correct++;
      else {
        const q = byId.get(id);
        if (q) wrong.push(q);
      }
    }
    return { correctCount: correct, wrongQuestions: wrong };
  }, [session]);

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
    availableCount: quizPool.length,
    source,
    correctCount,
    wrongQuestions,
    start,
    submitMultipleChoice,
    submitTextAnswer,
    submitMatchingPair,
    goToNext,
    reset,
  };
}
