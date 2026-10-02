import { useMemo, useSyncExternalStore } from 'react';

const KEY = 'cftv-theme';
const listeners = new Set();

// Sem escolha salva, segue o sistema (prefers-color-scheme). localStorage pode falhar: sempre em try/catch.
export function initialTheme() {
  try {
    const s = localStorage.getItem(KEY);
    if (s === 'light' || s === 'dark') return s;
  } catch { /* sem storage */ }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function currentTheme() {
  return document.documentElement.dataset.theme || 'light';
}

export function setTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem(KEY, t); } catch { /* sem storage */ }
  listeners.forEach((l) => l());
}

const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, currentTheme, () => 'light');
  return [theme, () => setTheme(theme === 'dark' ? 'light' : 'dark')];
}

// Cores do tema atual para libs que não entendem var() (recharts)
export function useThemeColors() {
  const [theme] = useTheme();
  return useMemo(() => {
    const cs = getComputedStyle(document.documentElement);
    const g = (n) => cs.getPropertyValue(`--c-${n}`).trim();
    return Object.fromEntries(['bg', 'panel', 'panel2', 'line', 'rule', 'ink', 'mute', 'accent', 'ok', 'warn', 'bad', 'mock'].map((n) => [n, g(n)]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);
}
