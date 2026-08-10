// API composable — typed wrapper over the generated hey-api client.
// All feature pages call useApi() for the backend base URL + fetch helpers.
import { getApiBase } from '~/lib/api-client';

export function useApi() {
  const { apiBase } = useRuntimeConfig().public;

  const api = {
    base: apiBase,
    async request<T>(path: string, options: RequestInit = {}): Promise<T> {
      const res = await fetch(`${apiBase}${path}`, {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as any).message || `Request failed: ${res.status}`);
      }
      if (res.status === 204) return undefined as T;
      return res.json() as Promise<T>;
    },
  };

  return { api };
}

// Re-export for pages that want the bare base URL.
export { getApiBase };
