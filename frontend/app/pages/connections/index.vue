<script setup lang="ts">
// Connections — API connection management (original parity).
// Add Connection modal (REST/GraphQL tabs, spec source, upstream auth),
// status toggle, refresh (non-local REST), Docs / GraphQL playground links,
// local-file path display, mock link.
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
  connection_type: 'rest',
  is_local_file: false,
  url: '',
  json_content: '',
  auth_type: 'none',
  auth_config: {} as Record<string, any>,
});

const authOptions = [
  { value: 'none', label: 'None' },
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'api_key', label: 'API Key' },
  { value: 'basic', label: 'Basic Authentication' },
];

const toggle = async (conn: any) => {
  await api.request(`/api/v1/connections/${conn.id}/toggle/`, {
    method: 'POST',
    body: JSON.stringify({ is_active: !conn.is_active }),
  });
  await refresh();
};

const refreshConn = async (conn: any) => {
  await api.request(`/api/v1/connections/${conn.id}/refresh/`, { method: 'POST' });
  await refresh();
};

const create = async () => {
  saving.value = true;
  error.value = '';
  try {
    await api.request('/api/v1/connections/', { method: 'POST', body: JSON.stringify({ ...form }) });
    showForm.value = false;
    Object.assign(form, {
      name: '', connection_type: 'rest', is_local_file: false, url: '',
      json_content: '', auth_type: 'none', auth_config: {},
    });
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
      <p class="text-sm text-slate-500 dark:text-slate-400">{{ page?.count ?? 0 }} API connections.</p>
      <button class="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500" @click="showForm = !showForm">
        {{ showForm ? 'Cancel' : '+ Add Connection' }}
      </button>
    </div>

    <!-- Add Connection modal (original parity) -->
    <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/50 p-4" @click.self="showForm = false">
      <div class="w-full max-w-2xl rounded-xl bg-white shadow-2xl dark:bg-slate-900">
        <div class="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <h3 class="font-semibold text-slate-800 dark:text-slate-100">Add Connection</h3>
          <button class="text-slate-400 hover:text-slate-600" @click="showForm = false">✕</button>
        </div>

        <div class="space-y-4 p-5">
          <div v-if="error" class="rounded-lg bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">{{ error }}</div>

          <!-- Type tabs -->
          <div class="flex gap-2">
            <button
              class="rounded-lg px-4 py-1.5 text-sm font-medium"
              :class="form.connection_type === 'rest' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'"
              @click="form.connection_type = 'rest'"
            >REST</button>
            <button
              class="rounded-lg px-4 py-1.5 text-sm font-medium"
              :class="form.connection_type === 'graphql' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'"
              @click="form.connection_type = 'graphql'"
            >GraphQL</button>
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-slate-600 dark:text-slate-300">Connection Name *</label>
            <input v-model="form.name" type="text" placeholder="e.g. Payment API" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
          </div>

          <!-- REST: spec source -->
          <template v-if="form.connection_type === 'rest'">
            <div>
              <label class="mb-1 block text-sm font-medium text-slate-600 dark:text-slate-300">API Specification Source *</label>
              <select v-model="form.is_local_file" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
                <option :value="false">URL</option>
                <option :value="true">Paste spec</option>
              </select>
            </div>
            <div v-if="!form.is_local_file">
              <label class="mb-1 block text-sm font-medium text-slate-600 dark:text-slate-300">OpenAPI / Swagger URL *</label>
              <input v-model="form.url" type="text" placeholder="https://api.example.com/swagger.json" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
            </div>
            <div v-else>
              <label class="mb-1 block text-sm font-medium text-slate-600 dark:text-slate-300">OpenAPI / Swagger Specification *</label>
              <textarea v-model="form.json_content" placeholder="{ &quot;openapi&quot;: &quot;3.0.3&quot;, ... }" class="h-40 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs dark:border-slate-700 dark:bg-slate-950" />
            </div>
          </template>

          <!-- GraphQL -->
          <template v-else>
            <div>
              <label class="mb-1 block text-sm font-medium text-slate-600 dark:text-slate-300">GraphQL API Base URL *</label>
              <input v-model="form.url" type="text" placeholder="https://api.example.com/graphql" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
            </div>
          </template>

          <!-- Upstream auth -->
          <div>
            <label class="mb-1 block text-sm font-medium text-slate-600 dark:text-slate-300">Upstream API Authentication</label>
            <select v-model="form.auth_type" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
              <option v-for="o in authOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
            <div v-if="form.auth_type === 'bearer'" class="mt-2">
              <input v-model="form.auth_config.token" type="password" placeholder="Bearer Token" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
            </div>
            <div v-else-if="form.auth_type === 'api_key'" class="mt-2 grid grid-cols-2 gap-2">
              <input v-model="form.auth_config.header_name" type="text" placeholder="Header name (X-API-Key)" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
              <input v-model="form.auth_config.header_value" type="password" placeholder="Key value" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
            </div>
            <div v-else-if="form.auth_type === 'basic'" class="mt-2 grid grid-cols-2 gap-2">
              <input v-model="form.auth_config.username" type="text" placeholder="Username" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
              <input v-model="form.auth_config.password" type="password" placeholder="Password" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
            </div>
          </div>
        </div>

        <div class="flex justify-end gap-3 border-t border-slate-200 px-5 py-4 dark:border-slate-800">
          <button class="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800" @click="showForm = false">
            Cancel
          </button>
          <button :disabled="saving || !form.name" class="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-50" @click="create">
            {{ saving ? 'Saving…' : 'Save Connection' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Connections table -->
    <div class="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th class="px-5 py-3">Name</th>
              <th class="px-5 py-3">Type</th>
              <th class="px-5 py-3">Source</th>
              <th class="px-5 py-3">Status</th>
              <th class="px-5 py-3">Updated</th>
              <th class="px-5 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
            <tr v-for="conn in page?.results ?? []" :key="conn.id">
              <td class="px-5 py-3 font-medium text-slate-700 dark:text-slate-200">{{ conn.name }}</td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ conn.connection_type }}</td>
              <td class="px-5 py-3 text-xs text-slate-400">
                <div v-if="conn.is_local_file">Local File: {{ conn.local_file_path }}</div>
                <div v-else class="max-w-[220px] truncate">{{ conn.url }}</div>
              </td>
              <td class="px-5 py-3">
                <button
                  class="rounded-full px-2 py-0.5 text-xs font-medium"
                  :class="conn.is_active ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400' : 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400'"
                  @click="toggle(conn)"
                >
                  {{ conn.is_active ? 'Active' : 'Inactive' }}
                </button>
              </td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ new Date(conn.last_updated).toLocaleString() }}</td>
              <td class="px-5 py-3">
                <div class="flex justify-end gap-2">
                  <!-- Refresh: only non-local REST connections (original parity) -->
                  <button
                    v-if="!conn.is_local_file && conn.connection_type !== 'graphql'"
                    class="rounded px-2 py-1 text-xs text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950"
                    @click="refreshConn(conn)"
                  >Refresh</button>
                  <!-- Docs: REST connections -->
                  <a
                    v-if="conn.connection_type === 'rest'"
                    :href="`${api.base}/api/v1/docs/${conn.id}/`"
                    target="_blank"
                    class="rounded px-2 py-1 text-xs text-emerald-600 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-950"
                  >Docs</a>
                  <!-- GraphQL playground -->
                  <a
                    v-if="conn.connection_type === 'graphql'"
                    :href="`${api.base}/api/v1/graphql/test/${conn.id}/`"
                    target="_blank"
                    class="rounded px-2 py-1 text-xs text-violet-600 hover:bg-violet-50 dark:text-violet-400 dark:hover:bg-violet-950"
                  >Playground</a>
                  <!-- Mock link -->
                  <a
                    v-if="conn.connection_type === 'rest'"
                    :href="`${api.base}/api/v1/mock/${conn.id}/users/1`"
                    target="_blank"
                    class="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                  >Mock</a>
                  <button class="rounded px-2 py-1 text-xs text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950" @click="remove(conn)">
                    Delete
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="pending"><td colspan="6" class="px-5 py-10 text-center text-slate-400">Loading…</td></tr>
            <tr v-if="!pending && !page?.results?.length"><td colspan="6" class="px-5 py-10 text-center text-slate-400">No connections yet.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
