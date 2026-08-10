<script setup lang="ts">
// Connections — API connection CRUD (Swagger/OpenAPI specs) + mock links.
definePageMeta({ title: 'Connections', layout: 'default' });

const { api } = useApi();
const { data: page, pending, refresh } = await useAsyncData('connections', () =>
  api.request<any>('/api/v1/connections/'),
);

const showForm = ref(false);
const saving = ref(false);
const error = ref('');
const form = reactive({
  name: '',
  url: '',
  connection_type: 'rest',
  auth_type: 'none',
});

const toggle = async (conn: any) => {
  await api.request(`/api/v1/connections/${conn.id}/toggle/`, {
    method: 'POST',
    body: JSON.stringify({ is_active: !conn.is_active }),
  });
  await refresh();
};

const create = async () => {
  saving.value = true;
  error.value = '';
  try {
    await api.request('/api/v1/connections/', { method: 'POST', body: JSON.stringify(form) });
    showForm.value = false;
    Object.assign(form, { name: '', url: '', connection_type: 'rest', auth_type: 'none' });
    await refresh();
  } catch (e: any) {
    error.value = e.message;
  } finally {
    saving.value = false;
  }
};

const remove = async (conn: any) => {
  if (!window.confirm(`Delete connection "${conn.name}"?`)) return;
  await api.request(`/api/v1/connections/${conn.id}/`, { method: 'DELETE' });
  await refresh();
};
</script>

<template>
  <div class="space-y-5">
    <div class="flex items-center justify-between">
      <p class="text-sm text-slate-500 dark:text-slate-400">{{ page?.count ?? 0 }} API connections with stored specs.</p>
      <button class="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500" @click="showForm = !showForm">
        {{ showForm ? 'Cancel' : '+ Add Connection' }}
      </button>
    </div>

    <div v-if="showForm" class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div v-if="error" class="mb-3 rounded-lg bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">{{ error }}</div>
      <div class="grid grid-cols-1 gap-4 md:grid-cols-4">
        <input v-model="form.name" placeholder="Connection name *" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
        <input v-model="form.url" placeholder="Swagger/OpenAPI URL" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
        <select v-model="form.connection_type" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
          <option value="rest">REST</option>
          <option value="graphql">GraphQL</option>
        </select>
        <button :disabled="saving || !form.name" class="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-50" @click="create">
          {{ saving ? 'Saving…' : 'Save' }}
        </button>
      </div>
    </div>

    <div class="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th class="px-5 py-3">Name</th>
              <th class="px-5 py-3">Type</th>
              <th class="px-5 py-3">Status</th>
              <th class="px-5 py-3">Updated</th>
              <th class="px-5 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
            <tr v-for="conn in page?.results ?? []" :key="conn.id">
              <td class="px-5 py-3 font-medium text-slate-700 dark:text-slate-200">{{ conn.name }}</td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ conn.connection_type }}</td>
              <td class="px-5 py-3">
                <button
                  class="rounded-full px-2 py-0.5 text-xs font-medium"
                  :class="conn.is_active
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400'
                    : 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400'"
                  @click="toggle(conn)"
                >
                  {{ conn.is_active ? 'Active' : 'Inactive' }}
                </button>
              </td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ new Date(conn.last_updated).toLocaleString() }}</td>
              <td class="px-5 py-3">
                <div class="flex justify-end gap-2">
                  <NuxtLink :href="`${api.base}/api/v1/mock/${conn.id}/users/1`" target="_blank" class="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
                    Mock
                  </NuxtLink>
                  <button class="rounded px-2 py-1 text-xs text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950" @click="remove(conn)">
                    Delete
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="pending"><td colspan="5" class="px-5 py-10 text-center text-slate-400">Loading…</td></tr>
            <tr v-if="!pending && !page?.results?.length"><td colspan="5" class="px-5 py-10 text-center text-slate-400">No connections yet.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
