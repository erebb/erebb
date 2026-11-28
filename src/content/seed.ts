import type { Course, QuestionSet, SRSEntries } from '@/types';
import { STORAGE_KEYS } from '@/lib/storageKeys';
import { itemsToQuestions, parseLesson } from '@/lib/parser';
import { newId } from '@/lib/utils';
import bundledManifest from '../../content/manifest.json';

/**
 * Hazır içerik. İçerik `content/` klasöründeki JSON dosyalarıdır — uygulama kodunda soru yoktur.
 * Hangi dersin hangi setinin hangi sürümde olduğu `content/manifest.json`'dadır; aynı dosya
 * hem uygulamanın içine gömülür hem de açılışta GitHub'daki son sürümden okunur (bkz.
 * lib/updates.ts) — böylece yeni içerik uygulamayı yeniden kurmadan gelir.
 *
 * Her set ayrı izlenir ve LocalStorage'daki `seededPacks` listesine `anahtar@sürüm` olarak
 * yazılır:
 * - Hiç yüklenmemişse eklenir.
 * - Daha eski bir sürümü yüklüyse ve kullanıcı o seti düzenlememişse içeriği yenilenir
 *   (soru kimlikleri JSON'daki `id` alanından geldiği için ilerleme korunur).
 * - Kullanıcı seti düzenlediyse ya da sildiyse dokunulmaz; silinen set geri gelmez.
 *
 * İÇERİK DEĞİŞTİĞİNDE: manifest'te o setin `version` değerini bir artır. Yeni hafta = yeni set.
 */
export interface ContentManifest {
  schema: number;
  packs: {
    course: string;
    /** Sürümlemeden önceki paket kimlikleri: listede varsa bu paketin setleri 1. sürüm sayılır. */
    legacyIds?: string[];
    sets: { key: string; version: number; file: string }[];
  }[];
}

export interface ContentFile {
  name: string;
  items: unknown[];
  lesson?: unknown;
}

/** Bu uygulamanın anlayabildiği en yeni manifest biçimi. */
export const SUPPORTED_SCHEMA = 1;

/** Dışarıdan gelen manifest'i doğrular (uzaktan okunan veri güvenilmez). */
export function isManifest(m: unknown): m is ContentManifest {
  if (typeof m !== 'object' || m === null) return false;
  const x = m as ContentManifest;
  return (
    typeof x.schema === 'number' &&
    Array.isArray(x.packs) &&
    x.packs.every(
      (p) =>
        typeof p?.course === 'string' &&
        Array.isArray(p.sets) &&
        p.sets.every(
          (s) =>
            typeof s?.key === 'string' &&
            Number.isInteger(s.version) &&
            s.version > 0 &&
            typeof s.file === 'string' &&
            /^[a-z0-9-]+\.json$/.test(s.file)
        )
    )
  );
}

export const BUNDLED_MANIFEST = bundledManifest as ContentManifest;

/** Gömülü içerik dosyaları ayrı parçalarda: yalnızca gerektiğinde (yeni ya da eskiyse) yüklenir. */
const bundledFiles = import.meta.glob<{ default: ContentFile }>(['../../content/*.json', '!../../content/manifest.json']);

export function loadBundled(file: string): Promise<ContentFile> {
  const loader = bundledFiles[`../../content/${file}`];
  if (!loader) return Promise.reject(new Error(`Gömülü içerik yok: ${file}`));
  return loader().then((m) => m.default);
}

const LEGACY_COURSE_NAME = 'Genel';

function read<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  window.localStorage.setItem(key, JSON.stringify(value));
}

/** Bu setin yüklü olduğu kaydedilmiş en yüksek sürüm (0 = hiç yüklenmemiş). */
function seededVersion(seeded: string[], key: string, legacyIds: string[] = []): number {
  let version = 0;
  for (const entry of seeded) {
    const at = entry.lastIndexOf('@');
    if (at > 0 && entry.slice(0, at) === key) version = Math.max(version, Number(entry.slice(at + 1)) || 0);
  }
  if (version === 0 && legacyIds.some((id) => seeded.includes(id))) version = 1;
  return version;
}

/**
 * Manifest'teki setleri depolamayla eşitler; eklenen ya da yenilenen setlerin adlarını döner.
 * `load` gömülü dosyayı ya da uzaktan indirilen dosyayı getirir. Bir dosya yüklenemez ya da
 * geçersizse o set atlanır ve sürümü işaretlenmez (bir sonraki açılışta yeniden denenir).
 */
export async function syncContent(
  manifest: ContentManifest,
  load: (file: string) => Promise<ContentFile>
): Promise<string[]> {
  const now = new Date().toISOString();
  const courses = read<Course[]>(STORAGE_KEYS.courses, []);
  const sets = read<QuestionSet[]>(STORAGE_KEYS.questionSets, []);
  let seeded = read<string[]>(STORAGE_KEYS.seededPacks, []);
  const changedNames: string[] = [];
  let changed = false;

  const findCourse = (name: string) =>
    courses.find((c) => c.name.toLocaleLowerCase('tr') === name.toLocaleLowerCase('tr'));

  for (const pack of manifest.packs) {
    for (const ms of pack.sets) {
      const have = seededVersion(seeded, ms.key, pack.legacyIds);
      if (have >= ms.version) continue;

      let data: ContentFile;
      try {
        data = await load(ms.file);
      } catch {
        continue;
      }
      if (!data || typeof data.name !== 'string' || !Array.isArray(data.items)) continue;
      const parsed = itemsToQuestions(data.items, { idPrefix: `${ms.key}:` });
      if ('error' in parsed) continue;
      const bundle = { key: ms.key, version: ms.version };
      const lesson = parseLesson(data.lesson);

      if (have === 0) {
        let course = findCourse(pack.course);
        if (!course) {
          course = { id: newId(), name: pack.course, createdAt: now };
          courses.push(course);
        }
        if (!sets.some((x) => x.courseId === course.id && x.name === data.name)) {
          sets.push({
            id: newId(),
            name: data.name,
            courseId: course.id,
            createdAt: now,
            updatedAt: now,
            sourceFormat: 'json',
            questions: parsed.questions,
            bundle,
            ...(lesson ? { lesson } : {}),
          });
          changedNames.push(data.name);
        }
      } else {
        // Eski sürüm yüklü: kullanıcının hiç dokunmadığı kopyayı yenile. Sürümlemeden önce
        // eklenen setlerde `bundle` alanı yoktur; onları dersteki adından tanırız.
        const course = findCourse(pack.course);
        const existing =
          sets.find((x) => x.bundle?.key === ms.key) ??
          (course ? sets.find((x) => !x.bundle && x.courseId === course.id && x.name === data.name) : undefined);
        if (existing && existing.updatedAt === existing.createdAt) {
          existing.name = data.name;
          existing.questions = parsed.questions;
          existing.bundle = bundle;
          if (lesson) existing.lesson = lesson;
          else delete existing.lesson;
          changedNames.push(data.name);
        }
      }
      seeded = [...seeded.filter((e) => !e.startsWith(`${ms.key}@`)), `${ms.key}@${ms.version}`];
      changed = true;
    }
  }

  if (changed) {
    if (changedNames.length) {
      write(STORAGE_KEYS.courses, courses);
      write(STORAGE_KEYS.questionSets, sets);
    }
    // "Yüklendi" işareti ancak setler yazıldıktan sonra: yazım başarısız olursa
    // (örn. depolama dolu) bir sonraki açılışta yeniden denenir, içerik sessizce kaybolmaz.
    write(STORAGE_KEYS.seededPacks, seeded);
  }
  return changedNames;
}

/**
 * React çizilmeden önce bir kez çalışır (main.tsx bekler): eski biçimdeki verileri taşır ve
 * gömülü içeriği ekler/günceller. Sağlayıcılar başlangıç durumunu doğrudan LocalStorage'dan
 * okuduğu için burada yazılan her şey ilk çizimde hazırdır.
 */
export async function prepareStorage(): Promise<void> {
  try {
    const now = new Date().toISOString();
    const courses = read<Course[]>(STORAGE_KEYS.courses, []);
    const sets = read<QuestionSet[]>(STORAGE_KEYS.questionSets, []);
    let changed = false;

    const ensureCourse = (name: string): Course => {
      const existing = courses.find((c) => c.name.toLocaleLowerCase('tr') === name.toLocaleLowerCase('tr'));
      if (existing) return existing;
      const course: Course = { id: newId(), name, createdAt: now };
      courses.push(course);
      changed = true;
      return course;
    };

    // 1) Ders kavramından önceki setler → "Genel" dersi.
    for (const s of sets) {
      if (!s.courseId || !courses.some((c) => c.id === s.courseId)) {
        s.courseId = ensureCourse(LEGACY_COURSE_NAME).id;
        changed = true;
      }
      // Eski kartlarda tür alanı yoktu.
      for (const q of s.questions) {
        if (!q.kind) {
          q.kind = 'card';
          changed = true;
        }
      }
    }
    if (changed) {
      write(STORAGE_KEYS.courses, courses);
      write(STORAGE_KEYS.questionSets, sets);
    }

    // 2) Eski set başına SRS kayıtlarını tek haritaya taşı.
    const legacySrs = read<Record<string, { entries?: SRSEntries }> | null>(STORAGE_KEYS.legacySrs, null);
    if (legacySrs && window.localStorage.getItem(STORAGE_KEYS.srs) === null) {
      const flat: SRSEntries = {};
      for (const deck of Object.values(legacySrs)) Object.assign(flat, deck?.entries ?? {});
      write(STORAGE_KEYS.srs, flat);
      window.localStorage.removeItem(STORAGE_KEYS.legacySrs);
    }

    // 3) Gömülü içeriği ekle / güncelle.
    await syncContent(BUNDLED_MANIFEST, loadBundled);
  } catch {
    // Depolama erişilemez (gizli pencere vb.) — uygulama boş durumla açılır.
  }
}
