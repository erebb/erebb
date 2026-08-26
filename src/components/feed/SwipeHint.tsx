import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ChevronUp } from 'lucide-react';

export interface SwipeHintProps {
  visible: boolean;
}

export function SwipeHint({ visible }: SwipeHintProps) {
  const reduced = useReducedMotion();
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="pointer-events-none absolute inset-x-0 bottom-10 z-20 flex flex-col items-center gap-1"
        >
          <motion.div
            animate={reduced ? undefined : { y: [0, -10, 0], opacity: [0.4, 1, 0.4] }}
            transition={{ repeat: Infinity, duration: 1.6 }}
          >
            <ChevronUp className="h-8 w-8 text-white" />
          </motion.div>
          <span className="text-sm font-extrabold text-white/80">Yukarı kaydır</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
