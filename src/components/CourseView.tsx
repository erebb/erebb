import { useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft, Pencil, Plus, Trash2 } from 'lucide-react';
import type { Question, QuestionSet, StudyMode } from '@/types';
import { isMcq } from '@/types';
import { useApp } from '@/context/AppContext';
import { parseInput, serializeForEdit } from '@/lib/parser';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { ImportPanel } from '@/components/ImportPanel';
import { StudyModeButtons } from '@/components/StudyModeButtons';

interface Props {
  courseId: string;
  onBack: () => void;
  /** setId null → dersin tüm setleri birlikte. */
  onStudy: (mode: StudyMode, setId: string | null) => void;
}

function counts(items: Question[]) {
  const mcq = items.filter(isMcq).length;
  return `${mcq} soru · ${items.length - mcq} kart`;
}

export function CourseView({ courseId, onBack, onStudy }: Props) {
  const { courses, setsOfCourse, renameCourse, deleteCourse, updateQuestionSet, deleteQuestionSet } = useApp();
  const course = courses.find((c) => c.id === courseId);
  const sets = setsOfCourse(courseId);

  const [renameOpen, setRenameOpen] = useState(false);
  const [courseName, setCourseName] = useState(course?.name ?? '');
  const [deleteCourseOpen, setDeleteCourseOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);

  const [editTarget, setEditTarget] = useState<QuestionSet | null>(null);
  const [editName, setEditName] = useState('');
  const [editText, setEditText] = useState('');
  const [editFormat, setEditFormat] = useState<'lines' | 'json'>('lines');
  const [editError, setEditError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<QuestionSet | null>(null);

  if (!course) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6">
        <p className="font-bold text-duo-gray-500">Ders bulunamadı.</p>
        <Button variant="blue" onClick={onBack}>
          Derslere dön
        </Button>
      </div>
    );
  }

  const all = sets.flatMap((s) => s.questions);

  const openEdit = (set: QuestionSet) => {
    const { text, format } = serializeForEdit(set.questions);
    setEditTarget(set);
    setEditName(set.name);
    setEditText(text);
    setEditFormat(format);
    setEditError(null);
  };

  const saveEdit = () => {
    if (!editTarget) return;
    const result = parseInput(editText);
    if (!result.success) {
      setEditError(result.error);
      return;
    }
    if (result.kind !== 'set') {
      setEditError('Burada tek bir setin öğeleri bekleniyor, ders paketi değil.');
      return;
    }
    updateQuestionSet(editTarget.id, editName.trim() || editTarget.name, result.questions);
    setEditTarget(null);
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-5 p-4 pb-12">
      <header className="flex items-center gap-2 pt-2">
        <Button variant="ghost" size="icon" onClick={onBack} aria-label="Derslere dön">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-2xl font-extrabold text-duo-gray-700">{course.name}</h1>
          <p className="text-xs font-bold text-duo-gray-300">
            {sets.length} set · {counts(all)}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Dersi yeniden adlandır"
          onClick={() => {
            setCourseName(course.name);
            setRenameOpen(true);
          }}
        >
          <Pencil className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" aria-label="Dersi sil" onClick={() => setDeleteCourseOpen(true)}>
          <Trash2 className="h-4 w-4 text-duo-red" />
        </Button>
      </header>

      {sets.length > 1 && (
        <Card className="border-duo-green">
          <CardContent className="flex flex-col gap-3 p-4">
            <div>
              <p className="font-extrabold text-duo-gray-700">Tüm ders</p>
              <p className="text-xs font-semibold text-duo-gray-300">Bütün setler birlikte · {counts(all)}</p>
            </div>
            <StudyModeButtons onStudy={(mode) => onStudy(mode, null)} disabled={all.length === 0} />
          </CardContent>
        </Card>
      )}

      <section className="flex flex-col gap-3" aria-label="Setler">
        {sets.length === 0 && (
          <Card>
            <CardContent className="p-8 text-center text-sm font-semibold text-duo-gray-300">
              Bu derste henüz set yok. Aşağıdan bir set ekle.
            </CardContent>
          </Card>
        )}
        {sets.map((set, i) => (
          <motion.div
            key={set.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
          >
            <Card data-set-card={set.name}>
              <CardContent className="flex flex-col gap-3 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-extrabold text-duo-gray-700">{set.name}</p>
                    <p className="text-xs font-semibold text-duo-gray-300">{counts(set.questions)}</p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(set)} aria-label="Düzenle">
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(set)} aria-label="Sil">
                      <Trash2 className="h-4 w-4 text-duo-red" />
                    </Button>
                  </div>
                </div>
                <StudyModeButtons onStudy={(mode) => onStudy(mode, set.id)} disabled={set.questions.length === 0} />
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </section>

      <Card>
        <CardContent className="flex flex-col gap-3 p-4">
          {addOpen ? (
            <ImportPanel fixedCourseId={course.id} />
          ) : (
            <Button variant="outline" onClick={() => setAddOpen(true)}>
              <Plus className="h-4 w-4" /> Bu derse set ekle
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Dersi yeniden adlandır */}
      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent>
          <DialogTitle>Dersi yeniden adlandır</DialogTitle>
          <form
            className="mt-4 flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              renameCourse(course.id, courseName);
              setRenameOpen(false);
            }}
          >
            <Input autoFocus value={courseName} onChange={(e) => setCourseName(e.target.value)} aria-label="Ders adı" />
            <div className="grid grid-cols-2 gap-2">
              <Button type="button" variant="outline" onClick={() => setRenameOpen(false)}>
                Vazgeç
              </Button>
              <Button type="submit" disabled={!courseName.trim()}>
                Kaydet
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Dersi sil */}
      <Dialog open={deleteCourseOpen} onOpenChange={setDeleteCourseOpen}>
        <DialogContent>
          <DialogTitle>Dersi sil</DialogTitle>
          <DialogDescription>
            “{course.name}” ve içindeki {sets.length} set ({all.length} öğe) kalıcı olarak silinecek. Emin misin?
          </DialogDescription>
          <div className="mt-6 grid grid-cols-2 gap-2">
            <Button variant="outline" onClick={() => setDeleteCourseOpen(false)}>
              Vazgeç
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                deleteCourse(course.id);
                setDeleteCourseOpen(false);
                onBack();
              }}
            >
              Evet, sil
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Seti düzenle */}
      <Dialog open={editTarget !== null} onOpenChange={(open) => !open && setEditTarget(null)}>
        <DialogContent className="max-w-2xl">
          <DialogTitle>Seti düzenle</DialogTitle>
          <DialogDescription>
            {editFormat === 'lines'
              ? 'Her satıra bir "Ön - Arka" çifti.'
              : 'Şıklı sorular, açıklamalar ve kaynaklar kaybolmasın diye JSON olarak düzenleniyor.'}
          </DialogDescription>
          <div className="mt-4 flex flex-col gap-3">
            <Input value={editName} onChange={(e) => setEditName(e.target.value)} placeholder="Set adı" aria-label="Set adı" />
            <Textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              className={editFormat === 'json' ? 'min-h-[320px] font-mono text-xs' : 'min-h-[220px]'}
              spellCheck={false}
            />
            {editError && (
              <p className="rounded-xl bg-duo-red-light p-3 text-sm font-bold text-duo-red-dark">{editError}</p>
            )}
            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={() => setEditTarget(null)}>
                Vazgeç
              </Button>
              <Button onClick={saveEdit}>Kaydet</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Seti sil */}
      <Dialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogTitle>Seti sil</DialogTitle>
          <DialogDescription>
            “{deleteTarget?.name}” ve tekrar kayıtları kalıcı olarak silinecek. Emin misin?
          </DialogDescription>
          <div className="mt-6 grid grid-cols-2 gap-2">
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Vazgeç
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                if (deleteTarget) deleteQuestionSet(deleteTarget.id);
                setDeleteTarget(null);
              }}
            >
              Evet, sil
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
