import type { FlashcardSRSEntry, LeitnerBox, Question } from '@/types';
import { addDays, shuffle, todayISO } from '@/lib/utils';

/** Kutu → sonraki tekrara kadar geçecek gün sayısı. */
export const BOX_INTERVAL_DAYS: Record<LeitnerBox, number> = {
  1: 0,
  2: 1,
  3: 3,
  4: 7,
  5: 14,
};

/** "Zor" işaretlenen kart, oturum kuyruğunda bu kadar pozisyon ileriye eklenir. */
export const REQUEUE_OFFSET = 4;

export function newEntry(questionId: string): FlashcardSRSEntry {
  return { questionId, box: 1, dueDate: todayISO(), lastSeenAt: null };
}

export function markHardEntry(entry: FlashcardSRSEntry): FlashcardSRSEntry {
  const box = Math.max(1, entry.box - 1) as LeitnerBox;
  return { ...entry, box, dueDate: todayISO(), lastSeenAt: new Date().toISOString() };
}

export function markEasyEntry(entry: FlashcardSRSEntry): FlashcardSRSEntry {
  const box = Math.min(5, entry.box + 1) as LeitnerBox;
  return {
    ...entry,
    box,
    dueDate: addDays(todayISO(), BOX_INTERVAL_DAYS[box]),
    lastSeenAt: new Date().toISOString(),
  };
}

/** Kutuyu değiştirmeden yalnızca "görüldü" damgasını tazeler. */
export function touchEntry(entry: FlashcardSRSEntry): FlashcardSRSEntry {
  return { ...entry, lastSeenAt: new Date().toISOString() };
}

/**
 * Oturum kuyruğunu kurar: bugünü geçmiş (veya yeni) kartlar, en düşük kutu önce,
 * aynı kutu içinde karışık. Hiç kart vadesi gelmemişse tüm deste döner
 * (erken tekrar), böylece kullanıcı asla boş ekranla karşılaşmaz.
 */
export function buildSessionQueue(
  questions: Question[],
  entries: Record<string, FlashcardSRSEntry>
): { queue: Question[]; isEarlyReview: boolean } {
  const today = todayISO();
  const due = questions.filter((q) => {
    const e = entries[q.id];
    return !e || e.dueDate <= today;
  });

  const pool = due.length > 0 ? due : questions;
  const boxOf = (q: Question) => entries[q.id]?.box ?? 1;

  const byBox = new Map<number, Question[]>();
  for (const q of pool) {
    const b = boxOf(q);
    const list = byBox.get(b) ?? [];
    list.push(q);
    byBox.set(b, list);
  }

  const queue: Question[] = [];
  for (const box of [1, 2, 3, 4, 5]) {
    const group = byBox.get(box);
    if (group) queue.push(...shuffle(group));
  }

  return { queue, isEarlyReview: due.length === 0 };
}
