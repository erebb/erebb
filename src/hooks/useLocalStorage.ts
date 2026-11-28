import { useCallback, useEffect, useRef, useState } from 'react';

/** Depolama dışarıdan (ör. içerik güncellemesi) yazıldığında yayılan olay; bkz. content/seed.ts. */
export const STORAGE_RELOAD_EVENT = 'kelime-ustasi:storage-reload';

/**
 * LocalStorage destekli, tipli React state.
 *
 * Yazma işlemi state güncelleyicisinin İÇİNDE değil, çağrı anında senkron yapılır:
 * güncelleyiciler saf olmalıdır ve React onları atlayabilir veya iki kez
 * çalıştırabilir — kalıcılık render zamanlamasına bağlı kalmamalı. Bir ref
 * güncel değeri tutar, böylece aynı tick içindeki ardışık çağrılar da doğru zincirlenir.
 */
export function useLocalStorage<T>(key: string, initialValue: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored !== null ? (JSON.parse(stored) as T) : initialValue;
    } catch {
      return initialValue;
    }
  });

  const currentRef = useRef(value);
  const initialRef = useRef(initialValue);

  // Uygulama açıkken depolama başka bir yerden güncellenirse (içerik güncellemesi) yeniden oku.
  useEffect(() => {
    const reload = () => {
      try {
        const stored = window.localStorage.getItem(key);
        const next = stored !== null ? (JSON.parse(stored) as T) : initialRef.current;
        currentRef.current = next;
        setValue(next);
      } catch {
        // okunamazsa bellekteki durum kalır
      }
    };
    window.addEventListener(STORAGE_RELOAD_EVENT, reload);
    return () => window.removeEventListener(STORAGE_RELOAD_EVENT, reload);
  }, [key]);

  const set = useCallback(
    (updater: T | ((prev: T) => T)) => {
      const next =
        typeof updater === 'function'
          ? (updater as (prev: T) => T)(currentRef.current)
          : updater;
      currentRef.current = next;
      try {
        window.localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // Depolama dolu/erişilemez — durum yalnızca bellekte tutulur.
      }
      setValue(next);
    },
    [key]
  );

  return [value, set] as const;
}
