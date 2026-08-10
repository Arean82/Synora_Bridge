// Base URL helper for API calls (single source of truth).
export function getApiBase(): string {
  if (import.meta.client) {
    return (useRuntimeConfig().public.apiBase as string) || 'http://127.0.0.1:8000';
  }
  return 'http://127.0.0.1:8000';
}
