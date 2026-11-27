import type { Course, QuestionSet, SRSEntries } from '@/types';
import { STORAGE_KEYS } from '@/lib/storageKeys';
import { itemsToQuestions } from '@/lib/parser';
import { newId } from '@/lib/utils';

/**
 * Uygulamayla birlikte gelen hazır içerik. İçerik `content/` klasöründeki JSON dosyalarıdır —
 * uygulama kodunda soru yoktur.
 *
 * Her set ayrı izlenir ve LocalStorage'daki `seededPacks` listesine `anahtar@sürüm` olarak
 * yazılır:
 * - Hiç yüklenmemişse eklenir.
 * - Daha eski bir sürümü yüklüyse ve kullanıcı o seti düzenlememişse içeriği yenilenir
 *   (soru kimlikleri JSON'daki `id` alanından geldiği için tekrar ilerlemesi korunur).
 * - Kullanıcı seti düzenlediyse ya da sildiyse dokunulmaz; silinen set geri gelmez.
 *
 * İÇERİK DEĞİŞTİĞİNDE: o setin `version` değerini bir artır. Yeni hafta = yeni set girdisi.
 */
interface BundledSet {
  key: string;
  version: number;
  /** İçerik ayrı bir parçada: yalnızca gerektiğinde (yeni ya da güncel değilse) okunur. */
  load: () => Promise<{ name: string; items: unknown[] }>;
}

interface BundledPack {
  course: string;
  /** Sürümlemeden önceki paket kimlikleri: listede varsa bu paketin setleri 1. sürüm sayılır. */
  legacyIds?: string[];
  sets: BundledSet[];
}

export const BUNDLED_PACKS: BundledPack[] = [
  {
    course: 'Mikrobiyoloji',
    legacyIds: ['mikrobiyoloji-hafta-7-8'],
    sets: [
      {
        key: 'mikrobiyoloji-hafta-7',
        version: 2,
        load: () => import('../../content/mikrobiyoloji-hafta-7.json').then((m) => m.default),
      },
      {
        key: 'mikrobiyoloji-hafta-8',
        version: 2,
        load: () => import('../../content/mikrobiyoloji-hafta-8.json').then((m) => m.default),
      },
    ],
  },
];

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
 * React çizilmeden önce bir kez çalışır (main.tsx bekler): eski biçimdeki verileri taşır ve
 * hazır içeriği ekler/günceller. Sağlayıcılar başlangıç durumunu doğrudan LocalStorage'dan
 * okuduğu için burada yazılan her şey ilk çizimde hazırdır (StrictMode'un çift
 * çalıştırdığı efektlerle yarış da olmaz).
 */
export async function prepareStorage(): Promise<void> {
  try {
    const now = new Date().toISOString();
    const courses = read<Course[]>(STORAGE_KEYS.courses, []);
    const sets = read<QuestionSet[]>(STORAGE_KEYS.questionSets, []);
    let changed = false;

    const findCourse = (name: string) =>
      courses.find((c) => c.name.toLocaleLowerCase('tr') === name.toLocaleLowerCase('tr'));
    const ensureCourse = (name: string): Course => {
      const existing = findCourse(name);
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

    // 2) Eski set başına SRS kayıtlarını tek haritaya taşı.
    const legacySrs = read<Record<string, { entries?: SRSEntries }> | null>(STORAGE_KEYS.legacySrs, null);
    if (legacySrs && window.localStorage.getItem(STORAGE_KEYS.srs) === null) {
      const flat: SRSEntries = {};
      for (const deck of Object.values(legacySrs)) Object.assign(flat, deck?.entries ?? {});
      write(STORAGE_KEYS.srs, flat);
      window.localStorage.removeItem(STORAGE_KEYS.legacySrs);
    }

    // 3) Hazır içeriği ekle / güncelle.
    let seeded = read<string[]>(STORAGE_KEYS.seededPacks, []);
    for (const pack of BUNDLED_PACKS) {
      for (const bs of pack.sets) {
        const have = seededVersion(seeded, bs.key, pack.legacyIds);
        if (have >= bs.version) continue;

        const data = await bs.load();
        const parsed = itemsToQuestions(data.items, { idPrefix: `${bs.key}:` });
        if ('error' in parsed) continue;
        const bundle = { key: bs.key, version: bs.version };

        if (have === 0) {
          const course = ensureCourse(pack.course);
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
            });
            changed = true;
          }
        } else {
          // Eski sürüm yüklü: kullanıcının hiç dokunmadığı kopyayı yenile. Sürümlemeden önce
          // eklenen setlerde `bundle` alanı yoktur; onları dersteki adından tanırız.
          const course = findCourse(pack.course);
          const existing =
            sets.find((x) => x.bundle?.key === bs.key) ??
            (course ? sets.find((x) => !x.bundle && x.courseId === course.id && x.name === data.name) : undefined);
          if (existing && existing.updatedAt === existing.createdAt) {
            existing.name = data.name;
            existing.questions = parsed.questions;
            existing.bundle = bundle;
            changed = true;
          }
        }
        seeded = [...seeded.filter((e) => !e.startsWith(`${bs.key}@`)), `${bs.key}@${bs.version}`];
      }
    }

    if (changed) {
      write(STORAGE_KEYS.courses, courses);
      write(STORAGE_KEYS.questionSets, sets);
    }
    // "Yüklendi" işareti ancak setler yazıldıktan sonra: yazım başarısız olursa
    // (örn. depolama dolu) bir sonraki açılışta yeniden denenir, içerik sessizce kaybolmaz.
    write(STORAGE_KEYS.seededPacks, seeded);
  } catch {
    // Depolama erişilemez (gizli pencere vb.) — uygulama boş durumla açılır.
  }
}
