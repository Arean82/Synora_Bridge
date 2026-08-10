<script setup lang="ts">
// Audit Logs — the Universal Audit Engine viewer.
definePageMeta({ title: 'Audit Logs', layout: 'default' });

const { api } = useApi();
const { data: page, pending, refresh } = await useAsyncData('audit-logs', () =>
  api.request<any>('/api/v1/audit-logs/?page=1'),
);

const modeFilter = ref('');
const applyFilter = async () => {
  const q = modeFilter.value ? `?mode=${modeFilter.value}` : '';
  page.value = await api.request<any>(`/api/v1/audit-logs/${q}`);
};
</script>

<template>
  <div class="space-y-5">
    <div class="flex items-center justify-between">
      <p class="text-sm text-slate-500 dark:text-slate-400">{{ page?.count ?? 0 }} transactions recorded.</p>
      <select v-model="modeFilter" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" @change="applyFilter">
        <option value="">All modes</option>
        <option value="PUSH">Push</option>
        <option value="PULL_REST">Pull REST</option>
        <option value="PULL_GRAPHQL">Pull GraphQL</option>
      </select>
    </div>

    <div class="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th class="px-5 py-3">Transaction</th>
              <th class="px-5 py-3">Mode</th>
              <th class="px-5 py-3">Caller</th>
              <th class="px-5 py-3">Bytes</th>
              <th class="px-5 py-3">Records</th>
              <th class="px-5 py-3">Status</th>
              <th class="px-5 py-3">Time</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
            <tr v-for="log in page?.results ?? []" :key="log.id">
              <td class="px-5 py-3 font-mono text-xs text-slate-500 dark:text-slate-400">{{ String(log.transaction_id).slice(0, 8) }}…</td>
              <td class="px-5 py-3">
                <span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">{{ log.mode }}</span>
              </td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ log.caller }}</td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ log.bytes_transferred }}</td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ log.record_count }}</td>
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
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ new Date(log.timestamp).toLocaleString() }}</td>
            </tr>
            <tr v-if="pending"><td colspan="7" class="px-5 py-10 text-center text-slate-400">Loading…</td></tr>
            <tr v-if="!pending && !page?.results?.length"><td colspan="7" class="px-5 py-10 text-center text-slate-400">No audit records yet.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
