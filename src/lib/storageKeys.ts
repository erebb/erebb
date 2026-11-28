export const STORAGE_KEYS = {
  courses: 'kelime-ustasi.courses',
  questionSets: 'kelime-ustasi.sets',
  /** questionId → Leitner kaydı (tüm setler için tek harita). */
  srs: 'kelime-ustasi.srs.v2',
  /** Eski biçim: setId → { entries }. Yalnızca taşıma için okunur. */
  legacySrs: 'kelime-ustasi.srs',
  /** Uygulamayla gelen içerik paketlerinden hangilerinin bir kez yüklendiği. */
  seededPacks: 'kelime-ustasi.seededPacks',
  feedSwipeHintSeen: 'kelime-ustasi.feed.swipeHintSeen',
  browseRevealAll: 'kelime-ustasi.browse.revealAll',
  quizCount: 'kelime-ustasi.quiz.count',
  /** questionId → doğru/yanlış sonuçları (bkz. ProgressMap). */
  progress: 'kelime-ustasi.progress.v1',
  /** Konu anlatımında kalınan bölüm: hedef anahtarı → bölüm sırası. */
  lessonPos: 'kelime-ustasi.lessonPos',
  /** Görünüm: 'system' | 'light' | 'dark'. */
  theme: 'kelime-ustasi.theme',
  /** Doğru/yanlış sesleri (varsayılan kapalı: odak). */
  sound: 'kelime-ustasi.sound',
} as const;
