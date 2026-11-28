import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, BookOpen, ClipboardCheck, CornerDownRight, Layers, ListOrdered } from 'lucide-react';
import type { StudyMode, StudyTarget } from '@/types';
import { Button } from '@/components/ui/button';
import { FullscreenButton } from '@/components/DisplayControls';
import { Card, CardContent } from '@/components/ui/card';
import { RichText } from '@/components/RichText';
import { useLocalStorage } from '@/hooks/useLocalStorage';
import { STORAGE_KEYS } from '@/lib/storageKeys';

interface Props {
  target: StudyTarget;
  onExit: () => void;
  /** Anlatımın sonundan aynı hedefle başka moda geç (soru çöz, kartlar). */
  onStudy?: (mode: StudyMode) => void;
  /** Kalınan bölümü hatırlamak için hedefin anahtarı (set ya da ders). */
  resumeKey?: string;
}

const sectionId = (li: number, si: number) => `konu-${li}-${si}`;

/**
 * Konu anlatımı: sınav için okunacak bölümler, içindekiler ve sonunda "şimdi soru çöz".
 * Tüm ders açıldığında her setin anlatımı kendi başlığı altında sırayla gelir.
 */
export function LessonZone({ target, onExit, onStudy, resumeKey }: Props) {
  const lessons = target.lessons ?? [];
  const many = lessons.length > 1;

  // Bölümler düz sırada: kalınan yer bu sırayla saklanır.
  const flat = useMemo(
    () => lessons.flatMap((l, li) => l.sections.map((s, si) => ({ li, si, title: s.title }))),
    [lessons]
  );
  const [positions, setPositions] = useLocalStorage<Record<string, number>>(STORAGE_KEYS.lessonPos, {});
  const [resumeAt] = useState(() => (resumeKey ? (positions[resumeKey] ?? 0) : 0));
  const resume = resumeAt > 0 && resumeAt < flat.length ? flat[resumeAt] : null;

  // Okurken en üstteki bölümü kaydet (kaydırma durunca).
  const posRef = useRef(resumeAt);
  useEffect(() => {
    if (!resumeKey) return;
    let timer: number | undefined;
    const onScroll = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const els = Array.from(document.querySelectorAll<HTMLElement>('[data-lesson-index]'));
        let idx = 0;
        for (const el of els) if (el.getBoundingClientRect().top <= 140) idx = Number(el.dataset.lessonIndex);
        if (idx !== posRef.current) {
          posRef.current = idx;
          setPositions((prev) => ({ ...prev, [resumeKey]: idx }));
        }
      }, 300);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('scroll', onScroll);
    };
  }, [resumeKey, setPositions]);

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
          <p className="text-xs font-medium text-duo-gray-500">Konu anlatımı</p>
          <h1 className="truncate text-xl font-semibold text-duo-gray-700">{target.title}</h1>
        </div>
        <FullscreenButton />
      </header>

      {lessons.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-sm font-normal text-duo-gray-300">
            Bu sette konu anlatımı yok.
          </CardContent>
        </Card>
      ) : (
        <>
          {resume && (
            <Button
              variant="blue"
              className="h-auto justify-start whitespace-normal py-3 text-left"
              onClick={() => jump(sectionId(resume.li, resume.si))}
              data-lesson-resume
            >
              <CornerDownRight className="h-5 w-5 shrink-0" />
              <span>
                Kaldığın yerden devam et
                <span className="block text-xs font-medium opacity-90">{resume.title}</span>
              </span>
            </Button>
          )}
          <Card>
            <CardContent className="flex flex-col gap-2 p-4">
              <p className="flex items-center gap-2 text-sm font-medium text-duo-gray-500">
                <ListOrdered className="h-4 w-4" /> İçindekiler
              </p>
              <nav aria-label="İçindekiler" className="flex flex-col gap-3">
                {lessons.map((lesson, li) => (
                  <div key={li} className="flex flex-col gap-1">
                    {many && <p className="text-sm font-semibold text-duo-gray-700">{lesson.title}</p>}
                    <ol className="flex flex-col">
                      {lesson.sections.map((s, si) => (
                        <li key={si}>
                          <button
                            type="button"
                            onClick={() => jump(sectionId(li, si))}
                            className="w-full rounded-lg px-2 py-1.5 text-left text-[15px] text-duo-blue-dark hover:bg-duo-blue-light"
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
                <h2 className="px-1 pt-2 text-lg font-semibold text-duo-gray-700" data-lesson-group>
                  {lesson.title}
                </h2>
              )}
              {lesson.sections.map((s, si) => (
                <Card
                  key={si}
                  id={sectionId(li, si)}
                  className="scroll-mt-4"
                  data-lesson-section
                  data-lesson-index={flat.findIndex((f) => f.li === li && f.si === si)}
                >
                  <CardContent className="flex flex-col gap-3.5 p-5 sm:p-6">
                    <h3 className="text-lg font-semibold leading-snug text-duo-gray-700">
                      <span className="tabular-nums text-duo-gray-300">{si + 1}.</span> {s.title}
                    </h3>
                    <RichText text={s.body} />
                    {s.source && (
                      <p className="flex items-center gap-1.5 text-xs font-medium text-duo-gray-300">
                        <BookOpen className="h-3.5 w-3.5" /> {s.source}
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </section>
          ))}

          {onStudy && target.questions.length > 0 && (
            <Card>
              <CardContent className="flex flex-col gap-3 p-4">
                <p className="font-semibold text-duo-gray-700">Okudun mu? Şimdi kendini sına.</p>
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
