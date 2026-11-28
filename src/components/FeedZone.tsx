import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useReducedMotion } from 'framer-motion';
import type { FeedCard, StudyTarget } from '@/types';
import { useFeed } from '@/hooks/useFeed';
import { useLocalStorage } from '@/hooks/useLocalStorage';
import { FEED_RENDER_WINDOW } from '@/lib/feed';
import { STORAGE_KEYS } from '@/lib/storageKeys';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { ExplainerBody, ExplainerCard } from '@/components/feed/ExplainerCard';
import { MultipleChoiceCard } from '@/components/feed/MultipleChoiceCard';
import { TextInputCard } from '@/components/feed/TextInputCard';
import { FeedActionRail } from '@/components/feed/FeedActionRail';
import { FeedTopBar } from '@/components/feed/FeedTopBar';
import { SwipeHint } from '@/components/feed/SwipeHint';
import { autoAdvanceAfter } from '@/components/feed/FeedAnswerBanner';
import { cn } from '@/lib/utils';

const AUTO_ADVANCE_MS = 900;
/** Bu kadar süre tekerlek olayı gelmezse hareket bitmiş sayılır. */
const WHEEL_QUIET_MS = 180;
/** Bir adım için gereken birikmiş tekerlek mesafesi (trackpad'in minik titremeleri sayılmasın). */
const WHEEL_THRESHOLD_PX = 20;
/** Programatik gezinme hedefinin geçerli kaldığı süre. */
const PENDING_TARGET_TTL_MS = 1000;

export interface FeedZoneProps {
  target: StudyTarget;
  onExit: () => void;
}

/** Olayın hedefinden kaba kadar, o yönde hâlâ kaydırılabilen bir iç öğe var mı? */
function innerCanScroll(target: EventTarget | null, container: HTMLElement, deltaY: number): boolean {
  let el = target instanceof HTMLElement ? target : null;
  while (el && el !== container) {
    const { overflowY } = getComputedStyle(el);
    if ((overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 1) {
      if (deltaY > 0 && el.scrollTop + el.clientHeight < el.scrollHeight - 1) return true;
      if (deltaY < 0 && el.scrollTop > 0) return true;
    }
    el = el.parentElement;
  }
  return false;
}

export function FeedZone({ target, onExit }: FeedZoneProps) {
  const {
    cards,
    currentIndex,
    setCurrentIndex,
    answers,
    submitAnswer,
    markPeeked,
    stats,
    isEmpty,
    headOffset,
  } = useFeed(target.questions);

  const containerRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<Array<HTMLElement | null>>([]);
  const advanceTimerRef = useRef<number | null>(null);
  const indexRef = useRef(currentIndex);
  const reduced = useReducedMotion();

  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [revealCard, setRevealCard] = useState<FeedCard | null>(null);
  const [hintSeen, setHintSeen] = useLocalStorage(STORAGE_KEYS.feedSwipeHintSeen, false);

  // Programatik gezinmenin son hedefi. Yumuşak kaydırma sürerken IntersectionObserver
  // yeni kartı henüz aktif saymamış olabilir; art arda gelen tuş/tekerlek adımları eski
  // indekse göre hesaplanırsa biri yutulur. Hedef kısa süre geçerlidir: kullanıcı bu
  // arada parmağıyla başka yere kaydırırsa eskimiş hedef onu geri çekmesin.
  const pendingTargetRef = useRef<{ index: number; at: number } | null>(null);

  useEffect(() => {
    indexRef.current = currentIndex;
    if (pendingTargetRef.current?.index === currentIndex) pendingTargetRef.current = null;
  }, [currentIndex]);

  // Sayfa arkasının kaymasını engelle.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  // Ok tuşlarının tıklama gerektirmeden çalışması için kaba odaklan.
  useEffect(() => {
    containerRef.current?.focus({ preventScroll: true });
  }, []);

  // İlk kaydırmadan sonra ipucu bir daha gösterilmez.
  useEffect(() => {
    if (currentIndex > 0 && !hintSeen) setHintSeen(true);
  }, [currentIndex, hintSeen, setHintSeen]);

  // --- Aktif kart tespiti ---
  // threshold 0.55 kritik: her çocuk tam 100dvh olduğu için iki kart aynı anda
  // %55'i aşamaz, dolayısıyla debounce'suz tek aktif kart garanti edilir.
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    const io = new IntersectionObserver(
      (entries) => {
        let best: IntersectionObserverEntry | null = null;
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          if (!best || e.intersectionRatio > best.intersectionRatio) best = e;
        }
        if (!best) return;
        const idx = Number((best.target as HTMLElement).dataset.index);
        if (!Number.isNaN(idx)) setCurrentIndex(idx);
      },
      { root, rootMargin: '0px', threshold: [0.55, 0.9] }
    );
    root.querySelectorAll<HTMLElement>('[data-feed-card]').forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [cards.length, setCurrentIndex]);

  // --- Baştan kart atıldığında kaydırma telafisi ---
  // useLayoutEffect şart: düzeltme boyamadan önce inmezse akış gözle görülür şekilde zıplar.
  const prevHeadRef = useRef(headOffset);
  useLayoutEffect(() => {
    const d = headOffset - prevHeadRef.current;
    prevHeadRef.current = headOffset;
    const el = containerRef.current;
    if (d > 0 && el) el.scrollTop -= d * el.clientHeight;
    if (d > 0) pendingTargetRef.current = null; // indeksler kaydı, eski hedef anlamsız
  }, [headOffset]);

  const goTo = useCallback(
    (i: number) => {
      const el = cardRefs.current[i];
      if (!el) return;
      el.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
    },
    [reduced]
  );

  /** Bir kart ileri/geri. Klavye ve tekerlek bunu kullanır. */
  const step = useCallback(
    (dir: 1 | -1) => {
      const pending = pendingTargetRef.current;
      const base =
        pending && performance.now() - pending.at < PENDING_TARGET_TTL_MS
          ? pending.index
          : indexRef.current;
      const next = base + dir;
      if (next < 0 || !cardRefs.current[next]) return;
      pendingTargetRef.current = { index: next, at: performance.now() };
      goTo(next);
    },
    [goTo]
  );
  const stepRef = useRef(step);
  useEffect(() => {
    stepRef.current = step;
  }, [step]);

  // --- Masaüstü: fare tekerleği ve trackpad ---
  // Yerel scroll-snap'te tek tekerlek çentiği (~100 px) kartın yarısını geçemez ve aynı
  // karta geri oturur; klasik fareyle her kart için 4–5 çentik gerekir. TikTok'un masaüstü
  // sürümündeki gibi "bir hareket = bir kart": ilk anlamlı olayda bir adım atılır, sonra
  // olaylar kesilene kadar (trackpad'in atalet kuyruğu dahil) yenisi yok sayılır.
  // Dokunmatik kaydırma tekerlek olayı üretmez; telefonda yerel snap aynen çalışır.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    let gestureActive = false;
    let accum = 0;
    let quietTimer: number | undefined;

    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey) return; // trackpad ile yakınlaştırma hareketi
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return; // yatay kaydırma
      // Uzun bir kartın (tablo özeti, açıklama) kendi içeriği kaydırılabiliyorsa önce o kaysın.
      if (!gestureActive && innerCanScroll(e.target, el, e.deltaY)) return;
      e.preventDefault();
      window.clearTimeout(quietTimer);
      quietTimer = window.setTimeout(() => {
        gestureActive = false;
        accum = 0;
      }, WHEEL_QUIET_MS);
      if (gestureActive) return;
      accum += e.deltaMode === 1 ? e.deltaY * 40 : e.deltaY; // satır kipi → piksel
      if (Math.abs(accum) < WHEEL_THRESHOLD_PX) return;
      gestureActive = true;
      stepRef.current(accum > 0 ? 1 : -1);
    };

    el.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      el.removeEventListener('wheel', onWheel);
      window.clearTimeout(quietTimer);
    };
  }, [isEmpty]);

  // Kart değişince bekleyen otomatik ilerlemeyi iptal et.
  useEffect(() => {
    return () => {
      if (advanceTimerRef.current !== null) {
        window.clearTimeout(advanceTimerRef.current);
        advanceTimerRef.current = null;
      }
    };
  }, [currentIndex]);

  const handleAnswer = useCallback(
    (card: FeedCard, raw: string) => {
      const res = submitAnswer(card, raw);
      // Yanlışta ya da açıklaması olan soruda ekranda kal — okunması gereken bir şey var.
      if (!autoAdvanceAfter(res, card.question)) return;
      const myIndex = indexRef.current;
      advanceTimerRef.current = window.setTimeout(() => {
        // Kullanıcı bu arada kendisi kaydırdıysa geri sürükleme.
        if (indexRef.current !== myIndex) return;
        goTo(myIndex + 1);
      }, AUTO_ADVANCE_MS);
    },
    [submitAnswer, goTo]
  );

  const handleExit = useCallback(() => onExit(), [onExit]);

  // --- Klavye ---
  // Pencere düzeyinde dinlenir. Akış kabına bağlı dinleyici kırılgandı: Safari/WebKit'te
  // düğmeye tıklamak odak vermez ve "Göster" penceresi kapanınca odak body'ye düşer —
  // ok tuşları sessizce çalışmayı bırakırdı.
  const revealOpenRef = useRef(false);
  useEffect(() => {
    revealOpenRef.current = revealCard !== null;
  }, [revealCard]);
  const handleExitRef = useRef(handleExit);
  useEffect(() => {
    handleExitRef.current = handleExit;
  }, [handleExit]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Tuşu başka bir bileşen zaten işlediyse karışma. Kritik durum: "Göster" penceresi
      // açıkken Esc. Radix pencereyi belge düzeyinde kapatıp olayı preventDefault eder;
      // React o güncellemeyi bu dinleyici çalışmadan işlediği için aşağıdaki "pencere açık"
      // bayrağı burada çoktan false olur — tek başına ona güvenilirse Esc hem pencereyi
      // kapatır hem akıştan çıkardı.
      if (e.defaultPrevented) return;
      if (revealOpenRef.current) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return; // ⌘ kısayollarına karışma
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      switch (e.key) {
        case ' ':
          if (t?.tagName === 'BUTTON') return; // Boşluk odaktaki düğmeye basabilsin
          e.preventDefault();
          stepRef.current(1);
          break;
        case 'ArrowDown':
        case 'PageDown':
          e.preventDefault();
          stepRef.current(1);
          break;
        case 'ArrowUp':
        case 'PageUp':
          e.preventDefault();
          stepRef.current(-1);
          break;
        case 'Escape':
          e.preventDefault();
          handleExitRef.current();
          break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (isEmpty) {
    return (
      <div className="flex h-feed flex-col items-center justify-center gap-4 bg-ink p-6 text-center">
        <p className="text-lg font-semibold text-white">Burada henüz soru yok.</p>
        <p className="text-sm font-normal text-white/60">Önce bir sete soru ekle.</p>
        <Button variant="blue" onClick={handleExit}>
          Geri dön
        </Button>
      </div>
    );
  }

  const activeCard = cards[currentIndex];

  return (
    // Kaydırıcı tüm pencere genişliğindedir; her kartın içeriği ortalanmış, telefon
    // genişliğinde bir sütundur. Böylece Mac penceresi genişletildiğinde kartlar ekran boyu
    // yayılmaz, ama yandaki siyah boşluklarda da tekerlek/trackpad akışı kaydırır ve
    // tıklamak odağı akıştan koparmaz. Üst çubuk, ray ve ipucu aynı sütuna hizalı bir
    // katmanda durur (kök öğeleri pointer-events-none; tıklamalar kartlara geçer).
    <div className="relative h-feed w-full overflow-hidden bg-ink-deep">
      <div className="pointer-events-none absolute inset-0 z-20 flex justify-center">
        <div className="relative h-full w-full max-w-md">
          <FeedTopBar title={target.title} subtitle={target.subtitle} onExit={handleExit} />

          <FeedActionRail
            stats={stats}
            box={activeCard?.box}
            onReveal={() => {
              if (!activeCard || activeCard.kind === 'explainer') return;
              markPeeked(activeCard.id);
              setRevealCard(activeCard);
            }}
            revealDisabled={!activeCard || activeCard.kind === 'explainer'}
          />

          <SwipeHint visible={!hintSeen && currentIndex === 0} />
        </div>
      </div>

      <div
        ref={containerRef}
        tabIndex={0}
        role="feed"
        aria-label="Akış modu"
        className={cn(
          'no-scrollbar h-feed w-full touch-pan-y overflow-y-auto overscroll-y-contain outline-none',
          // iOS'ta klavye açıkken 100dvh küçülür; snap zıplamasın diye geçici kapatılır.
          keyboardOpen ? 'snap-none' : 'snap-y snap-mandatory'
        )}
      >
        {cards.map((card, i) => {
          const inWindow = Math.abs(i - currentIndex) <= FEED_RENDER_WINDOW;
          return (
            <section
              key={card.id}
              ref={(el) => {
                cardRefs.current[i] = el;
              }}
              data-feed-card=""
              data-index={i}
              role="article"
              aria-posinset={i + 1}
              aria-setsize={-1}
              className="relative h-feed w-full shrink-0 snap-start snap-always overflow-hidden"
            >
              <div className="relative mx-auto h-full w-full max-w-md overflow-hidden bg-ink md:border-x md:border-white/5">
                {inWindow && (
                  <>
                    {card.kind === 'explainer' && (
                      <ExplainerCard card={card} isActive={i === currentIndex} />
                    )}
                    {card.kind === 'multiple-choice' && (
                      <MultipleChoiceCard
                        card={card}
                        isActive={i === currentIndex}
                        result={answers[card.id]}
                        onAnswer={(raw) => handleAnswer(card, raw)}
                      />
                    )}
                    {card.kind === 'text-input' && (
                      <TextInputCard
                        card={card}
                        isActive={i === currentIndex}
                        result={answers[card.id]}
                        onAnswer={(raw) => handleAnswer(card, raw)}
                        onKeyboardToggle={setKeyboardOpen}
                      />
                    )}
                  </>
                )}
              </div>
            </section>
          );
        })}
      </div>

      {/* "Göster" alt sayfası — anlatım içeriğini birebir yeniden kullanır. */}
      <Dialog open={revealCard !== null} onOpenChange={(open) => !open && setRevealCard(null)}>
        <DialogContent>
          <DialogTitle className="sr-only">Cevap</DialogTitle>
          {revealCard && (
            <ExplainerBody
              question={revealCard.question}
              box={revealCard.box}
              sessionSeenCount={revealCard.sessionSeenCount}
              lastSeenAt={revealCard.lastSeenAt}
              compact
              animate={false}
            />
          )}
          <p className="mt-4 text-center text-xs font-medium text-duo-gray-300">
            Baktığın için bu cevap tekrar seviyeni yükseltmez.
          </p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
