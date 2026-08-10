<script setup lang="ts">
// Dashboard — live overview of templates, jobs, connections and recent logs.
definePageMeta({ title: 'Dashboard', layout: 'default' });

const { api } = useApi();
const { data: metrics, pending, error } = await useAsyncData('metrics', () =>
  api.request<any>('/api/v1/metrics/'),
);
const { data: recentLogs } = await useAsyncData('recent-logs', () =>
  api.request<any>('/api/v1/job-logs/?page=1'),
);

const stats = computed(() => {
  const m = metrics.value;
  return [
    { label: 'Templates', value: m?.templates?.total ?? 0, icon: 'i-heroicons-squares-2x2 h-5 w-5 text-indigo-500' },
    { label: 'Jobs', value: m?.jobs?.total ?? 0, icon: 'i-heroicons-bolt h-5 w-5 text-amber-500' },
    { label: 'Active Jobs', value: m?.jobs?.active ?? 0, icon: 'i-heroicons-play h-5 w-5 text-emerald-500' },
    { label: 'Failed Runs', value: m?.logs?.failed ?? 0, icon: 'i-heroicons-exclamation-triangle h-5 w-5 text-rose-500' },
  ];
});
</script>

<template>
  <div class="space-y-6">
    <p v-if="error" class="rounded-lg bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">
      Could not reach the backend at {{ api.base }}. Is daphne running?
    </p>

    <!-- Stat cards -->
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div
        v-for="s in stats"
        :key="s.label"
        class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
      >
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium text-slate-500 dark:text-slate-400">{{ s.label }}</span>
          <span :class="s.icon" />
        </div>
        <p v-if="!pending" class="mt-2 text-3xl font-bold text-slate-800 dark:text-slate-100">{{ s.value }}</p>
        <div v-else class="mt-2 h-8 w-16 animate-pulse rounded bg-slate-100 dark:bg-slate-800" />
      </div>
    </div>

    <!-- Recent runs -->
    <div class="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="border-b border-slate-200 px-5 py-4 dark:border-slate-800">
        <h2 class="font-semibold text-slate-800 dark:text-slate-100">Recent Job Runs</h2>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th class="px-5 py-3">Job</th>
              <th class="px-5 py-3">Status</th>
              <th class="px-5 py-3">HTTP</th>
              <th class="px-5 py-3">Time</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
            <tr v-for="log in recentLogs?.results ?? []" :key="log.id">
              <td class="px-5 py-3 font-medium text-slate-700 dark:text-slate-200">Job #{{ log.job }}</td>
              <td class="px-5 py-3">
                <span
                  class="rounded-full px-2 py-0.5 text-xs font-medium"
                  :class="log.status === 'SUCCESS'
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400'
                    : 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-400'"
                >
                  {{ log.status }}
                </span>
              </td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ log.http_status ?? '—' }}</td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ new Date(log.timestamp).toLocaleString() }}</td>
            </tr>
            <tr v-if="!recentLogs?.results?.length">
              <td colspan="4" class="px-5 py-8 text-center text-slate-400">No job runs yet. Seed with <code>python manage.py seed_demo</code>.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
