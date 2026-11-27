import Papa from 'papaparse';
import type { Question } from '@/types';
import { isMcq } from '@/types';
import { dedupeBy, newId, normalizeAnswer } from '@/lib/utils';

/**
 * Girdi biçimleri:
 * - Düz metin: her satıra "Kelime - Tanım" (ayraç " - ", sekme ya da ": ").
 * - CSV: "Soru,Cevap" başlıklı ya da en az 2 sütunlu.
 * - JSON öğe dizisi: kart `{ "kelime": "...", "tanim": "..." }` ya da sınav sorusu
 *   `{ "type": "mcq", "question": "...", "options": [...], "answer": "...", "explanation": "...", "source": "..." }`.
 * - JSON tek set: `{ "name": "...", "items": [...] }`.
 * - JSON ders paketi: `{ "course": "...", "sets": [ { "name": "...", "items": [...] } ] }`.
 */

export interface ParsedPackSet {
  name: string;
  questions: Question[];
}

export type ParseResult =
  | { success: true; kind: 'set'; questions: Question[]; warnings: string[]; suggestedName?: string }
  | { success: true; kind: 'pack'; course: string; sets: ParsedPackSet[]; warnings: string[] }
  | { success: false; error: string };

const FRONT_KEYS = ['question', 'soru', 'word', 'front', 'kelime', 'term', 'terim'] as const;
const BACK_KEYS = ['answer', 'cevap', 'definition', 'back', 'tanim', 'tanım', 'doğru', 'dogru'] as const;
const OPTION_KEYS = ['options', 'choices', 'secenekler', 'seçenekler', 'siklar', 'şıklar'] as const;
const CORRECT_INDEX_KEYS = ['correct', 'correctIndex', 'dogruIndex', 'doğruIndex'] as const;
const EXPLANATION_KEYS = ['explanation', 'aciklama', 'açıklama'] as const;
const SOURCE_KEYS = ['source', 'kaynak'] as const;
const HINT_KEYS = ['hint', 'ipucu'] as const;

function findKey(obj: Record<string, unknown>, candidates: readonly string[]): string | null {
  const keys = Object.keys(obj);
  for (const candidate of candidates) {
    const want = candidate.toLocaleLowerCase('tr');
    const match = keys.find((k) => k.trim().toLocaleLowerCase('tr') === want);
    if (match) return match;
  }
  return null;
}

function str(obj: Record<string, unknown>, keys: readonly string[]): string {
  const k = findKey(obj, keys);
  if (!k) return '';
  const v = obj[k];
  return typeof v === 'string' || typeof v === 'number' ? String(v).trim() : '';
}

export function parseInput(raw: string, filenameHint?: string): ParseResult {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { success: false, error: 'Girdi boş. Lütfen bir dosya yükleyin veya metin yapıştırın.' };
  }

  const hint = (filenameHint ?? '').toLocaleLowerCase('tr');

  if (trimmed.startsWith('[') || trimmed.startsWith('{') || hint.endsWith('.json')) {
    return parseJSON(trimmed);
  }

  if (hint.endsWith('.csv') || looksLikeCSVHeader(trimmed)) {
    return finalizeSet(parseCSV(trimmed));
  }

  return finalizeSet(parseTextLines(trimmed));
}

function looksLikeCSVHeader(raw: string): boolean {
  const firstLine = raw.split(/\r?\n/).find((l) => l.trim().length > 0) ?? '';
  const cells = firstLine.split(',').map((c) => c.trim().toLocaleLowerCase('tr'));
  if (cells.length < 2) return false;
  const hasFront = cells.some((c) => (FRONT_KEYS as readonly string[]).includes(c));
  const hasBack = cells.some((c) => (BACK_KEYS as readonly string[]).includes(c));
  return hasFront && hasBack;
}

type RawParse = { questions: Question[]; warnings: string[] } | { error: string };

// ---------------------------------------------------------------------------
// JSON

function parseJSON(raw: string): ParseResult {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    return { success: false, error: `Geçerli bir JSON değil: ${e instanceof Error ? e.message : String(e)}` };
  }

  // Ders paketi: { course, sets: [{ name, items }] }
  if (isObject(data) && Array.isArray(data.sets)) {
    const course = str(data, ['course', 'ders', 'name']) || 'Yeni ders';
    const warnings: string[] = [];
    const sets: ParsedPackSet[] = [];
    data.sets.forEach((s, i) => {
      if (!isObject(s) || !Array.isArray(s.items)) {
        warnings.push(`${i + 1}. set atlandı — "items" dizisi yok.`);
        return;
      }
      const name = str(s, ['name', 'ad']) || `Set ${i + 1}`;
      const res = finalizeSet(itemsToQuestions(s.items));
      if (!res.success || res.kind !== 'set') {
        warnings.push(`"${name}" atlandı — ${res.success ? '' : res.error}`);
        return;
      }
      warnings.push(...res.warnings.map((w) => `${name}: ${w}`));
      sets.push({ name, questions: res.questions });
    });
    if (sets.length === 0) return { success: false, error: 'Paketteki setlerin hiçbirinde geçerli soru yok.' };
    return { success: true, kind: 'pack', course, sets, warnings };
  }

  // Tek set: { name, items }
  if (isObject(data) && Array.isArray(data.items)) {
    const res = finalizeSet(itemsToQuestions(data.items));
    if (res.success && res.kind === 'set') res.suggestedName = str(data, ['name', 'ad']) || undefined;
    return res;
  }

  if (!Array.isArray(data)) {
    return {
      success: false,
      error: 'JSON bir soru dizisi olmalı. Örnek: [{"kelime": "Ephemeral", "tanim": "Kısa süreli"}]',
    };
  }
  if (data.length === 0) return { success: false, error: 'JSON dizisi boş — hiç soru bulunamadı.' };
  return finalizeSet(itemsToQuestions(data));
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** JSON öğelerini (kart ya da çoktan seçmeli soru) doğrulayıp Question'a çevirir. */
export function itemsToQuestions(items: unknown[]): RawParse {
  const warnings: string[] = [];
  const questions: Question[] = [];

  items.forEach((item, i) => {
    const n = i + 1;
    if (!isObject(item)) {
      warnings.push(`${n}. öğe atlandı — bir nesne değil.`);
      return;
    }
    const front = str(item, FRONT_KEYS);
    const explanation = str(item, EXPLANATION_KEYS);
    const source = str(item, SOURCE_KEYS);
    const hint = str(item, HINT_KEYS);
    const extras = {
      ...(explanation ? { explanation } : {}),
      ...(source ? { source } : {}),
      ...(hint ? { hint } : {}),
    };

    const optionsKey = findKey(item, OPTION_KEYS);
    if (optionsKey && Array.isArray(item[optionsKey])) {
      const options = dedupeBy(
        (item[optionsKey] as unknown[]).map((o) => String(o ?? '').trim()).filter(Boolean),
        normalizeAnswer
      );
      if (!front) {
        warnings.push(`${n}. soru atlandı — soru metni yok.`);
        return;
      }
      if (options.length < 2) {
        warnings.push(`${n}. soru atlandı — en az 2 şık gerekli: "${front.slice(0, 50)}"`);
        return;
      }
      const answer = resolveAnswer(item, options);
      if (!answer) {
        warnings.push(`${n}. soru atlandı — doğru cevap şıklardan biriyle eşleşmiyor: "${front.slice(0, 50)}"`);
        return;
      }
      questions.push({ id: newId(), kind: 'mcq', front, back: answer, options, ...extras });
      return;
    }

    const back = str(item, BACK_KEYS);
    if (!front || !back) {
      warnings.push(
        `${n}. öğe atlandı — tanınabilir soru/cevap alanı yok (beklenen: question, word, front, kelime / answer, definition, back, tanim).`
      );
      return;
    }
    questions.push({ id: newId(), kind: 'card', front, back, ...extras });
  });

  if (questions.length === 0) return { error: 'JSON içinde geçerli soru/cevap bulunamadı.' };
  return { questions, warnings };
}

/** Doğru şıkkı bulur: metin eşleşmesi, sıfır tabanlı indeks ya da "A"–"F" harfi. */
function resolveAnswer(item: Record<string, unknown>, options: string[]): string | null {
  const answerKey = findKey(item, BACK_KEYS);
  const raw = answerKey ? item[answerKey] : undefined;

  if (typeof raw === 'string' && raw.trim()) {
    const want = normalizeAnswer(raw);
    const byText = options.find((o) => normalizeAnswer(o) === want);
    if (byText) return byText;
    if (/^[a-f]$/i.test(raw.trim())) {
      const idx = raw.trim().toUpperCase().charCodeAt(0) - 65;
      return options[idx] ?? null;
    }
  }
  if (typeof raw === 'number') return options[raw] ?? null;

  const idxKey = findKey(item, CORRECT_INDEX_KEYS);
  const idx = idxKey ? item[idxKey] : undefined;
  if (typeof idx === 'number') return options[idx] ?? null;
  return null;
}

// ---------------------------------------------------------------------------
// CSV

function parseCSV(raw: string): RawParse {
  const withHeader = Papa.parse<Record<string, string>>(raw, { header: true, skipEmptyLines: true });

  const warnings: string[] = [];
  const questions: Question[] = [];

  const headerRow = withHeader.meta.fields ?? [];
  const headerObj: Record<string, unknown> = Object.fromEntries(headerRow.map((h) => [h, '']));
  const frontKey = findKey(headerObj, FRONT_KEYS);
  const backKey = findKey(headerObj, BACK_KEYS);

  if (frontKey && backKey) {
    const hintKey = findKey(headerObj, HINT_KEYS);
    withHeader.data.forEach((row, i) => {
      const front = (row[frontKey] ?? '').trim();
      const back = (row[backKey] ?? '').trim();
      if (!front || !back) {
        warnings.push(`${i + 2}. satır atlandı — soru veya cevap boş.`);
        return;
      }
      const hint = hintKey ? (row[hintKey] ?? '').trim() : '';
      questions.push({ id: newId(), kind: 'card', front, back, ...(hint ? { hint } : {}) });
    });
  } else {
    // Tanınabilir başlık yok — sütunları konumsal olarak (0: soru, 1: cevap) kullan.
    const positional = Papa.parse<string[]>(raw, { header: false, skipEmptyLines: true });
    if (positional.data.length === 0) {
      return { error: `CSV ayrıştırılamadı: ${positional.errors[0]?.message ?? 'satır bulunamadı'}.` };
    }
    positional.data.forEach((row, i) => {
      const front = (row[0] ?? '').trim();
      const back = (row[1] ?? '').trim();
      if (!front || !back) {
        warnings.push(`${i + 1}. satır atlandı — en az 2 dolu sütun gerekli.`);
        return;
      }
      questions.push({ id: newId(), kind: 'card', front, back });
    });
  }

  if (questions.length === 0) {
    return {
      error:
        'CSV içinde geçerli satır bulunamadı. "Soru,Cevap" başlıklı veya her satırda en az 2 sütunlu bir dosya bekleniyor.',
    };
  }
  return { questions, warnings };
}

// ---------------------------------------------------------------------------
// Düz metin

function parseTextLines(raw: string): RawParse {
  const lines = raw.split(/\r?\n/);
  const warnings: string[] = [];
  const questions: Question[] = [];

  lines.forEach((line, i) => {
    const text = line.trim();
    if (!text) return;

    // Ayraç önceliği: " - " → sekme → ": " (ilk eşleşme kullanılır,
    // böylece tire veya iki nokta içeren cevaplar bozulmaz).
    let sepIndex = -1;
    let sepLength = 0;
    for (const sep of [' - ', '\t', ': ']) {
      const idx = text.indexOf(sep);
      if (idx > 0) {
        sepIndex = idx;
        sepLength = sep.length;
        break;
      }
    }

    if (sepIndex === -1) {
      warnings.push(`${i + 1}. satır atlandı — ayraç ("-", sekme veya ":") bulunamadı: "${text}"`);
      return;
    }

    const front = text.slice(0, sepIndex).trim();
    const back = text.slice(sepIndex + sepLength).trim();
    if (!front || !back) {
      warnings.push(`${i + 1}. satır atlandı — soru veya cevap boş.`);
      return;
    }
    questions.push({ id: newId(), kind: 'card', front, back });
  });

  if (questions.length === 0) {
    return {
      error:
        'Geçerli "Kelime - Tanım" satırı bulunamadı. Her satıra bir çift yazın, örn: Ephemeral - Kısa süreli, geçici',
    };
  }
  return { questions, warnings };
}

// ---------------------------------------------------------------------------

function finalizeSet(result: RawParse): ParseResult {
  if ('error' in result) return { success: false, error: result.error };

  const warnings = [...result.warnings];
  const questions = dedupeBy(result.questions, (q) => normalizeAnswer(q.front));
  if (questions.length < result.questions.length) {
    const kept = new Set(questions.map((q) => q.id));
    for (const d of result.questions) {
      if (!kept.has(d.id)) warnings.push(`"${d.front.slice(0, 60)}" için yinelenen kayıt atlandı.`);
    }
  }

  const cards = questions.filter((q) => !isMcq(q));
  if (cards.length > 0 && cards.length < 4 && cards.length === questions.length) {
    warnings.push(
      `Yalnızca ${cards.length} kart bulundu — çoktan seçmeli sorularda daha az seçenek gösterilecek, eşleştirme oyunu atlanabilir.`
    );
  }

  return { success: true, kind: 'set', questions, warnings };
}

/**
 * Düzenleme penceresi için metne çevirir. Yalnızca ek alanı olmayan kartlar varsa
 * okunaklı "ön - arka" satırları; şıklı soru, açıklama ya da kaynak varsa kayıpsız JSON.
 */
export function serializeForEdit(questions: Question[]): { text: string; format: 'lines' | 'json' } {
  const simple = questions.every(
    (q) => !isMcq(q) && !q.explanation && !q.source && !q.hint && !q.front.includes(' - ')
  );
  if (simple) return { text: questions.map((q) => `${q.front} - ${q.back}`).join('\n'), format: 'lines' };

  const items = questions.map((q) =>
    isMcq(q)
      ? {
          type: 'mcq',
          question: q.front,
          options: q.options,
          answer: q.back,
          ...(q.explanation ? { explanation: q.explanation } : {}),
          ...(q.source ? { source: q.source } : {}),
        }
      : {
          type: 'card',
          front: q.front,
          back: q.back,
          ...(q.explanation ? { explanation: q.explanation } : {}),
          ...(q.source ? { source: q.source } : {}),
          ...(q.hint ? { hint: q.hint } : {}),
        }
  );
  return { text: JSON.stringify(items, null, 2), format: 'json' };
}
