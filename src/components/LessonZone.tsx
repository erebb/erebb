import { useEffect, useRef } from 'react';
import { ArrowLeft, BookOpen, ClipboardCheck, Layers, ListOrdered } from 'lucide-react';
import type { StudyMode, StudyTarget } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { RichText } from '@/components/RichText';

interface Props {
  target: StudyTarget;
  onExit: () => void;
  /** Anlatımın sonundan aynı hedefle başka moda geç (soru çöz, kartlar). */
  onStudy?: (mode: StudyMode) => void;
}

const sectionId = (li: number, si: number) => `konu-${li}-${si}`;

/**
 * Konu anlatımı: sınav için okunacak bölümler, içindekiler ve sonunda "şimdi soru çöz".
 * Tüm ders açıldığında her setin anlatımı kendi başlığı altında sırayla gelir.
 */
export function LessonZone({ target, onExit, onStudy }: Props) {
  const lessons = target.lessons ?? [];
  const many = lessons.length > 1;

  // Escape → derse dön. onExit her çizimde yeni bir fonksiyon olabilir; dinleyici ref'ten okur.
  const exitRef = useRef(onExit);
  exitRef.current = onExit;
  useEffect(() => {
    window.scrollTo({ top: 0 });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !e.defaultPrevented) exitRef.current();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-4 p-4 pb-16">
      <header className="flex items-center gap-2 pt-2">
        <Button variant="ghost" size="icon" onClick={onExit} aria-label="Derse dön">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-extrabold uppercase tracking-wide text-duo-blue">Konu anlatımı</p>
          <h1 className="truncate text-xl font-extrabold text-duo-gray-700">{target.title}</h1>
        </div>
      </header>

      {lessons.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-sm font-semibold text-duo-gray-300">
            Bu sette konu anlatımı yok.
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardContent className="flex flex-col gap-2 p-4">
              <p className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wide text-duo-gray-500">
                <ListOrdered className="h-4 w-4" /> İçindekiler
              </p>
              <nav aria-label="İçindekiler" className="flex flex-col gap-3">
                {lessons.map((lesson, li) => (
                  <div key={li} className="flex flex-col gap-1">
                    {many && <p className="text-sm font-extrabold text-duo-gray-700">{lesson.title}</p>}
                    <ol className="flex flex-col">
                      {lesson.sections.map((s, si) => (
                        <li key={si}>
                          <button
                            type="button"
                            onClick={() => jump(sectionId(li, si))}
                            className="w-full rounded-lg px-2 py-1.5 text-left text-sm font-bold text-duo-blue-dark hover:bg-duo-blue-light"
                          >
                            {si + 1}. {s.title}
                          </button>
                        </li>
                      ))}
                    </ol>
                  </div>
                ))}
              </nav>
            </CardContent>
          </Card>

          {lessons.map((lesson, li) => (
            <section key={li} className="flex flex-col gap-4" aria-label={lesson.title}>
              {many && (
                <h2 className="px-1 pt-2 text-lg font-extrabold text-duo-gray-700" data-lesson-group>
                  {lesson.title}
                </h2>
              )}
              {lesson.sections.map((s, si) => (
                <Card key={si} id={sectionId(li, si)} className="scroll-mt-4" data-lesson-section>
                  <CardContent className="flex flex-col gap-3 p-4 sm:p-5">
                    <h3 className="text-lg font-extrabold leading-snug text-duo-gray-700">
                      <span className="text-duo-blue">{si + 1}.</span> {s.title}
                    </h3>
                    <RichText text={s.body} />
                    {s.source && (
                      <p className="flex items-center gap-1.5 text-xs font-bold text-duo-gray-300">
                        <BookOpen className="h-3.5 w-3.5" /> {s.source}
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </section>
          ))}

          {onStudy && target.questions.length > 0 && (
            <Card className="border-duo-green">
              <CardContent className="flex flex-col gap-3 p-4">
                <p className="font-extrabold text-duo-gray-700">Okudun mu? Şimdi kendini sına.</p>
                <div className="grid grid-cols-2 gap-2">
                  <Button size="sm" onClick={() => onStudy('quiz')}>
                    <ClipboardCheck className="h-4 w-4" /> Soru çöz
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => onStudy('flashcards')}>
                    <Layers className="h-4 w-4" /> Kartlar
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
