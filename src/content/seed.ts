import type { Course, QuestionSet, SRSEntries } from '@/types';
import { STORAGE_KEYS } from '@/lib/storageKeys';
import { itemsToQuestions } from '@/lib/parser';
import { newId } from '@/lib/utils';

/**
 * Uygulamayla birlikte gelen içerik paketleri. Her paket ilk açılışta bir kez
 * LocalStorage'a eklenir ve kimliği `seededPacks` listesine yazılır; kullanıcı
 * sonradan silerse geri gelmez. İçerik `content/` klasöründeki JSON dosyalarıdır —
 * uygulama kodunda soru yoktur.
 */
interface BundledPack {
  id: string;
  course: string;
  /** İçerik ayrı bir parçada: yalnızca paket henüz tohumlanmadıysa indirilir/okunur. */
  load: () => Promise<{ name: string; items: unknown[] }[]>;
}

export const BUNDLED_PACKS: BundledPack[] = [
  {
    id: 'mikrobiyoloji-hafta-7-8',
    course: 'Mikrobiyoloji',
    load: async () => {
      const [h7, h8] = await Promise.all([
        import('../../content/mikrobiyoloji-hafta-7.json'),
        import('../../content/mikrobiyoloji-hafta-8.json'),
      ]);
      return [h7.default, h8.default];
    },
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

/**
 * React çizilmeden önce bir kez çalışır (main.tsx bekler): eski biçimdeki verileri taşır ve
 * paketleri tohumlar. Sağlayıcılar başlangıç durumunu doğrudan LocalStorage'dan
 * okuduğu için burada yazılan her şey ilk çizimde hazırdır (StrictMode'un çift
 * çalıştırdığı efektlerle yarış da olmaz).
 */
export async function prepareStorage(): Promise<void> {
  try {
    const now = new Date().toISOString();
    const courses = read<Course[]>(STORAGE_KEYS.courses, []);
    const sets = read<QuestionSet[]>(STORAGE_KEYS.questionSets, []);
    let changed = false;

    const ensureCourse = (name: string): Course => {
      const existing = courses.find(
        (c) => c.name.toLocaleLowerCase('tr') === name.toLocaleLowerCase('tr')
      );
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

    // 3) Paketleri tohumla.
    const seeded = read<string[]>(STORAGE_KEYS.seededPacks, []);
    for (const pack of BUNDLED_PACKS) {
      if (seeded.includes(pack.id)) continue;
      const packSets = await pack.load();
      const course = ensureCourse(pack.course);
      for (const s of packSets) {
        const duplicate = sets.some((x) => x.courseId === course.id && x.name === s.name);
        if (duplicate) continue;
        const parsed = itemsToQuestions(s.items);
        if ('error' in parsed) continue;
        sets.push({
          id: newId(),
          name: s.name,
          courseId: course.id,
          createdAt: now,
          updatedAt: now,
          sourceFormat: 'json',
          questions: parsed.questions,
        });
        changed = true;
      }
      seeded.push(pack.id);
    }

    if (changed) {
      write(STORAGE_KEYS.courses, courses);
      write(STORAGE_KEYS.questionSets, sets);
    }
    // Paket "yüklendi" işareti ancak setler yazıldıktan sonra: yazım başarısız olursa
    // (örn. depolama dolu) bir sonraki açılışta yeniden denenir, içerik sessizce kaybolmaz.
    write(STORAGE_KEYS.seededPacks, seeded);
  } catch {
    // Depolama erişilemez (gizli pencere vb.) — uygulama boş durumla açılır.
  }
}
