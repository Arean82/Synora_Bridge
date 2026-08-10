<script setup lang="ts">
// Default layout — sidebar navigation (mirrors the Flask UI structure).
const nav = [
  { to: '/', label: 'Dashboard', icon: 'i-heroicons-home' },
  { to: '/templates', label: 'Templates', icon: 'i-heroicons-squares-2x2' },
  { to: '/connections', label: 'Connections', icon: 'i-heroicons-link' },
  { to: '/settings', label: 'Settings', icon: 'i-heroicons-cog-6-tooth' },
  { to: '/audit', label: 'Audit Logs', icon: 'i-heroicons-clipboard-document-list' },
];

const route = useRoute();
const { apiBase } = useRuntimeConfig().public;

const isActive = (to: string) => route.path === to || (to !== '/' && route.path.startsWith(to));
</script>

<template>
  <div class="flex min-h-screen">
    <!-- Sidebar -->
    <aside class="w-60 shrink-0 border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div class="flex h-16 items-center gap-2 border-b border-slate-200 px-5 dark:border-slate-800">
        <span class="text-xl font-bold text-indigo-600 dark:text-indigo-400">Synora</span>
        <span class="text-sm font-medium text-slate-400">Bridge</span>
      </div>
      <nav class="space-y-1 p-3">
        <NuxtLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors"
          :class="isActive(item.to)
            ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
            : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'"
        >
          <span :class="item.icon" class="h-4 w-4" />
          {{ item.label }}
        </NuxtLink>
      </nav>
      <div class="border-t border-slate-200 p-4 dark:border-slate-800">
        <a
          :href="`${apiBase}/schema/swagger-ui/`"
          target="_blank"
          class="flex items-center gap-2 text-xs text-slate-400 hover:text-indigo-500"
        >
          <span class="i-heroicons-book-open h-4 w-4" />
          API Docs (Swagger)
        </a>
      </div>
    </aside>

    <!-- Main -->
    <div class="flex min-w-0 flex-1 flex-col">
      <header class="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-6 dark:border-slate-800 dark:bg-slate-900">
        <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">
          {{ route.meta.title || 'Synora Bridge' }}
        </h1>
        <div class="flex items-center gap-3">
          <span class="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
            Backend: {{ apiBase }}
          </span>
        </div>
      </header>
      <main class="flex-1 overflow-y-auto p-6">
        <slot />
      </main>
    </div>
  </div>
</template>
