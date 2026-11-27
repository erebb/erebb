import { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type { StudyMode, StudyTarget } from '@/types';
import { AppProvider, useApp } from '@/context/AppContext';
import { Dashboard } from '@/components/Dashboard';
import { CourseView } from '@/components/CourseView';
import { BrowseZone } from '@/components/BrowseZone';
import { FlashcardZone } from '@/components/FlashcardZone';
import { DuolingoZone } from '@/components/DuolingoZone';
import { FeedZone } from '@/components/FeedZone';
import { LessonZone } from '@/components/LessonZone';
import { Button } from '@/components/ui/button';

type View =
  | { name: 'home' }
  | { name: 'course'; courseId: string }
  | { name: 'study'; mode: StudyMode; courseId: string; setId: string | null };

export default function App() {
  return (
    // Tek bir sağlayıcı: görünüm değişince unmount olmamalı; aksi halde çıkışta tetiklenen
    // güncellemeler sağlayıcıyla birlikte sökülür ve hiç işlenmez.
    <AppProvider>
      <Router />
    </AppProvider>
  );
}

function Router() {
  const { courses, getSet, setsOfCourse } = useApp();
  const [view, setView] = useState<View>({ name: 'home' });

  // Çalışma hedefi oturum açıldığında bir kez çözülür: oturum sürerken tekrar kayıtları
  // güncellendikçe soru listesinin kimliği değişip oturumu sıfırlamasın.
  const target = useMemo<StudyTarget | null>(() => {
    if (view.name !== 'study') return null;
    const course = courses.find((c) => c.id === view.courseId);
    if (view.setId) {
      const set = getSet(view.setId);
      return set
        ? {
            title: set.name,
            subtitle: course?.name,
            questions: set.questions,
            lessons: set.lesson?.length ? [{ title: set.name, sections: set.lesson }] : [],
          }
        : null;
    }
    const sets = setsOfCourse(view.courseId);
    return {
      title: `${course?.name ?? 'Ders'} · Tüm ders`,
      subtitle: `${sets.length} set`,
      questions: sets.flatMap((s) => s.questions),
      lessons: sets.filter((s) => s.lesson?.length).map((s) => ({ title: s.name, sections: s.lesson! })),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  const exitStudy = () =>
    setView(view.name === 'study' ? { name: 'course', courseId: view.courseId } : { name: 'home' });

  if (view.name === 'study' && view.mode === 'feed' && target) {
    // Akış tam görünüm alanını sahiplenir; dikey kaydırma yüzeyinde dikey slayt yanlış
    // kaydırma gibi okunacağı için düz solma geçişi.
    return (
      <motion.div key="feed" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
        <FeedZone target={target} onExit={exitStudy} />
      </motion.div>
    );
  }

  const key =
    view.name === 'home' ? 'home' : view.name === 'course' ? `c-${view.courseId}` : `s-${view.mode}-${view.setId}`;

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={key}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -16 }}
        transition={{ duration: 0.18 }}
      >
        {view.name === 'home' && <Dashboard onOpenCourse={(courseId) => setView({ name: 'course', courseId })} />}
        {view.name === 'course' && (
          <CourseView
            courseId={view.courseId}
            onBack={() => setView({ name: 'home' })}
            onStudy={(mode, setId) => setView({ name: 'study', mode, courseId: view.courseId, setId })}
          />
        )}
        {view.name === 'study' && !target && (
          <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6">
            <p className="font-bold text-duo-gray-500">Set bulunamadı.</p>
            <Button variant="blue" onClick={exitStudy}>
              Geri dön
            </Button>
          </div>
        )}
        {view.name === 'study' && target && view.mode === 'browse' && <BrowseZone target={target} onExit={exitStudy} />}
        {view.name === 'study' && target && view.mode === 'quiz' && <DuolingoZone target={target} onExit={exitStudy} />}
        {view.name === 'study' && target && view.mode === 'flashcards' && (
          <FlashcardZone target={target} onExit={exitStudy} />
        )}
        {view.name === 'study' && target && view.mode === 'lesson' && (
          <LessonZone target={target} onExit={exitStudy} onStudy={(mode) => setView({ ...view, mode })} />
        )}
      </motion.div>
    </AnimatePresence>
  );
}
