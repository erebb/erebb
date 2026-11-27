// ---- Ders / Soru Seti / Soru ----

/**
 * Bir çalışma öğesi. İki türü vardır:
 * - `card` (bilgi kartı): `front` → `back`.
 * - `mcq` (sınav sorusu): `front` soru kökü, `options` tüm şıklar, `back` doğru şıkkın metni.
 *
 * MCQ'da da `front`/`back` dolu tutulur; böylece kartlar, akış ve göz atma modları her iki
 * türü aynı alanlardan okuyabilir.
 */
export type QuestionKind = 'card' | 'mcq';

export interface Question {
  id: string;
  front: string;
  back: string;
  kind?: QuestionKind; // yoksa 'card'
  /** Yalnızca mcq: doğru cevap dahil tüm şıklar. */
  options?: string[];
  /** Neden doğru — cevaptan sonra gösterilir. */
  explanation?: string;
  /** Örn. "Slayt 4 · Table 3-2". */
  source?: string;
  hint?: string;
}

export const isMcq = (q: Question): boolean => q.kind === 'mcq' && (q.options?.length ?? 0) >= 2;

export interface Course {
  id: string;
  name: string;
  createdAt: string;
}

export type SourceFormat = 'json' | 'csv' | 'text';

export interface QuestionSet {
  id: string;
  name: string;
  courseId: string;
  createdAt: string; // ISO zaman damgası
  updatedAt: string;
  sourceFormat: SourceFormat;
  questions: Question[];
  /** Uygulamayla gelen hazır içerikten geldiyse: içerik anahtarı ve yüklenen sürüm. */
  bundle?: { key: string; version: number };
}

/** Bir çalışma oturumunun hedefi: tek set ya da bir dersin tüm setleri. */
export interface StudyTarget {
  title: string;
  subtitle?: string;
  questions: Question[];
}

export type StudyMode = 'browse' | 'quiz' | 'flashcards' | 'feed';

// ---- Aralıklı tekrar (Leitner kutuları) ----

export type LeitnerBox = 1 | 2 | 3 | 4 | 5;

export interface FlashcardSRSEntry {
  questionId: string;
  box: LeitnerBox;
  dueDate: string; // 'YYYY-MM-DD' — tekrar gösterilebileceği ilk gün
  lastSeenAt: string | null; // ISO zaman damgası
}

/** questionId → kayıt. Soru id'leri tüm setlerde benzersiz olduğu için tek bir harita yeter. */
export type SRSEntries = Record<string, FlashcardSRSEntry>;

// ---- Soru çözme oturumu ----

export type QuizMode = 'multiple-choice' | 'text-input' | 'matching-pairs';

export type QuizItem =
  | { kind: 'multiple-choice'; question: Question; choices: string[] }
  | { kind: 'text-input'; question: Question }
  | { kind: 'matching-pairs'; pairs: Question[] };

export interface QuizAnswerRecord {
  questionId: string;
  userAnswer: string;
  correct: boolean;
  mode: QuizMode;
}

export type QuizStatus = 'in-progress' | 'completed';

export interface QuizSession {
  items: QuizItem[];
  currentIndex: number;
  answers: QuizAnswerRecord[];
  status: QuizStatus;
  /** Toplam cevaplanabilir birim (eşleştirmede çift başına 1). */
  totalAnswerable: number;
}

export interface QuizFeedback {
  type: 'correct' | 'incorrect';
  correctAnswer: string;
  explanation?: string;
  source?: string;
}

// ---- Akış modu (TikTok tarzı dikey kaydırma) ----

export type FeedCardKind = 'explainer' | 'multiple-choice' | 'text-input';

interface FeedCardBase {
  /** Kart başına benzersiz. Soru id'si DEĞİL — aynı soru akışta defalarca belirir. */
  id: string;
  question: Question;
  /** Üretim anındaki Leitner kutusu; undefined = hiç çalışılmamış. */
  box?: LeitnerBox;
  /** Bu sorunun BU akış oturumunda kaçıncı görünüşü olduğu (1 tabanlı). */
  sessionSeenCount: number;
  /** Son çalışma zaman damgası (anlatım kartındaki "n gün önce" için). */
  lastSeenAt?: string | null;
}

export interface ExplainerFeedCard extends FeedCardBase {
  kind: 'explainer';
  isNew: boolean;
}

export interface MultipleChoiceFeedCard extends FeedCardBase {
  kind: 'multiple-choice';
  choices: string[];
}

export interface TextInputFeedCard extends FeedCardBase {
  kind: 'text-input';
}

export type FeedCard = ExplainerFeedCard | MultipleChoiceFeedCard | TextInputFeedCard;

export interface FeedAnswerResult {
  correct: boolean;
  /** Daima birebir `question.back`; yanlışta gösterilir. */
  correctAnswer: string;
  /** Kullanıcının verdiği cevap (seçtiği şık ya da yazdığı metin). */
  userAnswer: string;
  /** Kullanıcı cevaplamadan önce "Göster" ile baktıysa true. */
  peeked: boolean;
}

export interface FeedSessionStats {
  correct: number;
  answered: number;
}
