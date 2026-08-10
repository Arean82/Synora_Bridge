<script setup lang="ts">
// TemplateBuilder — create & edit bridge templates (sources → destinations →
// field mappings). Mirrors the Flask create_template.js builder functionality.

const props = defineProps<{ templateId?: number }>();
const { api } = useApi();
const router = useRouter();

const form = reactive({
  name: '',
  execution_mode: 'push',
  pull_method: 'GET',
  sources: [] as any[],
  destinations: [] as any[],
  client_credentials: {} as Record<string, any>,
});

const saving = ref(false);
const error = ref('');
const loading = ref(Boolean(props.templateId));

const modeOptions = [
  { value: 'push', label: 'Push (scheduled)' },
  { value: 'pull_rest', label: 'Pull REST' },
  { value: 'pull_graphql', label: 'Pull GraphQL' },
];

// Load existing template for edit mode.
if (props.templateId) {
  const { data } = await useAsyncData(`template-${props.templateId}`, () =>
    api.request<any>(`/api/v1/templates/${props.templateId}/`),
  );
  watch(data, (tpl) => {
    if (!tpl) return;
    form.name = tpl.name;
    form.execution_mode = tpl.execution_mode;
    form.pull_method = tpl.pull_method;
    form.sources = tpl.sources || [];
    form.destinations = tpl.destinations || [];
    form.client_credentials = tpl.client_credentials || {};
    loading.value = false;
  }, { immediate: true });
}

const addSource = () => {
  form.sources.push({
    name: `Source ${form.sources.length + 1}`,
    url: '',
    source_type: 'rest',
    method: 'GET',
    auth_token: '',
    selectedApi: '',
    graphql_query: '',
  });
};

const removeSource = (idx: number) => form.sources.splice(idx, 1);

const addDestination = () => {
  form.destinations.push({
    name: `Destination ${form.destinations.length + 1}`,
    url: '',
    method: 'POST',
    auth_type: 'none',
    credentials: {},
    field_mapping: [] as any[],
  });
};

const removeDestination = (idx: number) => form.destinations.splice(idx, 1);

const addMapping = (dest: any) => {
  dest.field_mapping.push({ source: '', target: '' });
};

const removeMapping = (dest: any, idx: number) => dest.field_mapping.splice(idx, 1);

// Collect all source fields for the mapping source dropdown.
const allSourceFields = computed(() => {
  const fields: string[] = [];
  form.sources.forEach((src, i) => {
    fields.push(`source_${i}.id`);
    fields.push(`source_${i}.name`);
  });
  return fields;
});

const submit = async () => {
  saving.value = true;
  error.value = '';
  try {
    const payload = {
      name: form.name,
      execution_mode: form.execution_mode,
      pull_method: form.pull_method,
      sources: form.sources,
      destinations: form.destinations,
      client_credentials: form.client_credentials,
    };
    if (props.templateId) {
      await api.request(`/api/v1/templates/${props.templateId}/`, { method: 'PUT', body: JSON.stringify(payload) });
    } else {
      await api.request('/api/v1/templates/', { method: 'POST', body: JSON.stringify(payload) });
    }
    await router.push('/templates');
  } catch (e: any) {
    error.value = e.message;
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <div class="space-y-6">
    <div v-if="loading" class="rounded-xl border p-10 text-center text-slate-400 dark:border-slate-800">Loading…</div>

    <template v-else>
      <div v-if="error" class="rounded-lg bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">{{ error }}</div>

      <!-- Basics -->
      <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h2 class="mb-4 font-semibold text-slate-800 dark:text-slate-100">Basics</h2>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-500">Template Name *</label>
            <input v-model="form.name" type="text" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-500">Execution Mode</label>
            <select v-model="form.execution_mode" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
              <option v-for="o in modeOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-500">Pull Method</label>
            <select v-model="form.pull_method" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
              <option>GET</option><option>POST</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Sources -->
      <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="font-semibold text-slate-800 dark:text-slate-100">Sources ({{ form.sources.length }})</h2>
          <button class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800" @click="addSource">
            + Add Source
          </button>
        </div>
        <div v-if="!form.sources.length" class="rounded-lg bg-slate-50 p-4 text-sm text-slate-400 dark:bg-slate-950">
          No sources. Add at least one source endpoint.
        </div>
        <div v-for="(src, i) in form.sources" :key="i" class="mb-4 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
          <div class="mb-3 flex items-center justify-between">
            <span class="text-sm font-medium text-slate-600 dark:text-slate-300">Source {{ i + 1 }}</span>
            <button class="text-xs text-rose-500 hover:underline" @click="removeSource(i)">Remove</button>
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <input v-model="src.name" placeholder="Name" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
            <input v-model="src.url" placeholder="https://api.example.com/…" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
            <select v-model="src.source_type" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
              <option value="rest">REST</option>
              <option value="graphql">GraphQL</option>
            </select>
            <input v-model="src.method" placeholder="Method (GET)" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
            <input v-model="src.auth_token" placeholder="Auth token (optional)" type="password" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
            <textarea v-if="src.source_type === 'graphql'" v-model="src.graphql_query" placeholder="GraphQL query…" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
          </div>
        </div>
      </div>

      <!-- Destinations + mappings -->
      <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="font-semibold text-slate-800 dark:text-slate-100">Destinations ({{ form.destinations.length }})</h2>
          <button class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800" @click="addDestination">
            + Add Destination
          </button>
        </div>
        <div v-if="!form.destinations.length" class="rounded-lg bg-slate-50 p-4 text-sm text-slate-400 dark:bg-slate-950">
          No destinations yet.
        </div>
        <div v-for="(dest, di) in form.destinations" :key="di" class="mb-4 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
          <div class="mb-3 flex items-center justify-between">
            <span class="text-sm font-medium text-slate-600 dark:text-slate-300">Destination {{ di + 1 }}</span>
            <button class="text-xs text-rose-500 hover:underline" @click="removeDestination(di)">Remove</button>
          </div>
          <div class="mb-3 grid grid-cols-1 gap-3 md:grid-cols-3">
            <input v-model="dest.name" placeholder="Name (e.g. Client A)" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
            <input v-model="dest.url" placeholder="https://dest.example.com/ingest" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
            <select v-model="dest.method" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
              <option>POST</option><option>PUT</option><option>PATCH</option><option>GET</option>
            </select>
          </div>

          <!-- Field mappings -->
          <div class="rounded-lg bg-slate-50 p-3 dark:bg-slate-950">
            <div class="mb-2 flex items-center justify-between">
              <span class="text-xs font-medium uppercase tracking-wide text-slate-500">Field Mapping</span>
              <button class="text-xs text-indigo-500 hover:underline" @click="addMapping(dest)">+ Add Mapping</button>
            </div>
            <div v-for="(m, mi) in dest.field_mapping" :key="mi" class="mb-2 flex items-center gap-2">
              <select v-model="m.source" class="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950">
                <option value="">source field…</option>
                <option v-for="f in allSourceFields" :key="f" :value="f">{{ f }}</option>
              </select>
              <span class="text-slate-400">→</span>
              <input v-model="m.target" placeholder="target.path[0].field" class="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950" />
              <button class="text-xs text-rose-500 hover:underline" @click="removeMapping(dest, mi)">✕</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="flex justify-end gap-3">
        <NuxtLink to="/templates" class="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
          Cancel
        </NuxtLink>
        <button
          :disabled="saving || !form.name"
          class="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          @click="submit"
        >
          {{ saving ? 'Saving…' : (props.templateId ? 'Save Changes' : 'Create Template') }}
        </button>
      </div>
    </template>
  </div>
</template>
