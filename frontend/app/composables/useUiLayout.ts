// useUiLayout — sidebar/top layout switcher (original Flask layout.html parity:
// ui_layout == 'sidebar' renders the sidebar, anything else the top navbar).
// Persists via localStorage (instant) and mirrors the config.ini UI.layout
// value served by the Settings API. SSR-safe: document/localStorage are only
// touched in onMounted (same pattern as useTheme).
import { getApiBase } from '~/lib/api-client';

const STORAGE_KEY = 'synora-ui-layout';
export type UiLayout = 'sidebar' | 'top';

// Module-level singleton so the layout and the Settings page share one state.
const layout = ref<UiLayout>('sidebar');

const isUiLayout = (v: unknown): v is UiLayout => v === 'sidebar' || v === 'top';

export function useUiLayout() {
  const setLayout = (m: UiLayout) => {
    layout.value = m;
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, m);
  };

  // Pull the authoritative value from the backend config (UI.layout) and apply.
  const syncFromConfig = async () => {
    try {
      const base = getApiBase();
      const res = await (await fetch(`${base}/api/v1/config/`)).json();
      const value = res?.sections?.UI?.layout?.value;
      if (isUiLayout(value)) setLayout(value);
    } catch { /* non-fatal — keep the current layout */ }
  };

  onMounted(() => {
    const saved = typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
    if (isUiLayout(saved)) layout.value = saved;
    syncFromConfig();
  });

  return { layout, setLayout, syncFromConfig };
}
