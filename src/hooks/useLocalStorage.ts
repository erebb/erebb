import { useCallback, useState } from 'react';

/** LocalStorage destekli, tipli React state. */
export function useLocalStorage<T>(key: string, initialValue: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored !== null ? (JSON.parse(stored) as T) : initialValue;
    } catch {
      return initialValue;
    }
  });

  const set = useCallback(
    (updater: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const next = typeof updater === 'function' ? (updater as (prev: T) => T)(prev) : updater;
        try {
          window.localStorage.setItem(key, JSON.stringify(next));
        } catch {
          // Depolama dolu/erişilemez — durum yalnızca bellekte tutulur.
        }
        return next;
      });
    },
    [key]
  );

  return [value, set] as const;
}
