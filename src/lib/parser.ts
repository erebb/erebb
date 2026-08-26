import Papa from 'papaparse';
import type { Question } from '@/types';
import { dedupeBy, newId, normalizeAnswer } from '@/lib/utils';

export type ParseResult =
  | { success: true; questions: Question[]; warnings: string[] }
  | { success: false; error: string };

const FRONT_KEYS = ['question', 'word', 'front', 'soru', 'kelime'] as const;
const BACK_KEYS = ['answer', 'definition', 'back', 'cevap', 'tanim', 'tanım'] as const;
const HINT_KEYS = ['hint', 'ipucu', 'İpucu'] as const;

function findKey(obj: Record<string, unknown>, candidates: readonly string[]): string | null {
  const keys = Object.keys(obj);
  for (const candidate of candidates) {
    const match = keys.find((k) => k.trim().toLocaleLowerCase('tr') === candidate.toLocaleLowerCase('tr'));
    if (match) return match;
  }
  return null;
}

export function parseInput(raw: string, filenameHint?: string): ParseResult {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { success: false, error: 'Girdi boş. Lütfen bir dosya yükleyin veya metin yapıştırın.' };
  }

  const hint = (filenameHint ?? '').toLocaleLowerCase('tr');

  if (trimmed.startsWith('[') || trimmed.startsWith('{') || hint.endsWith('.json')) {
    return finalize(parseJSON(trimmed));
  }

  if (hint.endsWith('.csv') || looksLikeCSVHeader(trimmed)) {
    return finalize(parseCSV(trimmed));
  }

  return finalize(parseTextLines(trimmed));
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

function parseJSON(raw: string): RawParse {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    return { error: `Geçerli bir JSON değil: ${e instanceof Error ? e.message : String(e)}` };
  }

  if (!Array.isArray(data)) {
    return {
      error: 'JSON bir soru dizisi olmalı. Örnek: [{"kelime": "Ephemeral", "tanim": "Kısa süreli"}]',
    };
  }
  if (data.length === 0) {
    return { error: 'JSON dizisi boş — hiç soru bulunamadı.' };
  }

  const warnings: string[] = [];
  const questions: Question[] = [];

  data.forEach((item, i) => {
    if (typeof item !== 'object' || item === null || Array.isArray(item)) {
      warnings.push(`${i + 1}. öğe atlandı — bir nesne değil.`);
      return;
    }
    const obj = item as Record<string, unknown>;
    const frontKey = findKey(obj, FRONT_KEYS);
    const backKey = findKey(obj, BACK_KEYS);
    if (!frontKey || !backKey) {
      warnings.push(
        `${i + 1}. öğe atlandı — tanınabilir soru/cevap alanı yok (beklenen: question, word, front, kelime / answer, definition, back, tanim).`
      );
      return;
    }
    const front = String(obj[frontKey] ?? '').trim();
    const back = String(obj[backKey] ?? '').trim();
    if (!front || !back) {
      warnings.push(`${i + 1}. öğe atlandı — soru veya cevap boş.`);
      return;
    }
    const hintKey = findKey(obj, HINT_KEYS);
    const hint = hintKey ? String(obj[hintKey] ?? '').trim() : '';
    questions.push({ id: newId(), front, back, ...(hint ? { hint } : {}) });
  });

  if (questions.length === 0) {
    return { error: 'JSON dosyasında geçerli soru/cevap çifti bulunamadı.' };
  }
  return { questions, warnings };
}

function parseCSV(raw: string): RawParse {
  const withHeader = Papa.parse<Record<string, string>>(raw, {
    header: true,
    skipEmptyLines: true,
  });

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
      questions.push({ id: newId(), front, back, ...(hint ? { hint } : {}) });
    });
  } else {
    // Tanınabilir başlık yok — sütunları konumsal olarak (0: soru, 1: cevap) kullan.
    const positional = Papa.parse<string[]>(raw, { header: false, skipEmptyLines: true });
    if (positional.data.length === 0) {
      return {
        error: `CSV ayrıştırılamadı: ${positional.errors[0]?.message ?? 'satır bulunamadı'}.`,
      };
    }
    positional.data.forEach((row, i) => {
      const front = (row[0] ?? '').trim();
      const back = (row[1] ?? '').trim();
      if (!front || !back) {
        warnings.push(`${i + 1}. satır atlandı — en az 2 dolu sütun gerekli.`);
        return;
      }
      questions.push({ id: newId(), front, back });
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
    questions.push({ id: newId(), front, back });
  });

  if (questions.length === 0) {
    return {
      error:
        'Geçerli "Kelime - Tanım" satırı bulunamadı. Her satıra bir çift yazın, örn: Ephemeral - Kısa süreli, geçici',
    };
  }
  return { questions, warnings };
}

function finalize(result: RawParse): ParseResult {
  if ('error' in result) {
    return { success: false, error: result.error };
  }

  const warnings = [...result.warnings];
  const questions = dedupeBy(result.questions, (q) => normalizeAnswer(q.front));
  if (questions.length < result.questions.length) {
    const kept = new Set(questions.map((q) => q.id));
    for (const d of result.questions) {
      if (!kept.has(d.id)) warnings.push(`"${d.front}" için yinelenen kayıt atlandı.`);
    }
  }

  if (questions.length < 4) {
    warnings.push(
      `Yalnızca ${questions.length} soru bulundu — çoktan seçmeli sorularda daha az seçenek gösterilecek, eşleştirme oyunu atlanabilir.`
    );
  }

  return { success: true, questions, warnings };
}
