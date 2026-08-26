// ---- Soru / Soru Seti ----

export interface Question {
  id: string;
  front: string; // soru / kelime
  back: string; // cevap / tanım
  hint?: string;
}

export type SourceFormat = 'json' | 'csv' | 'text';

export interface QuestionSet {
  id: string;
  name: string;
  createdAt: string; // ISO zaman damgası
  updatedAt: string;
  sourceFormat: SourceFormat;
  questions: Question[];
}

// ---- Kullanıcı ilerlemesi / oyunlaştırma ----

export interface UserProgress {
  totalXP: number;
  streak: number;
  lastPracticedDate: string | null; // 'YYYY-MM-DD' (yerel tarih)
  dailyGoalXP: number;
  dailyXPEarned: number;
  dailyXPDate: string; // dailyXPEarned sayacının ait olduğu gün
}

export const DEFAULT_PROGRESS: UserProgress = {
  totalXP: 0,
  streak: 0,
  lastPracticedDate: null,
  dailyGoalXP: 50,
  dailyXPEarned: 0,
  dailyXPDate: '',
};

// ---- Aralıklı tekrar (Flashcard modu, Leitner kutuları) ----

export type LeitnerBox = 1 | 2 | 3 | 4 | 5;

export interface FlashcardSRSEntry {
  questionId: string;
  box: LeitnerBox;
  dueDate: string; // 'YYYY-MM-DD' — tekrar gösterilebileceği ilk gün
  lastSeenAt: string | null; // ISO zaman damgası
}

export interface FlashcardDeckState {
  setId: string;
  entries: Record<string, FlashcardSRSEntry>; // questionId ile anahtarlı
}

// ---- Quiz oturumu (Duolingo modu) ----

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

export type QuizStatus = 'in-progress' | 'game-over' | 'completed';

export interface QuizSession {
  setId: string;
  items: QuizItem[];
  currentIndex: number;
  hearts: number;
  maxHearts: number;
  score: number;
  totalAnswerable: number; // toplam cevaplanabilir birim (eşleştirmede çift başına 1)
  xpEarned: number;
  answers: QuizAnswerRecord[];
  status: QuizStatus;
}

export interface QuizFeedback {
  type: 'correct' | 'incorrect';
  correctAnswer?: string;
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
  xpEarned: number;
  /** Kullanıcı cevaplamadan önce "Kelimeyi göster" ile baktıysa true. */
  peeked: boolean;
}

export interface FeedSessionStats {
  xpEarned: number;
  correct: number;
  answered: number;
}
