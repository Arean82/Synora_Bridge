<script setup lang="ts">
// Audit Logs — the Universal Audit Engine viewer (original parity).
// Transaction Details modal: transaction id, mode, status, caller, bytes,
// records, endpoint + syntax-highlighted payload JSON.
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

const selected = ref<any>(null);
const openDetails = (log: any) => { selected.value = log; };
const closeDetails = () => { selected.value = null; };

// Lightweight JSON syntax highlighting (payload is stored as JSON).
const highlightJson = (payload: any): string => {
  let text: string;
  try {
    text = JSON.stringify(payload ?? {}, null, 2);
  } catch {
    text = String(payload ?? '');
  }
  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return esc(text)
    .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*")(\s*:)?/g, (m, key, _c, colon) =>
      colon ? `<span class="text-sky-500">${key}</span><span class="text-slate-400">:</span>` : `<span class="text-emerald-600 dark:text-emerald-400">${key}</span>`)
    .replace(/\b(true|false)\b/g, '<span class="text-amber-600 dark:text-amber-400">$1</span>')
    .replace(/\b-?\d+(\.\d+)?\b/g, '<span class="text-violet-600 dark:text-violet-400">$1</span>');
};

const modeBadge = (mode: string) =>
  mode === 'PUSH' ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300' :
  mode === 'PULL_REST' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300' :
  mode === 'PULL_GRAPHQL' ? 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300' :
  'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';
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
              <th class="px-5 py-3">Time</th>
              <th class="px-5 py-3">Mode</th>
              <th class="px-5 py-3">Caller</th>
              <th class="px-5 py-3">Endpoint</th>
              <th class="px-5 py-3">Bytes</th>
              <th class="px-5 py-3">Records</th>
              <th class="px-5 py-3">Status</th>
              <th class="px-5 py-3 text-right">Details</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
            <tr v-for="log in page?.results ?? []" :key="log.id">
              <td class="px-5 py-3 font-mono text-xs text-slate-500 dark:text-slate-400">{{ new Date(log.timestamp).toLocaleString() }}</td>
              <td class="px-5 py-3">
                <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="modeBadge(log.mode)">{{ log.mode }}</span>
              </td>
              <td class="px-5 py-3 font-mono text-xs text-slate-500 dark:text-slate-400">{{ log.caller }}</td>
              <td class="max-w-xs truncate px-5 py-3 text-xs text-slate-500 dark:text-slate-400" :title="log.endpoint">{{ log.endpoint }}</td>
              <td class="px-5 py-3 font-mono text-slate-500 dark:text-slate-400">{{ log.bytes_transferred }}</td>
              <td class="px-5 py-3 font-mono text-slate-500 dark:text-slate-400">{{ log.record_count }}</td>
              <td class="px-5 py-3">
                <span
                  class="rounded-full px-2 py-0.5 text-xs font-medium"
                  :class="log.status === 'SUCCESS'
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400'
                    : 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-400'"
                >{{ log.status }}</span>
              </td>
              <td class="px-5 py-3 text-right">
                <button class="rounded px-2 py-1 text-xs text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950" @click="openDetails(log)">
                  Details
                </button>
              </td>
            </tr>
            <tr v-if="pending"><td colspan="8" class="px-5 py-10 text-center text-slate-400">Loading…</td></tr>
            <tr v-if="!pending && !page?.results?.length"><td colspan="8" class="px-5 py-10 text-center text-slate-400">No audit records yet.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Transaction Details modal (original parity) -->
    <div v-if="selected" class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/50 p-4" @click.self="closeDetails">
      <div class="w-full max-w-2xl rounded-xl bg-white shadow-2xl dark:bg-slate-900">
        <div class="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <h3 class="text-lg font-bold text-slate-800 dark:text-slate-100">Transaction Details</h3>
          <button class="text-slate-400 hover:text-slate-600" @click="closeDetails">✕</button>
        </div>
        <div class="space-y-4 p-5">
          <div>
            <span class="block text-sm font-semibold text-slate-500 dark:text-slate-400">Transaction ID</span>
            <span class="block break-all font-mono text-sm text-slate-700 dark:text-slate-200">{{ selected.transaction_id }}</span>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <span class="block text-sm font-semibold text-slate-500 dark:text-slate-400">Mode</span>
              <span class="block font-bold text-slate-700 dark:text-slate-200">{{ selected.mode }}</span>
            </div>
            <div>
              <span class="block text-sm font-semibold text-slate-500 dark:text-slate-400">Status</span>
              <span class="font-bold" :class="selected.status === 'SUCCESS' ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'">
                {{ selected.status }}
              </span>
            </div>
            <div>
              <span class="block text-sm font-semibold text-slate-500 dark:text-slate-400">Caller / IP</span>
              <span class="block font-mono text-sm text-slate-700 dark:text-slate-200">{{ selected.caller }}</span>
            </div>
            <div>
              <span class="block text-sm font-semibold text-slate-500 dark:text-slate-400">Volume / Records</span>
              <span class="text-sm text-slate-700 dark:text-slate-200">{{ selected.bytes_transferred }} Bytes / {{ selected.record_count }} Records</span>
            </div>
            <div v-if="selected.endpoint" class="col-span-2">
              <span class="block text-sm font-semibold text-slate-500 dark:text-slate-400">Endpoint</span>
              <span class="block break-all font-mono text-sm text-slate-700 dark:text-slate-200">{{ selected.endpoint }}</span>
            </div>
          </div>
          <div>
            <span class="mb-2 block text-sm font-semibold text-slate-500 dark:text-slate-400">Payload JSON</span>
            <pre class="max-h-80 overflow-auto rounded-lg bg-slate-950 p-4 text-xs leading-relaxed text-slate-100"><code v-html="highlightJson(selected.payload_json)" /></pre>
          </div>
        </div>
        <div class="flex justify-end border-t border-slate-200 px-5 py-3 dark:border-slate-800">
          <button class="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500" @click="closeDetails">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>
