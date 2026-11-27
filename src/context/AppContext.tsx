import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react';
import type {
  Course,
  FlashcardSRSEntry,
  Question,
  QuestionSet,
  SRSEntries,
  SourceFormat,
} from '@/types';
import type { ParsedPackSet } from '@/lib/parser';
import { STORAGE_KEYS } from '@/lib/storageKeys';
import { newId } from '@/lib/utils';
import { useLocalStorage } from '@/hooks/useLocalStorage';

interface AppContextValue {
  courses: Course[];
  sets: QuestionSet[];
  createCourse: (name: string) => Course;
  renameCourse: (id: string, name: string) => void;
  /** Dersi, setlerini ve o setlerin tekrar kayıtlarını siler. */
  deleteCourse: (id: string) => void;
  setsOfCourse: (courseId: string) => QuestionSet[];
  createQuestionSet: (
    name: string,
    questions: Question[],
    sourceFormat: SourceFormat,
    courseId: string
  ) => QuestionSet;
  /** Bir ders paketini ekler; aynı adlı ders varsa ona katar. Dersin id'sini döner. */
  importPack: (courseName: string, sets: ParsedPackSet[]) => string;
  updateQuestionSet: (id: string, name: string, questions: Question[]) => void;
  deleteQuestionSet: (id: string) => void;
  getSet: (id: string) => QuestionSet | undefined;
  srsEntries: SRSEntries;
  updateSrsEntry: (entry: FlashcardSRSEntry) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [courses, setCourses] = useLocalStorage<Course[]>(STORAGE_KEYS.courses, []);
  const [sets, setSets] = useLocalStorage<QuestionSet[]>(STORAGE_KEYS.questionSets, []);
  const [srsEntries, setSrs] = useLocalStorage<SRSEntries>(STORAGE_KEYS.srs, {});

  const createCourse = useCallback(
    (name: string): Course => {
      const course: Course = { id: newId(), name: name.trim() || 'Yeni ders', createdAt: new Date().toISOString() };
      setCourses((prev) => [...prev, course]);
      return course;
    },
    [setCourses]
  );

  const renameCourse = useCallback(
    (id: string, name: string) => {
      const trimmed = name.trim();
      if (!trimmed) return;
      setCourses((prev) => prev.map((c) => (c.id === id ? { ...c, name: trimmed } : c)));
    },
    [setCourses]
  );

  const forgetSrs = useCallback(
    (questionIds: string[]) => {
      if (questionIds.length === 0) return;
      setSrs((prev) => {
        const next = { ...prev };
        for (const id of questionIds) delete next[id];
        return next;
      });
    },
    [setSrs]
  );

  const deleteCourse = useCallback(
    (id: string) => {
      const removed = sets.filter((s) => s.courseId === id);
      setSets((prev) => prev.filter((s) => s.courseId !== id));
      setCourses((prev) => prev.filter((c) => c.id !== id));
      forgetSrs(removed.flatMap((s) => s.questions.map((q) => q.id)));
    },
    [sets, setSets, setCourses, forgetSrs]
  );

  const setsOfCourse = useCallback(
    (courseId: string) => sets.filter((s) => s.courseId === courseId),
    [sets]
  );

  const createQuestionSet = useCallback(
    (name: string, questions: Question[], sourceFormat: SourceFormat, courseId: string): QuestionSet => {
      const now = new Date().toISOString();
      const set: QuestionSet = { id: newId(), name, courseId, createdAt: now, updatedAt: now, sourceFormat, questions };
      setSets((prev) => [...prev, set]);
      return set;
    },
    [setSets]
  );

  const importPack = useCallback(
    (courseName: string, packSets: ParsedPackSet[]): string => {
      const existing = courses.find(
        (c) => c.name.toLocaleLowerCase('tr') === courseName.trim().toLocaleLowerCase('tr')
      );
      const course = existing ?? createCourse(courseName);
      const now = new Date().toISOString();
      setSets((prev) => [
        ...prev,
        ...packSets.map<QuestionSet>((s) => ({
          id: newId(),
          name: s.name,
          courseId: course.id,
          createdAt: now,
          updatedAt: now,
          sourceFormat: 'json',
          questions: s.questions,
        })),
      ]);
      return course.id;
    },
    [courses, createCourse, setSets]
  );

  const updateQuestionSet = useCallback(
    (id: string, name: string, questions: Question[]) => {
      setSets((prev) =>
        prev.map((s) => (s.id === id ? { ...s, name, questions, updatedAt: new Date().toISOString() } : s))
      );
    },
    [setSets]
  );

  const deleteQuestionSet = useCallback(
    (id: string) => {
      const removed = sets.find((s) => s.id === id);
      setSets((prev) => prev.filter((s) => s.id !== id));
      if (removed) forgetSrs(removed.questions.map((q) => q.id));
    },
    [sets, setSets, forgetSrs]
  );

  const getSet = useCallback((id: string) => sets.find((s) => s.id === id), [sets]);

  const updateSrsEntry = useCallback(
    (entry: FlashcardSRSEntry) => setSrs((prev) => ({ ...prev, [entry.questionId]: entry })),
    [setSrs]
  );

  const value = useMemo<AppContextValue>(
    () => ({
      courses,
      sets,
      createCourse,
      renameCourse,
      deleteCourse,
      setsOfCourse,
      createQuestionSet,
      importPack,
      updateQuestionSet,
      deleteQuestionSet,
      getSet,
      srsEntries,
      updateSrsEntry,
    }),
    [
      courses,
      sets,
      createCourse,
      renameCourse,
      deleteCourse,
      setsOfCourse,
      createQuestionSet,
      importPack,
      updateQuestionSet,
      deleteQuestionSet,
      getSet,
      srsEntries,
      updateSrsEntry,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp yalnızca AppProvider içinde kullanılabilir.');
  return ctx;
}
