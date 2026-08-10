<script setup lang="ts">
// Dashboard — schedule dashboard (original parity): per-job checkboxes,
// master select-all, Bulk Start/Stop, per-job toggle, live 5s polling.
definePageMeta({ title: 'Dashboard', layout: 'default' });

const { api } = useApi();
const { data: metrics, pending: metricsPending, error } = await useAsyncData('metrics', () =>
  api.request<any>('/api/v1/metrics/'),
);
const { data: jobs, refresh } = await useAsyncData('jobs', () =>
  api.request<any>('/api/v1/jobs/?page_size=200'),
);

// Live polling every 5s (replaces the original htmx every-5s poll).
onMounted(() => {
  const id = setInterval(() => refresh(), 5000);
  onUnmounted(() => clearInterval(id));
});

const selected = ref<Set<number>>(new Set());
const toggleRow = (id: number) => {
  const s = new Set(selected.value);
  if (s.has(id)) s.delete(id); else s.add(id);
  selected.value = s;
};
const toggleMaster = () => {
  const all = (jobs.value?.results ?? []).map((j: any) => j.id);
  selected.value = selected.value.size === all.length ? new Set() : new Set(all);
};
const hasSelection = computed(() => selected.value.size > 0);
const masterChecked = computed(() => {
  const all = (jobs.value?.results ?? []).map((j: any) => j.id);
  return all.length > 0 && selected.value.size === all.length;
});

const bulk = async (action: 'start' | 'stop') => {
  await api.request('/api/v1/jobs/bulk_toggle/', {
    method: 'POST',
    body: JSON.stringify({ action, job_ids: [...selected.value] }),
  });
  selected.value = new Set();
  await refresh();
};

const toggleJob = async (job: any) => {
  await api.request(`/api/v1/jobs/${job.id}/toggle/`, { method: 'POST' });
  await refresh();
};

const stats = computed(() => {
  const m = metrics.value;
  return [
    { label: 'Templates', value: m?.templates?.total ?? 0, icon: 'i-heroicons-squares-2x2 h-5 w-5 text-indigo-500' },
    { label: 'Jobs', value: m?.jobs?.total ?? 0, icon: 'i-heroicons-bolt h-5 w-5 text-amber-500' },
    { label: 'Active Jobs', value: m?.jobs?.active ?? 0, icon: 'i-heroicons-play h-5 w-5 text-emerald-500' },
    { label: 'Failed Runs', value: m?.logs?.failed ?? 0, icon: 'i-heroicons-exclamation-triangle h-5 w-5 text-rose-500' },
  ];
});

const fmtTime = (iso?: string) => (iso ? new Date(iso).toLocaleString() : '—');
</script>

<template>
  <div class="space-y-6">
    <p v-if="error" class="rounded-lg bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">
      Could not reach the backend at {{ api.base }}. Is daphne running?
    </p>

    <!-- Stat cards -->
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div v-for="s in stats" :key="s.label" class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium text-slate-500 dark:text-slate-400">{{ s.label }}</span>
          <span :class="s.icon" />
        </div>
        <p v-if="!metricsPending" class="mt-2 text-3xl font-bold text-slate-800 dark:text-slate-100">{{ s.value }}</p>
        <div v-else class="mt-2 h-8 w-16 animate-pulse rounded bg-slate-100 dark:bg-slate-800" />
      </div>
    </div>

    <!-- Schedule Dashboard -->
    <div class="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
        <h2 class="font-semibold text-slate-800 dark:text-slate-100">Schedule Dashboard</h2>
        <div class="flex items-center gap-2">
          <button
            v-if="hasSelection"
            class="rounded-lg bg-emerald-600 px-4 py-1.5 text-sm text-white hover:bg-emerald-500"
            @click="bulk('start')"
          >Bulk Start</button>
          <button
            v-if="hasSelection"
            class="rounded-lg bg-rose-600 px-4 py-1.5 text-sm text-white hover:bg-rose-500"
            @click="bulk('stop')"
          >Bulk Stop</button>
          <span class="text-xs text-slate-400">{{ selected.size }} selected</span>
        </div>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th class="w-12 px-5 py-3 text-center">
                <input type="checkbox" class="h-4 w-4 rounded" :checked="masterChecked" @change="toggleMaster" />
              </th>
              <th class="px-5 py-3">Client</th>
              <th class="px-5 py-3">Template</th>
              <th class="px-5 py-3">Status</th>
              <th class="px-5 py-3">Interval</th>
              <th class="px-5 py-3">Last Run</th>
              <th class="px-5 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
            <tr v-for="job in jobs?.results ?? []" :key="job.id">
              <td class="px-5 py-3 text-center">
                <input type="checkbox" class="h-4 w-4 rounded" :checked="selected.has(job.id)" @change="toggleRow(job.id)" />
              </td>
              <td class="px-5 py-3 font-semibold text-slate-700 dark:text-slate-200">{{ job.template_detail?.client_name || 'N/A' }}</td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ job.template_name || 'Unknown' }}</td>
              <td class="px-5 py-3">
                <span
                  class="rounded-full px-2 py-0.5 text-xs font-medium"
                  :class="job.is_active
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400'
                    : 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400'"
                >
                  {{ job.is_active ? 'Active' : 'Inactive' }}
                </span>
              </td>
              <td class="px-5 py-3 font-mono text-slate-500 dark:text-slate-400">Every {{ job.schedule_interval }}s</td>
              <td class="px-5 py-3 font-mono text-slate-500 dark:text-slate-400">{{ fmtTime(job.last_run) }}</td>
              <td class="px-5 py-3 text-right">
                <button
                  class="rounded px-2 py-1 text-xs"
                  :class="job.is_active ? 'text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950' : 'text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950'"
                  @click="toggleJob(job)"
                >
                  {{ job.is_active ? 'Stop' : 'Start' }}
                </button>
              </td>
            </tr>
            <tr v-if="!jobs?.results?.length">
              <td colspan="7" class="px-5 py-10 text-center text-slate-400">
                No scheduled jobs yet. Create a template with "Run Every" or seed with <code>python scripts/seed_demo.py</code>.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
