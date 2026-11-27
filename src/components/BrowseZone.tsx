import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowLeft, BookOpen, Check, ChevronLeft, ChevronRight, Eye, List, Search, X } from 'lucide-react';
import type { Question, StudyTarget } from '@/types';
import { isMcq } from '@/types';
import { useLocalStorage } from '@/hooks/useLocalStorage';
import { STORAGE_KEYS } from '@/lib/storageKeys';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn, fitText, normalizeAnswer } from '@/lib/utils';

interface Props {
  target: StudyTarget;
  onExit: () => void;
}

type Filter = 'all' | 'mcq' | 'card';

/**
 * Göz at: tüm sorular ve kartlar bir listede; birine tıklayınca tek tek, önceki/sonraki ile
 * gezilir. Sorular yayımlanan sırasıyla (slayt sırası) durur, karıştırılmaz.
 */
export function BrowseZone({ target, onExit }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [revealAll, setRevealAll] = useLocalStorage<boolean>(STORAGE_KEYS.browseRevealAll, false);

  const mcqCount = useMemo(() => target.questions.filter(isMcq).length, [target.questions]);
  const cardCount = target.questions.length - mcqCount;

  const visible = useMemo(() => {
    const q = normalizeAnswer(query);
    return target.questions.filter((item) => {
      if (filter === 'mcq' && !isMcq(item)) return false;
      if (filter === 'card' && isMcq(item)) return false;
      if (!q) return true;
      const hay = normalizeAnswer(
        [item.front, item.back, item.explanation ?? '', item.source ?? '', ...(item.options ?? [])].join(' ')
      );
      return hay.includes(q);
    });
  }, [target.questions, filter, query]);

  if (openIndex !== null && visible[openIndex]) {
    return (
      <ItemViewer
        items={visible}
        index={openIndex}
        onIndex={setOpenIndex}
        onClose={() => setOpenIndex(null)}
        revealAll={revealAll}
        onRevealAll={setRevealAll}
        title={target.title}
      />
    );
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-4 p-4 pb-12">
      <header className="flex items-center gap-3 pt-2">
        <Button variant="ghost" size="icon" onClick={onExit} aria-label="Geri">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="min-w-0">
          <p className="truncate text-lg font-extrabold text-duo-gray-700">{target.title}</p>
          <p className="text-xs font-bold text-duo-gray-300">
            {mcqCount} soru · {cardCount} kart
          </p>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        {(
          [
            ['all', `Hepsi (${target.questions.length})`],
            ['mcq', `Sorular (${mcqCount})`],
            ['card', `Kartlar (${cardCount})`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={cn(
              'h-9 rounded-xl border-2 px-3 text-xs font-extrabold transition-colors',
              filter === key
                ? 'border-duo-blue bg-duo-blue-light text-duo-blue-dark'
                : 'border-duo-gray-100 bg-white text-duo-gray-500 hover:border-duo-blue'
            )}
          >
            {label}
          </button>
        ))}
        <label className="ml-auto flex cursor-pointer items-center gap-2 text-xs font-extrabold text-duo-gray-500">
          <input
            type="checkbox"
            checked={revealAll}
            onChange={(e) => setRevealAll(e.target.checked)}
            className="h-4 w-4 accent-duo-green"
          />
          Cevaplar açık
        </label>
      </div>

      <div className="relative">
        <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-duo-gray-300" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ara: kelime, ilaç, organizma…"
          className="pl-10"
        />
      </div>

      {visible.length === 0 ? (
        <p className="py-10 text-center text-sm font-semibold text-duo-gray-300">Eşleşen öğe yok.</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {visible.map((item, i) => (
            <li key={item.id}>
              <button
                onClick={() => setOpenIndex(i)}
                className="flex w-full items-start gap-3 rounded-2xl border-2 border-duo-gray-100 bg-white p-3 text-left shadow-duo-card transition-colors hover:border-duo-blue active:translate-y-0.5 active:shadow-none"
              >
                <span className="mt-0.5 w-7 shrink-0 text-right text-xs font-extrabold tabular-nums text-duo-gray-300">
                  {i + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="mb-1 flex items-center gap-2">
                    <Badge variant={isMcq(item) ? 'green' : 'blue'}>{isMcq(item) ? 'SORU' : 'KART'}</Badge>
                    {item.source && (
                      <span className="truncate text-[0.7rem] font-bold text-duo-gray-300">{item.source}</span>
                    )}
                  </span>
                  <span className="line-clamp-2 block text-sm font-bold text-duo-gray-700">{item.front}</span>
                  {revealAll && (
                    <span className="mt-1 line-clamp-2 block text-xs font-extrabold text-duo-green-dark">
                      {item.back}
                    </span>
                  )}
                </span>
                <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-duo-gray-300" />
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

interface ViewerProps {
  items: Question[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
  revealAll: boolean;
  onRevealAll: (v: boolean) => void;
  title: string;
}

function ItemViewer({ items, index, onIndex, onClose, revealAll, onRevealAll, title }: ViewerProps) {
  const item = items[index];
  const mcq = isMcq(item);
  const [revealed, setRevealed] = useState(revealAll);
  const [chosen, setChosen] = useState<string | null>(null);

  useEffect(() => {
    setRevealed(revealAll);
    setChosen(null);
  }, [item.id, revealAll]);

  const go = (d: 1 | -1) => {
    const next = index + d;
    if (next >= 0 && next < items.length) onIndex(next);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
      if (e.key === 'ArrowRight') go(1);
      else if (e.key === 'ArrowLeft') go(-1);
      else if (e.key === 'Escape') onClose();
      else if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        setRevealed((r) => !r);
      } else return;
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const options = item.options ?? [];

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-xl flex-col p-4">
      <header className="flex items-center gap-3 py-2">
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Listeye dön">
          <List className="h-5 w-5" />
        </Button>
        <p className="min-w-0 flex-1 truncate text-sm font-extrabold text-duo-gray-500">{title}</p>
        <span className="text-sm font-extrabold tabular-nums text-duo-gray-500" data-browse-position="">
          {index + 1} / {items.length}
        </span>
      </header>

      <AnimatePresence mode="wait">
        <motion.main
          key={item.id}
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -24 }}
          transition={{ duration: 0.15 }}
          className="flex flex-1 flex-col gap-4 py-4"
        >
          <div className="flex items-center gap-2">
            <Badge variant={mcq ? 'green' : 'blue'}>{mcq ? 'SORU' : 'KART'}</Badge>
            {item.source && (
              <span className="inline-flex items-center gap-1 text-xs font-bold text-duo-gray-300">
                <BookOpen className="h-3.5 w-3.5" /> {item.source}
              </span>
            )}
          </div>

          <h2
            className={cn(
              'font-extrabold leading-snug text-duo-gray-700',
              fitText(item.front, ['text-3xl', 'text-2xl', 'text-xl', 'text-lg'])
            )}
          >
            {item.front}
          </h2>

          {mcq && (
            <div className="flex flex-col gap-2">
              {options.map((opt, i) => {
                const isCorrect = opt === item.back;
                const isChosenWrong = revealed && chosen === opt && !isCorrect;
                return (
                  <button
                    key={opt}
                    disabled={revealed}
                    onClick={() => {
                      setChosen(opt);
                      setRevealed(true);
                    }}
                    className={cn(
                      'flex items-start gap-3 rounded-2xl border-2 p-3 text-left text-sm font-bold transition-colors',
                      !revealed && 'border-duo-gray-100 bg-white text-duo-gray-700 hover:border-duo-blue',
                      revealed && isCorrect && 'border-duo-green bg-duo-green-light text-duo-green-dark',
                      isChosenWrong && 'border-duo-red bg-duo-red-light text-duo-red-dark',
                      revealed && !isCorrect && !isChosenWrong && 'border-duo-gray-100 bg-white text-duo-gray-300'
                    )}
                  >
                    <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border-2 border-current text-xs font-extrabold">
                      {revealed && isCorrect ? (
                        <Check className="h-3.5 w-3.5" />
                      ) : isChosenWrong ? (
                        <X className="h-3.5 w-3.5" />
                      ) : (
                        String.fromCharCode(65 + i)
                      )}
                    </span>
                    <span className="pt-0.5">{opt}</span>
                  </button>
                );
              })}
            </div>
          )}

          {!revealed ? (
            <Button variant="blue" onClick={() => setRevealed(true)} className="self-start">
              <Eye className="h-4 w-4" /> Cevabı göster
            </Button>
          ) : (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col gap-2 rounded-2xl border-2 border-duo-green bg-duo-green-light p-4"
              data-browse-answer=""
            >
              <span className="text-xs font-extrabold tracking-widest text-duo-green-dark">CEVAP</span>
              <p className="font-extrabold text-duo-gray-700">{item.back}</p>
              {item.explanation && (
                <p className="text-sm font-semibold leading-relaxed text-duo-gray-500">{item.explanation}</p>
              )}
            </motion.div>
          )}
        </motion.main>
      </AnimatePresence>

      <footer className="sticky bottom-0 flex items-center gap-2 bg-duo-gray-50 py-3">
        <Button variant="outline" onClick={() => go(-1)} disabled={index === 0} aria-label="Önceki">
          <ChevronLeft className="h-5 w-5" /> Önceki
        </Button>
        <label className="mx-auto flex cursor-pointer items-center gap-2 text-xs font-extrabold text-duo-gray-500">
          <input
            type="checkbox"
            checked={revealAll}
            onChange={(e) => onRevealAll(e.target.checked)}
            className="h-4 w-4 accent-duo-green"
          />
          Cevaplar açık
        </label>
        <Button onClick={() => go(1)} disabled={index === items.length - 1} aria-label="Sonraki">
          Sonraki <ChevronRight className="h-5 w-5" />
        </Button>
      </footer>
    </div>
  );
}
