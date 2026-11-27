import { useRef, useState, type DragEvent } from 'react';
import { AlertTriangle, ClipboardPaste, Upload, XCircle } from 'lucide-react';
import { useApp } from '@/context/AppContext';
import { parseInput } from '@/lib/parser';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';

const NEW_COURSE = '__new__';

interface Props {
  /** Verilirse set bu derse eklenir ve ders seçimi gösterilmez. */
  fixedCourseId?: string;
  onImported?: (courseId: string) => void;
}

/**
 * Dosya (JSON/CSV/TXT) ya da yapıştırılan metinden set ekler. Bir "ders paketi" JSON'u
 * (`{ course, sets: [...] }`) yapıştırılırsa dersi ve tüm setlerini tek seferde ekler.
 */
export function ImportPanel({ fixedCourseId, onImported }: Props) {
  const { courses, createCourse, createQuestionSet, importPack, setsOfCourse } = useApp();

  const [setName, setSetName] = useState('');
  const [courseChoice, setCourseChoice] = useState<string>(fixedCourseId ?? courses[0]?.id ?? NEW_COURSE);
  const [newCourseName, setNewCourseName] = useState('');
  const [pasteText, setPasteText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resolveCourseId = (): string | null => {
    if (fixedCourseId) return fixedCourseId;
    if (courseChoice !== NEW_COURSE && courses.some((c) => c.id === courseChoice)) return courseChoice;
    const name = newCourseName.trim();
    if (!name) {
      setError('Yeni dersin adını yaz ya da listeden bir ders seç.');
      return null;
    }
    const course = createCourse(name);
    setCourseChoice(course.id);
    setNewCourseName('');
    return course.id;
  };

  const importData = (raw: string, filenameHint?: string) => {
    setError(null);
    setWarnings([]);
    setSuccessMsg(null);
    const result = parseInput(raw, filenameHint);
    if (!result.success) {
      setError(result.error);
      return;
    }

    if (result.kind === 'pack') {
      const courseId = importPack(result.course, result.sets);
      const n = result.sets.reduce((sum, s) => sum + s.questions.length, 0);
      setWarnings(result.warnings);
      setSuccessMsg(`"${result.course}" dersine ${result.sets.length} set eklendi — ${n} öğe.`);
      setPasteText('');
      onImported?.(courseId);
      return;
    }

    const courseId = resolveCourseId();
    if (!courseId) return;
    const name =
      setName.trim() ||
      result.suggestedName ||
      filenameHint?.replace(/\.(json|csv|txt)$/i, '') ||
      `Set ${setsOfCourse(courseId).length + 1}`;
    const lower = filenameHint?.toLocaleLowerCase('tr') ?? '';
    const format = lower.endsWith('.json') || raw.trim().startsWith('[') || raw.trim().startsWith('{')
      ? 'json'
      : lower.endsWith('.csv')
        ? 'csv'
        : 'text';
    createQuestionSet(name, result.questions, format, courseId);
    setWarnings(result.warnings);
    setSuccessMsg(`"${name}" kaydedildi — ${result.questions.length} öğe.`);
    setSetName('');
    setPasteText('');
    if (fileInputRef.current) fileInputRef.current.value = '';
    onImported?.(courseId);
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

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Input
          value={setName}
          onChange={(e) => setSetName(e.target.value)}
          placeholder="Set adı (örn. Hafta 9)"
          aria-label="Set adı"
        />
        {!fixedCourseId && (
          <select
            value={courseChoice}
            onChange={(e) => setCourseChoice(e.target.value)}
            aria-label="Ders"
            className="h-12 w-full rounded-xl border-2 border-duo-gray-100 bg-duo-gray-50 px-3 text-base font-semibold text-duo-gray-700 focus:border-duo-blue focus:bg-white focus:outline-none"
          >
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
            <option value={NEW_COURSE}>+ Yeni ders…</option>
          </select>
        )}
      </div>
      {!fixedCourseId && courseChoice === NEW_COURSE && (
        <Input
          value={newCourseName}
          onChange={(e) => setNewCourseName(e.target.value)}
          placeholder="Yeni dersin adı (örn. Biyokimya)"
          aria-label="Yeni ders adı"
        />
      )}

      <Tabs defaultValue="paste">
        <TabsList>
          <TabsTrigger value="paste">
            <ClipboardPaste className="h-4 w-4" /> Metin Yapıştır
          </TabsTrigger>
          <TabsTrigger value="upload">
            <Upload className="h-4 w-4" /> Dosya Yükle
          </TabsTrigger>
        </TabsList>

        <TabsContent value="paste" className="flex flex-col gap-3">
          <Textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={
              'Her satıra bir çift yaz:\nEphemeral - Kısa süreli, geçici\n\nya da sınav soruları / ders paketi JSON\'u yapıştır.'
            }
          />
          <Button onClick={() => importData(pasteText)} disabled={!pasteText.trim()}>
            Kaydet
          </Button>
        </TabsContent>

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
            <p className="font-bold text-duo-gray-700">JSON, CSV ya da TXT dosyasını buraya sürükle</p>
            <p className="text-xs font-semibold text-duo-gray-300">ya da seçmek için tıkla</p>
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
      </Tabs>

      {error && (
        <div className="flex items-start gap-2 rounded-xl bg-duo-red-light p-3 text-sm font-bold text-duo-red-dark">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {successMsg && (
        <div className="rounded-xl bg-duo-green-light p-3 text-sm font-bold text-duo-green-dark">✅ {successMsg}</div>
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
    </div>
  );
}
