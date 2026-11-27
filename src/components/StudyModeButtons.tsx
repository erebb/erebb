import { BookOpen, ClipboardCheck, Eye, Layers, Sparkles } from 'lucide-react';
import type { StudyMode } from '@/types';
import { Button } from '@/components/ui/button';

interface Props {
  onStudy: (mode: StudyMode) => void;
  disabled?: boolean;
  /** Konu anlatımı varsa en üstte "Konu anlatımı" düğmesi. */
  hasLesson?: boolean;
}

/** Bir set ya da tüm ders için çalışma modları (+ varsa konu anlatımı). */
export function StudyModeButtons({ onStudy, disabled, hasLesson }: Props) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {hasLesson && (
        <Button size="sm" variant="outline" className="col-span-2 border-duo-blue text-duo-blue-dark" onClick={() => onStudy('lesson')}>
          <BookOpen className="h-4 w-4" /> Konu anlatımı
        </Button>
      )}
      <Button size="sm" variant="primary" disabled={disabled} onClick={() => onStudy('quiz')}>
        <ClipboardCheck className="h-4 w-4" /> Soru çöz
      </Button>
      <Button size="sm" variant="blue" disabled={disabled} onClick={() => onStudy('browse')}>
        <Eye className="h-4 w-4" /> Göz at
      </Button>
      <Button size="sm" variant="outline" disabled={disabled} onClick={() => onStudy('flashcards')}>
        <Layers className="h-4 w-4" /> Kartlar
      </Button>
      <Button size="sm" variant="outline" disabled={disabled} onClick={() => onStudy('feed')}>
        <Sparkles className="h-4 w-4" /> Akış
      </Button>
    </div>
  );
}
