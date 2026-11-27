import type { FeedCard, FeedCardKind, FlashcardSRSEntry, LeitnerBox, Question } from '@/types';
import { isMcq } from '@/types';
import { newId, shuffle } from '@/lib/utils';
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
 *
 * `alreadyTaught`: kelime bu oturumda anlatım kartı almışsa. Aşağıdaki
 * "öğret-sonra-test" kuralı ilk karşılaşmayı zaten anlatıma zorladığı için,
 * öğretilmiş bir kelimeye tekrar anlatım basmak yeni bilgi vermez — bu yüzden
 * ağırlık soruya kayar. Aksi halde yeni bir destede akış neredeyse tamamen
 * anlatım kartlarından oluşur ve "sorular" tarafı hiç görünmez.
 */
export function weightsForBox(box: LeitnerBox | undefined, alreadyTaught = false): KindWeights {
  if (box === undefined) {
    return alreadyTaught
      ? { explainer: 0.2, mc: 0.5, ti: 0.3 }
      : { explainer: 0.7, mc: 0.25, ti: 0.05 };
  }
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

/** Bundan uzun cevaplar akışta yazılı soru olarak sorulmaz. */
export const FEED_TEXT_INPUT_MAX_LEN = 30;

/**
 * Şıklı sınav soruları için ağırlıklar: önce sorulur (cevaptan sonra açıklama zaten
 * gösterilir), ara sıra cevaplı anlatım kartı olarak tekrar edilir. Yazılı soru yok.
 */
const MCQ_WEIGHTS: KindWeights = { explainer: 0.25, mc: 0.75, ti: 0 };

export interface BuildCardArgs {
  question: Question;
  /** Kartlar için çeldirici havuzu (yalnızca kart türündeki öğeler). */
  cardPool: Question[];
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
  const q = a.question;
  const mcq = isMcq(q);
  const box = a.entry?.box;
  const w = mcq ? MCQ_WEIGHTS : weightsForBox(box, a.taught.has(q.id));

  let kind = a.forceKind ?? rollKind(w);

  if (!a.forceKind) {
    // Tekdüzeliği kır: aynı türden üst üste üç kart gelmesin.
    if (a.recentKinds.length === 2 && a.recentKinds[0] === kind && a.recentKinds[1] === kind) {
      kind = rollKind(w, kind);
    }
    // Öğret-sonra-test: hiç görülmemiş bilgi kartı önce anlatım kartı alır.
    // (Sınav sorularında tersi: önce sorulur.)
    if (!mcq && kind !== 'explainer' && box === undefined && !a.taught.has(q.id)) {
      kind = 'explainer';
    }
  }

  const base = {
    id: newId(),
    question: q,
    box,
    sessionSeenCount: a.sessionSeenCount,
    lastSeenAt: a.entry?.lastSeenAt ?? null,
  };

  if (kind === 'explainer') return { ...base, kind: 'explainer', isNew: box === undefined };

  if (mcq) return { ...base, kind: 'multiple-choice', choices: shuffle(q.options ?? [q.back]) };

  const shortAnswer = q.back.length <= FEED_TEXT_INPUT_MAX_LEN;
  if (kind === 'text-input' && shortAnswer) return { ...base, kind: 'text-input' };

  const choices = buildChoices(q, a.cardPool);
  if (choices.length >= 2) return { ...base, kind: 'multiple-choice', choices };
  // Küçük havuz: tek seçenekli "çoktan seçmeli" soru değildir.
  return shortAnswer ? { ...base, kind: 'text-input' } : { ...base, kind: 'explainer', isNew: box === undefined };
}
