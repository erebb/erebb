import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useReducedMotion } from 'framer-motion';
import type { FeedCard } from '@/types';
import { useApp } from '@/context/AppContext';
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
import { cn } from '@/lib/utils';

const AUTO_ADVANCE_MS = 900;

export interface FeedZoneProps {
  setId: string;
  onExit: () => void;
}

export function FeedZone({ setId, onExit }: FeedZoneProps) {
  const { getSet, progress } = useApp();
  const set = getSet(setId);
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
    flushXP,
  } = useFeed(setId);

  const containerRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<Array<HTMLElement | null>>([]);
  const advanceTimerRef = useRef<number | null>(null);
  const indexRef = useRef(currentIndex);
  const reduced = useReducedMotion();

  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [revealCard, setRevealCard] = useState<FeedCard | null>(null);
  const [hintSeen, setHintSeen] = useLocalStorage(STORAGE_KEYS.feedSwipeHintSeen, false);

  useEffect(() => {
    indexRef.current = currentIndex;
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
  }, [headOffset]);

  const goTo = useCallback(
    (i: number) => {
      const el = cardRefs.current[i];
      if (!el) return;
      el.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
    },
    [reduced]
  );

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
      if (!res.correct) return; // Yanlışta ekranda kal — açığa çıkan cevap okunmalı.
      const myIndex = indexRef.current;
      advanceTimerRef.current = window.setTimeout(() => {
        // Kullanıcı bu arada kendisi kaydırdıysa geri sürükleme.
        if (indexRef.current !== myIndex) return;
        goTo(myIndex + 1);
      }, AUTO_ADVANCE_MS);
    },
    [submitAnswer, goTo]
  );

  const handleExit = useCallback(() => {
    flushXP();
    onExit();
  }, [flushXP, onExit]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const tag = (e.target as HTMLElement).tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return; // Yazmaya asla karışma.
    switch (e.key) {
      case 'ArrowDown':
      case 'PageDown':
      case ' ':
        e.preventDefault();
        goTo(currentIndex + 1);
        break;
      case 'ArrowUp':
      case 'PageUp':
        e.preventDefault();
        goTo(currentIndex - 1);
        break;
      case 'Escape':
        e.preventDefault();
        handleExit();
        break;
    }
  };

  if (!set || isEmpty) {
    return (
      <div className="flex h-[100dvh] flex-col items-center justify-center gap-4 bg-duo-gray-900 p-6 text-center">
        <p className="text-lg font-extrabold text-white">
          {set ? 'Bu sette henüz soru yok.' : 'Soru seti bulunamadı.'}
        </p>
        {set && <p className="text-sm font-semibold text-white/60">Önce sete soru ekle.</p>}
        <Button variant="blue" onClick={handleExit}>
          Geri dön
        </Button>
      </div>
    );
  }

  const activeCard = cards[currentIndex];

  return (
    <div className="relative h-[100dvh] w-full overflow-hidden bg-duo-gray-900">
      <FeedTopBar
        setName={set.name}
        dailyXPEarned={progress.dailyXPEarned}
        dailyGoalXP={progress.dailyGoalXP}
        onExit={handleExit}
      />

      <FeedActionRail
        stats={stats}
        streak={progress.streak}
        dailyXPEarned={progress.dailyXPEarned}
        dailyGoalXP={progress.dailyGoalXP}
        box={activeCard?.box}
        onReveal={() => {
          if (!activeCard || activeCard.kind === 'explainer') return;
          markPeeked(activeCard.id);
          setRevealCard(activeCard);
        }}
        revealDisabled={!activeCard || activeCard.kind === 'explainer'}
      />

      <SwipeHint visible={!hintSeen && currentIndex === 0} />

      <div
        ref={containerRef}
        tabIndex={0}
        role="feed"
        aria-label="Akış modu"
        onKeyDown={handleKeyDown}
        className={cn(
          'no-scrollbar h-[100dvh] w-full touch-pan-y overflow-y-auto overscroll-y-contain outline-none',
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
              className="relative h-[100dvh] w-full shrink-0 snap-start snap-always overflow-hidden"
            >
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
            </section>
          );
        })}
      </div>

      {/* "Kelimeyi göster" alt sayfası — anlatım içeriğini birebir yeniden kullanır. */}
      <Dialog open={revealCard !== null} onOpenChange={(open) => !open && setRevealCard(null)}>
        <DialogContent>
          <DialogTitle className="sr-only">Kelime açıklaması</DialogTitle>
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
          <p className="mt-4 text-center text-xs font-bold text-duo-gray-300">
            Baktığın için bu kart XP kazandırmaz.
          </p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
