// useTheme — dark/light theme switcher (original theme.js parity).
// Persists via localStorage (instant) + the ui.theme AppSetting (server-side).
// SSR-safe: `window` is only touched in onMounted / effects that run client-side.
import { getApiBase } from '~/lib/api-client';

const STORAGE_KEY = 'synora-color-mode';
type ColorMode = 'light' | 'dark' | 'auto';

export function useTheme() {
  const mode = ref<ColorMode>('auto');

  // Client-only helpers (never called during SSR).
  const isSystemDark = () =>
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches === true;

  const resolveDark = (m: ColorMode) => m === 'dark' || (m === 'auto' && isSystemDark());

  const apply = (m: ColorMode) => {
    if (typeof document === 'undefined') return; // SSR: no DOM to toggle
    document.documentElement.classList.toggle('dark', resolveDark(m));
    mode.value = m;
  };

  const setMode = async (m: ColorMode) => {
    apply(m);
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, m);
    try {
      await fetch(`${getApiBase()}/api/v1/settings/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'ui.theme', value: { colorMode: m } }),
      });
    } catch { /* non-fatal — theme still works locally */ }
  };

  const toggle = () => setMode(isDark.value ? 'light' : 'dark');

  // Computed reads are SSR-safe (resolveDark guards window access).
  const isDark = computed(() => resolveDark(mode.value));

  onMounted(() => {
    const saved = (typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null) as ColorMode | null;
    apply(saved ?? 'auto');
    window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', () => {
      if (mode.value === 'auto') apply('auto');
    });
  });

  return { mode, isDark, setMode, toggle };
}
