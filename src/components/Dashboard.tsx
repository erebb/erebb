import { useState } from 'react';
import { ChevronRight, FolderPlus, GraduationCap, Plus, Upload, Volume2, VolumeX } from 'lucide-react';
import { isMcq } from '@/types';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { ImportPanel } from '@/components/ImportPanel';
import { FullscreenButton, ThemeSwitcher } from '@/components/DisplayControls';
import { setSoundEnabled, soundEnabled } from '@/lib/sound';

interface Props {
  onOpenCourse: (courseId: string) => void;
}

/** Ana ekran: dersler. Bir derse tıklayınca setleri (haftaları) açılır. */
export function Dashboard({ onOpenCourse }: Props) {
  const { courses, setsOfCourse, createCourse } = useApp();
  const [newCourseOpen, setNewCourseOpen] = useState(false);
  const [newCourseName, setNewCourseName] = useState('');
  const [importOpen, setImportOpen] = useState(false);
  const [sound, setSound] = useState(soundEnabled);

  const submitNewCourse = () => {
    const name = newCourseName.trim();
    if (!name) return;
    const course = createCourse(name);
    setNewCourseName('');
    setNewCourseOpen(false);
    onOpenCourse(course.id);
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-6 p-4 pb-12">
      <header className="flex items-center justify-between gap-3 pt-4">
        <div>
          <h1 className="text-2xl font-semibold text-duo-gray-900">Derslerim</h1>
          <p className="text-sm text-duo-gray-500">Bir derse gir, haftayı seç, çalış.</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setNewCourseOpen(true)}>
          <FolderPlus className="h-4 w-4" /> Yeni ders
        </Button>
      </header>

      <section className="flex flex-col gap-3" aria-label="Dersler">
        {courses.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-sm font-normal text-duo-gray-300">
              Henüz dersin yok. “Yeni ders” ile başla ya da aşağıdan içerik içe aktar.
            </CardContent>
          </Card>
        ) : (
          courses.map((course) => {
            const sets = setsOfCourse(course.id);
            const items = sets.flatMap((s) => s.questions);
            const mcq = items.filter(isMcq).length;
            return (
              <button
                key={course.id}
                onClick={() => onOpenCourse(course.id)}
                className="flex w-full items-center gap-4 rounded-2xl border border-duo-gray-100 bg-surface p-4 text-left shadow-duo-card transition-colors hover:border-duo-blue/50"
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-duo-blue-light text-duo-blue-dark">
                  <GraduationCap className="h-6 w-6" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-lg font-semibold text-duo-gray-700">{course.name}</span>
                  <span className="block text-xs font-medium text-duo-gray-300">
                    {sets.length} set · {mcq} soru · {items.length - mcq} kart
                  </span>
                </span>
                <ChevronRight className="h-5 w-5 shrink-0 text-duo-gray-300" />
              </button>
            );
          })
        )}
      </section>

      <Card>
        <CardHeader className="pb-3">
          <button
            onClick={() => setImportOpen((o) => !o)}
            className="flex items-center justify-between text-left"
            aria-expanded={importOpen}
          >
            <CardTitle className="flex items-center gap-2">
              <Upload className="h-5 w-5 text-duo-blue" /> İçe aktar
            </CardTitle>
            <Plus className={importOpen ? 'h-5 w-5 rotate-45 text-duo-gray-300 transition-transform' : 'h-5 w-5 text-duo-gray-300 transition-transform'} />
          </button>
          {!importOpen && (
            <p className="text-xs font-normal text-duo-gray-300">
              Metin, CSV ya da JSON (sınav soruları veya ders paketi) ile bir derse set ekle.
            </p>
          )}
        </CardHeader>
        {importOpen && (
          <CardContent>
            <ImportPanel />
          </CardContent>
        )}
      </Card>

      <Dialog open={newCourseOpen} onOpenChange={setNewCourseOpen}>
        <DialogContent>
          <DialogTitle>Yeni ders</DialogTitle>
          <DialogDescription>Örn. Biyokimya, Anatomi, Farmakoloji.</DialogDescription>
          <form
            className="mt-4 flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              submitNewCourse();
            }}
          >
            <Input
              autoFocus
              value={newCourseName}
              onChange={(e) => setNewCourseName(e.target.value)}
              placeholder="Ders adı"
              aria-label="Ders adı"
            />
            <div className="grid grid-cols-2 gap-2">
              <Button type="button" variant="outline" onClick={() => setNewCourseOpen(false)}>
                Vazgeç
              </Button>
              <Button type="submit" disabled={!newCourseName.trim()}>
                Oluştur
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <footer className="mt-auto flex flex-col items-center gap-3 pt-6">
        <div className="flex flex-wrap items-center justify-center gap-2" aria-label="Görünüm">
          <ThemeSwitcher />
          <button
            type="button"
            onClick={() => {
              setSoundEnabled(!sound);
              setSound(!sound);
            }}
            aria-pressed={sound}
            data-sound-toggle=""
            className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-duo-gray-100 bg-surface px-3 text-xs font-medium text-duo-gray-500 hover:text-duo-gray-700"
          >
            {sound ? <Volume2 className="h-3.5 w-3.5" /> : <VolumeX className="h-3.5 w-3.5" />}
            {sound ? 'Sesler açık' : 'Sesler kapalı'}
          </button>
          <FullscreenButton className="h-9 w-9 border border-duo-gray-100 bg-surface" />
        </div>
        <p className="text-center text-xs text-duo-gray-300" data-app-version>
          Kelime Ustası · sürüm {__APP_VERSION__}
        </p>
      </footer>
    </div>
  );
}
