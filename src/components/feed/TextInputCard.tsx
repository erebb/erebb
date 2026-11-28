import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import type { FeedAnswerResult, TextInputFeedCard } from '@/types';
import { Button } from '@/components/ui/button';
import { cn, fitText } from '@/lib/utils';
import { FeedAnswerBanner } from '@/components/feed/FeedAnswerBanner';

export interface TextInputCardProps {
  card: TextInputFeedCard;
  isActive: boolean;
  result?: FeedAnswerResult;
  onAnswer: (raw: string) => void;
  /** iOS'ta klavye açılınca 100dvh küçülür ve snap zıplar — FeedZone snap'i geçici kapatır. */
  onKeyboardToggle: (open: boolean) => void;
}

export function TextInputCard({
  card,
  isActive,
  result,
  onAnswer,
  onKeyboardToggle,
}: TextInputCardProps) {
  const reduced = useReducedMotion();
  const [text, setText] = useState('');
  const locked = result !== undefined;

  // Kart değişince alanı temizle.
  useEffect(() => {
    setText('');
  }, [card.id]);

  return (
    // pr-20: sağdaki eylem rayının (w-10 + right-3) üstüne binmesini önler.
    <div data-feed-kind="ti" className="no-scrollbar flex h-full w-full flex-col overflow-y-auto bg-ink pb-24 pl-6 pr-20 pt-20">
      <motion.div
        initial={isActive && !reduced ? { opacity: 0 } : false}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.15 }}
        className="flex flex-1 flex-col justify-center gap-3 py-4"
      >
        <span className="text-xs font-medium text-white/50">Cevabı yaz</span>
        <h2
          className={cn(
            'break-words font-semibold leading-tight text-white',
            fitText(card.question.front, ['text-3xl', 'text-2xl', 'text-xl', 'text-lg'])
          )}
        >
          {card.question.front}
        </h2>
        {card.question.hint && (
          <p className="text-sm font-normal text-white/60">İpucu: {card.question.hint}</p>
        )}
      </motion.div>

      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!locked && text.trim()) onAnswer(text);
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => onKeyboardToggle(true)}
          onBlur={() => onKeyboardToggle(false)}
          placeholder="Cevabını yaz..."
          disabled={locked}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          className="h-14 w-full rounded-2xl border border-white/20 bg-white/[0.06] px-4 text-lg font-medium text-white placeholder:text-white/40 focus:border-duo-blue focus:outline-none disabled:opacity-60"
        />
        <Button type="submit" variant="blue" size="lg" disabled={locked || !text.trim()}>
          Kontrol Et
        </Button>
      </form>

      <FeedAnswerBanner result={result} question={card.question} />
    </div>
  );
}
