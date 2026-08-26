import { useRef, useState, type DragEvent } from 'react';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  BookOpen,
  ClipboardPaste,
  Flame,
  Gamepad2,
  Layers,
  Pencil,
  Sparkles,
  Trash2,
  Upload,
  XCircle,
} from 'lucide-react';
import type { QuestionSet } from '@/types';
import { useApp } from '@/context/AppContext';
import { parseInput } from '@/lib/parser';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';

export type StudyMode = 'flashcards' | 'quiz' | 'feed';

interface Props {
  onStudy: (setId: string, mode: StudyMode) => void;
}

export function Dashboard({ onStudy }: Props) {
  const { sets, progress, createQuestionSet, updateQuestionSet, deleteQuestionSet } = useApp();

  const [setName, setSetName] = useState('');
  const [pasteText, setPasteText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [editTarget, setEditTarget] = useState<QuestionSet | null>(null);
  const [editName, setEditName] = useState('');
  const [editText, setEditText] = useState('');
  const [editError, setEditError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<QuestionSet | null>(null);

  const dailyPercent =
    progress.dailyGoalXP > 0
      ? Math.min(100, (progress.dailyXPEarned / progress.dailyGoalXP) * 100)
      : 0;

  const resetFeedback = () => {
    setError(null);
    setWarnings([]);
    setSuccessMsg(null);
  };

  const importData = (raw: string, filenameHint?: string) => {
    resetFeedback();
    const result = parseInput(raw, filenameHint);
    if (!result.success) {
      setError(result.error);
      return;
    }
    const name =
      setName.trim() ||
      filenameHint?.replace(/\.(json|csv|txt)$/i, '') ||
      `Soru Seti ${sets.length + 1}`;
    const lower = filenameHint?.toLocaleLowerCase('tr') ?? '';
    const format = lower.endsWith('.json') ? 'json' : lower.endsWith('.csv') ? 'csv' : 'text';
    createQuestionSet(name, result.questions, format);
    setWarnings(result.warnings);
    setSuccessMsg(`"${name}" kaydedildi — ${result.questions.length} soru.`);
    setSetName('');
    setPasteText('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => importData(String(reader.result ?? ''), file.name);
    reader.onerror = () => setError('Dosya okunamadı. Lütfen tekrar deneyin.');
    reader.readAsText(file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const openEdit = (set: QuestionSet) => {
    setEditTarget(set);
    setEditName(set.name);
    setEditText(set.questions.map((q) => `${q.front} - ${q.back}`).join('\n'));
    setEditError(null);
  };

  const saveEdit = () => {
    if (!editTarget) return;
    const result = parseInput(editText);
    if (!result.success) {
      setEditError(result.error);
      return;
    }
    updateQuestionSet(editTarget.id, editName.trim() || editTarget.name, result.questions);
    setEditTarget(null);
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-6 p-4 pb-12">
      {/* Başlık + oyunlaştırma özeti */}
      <header className="flex flex-col gap-4 pt-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-extrabold text-duo-green">Kelime Ustası</h1>
          <div className="flex items-center gap-2">
            <Badge variant="gold">
              <Flame className="h-4 w-4" /> {progress.streak} gün
            </Badge>
            <Badge variant="blue">
              <Sparkles className="h-4 w-4" /> {progress.totalXP} XP
            </Badge>
          </div>
        </div>
        <Card>
          <CardContent className="flex flex-col gap-2 p-4">
            <div className="flex items-center justify-between text-sm font-extrabold">
              <span className="text-duo-gray-500">Günlük Hedef</span>
              <span className="text-duo-gold-dark">
                {progress.dailyXPEarned} / {progress.dailyGoalXP} XP
              </span>
            </div>
            <Progress value={dailyPercent} indicatorClassName="bg-duo-gold" />
          </CardContent>
        </Card>
      </header>

      {/* Veri yükleme */}
      <Card>
        <CardHeader>
          <CardTitle>Yeni Soru Seti Ekle</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Input
            value={setName}
            onChange={(e) => setSetName(e.target.value)}
            placeholder="Set adı (boş bırakılırsa otomatik verilir)"
          />

          <Tabs defaultValue="upload">
            <TabsList>
              <TabsTrigger value="upload">
                <Upload className="h-4 w-4" /> Dosya Yükle
              </TabsTrigger>
              <TabsTrigger value="paste">
                <ClipboardPaste className="h-4 w-4" /> Metin Yapıştır
              </TabsTrigger>
            </TabsList>

            <TabsContent value="upload">
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={onDrop}
                onClick={() => fileInputRef.current?.click()}
                className={
                  isDragging
                    ? 'flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-duo-blue bg-duo-blue-light p-8 text-center transition-colors'
                    : 'flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-duo-gray-100 p-8 text-center transition-colors hover:border-duo-blue'
                }
              >
                <Upload className="h-8 w-8 text-duo-blue" />
                <p className="font-bold text-duo-gray-700">
                  JSON veya CSV dosyasını buraya sürükle
                </p>
                <p className="text-xs font-semibold text-duo-gray-300">
                  ya da seçmek için tıkla · örn: {'[{"kelime": "Hello", "tanim": "Merhaba"}]'}
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json,.csv,.txt,application/json,text/csv,text/plain"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFile(file);
                  }}
                />
              </div>
            </TabsContent>

            <TabsContent value="paste" className="flex flex-col gap-3">
              <Textarea
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                placeholder={
                  'Her satıra bir çift yaz:\nEphemeral - Kısa süreli, geçici\nUbiquitous - Her yerde bulunan'
                }
              />
              <Button onClick={() => importData(pasteText)} disabled={!pasteText.trim()}>
                Seti Kaydet
              </Button>
            </TabsContent>
          </Tabs>

          {error && (
            <div className="flex items-start gap-2 rounded-xl bg-duo-red-light p-3 text-sm font-bold text-duo-red-dark">
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {successMsg && (
            <div className="rounded-xl bg-duo-green-light p-3 text-sm font-bold text-duo-green-dark">
              ✅ {successMsg}
            </div>
          )}
          {warnings.length > 0 && (
            <div className="flex flex-col gap-1 rounded-xl bg-duo-gold-light p-3 text-xs font-semibold text-duo-gold-dark">
              <span className="flex items-center gap-1 font-extrabold">
                <AlertTriangle className="h-4 w-4" /> Uyarılar
              </span>
              {warnings.slice(0, 5).map((w, i) => (
                <span key={i}>• {w}</span>
              ))}
              {warnings.length > 5 && <span>… ve {warnings.length - 5} uyarı daha</span>}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Kayıtlı setler */}
      <section className="flex flex-col gap-3">
        <h2 className="flex items-center gap-2 text-lg font-extrabold text-duo-gray-700">
          <Layers className="h-5 w-5 text-duo-blue" /> Soru Setlerim
        </h2>

        {sets.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-sm font-semibold text-duo-gray-300">
              Henüz soru setin yok. Yukarıdan bir dosya yükle veya metin yapıştır! 🚀
            </CardContent>
          </Card>
        ) : (
          sets.map((set, i) => (
            <motion.div
              key={set.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <Card>
                <CardContent className="flex flex-col gap-3 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-extrabold text-duo-gray-700">{set.name}</p>
                      <p className="text-xs font-semibold text-duo-gray-300">
                        {set.questions.length} soru ·{' '}
                        {new Date(set.updatedAt).toLocaleDateString('tr-TR')}
                      </p>
                    </div>
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openEdit(set)}
                        aria-label="Düzenle"
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setDeleteTarget(set)}
                        aria-label="Sil"
                      >
                        <Trash2 className="h-4 w-4 text-duo-red" />
                      </Button>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Button
                      variant="primary"
                      size="sm"
                      className="col-span-2"
                      onClick={() => onStudy(set.id, 'feed')}
                    >
                      <Sparkles className="h-4 w-4" /> Akış
                      <Badge variant="gold" className="ml-1">
                        YENİ
                      </Badge>
                    </Button>
                    <Button variant="blue" size="sm" onClick={() => onStudy(set.id, 'flashcards')}>
                      <BookOpen className="h-4 w-4" /> Kartlar
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => onStudy(set.id, 'quiz')}>
                      <Gamepad2 className="h-4 w-4" /> Test
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))
        )}
      </section>

      {/* Düzenleme penceresi */}
      <Dialog open={editTarget !== null} onOpenChange={(open) => !open && setEditTarget(null)}>
        <DialogContent>
          <DialogTitle>Seti Düzenle</DialogTitle>
          <DialogDescription>
            Her satıra bir "Kelime - Tanım" çifti gelecek şekilde düzenle.
          </DialogDescription>
          <div className="mt-4 flex flex-col gap-3">
            <Input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              placeholder="Set adı"
            />
            <Textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              className="min-h-[200px]"
            />
            {editError && (
              <p className="rounded-xl bg-duo-red-light p-3 text-sm font-bold text-duo-red-dark">
                {editError}
              </p>
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

      {/* Silme onayı */}
      <Dialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogTitle>Seti Sil</DialogTitle>
          <DialogDescription>
            "{deleteTarget?.name}" seti ve ilerleme kayıtları kalıcı olarak silinecek. Emin misin?
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
              Evet, Sil
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
