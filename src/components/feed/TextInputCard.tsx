import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import type { FeedAnswerResult, TextInputFeedCard } from '@/types';
import { Button } from '@/components/ui/button';
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
    <div className="flex h-full w-full flex-col justify-between bg-duo-gray-900 px-6 pb-28 pt-24">
      <motion.div
        initial={isActive && !reduced ? { opacity: 0, y: 16 } : false}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-1 flex-col items-center justify-center gap-3 text-center"
      >
        <span className="text-xs font-extrabold tracking-[0.2em] text-white/50">
          ANLAMINI YAZ
        </span>
        <h2 className="break-words text-4xl font-extrabold leading-tight text-white sm:text-5xl">
          {card.question.front}
        </h2>
        {card.question.hint && (
          <p className="text-sm font-semibold text-white/60">İpucu: {card.question.hint}</p>
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
          className="h-14 w-full rounded-2xl border-2 border-white/20 bg-white/10 px-4 text-lg font-bold text-white placeholder:text-white/40 focus:border-duo-blue focus:outline-none disabled:opacity-60"
        />
        <Button type="submit" variant="blue" size="lg" disabled={locked || !text.trim()}>
          Kontrol Et
        </Button>
      </form>

      <FeedAnswerBanner result={result} />
    </div>
  );
}
