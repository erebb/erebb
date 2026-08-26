import type { FeedCard, FeedCardKind, FlashcardSRSEntry, LeitnerBox, Question } from '@/types';
import { newId } from '@/lib/utils';
import { buildChoices } from '@/hooks/useLearningEngine';

export const FEED_BATCH_SIZE = 8;
export const FEED_PREFETCH_WITHIN = 3;
export const FEED_MAX_CARDS = 120;
export const FEED_TRIM_CHUNK = 40;
export const FEED_RENDER_WINDOW = 2;

export interface KindWeights {
  explainer: number;
  mc: number;
  ti: number;
}

/**
 * Hiç görülmemiş / zorlanılan kelimelerde öğretmeye, ustalaşılanlarda
 * hatırlamaya ağırlık verir. Karışık bir destede ortalama ~%40/%35/%25 çıkar.
 */
export function weightsForBox(box: LeitnerBox | undefined): KindWeights {
  if (box === undefined) return { explainer: 0.7, mc: 0.25, ti: 0.05 };
  switch (box) {
    case 1:
      return { explainer: 0.55, mc: 0.35, ti: 0.1 };
    case 2:
      return { explainer: 0.4, mc: 0.38, ti: 0.22 };
    case 3:
      return { explainer: 0.3, mc: 0.4, ti: 0.3 };
    case 4:
      return { explainer: 0.18, mc: 0.4, ti: 0.42 };
    case 5:
      return { explainer: 0.1, mc: 0.38, ti: 0.52 };
  }
}

export function rollKind(w: KindWeights, exclude?: FeedCardKind): FeedCardKind {
  const all: Array<[FeedCardKind, number]> = [
    ['explainer', w.explainer],
    ['multiple-choice', w.mc],
    ['text-input', w.ti],
  ];
  const entries = all.filter(([k]) => k !== exclude);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  let r = Math.random() * total;
  for (const [k, v] of entries) {
    r -= v;
    if (r <= 0) return k;
  }
  return entries[entries.length - 1][0];
}

export interface BuildCardArgs {
  question: Question;
  allQuestions: Question[];
  entry: FlashcardSRSEntry | undefined;
  /** Bu oturumda anlatım kartı almış soru id'leri. */
  taught: Set<string>;
  /** Son iki kartın türü, en yenisi sonda. */
  recentKinds: FeedCardKind[];
  sessionSeenCount: number;
  /** Türü zorla (ilk kartın daima anlatım olması için). */
  forceKind?: FeedCardKind;
}

export function buildFeedCard(a: BuildCardArgs): FeedCard {
  const box = a.entry?.box;
  const w = weightsForBox(box);

  let kind = a.forceKind ?? rollKind(w);

  if (!a.forceKind) {
    // Tekdüzeliği kır: aynı türden üst üste üç kart gelmesin.
    if (a.recentKinds.length === 2 && a.recentKinds[0] === kind && a.recentKinds[1] === kind) {
      kind = rollKind(w, kind);
    }
    // Öğret-sonra-test: hiç görülmemiş kelime önce anlatım kartı alır.
    if (kind !== 'explainer' && box === undefined && !a.taught.has(a.question.id)) {
      kind = 'explainer';
    }
  }

  const base = {
    id: newId(),
    question: a.question,
    box,
    sessionSeenCount: a.sessionSeenCount,
    lastSeenAt: a.entry?.lastSeenAt ?? null,
  };

  if (kind === 'multiple-choice') {
    const choices = buildChoices(a.question, a.allQuestions);
    // Küçük set koruması: tek seçenekli "çoktan seçmeli" soru değildir.
    if (choices.length < 2) return { ...base, kind: 'text-input' };
    return { ...base, kind: 'multiple-choice', choices };
  }
  if (kind === 'text-input') return { ...base, kind: 'text-input' };
  return { ...base, kind: 'explainer', isNew: box === undefined };
}
