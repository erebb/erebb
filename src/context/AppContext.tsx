import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react';
import type {
  FlashcardDeckState,
  FlashcardSRSEntry,
  Question,
  QuestionSet,
  SourceFormat,
  UserProgress,
} from '@/types';
import { DEFAULT_PROGRESS } from '@/types';
import { STORAGE_KEYS } from '@/lib/storageKeys';
import { addDays, newId, todayISO } from '@/lib/utils';
import { useLocalStorage } from '@/hooks/useLocalStorage';

interface AppContextValue {
  sets: QuestionSet[];
  progress: UserProgress;
  createQuestionSet: (
    name: string,
    questions: Question[],
    sourceFormat: SourceFormat
  ) => QuestionSet;
  updateQuestionSet: (id: string, name: string, questions: Question[]) => void;
  deleteQuestionSet: (id: string) => void;
  getSet: (id: string) => QuestionSet | undefined;
  recordSessionResult: (xpEarned: number) => void;
  setDailyGoal: (xp: number) => void;
  getDeckState: (setId: string) => FlashcardDeckState;
  updateDeckEntry: (setId: string, entry: FlashcardSRSEntry) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [sets, setSets] = useLocalStorage<QuestionSet[]>(STORAGE_KEYS.questionSets, []);
  const [progress, setProgress] = useLocalStorage<UserProgress>(
    STORAGE_KEYS.userProgress,
    DEFAULT_PROGRESS
  );
  const [srs, setSrs] = useLocalStorage<Record<string, FlashcardDeckState>>(STORAGE_KEYS.srs, {});

  const createQuestionSet = useCallback(
    (name: string, questions: Question[], sourceFormat: SourceFormat): QuestionSet => {
      const now = new Date().toISOString();
      const set: QuestionSet = {
        id: newId(),
        name,
        createdAt: now,
        updatedAt: now,
        sourceFormat,
        questions,
      };
      setSets((prev) => [set, ...prev]);
      return set;
    },
    [setSets]
  );

  const updateQuestionSet = useCallback(
    (id: string, name: string, questions: Question[]) => {
      setSets((prev) =>
        prev.map((s) =>
          s.id === id ? { ...s, name, questions, updatedAt: new Date().toISOString() } : s
        )
      );
    },
    [setSets]
  );

  const deleteQuestionSet = useCallback(
    (id: string) => {
      setSets((prev) => prev.filter((s) => s.id !== id));
      setSrs((prev) => {
        if (!(id in prev)) return prev;
        const next = { ...prev };
        delete next[id];
        return next;
      });
    },
    [setSets, setSrs]
  );

  const getSet = useCallback((id: string) => sets.find((s) => s.id === id), [sets]);

  const recordSessionResult = useCallback(
    (xpEarned: number) => {
      if (xpEarned <= 0) return;
      const today = todayISO();
      setProgress((prev) => {
        // Gün değiştiyse günlük sayacı sıfırla.
        const daily = prev.dailyXPDate === today ? prev.dailyXPEarned : 0;

        // Seri: aynı gün → değişmez; dün → +1; aksi halde → 1.
        let streak = prev.streak;
        if (prev.lastPracticedDate !== today) {
          streak = prev.lastPracticedDate === addDays(today, -1) ? prev.streak + 1 : 1;
        }

        return {
          ...prev,
          totalXP: prev.totalXP + xpEarned,
          dailyXPEarned: daily + xpEarned,
          dailyXPDate: today,
          streak,
          lastPracticedDate: today,
        };
      });
    },
    [setProgress]
  );

  const setDailyGoal = useCallback(
    (xp: number) => setProgress((prev) => ({ ...prev, dailyGoalXP: Math.max(10, xp) })),
    [setProgress]
  );

  const getDeckState = useCallback(
    (setId: string): FlashcardDeckState => srs[setId] ?? { setId, entries: {} },
    [srs]
  );

  const updateDeckEntry = useCallback(
    (setId: string, entry: FlashcardSRSEntry) => {
      setSrs((prev) => {
        const deck = prev[setId] ?? { setId, entries: {} };
        return {
          ...prev,
          [setId]: { ...deck, entries: { ...deck.entries, [entry.questionId]: entry } },
        };
      });
    },
    [setSrs]
  );

  const value = useMemo<AppContextValue>(
    () => ({
      sets,
      progress,
      createQuestionSet,
      updateQuestionSet,
      deleteQuestionSet,
      getSet,
      recordSessionResult,
      setDailyGoal,
      getDeckState,
      updateDeckEntry,
    }),
    [
      sets,
      progress,
      createQuestionSet,
      updateQuestionSet,
      deleteQuestionSet,
      getSet,
      recordSessionResult,
      setDailyGoal,
      getDeckState,
      updateDeckEntry,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp yalnızca AppProvider içinde kullanılabilir.');
  return ctx;
}
