import { useEffect, useRef, useState } from 'react';
import type { Question, QuizFeedback } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface Props {
  question: Question;
  feedback: QuizFeedback | null;
  onSubmit: (text: string) => void;
}

export function TextInputQuestion({ question, feedback, onSubmit }: Props) {
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Yeni soru geldiğinde alanı temizle ve odaklan.
  useEffect(() => {
    setText('');
    inputRef.current?.focus();
  }, [question.id]);

  const locked = feedback !== null;

  return (
    <form
      className="flex flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (!locked && text.trim()) onSubmit(text);
      }}
    >
      <h2 className="text-center text-2xl font-extrabold text-duo-gray-700">{question.front}</h2>
      <Input
        ref={inputRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Cevabını yaz..."
        disabled={locked}
        autoComplete="off"
        autoCapitalize="off"
        spellCheck={false}
      />
      <Button type="submit" disabled={locked || !text.trim()}>
        Kontrol Et
      </Button>
    </form>
  );
}
