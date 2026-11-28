import type { ProgressMap, Question } from '@/types';

export interface ProgressStats {
  total: number;
  /** En az bir kez cevaplanan (ya da kartta işaretlenen). */
  answered: number;
  /** Son cevabı doğru olan. */
  correct: number;
  /** Son cevabı yanlış olan. */
  wrong: number;
}

export function progressStats(questions: Question[], progress: ProgressMap): ProgressStats {
  let answered = 0;
  let correct = 0;
  let wrong = 0;
  for (const q of questions) {
    const p = progress[q.id];
    if (!p) continue;
    answered++;
    if (p.last === 'correct') correct++;
    else wrong++;
  }
  return { total: questions.length, answered, correct, wrong };
}
