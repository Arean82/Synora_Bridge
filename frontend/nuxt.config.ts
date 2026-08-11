import tailwindcss from '@tailwindcss/vite';

// Nuxt 4 configuration for the Synora Bridge frontend.
// Fully modular: feature domains live in app/feature/<name>/ with their own
// components, composables and pages; shared UI in app/components/ui.
// Runtime config points at the Django backend (daphne).
export default defineNuxtConfig({
  compatibilityDate: '2026-01-01',

  devtools: { enabled: false },

  // Nuxt 4 app directory (srcDir).
  srcDir: 'app/',

  modules: [],

  css: ['~/assets/css/main.css'],

  app: {
    head: {
      title: 'Synora Bridge',
      htmlAttrs: { lang: 'en' },
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'Universal API bridge - dynamic push, pull REST and pull GraphQL endpoints' },
      ],
    },
  },

  runtimeConfig: {
    public: {
      // Backend base URL (Django/daphne). Override via NUXT_PUBLIC_API_BASE.
      apiBase: (globalThis as typeof globalThis & { process?: { env?: Record<string, string | undefined> } }).process?.env?.NUXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000',
      // WebSocket base for the live feed (daphne).
      wsBase: (globalThis as typeof globalThis & { process?: { env?: Record<string, string | undefined> } }).process?.env?.NUXT_PUBLIC_WS_BASE || 'ws://127.0.0.1:8000',
    },
  },

  typescript: {
    strict: true,
    typeCheck: false,
  },

  vite: {
    plugins: [tailwindcss()],
  },
});
