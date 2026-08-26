import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AppProvider } from '@/context/AppContext';
import { Dashboard, type StudyMode } from '@/components/Dashboard';
import { FlashcardZone } from '@/components/FlashcardZone';
import { DuolingoZone } from '@/components/DuolingoZone';
import { FeedZone } from '@/components/FeedZone';

type View =
  | { name: 'dashboard' }
  | { name: 'flashcards'; setId: string }
  | { name: 'quiz'; setId: string }
  | { name: 'feed'; setId: string };

export default function App() {
  const [view, setView] = useState<View>({ name: 'dashboard' });

  const goDashboard = () => setView({ name: 'dashboard' });

  const startStudy = (setId: string, mode: StudyMode) => {
    if (mode === 'feed') setView({ name: 'feed', setId });
    else if (mode === 'flashcards') setView({ name: 'flashcards', setId });
    else setView({ name: 'quiz', setId });
  };

  return (
    // Tek bir sağlayıcı: görünüm değişince unmount olmamalı. Aksi halde çıkışta
    // tetiklenen ilerleme güncellemesi (ör. akışın biriken XP'sini yazan
    // recordSessionResult) sağlayıcıyla birlikte sökülür ve hiç işlenmez.
    <AppProvider>
      {view.name === 'feed' ? (
        // Akış tam görünüm alanını sahiplenir ve dikey kaydırma yüzeyi olduğu için
        // dikey slayt yerine düz solma geçişi kullanır (yanlış kaydırma gibi okunmasın).
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
          <FeedZone setId={view.setId} onExit={goDashboard} />
        </motion.div>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div
            key={view.name + ('setId' in view ? view.setId : '')}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            transition={{ duration: 0.2 }}
          >
            {view.name === 'dashboard' && <Dashboard onStudy={startStudy} />}
            {view.name === 'flashcards' && <FlashcardZone setId={view.setId} onExit={goDashboard} />}
            {view.name === 'quiz' && <DuolingoZone setId={view.setId} onExit={goDashboard} />}
          </motion.div>
        </AnimatePresence>
      )}
    </AppProvider>
  );
}
